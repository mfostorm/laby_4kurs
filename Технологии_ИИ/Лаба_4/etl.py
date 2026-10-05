"""ETL-процесс подготовки данных AI4I 2020 (лабораторная работа 4, вариант 10).

Реализует проект ETL-процесса из лабы 3 (спецификация трансформаций, табл. 3),
составленный по результатам EDA из лабы 2:
извлечение -> нормализация текста -> приведение типов -> проверка допустимых
диапазонов -> дубликаты -> пропуски -> выбросы (флаги) -> дефекты разметки ->
производные признаки -> валидация -> сохранение (CSV, Parquet, отчёт о качестве).

Запуск:  python etl.py            (data/ai4i2020.csv -> data/data_cleaned.*)
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
RAW = HERE / 'data' / 'ai4i2020.csv'
OUT = HERE / 'data'

# --- справочные параметры конвейера ------------------------------------------
RENAME = {
    'UDI': 'udi',
    'Product ID': 'product_id',
    'Type': 'quality_class',
    'Air temperature [K]': 'air_temp_k',
    'Process temperature [K]': 'process_temp_k',
    'Rotational speed [rpm]': 'rot_speed_rpm',
    'Torque [Nm]': 'torque_nm',
    'Tool wear [min]': 'tool_wear_min',
    'Machine failure': 'machine_failure',
    'TWF': 'twf', 'HDF': 'hdf', 'PWF': 'pwf', 'OSF': 'osf', 'RNF': 'rnf',
}
SENSORS = ['air_temp_k', 'process_temp_k', 'rot_speed_rpm', 'torque_nm', 'tool_wear_min']
MODES = ['twf', 'hdf', 'pwf', 'osf']            # подтипы, входящие в целевую переменную
LABELS = ['machine_failure'] + MODES + ['rnf']
CLASSES = ['L', 'M', 'H']

# Физически допустимые диапазоны (паспорт станка, ISO 17359): значения вне
# диапазона считаются ошибкой датчика и заменяются пропуском.
VALID_RANGE = {
    'air_temp_k': (273.0, 343.0),      # 0 ... 70 °C
    'process_temp_k': (273.0, 373.0),  # 0 ... 100 °C
    'rot_speed_rpm': (1.0, 5000.0),
    'torque_nm': (0.0, 150.0),
    'tool_wear_min': (0.0, 400.0),
}
# Пороги правил из лабы 1 (табл. 4) и лабы 2 (табл. 7)
OSF_LIMIT = {'L': 11000, 'M': 12000, 'H': 13000}
WEAR_STEP = {'L': 2, 'M': 3, 'H': 5}            # приращение износа за изделие
POWER_MIN, POWER_MAX = 3500.0, 9000.0
# Медианы связей между признаками (лаба 2, раздел 4.4): мощность привода
# используется для восстановления момента, разность температур - только
# в сравнении стратегий (test_robustness.py)
TEMP_DIFF_MED = 10.0          # K
POWER_MED = 6271.0            # Вт
# Границы IQR, рассчитанные на эталонном наборе (лаба 2, табл. 4). Фиксируются,
# чтобы новые партии данных оценивались по тем же порогам и заполненные
# значения не сдвигали границы.
IQR_BOUNDS = {'rot_speed_rpm': (1139.5, 1895.5), 'torque_nm': (12.8, 67.2)}
# Приоритет подтипов по тяжести последствий (для одноклассовой постановки)
PRIORITY = ['pwf', 'osf', 'hdf', 'twf']


def md5(path):
    return hashlib.md5(Path(path).read_bytes()).hexdigest()


# --- E: извлечение -----------------------------------------------------------
def extract(path=RAW):
    df = pd.read_csv(path, encoding='utf-8-sig')
    missing_cols = set(RENAME) - set(df.columns)
    if missing_cols:
        raise ValueError(f'В источнике нет полей: {sorted(missing_cols)}')
    return df


# --- T: трансформации --------------------------------------------------------
def rename(df, log):
    df = df.rename(columns=RENAME)[list(RENAME.values())]
    log.append(('Переименование полей в snake_case', len(RENAME), 'все поля'))
    return df


def normalize_text(df, log):
    before_pid = df['product_id'].astype(str)
    before_cls = df['quality_class'].astype(str)
    df['product_id'] = before_pid.str.strip().str.upper()
    df['quality_class'] = before_cls.str.strip().str.upper()
    changed = int((before_pid != df['product_id']).sum() + (before_cls != df['quality_class']).sum())
    # класс качества, отсутствующий или недопустимый, восстанавливается по букве Product ID
    bad = ~df['quality_class'].isin(CLASSES)
    restored = bad & df['product_id'].str[0].isin(CLASSES)
    df.loc[restored, 'quality_class'] = df.loc[restored, 'product_id'].str[0]
    df.loc[bad & ~restored, 'quality_class'] = np.nan
    mismatch = int((df['product_id'].str[0] != df['quality_class']).sum())
    df['product_serial'] = pd.to_numeric(df['product_id'].str[1:], errors='coerce').astype('Int32')
    log.append(('Нормализация текстовых полей (пробелы, регистр)', changed, 'product_id, quality_class'))
    log.append(('Восстановление класса качества по Product ID', int(restored.sum()), 'quality_class'))
    log.append(('Несоответствие буквы Product ID классу качества', mismatch, 'контроль'))
    return df


def cast_types(df, log):
    n_bad = 0
    for c in SENSORS + LABELS + ['udi']:
        conv = pd.to_numeric(df[c], errors='coerce')
        n_bad += int((conv.isna() & df[c].notna()).sum())
        df[c] = conv
    df['quality_class'] = pd.Categorical(df['quality_class'], categories=CLASSES, ordered=True)
    log.append(('Приведение типов; нечисловые значения -> пропуск', n_bad, 'числовые поля'))
    return df


def check_ranges(df, log):
    total = 0
    for c, (lo, hi) in VALID_RANGE.items():
        bad = df[c].notna() & ~df[c].between(lo, hi)
        total += int(bad.sum())
        df.loc[bad, c] = np.nan
    # температура процесса физически не может быть ниже температуры воздуха
    inv = df['process_temp_k'] < df['air_temp_k']
    total += int(inv.sum())
    df.loc[inv, 'process_temp_k'] = np.nan
    log.append(('Физически недопустимые значения -> пропуск', total, ', '.join(SENSORS)))
    return df


def drop_duplicates(df, log):
    n0 = len(df)
    df = df.drop_duplicates()
    full = n0 - len(df)
    n1 = len(df)
    df = df.drop_duplicates(subset='udi', keep='first')
    by_key = n1 - len(df)
    log.append(('Удаление полных дубликатов', full, 'все поля'))
    log.append(('Удаление дубликатов по ключу UDI', by_key, 'udi'))
    return df.sort_values('udi').reset_index(drop=True)


def handle_missing(df, log, stats):
    """Стратегии заполнения выбраны по результатам EDA (лаба 2) и сравнения
    стратегий на внесённых пропусках (test_robustness.py)."""
    # 1. Записи без ключа или с пропуском обобщённой метки отказа не восстанавливаются:
    #    метка - эталон для проверки базы правил, подставлять её нельзя.
    key_bad = df['udi'].isna() | df['product_id'].isna() | df['machine_failure'].isna()
    # 2. Записи, где утрачено больше половины показаний датчиков, тоже удаляются.
    sens_bad = df[SENSORS].isna().sum(axis=1) > len(SENSORS) // 2
    drop = key_bad | sens_bad
    log.append(('Удаление записей без ключа/метки или с > 50 % пропусков датчиков',
                int(drop.sum()), 'udi, product_id, machine_failure, датчики'))
    df = df[~drop].copy()

    filled = {}
    # Класс качества - модой (категориальный признак)
    m = df['quality_class'].isna()
    if m.any():
        df.loc[m, 'quality_class'] = df['quality_class'].mode()[0]
    filled['quality_class'] = int(m.sum())

    # Износ инструмента: внутри цикла инструмента износ растёт с шагом,
    # заданным классом предыдущего изделия (2/3/5 мин для L/M/H). Пропуск
    # восстанавливается по предыдущему значению и шагу; если следующее известное
    # значение меньше предыдущего (между ними была замена инструмента) -
    # обратным счётом от следующего значения.
    w = df['tool_wear_min'].to_numpy(dtype=float).copy()
    step = df['quality_class'].astype(str).map(WEAR_STEP).to_numpy(dtype=float)
    miss = np.where(np.isnan(w))[0]
    for i in miss:
        if i == 0:
            w[i] = 0.0
            continue
        fwd = w[i - 1] + step[i - 1]
        nxt = next((j for j in range(i + 1, len(w)) if not np.isnan(w[j])), None)
        if nxt is not None and w[nxt] < w[i - 1]:
            w[i] = max(w[nxt] - step[i:nxt].sum(), 0.0)
        else:
            w[i] = fwd
    filled['tool_wear_min'] = len(miss)
    df['tool_wear_min'] = w

    # Температуры генерируются как плавный временной ряд (случайное блуждание
    # вдоль порядка записей), поэтому лучшая стратегия - линейная интерполяция
    # по соседним записям (сравнение стратегий - в test_robustness.py).
    m_air, m_proc = df['air_temp_k'].isna(), df['process_temp_k'].isna()
    for c in ('air_temp_k', 'process_temp_k'):
        df[c] = df[c].interpolate(limit_direction='both').round(1)

    # Момент: мощность привода примерно постоянна (корреляция с оборотами -0,875),
    # поэтому момент = медианная мощность / угловая скорость.
    # Обратный пересчёт оборотов по моменту не применяется: при малом моменте
    # он даёт большую ошибку (см. отчёт, табл. сравнения стратегий).
    m_t, m_n = df['torque_nm'].isna(), df['rot_speed_rpm'].isna()
    omega = 2 * np.pi / 60
    df.loc[m_t & ~m_n, 'torque_nm'] = (POWER_MED / (df['rot_speed_rpm'] * omega)).round(1)
    # Остальное (обороты; пары с двумя пропусками) - медиана внутри класса качества
    # (устойчива к выбросам, которых в моменте и оборотах много)
    for c, m in [('air_temp_k', m_air), ('process_temp_k', m_proc),
                 ('torque_nm', m_t), ('rot_speed_rpm', m_n)]:
        rest = df[c].isna()
        if rest.any():
            med = df.groupby('quality_class', observed=True)[c].transform('median')
            df.loc[rest, c] = med[rest]
        filled[c] = int(m.sum())

    # Подтипы отказа: пропуск -> 0. Если при этом обобщённая метка = 1 и других
    # подтипов нет, запись получит флаг failure_type_unknown (см. fix_labels).
    for c in MODES + ['rnf']:
        m = df[c].isna()
        df.loc[m, c] = 0
        filled[c] = int(m.sum())

    for c, n in filled.items():
        if n:
            log.append((f'Заполнение пропусков: {c}', n, c))
    stats['filled'] = filled
    return df


def iqr_bounds(s):
    q1, q3 = s.quantile(.25), s.quantile(.75)
    return q1 - 1.5 * (q3 - q1), q3 + 1.5 * (q3 - q1)


def flag_outliers(df, log, stats):
    """Выбросы не удаляются: в лабе 2 показано, что это предотказные режимы."""
    out = {}
    for c, flag in [('rot_speed_rpm', 'is_outlier_speed'), ('torque_nm', 'is_outlier_torque')]:
        lo, hi = IQR_BOUNDS[c]
        # Значения точно на границе тоже помечаются: из 5 таких записей по моменту
        # (12,8 и 67,2 Н·м) 4 - отказы; так же их учитывал расчёт в лабе 2.
        mask = (df[c] <= lo) | (df[c] >= hi)
        df[flag] = mask.astype('int8')
        z = (df[c] - df[c].mean()).abs() / df[c].std()
        out[c] = {'lo': lo, 'hi': hi, 'n': int(mask.sum()), 'actual': iqr_bounds(df[c]),
                  'fail': int((mask & (df['machine_failure'] == 1)).sum()),
                  'z3': int((z > 3).sum())}
        log.append((f'Флаг выброса {flag} (IQR), записи сохранены', int(mask.sum()), c))
    stats['outliers'] = out
    return df


def fix_labels(df, log):
    sub = df[MODES].sum(axis=1)
    df['failure_type_unknown'] = ((df['machine_failure'] == 1) & (sub == 0)).astype('int8')
    df['n_failure_modes'] = sub.astype('int8')
    # Одноклассовая метка: подтип с наивысшим приоритетом по тяжести последствий
    mode = pd.Series('NONE', index=df.index)
    for c in reversed(PRIORITY):
        mode[df[c] == 1] = c.upper()
    mode[df['failure_type_unknown'] == 1] = 'UNKNOWN'
    df['failure_mode'] = pd.Categorical(mode, categories=['NONE', 'TWF', 'HDF', 'PWF', 'OSF', 'UNKNOWN'])
    # RNF исключается из целевых переменных и сохраняется как справочный признак
    rnf_inconsistent = int(((df['rnf'] == 1) & (df['machine_failure'] == 0)).sum())
    df = df.rename(columns={'rnf': 'rnf_ref'})
    log.append(('Флаг отказа без подтипа failure_type_unknown', int(df['failure_type_unknown'].sum()), 'machine_failure'))
    log.append(('Записи с несколькими подтипами -> failure_mode по приоритету', int((sub > 1).sum()), 'twf, hdf, pwf, osf'))
    log.append(('RNF выведен из целевых переменных (rnf_ref); несогласованных меток', rnf_inconsistent, 'rnf'))
    return df


def add_features(df, log):
    cls = df['quality_class'].astype(str)
    df['temp_diff_k'] = (df['process_temp_k'] - df['air_temp_k']).round(1)
    df['power_w'] = (df['torque_nm'] * df['rot_speed_rpm'] * 2 * np.pi / 60).round(1)
    df['wear_torque'] = (df['tool_wear_min'] * df['torque_nm']).round(1)
    df['osf_limit'] = cls.map(OSF_LIMIT).astype('int32')
    df['osf_margin'] = (df['osf_limit'] - df['wear_torque']).round(1)
    # запас по мощности до ближайшей границы допустимого диапазона, Вт (< 0 - вне диапазона)
    df['power_margin'] = np.minimum(df['power_w'] - POWER_MIN, POWER_MAX - df['power_w']).round(1)
    # Цикл инструмента: износ сбрасывается в 0 при замене инструмента
    reset = df['tool_wear_min'].diff() < 0
    df['tool_cycle_id'] = (reset.cumsum() + 1).astype('int16')
    df['cycle_pos'] = (df.groupby('tool_cycle_id').cumcount() + 1).astype('int16')
    new = ['temp_diff_k', 'power_w', 'wear_torque', 'osf_limit', 'osf_margin',
           'power_margin', 'tool_cycle_id', 'cycle_pos']
    log.append(('Расчёт производных признаков', len(new), ', '.join(new)))
    return df


def downcast(df):
    for c in LABELS[:-1] + ['rnf_ref']:
        df[c] = df[c].astype('int8')
    df['udi'] = df['udi'].astype('int32')
    df['rot_speed_rpm'] = df['rot_speed_rpm'].round().astype('int32')
    df['tool_wear_min'] = df['tool_wear_min'].astype('int16')
    return df


ORDER = ['udi', 'product_id', 'product_serial', 'quality_class',
         'air_temp_k', 'process_temp_k', 'rot_speed_rpm', 'torque_nm', 'tool_wear_min',
         'temp_diff_k', 'power_w', 'power_margin', 'wear_torque', 'osf_limit', 'osf_margin',
         'tool_cycle_id', 'cycle_pos', 'is_outlier_speed', 'is_outlier_torque',
         'machine_failure', 'twf', 'hdf', 'pwf', 'osf', 'failure_mode', 'n_failure_modes',
         'failure_type_unknown', 'rnf_ref']


def transform(raw):
    log, stats = [], {}
    df = rename(raw.copy(), log)
    df = normalize_text(df, log)
    df = cast_types(df, log)
    df = check_ranges(df, log)
    df = drop_duplicates(df, log)
    df = handle_missing(df, log, stats)
    df = flag_outliers(df, log, stats)
    df = fix_labels(df, log)
    df = add_features(df, log)
    df = downcast(df)
    return df[ORDER].reset_index(drop=True), log, stats


# --- валидация ---------------------------------------------------------------
def validate(df):
    """Утверждения о качестве результата; при нарушении конвейер останавливается."""
    checks = {
        'нет пропусков': int(df.isnull().sum().sum()) == 0,
        'UDI уникален': df['udi'].is_unique,
        'Product ID уникален': df['product_id'].is_unique,
        'класс совпадает с буквой Product ID': bool((df['product_id'].str[0] == df['quality_class'].astype(str)).all()),
        'показания в допустимых диапазонах': all(df[c].between(*VALID_RANGE[c]).all() for c in SENSORS),
        'метки бинарные': bool(df[LABELS[:-1] + ['rnf_ref']].isin([0, 1]).all().all()),
        'machine_failure = OR(подтипов) или failure_type_unknown':
            bool(((df[MODES].max(axis=1) | df['failure_type_unknown']) == df['machine_failure']).all()),
        'объём не меньше 500 записей': len(df) >= 500,
    }
    return checks


def wear_step_consistency(df):
    """Доля шагов износа, совпадающих с нормативом по классу предыдущего изделия."""
    d = df['tool_wear_min'].diff()
    prev = df['quality_class'].astype(str).shift(1).map(WEAR_STEP)
    m = d >= 0
    return int((d[m] == prev[m]).sum()), int(m.sum())


# --- L: сохранение -----------------------------------------------------------
def quality_report(df):
    return pd.DataFrame({
        'Поле': df.columns,
        'Тип': df.dtypes.astype(str).values,
        'Уникальных': df.nunique().values,
        'Пропусков': df.isnull().sum().values,
        'Пропусков_%': (df.isnull().sum() / len(df) * 100).round(2).values,
        'Мин': [df[c].min() if df[c].dtype.kind in 'if' else '' for c in df.columns],
        'Макс': [df[c].max() if df[c].dtype.kind in 'if' else '' for c in df.columns],
    })


def load(df, log, out=OUT):
    out.mkdir(exist_ok=True)
    df.to_csv(out / 'data_cleaned.csv', index=False)
    df.to_parquet(out / 'data_cleaned.parquet', index=False)
    quality_report(df).to_csv(out / 'quality_report.csv', index=False)
    pd.DataFrame(log, columns=['Операция', 'Затронуто', 'Поля']).to_csv(out / 'etl_log.csv', index=False)


def run(raw_path=RAW, out=OUT, save=True):
    raw = extract(raw_path)
    df, log, stats = transform(raw)
    checks = validate(df)
    failed = [k for k, ok in checks.items() if not ok]
    if failed:
        raise AssertionError(f'Валидация не пройдена: {failed}')
    if save:
        load(df, log, out)
    stats.update({
        'source_md5': md5(raw_path),
        'rows_in': len(raw), 'rows_out': len(df),
        'cols_in': raw.shape[1], 'cols_out': df.shape[1],
        'mem_in_kb': raw.memory_usage(deep=True).sum() / 1024,
        'mem_out_kb': df.memory_usage(deep=True).sum() / 1024,
        'checks': checks,
        'wear_step': wear_step_consistency(df),
    })
    return raw, df, log, stats


if __name__ == '__main__':
    raw, df, log, stats = run()
    print(f'Исходный размер: {raw.shape}, итоговый: {df.shape}')
    for op, n, cols in log:
        print(f'  {n:>6}  {op}')
    print('Проверки:', 'все пройдены' if all(stats['checks'].values()) else stats['checks'])
    print(f"Память: {stats['mem_in_kb']:.0f} КБ -> {stats['mem_out_kb']:.0f} КБ")
    json.dump(stats, open(OUT / 'etl_stats.json', 'w'), ensure_ascii=False, indent=1, default=float)
    sys.exit(0)
