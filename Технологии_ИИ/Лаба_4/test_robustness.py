"""Проверка устойчивости ETL к дефектам данных (нефункциональное требование № 4, лаба 1).

Исходный набор AI4I 2020 не содержит пропусков, дубликатов и ошибочных
значений, поэтому ветви очистки на нём не срабатывают. Чтобы проверить их,
в копию набора намеренно вносятся дефекты известного объёма, после чего
результат конвейера сравнивается с эталоном (исходными значениями).
"""
import json

import numpy as np
import pandas as pd

import etl

rng = np.random.default_rng(10)          # вариант 10 - фиксированное зерно
raw = etl.extract()
ref, _, _ = etl.transform(raw)           # эталон: результат на чистых данных
bad = raw.copy()
n = len(bad)
injected = {}

# 1. Пропуски: 2 % значений каждого датчика
for c in ['Air temperature [K]', 'Process temperature [K]', 'Rotational speed [rpm]',
          'Torque [Nm]', 'Tool wear [min]']:
    idx = rng.choice(n, size=n // 50, replace=False)
    bad.loc[idx, c] = np.nan
    injected[c] = len(idx)

# 2. Ошибки датчика: температура в градусах Цельсия и отрицательный момент
idx_c = rng.choice(n, 10, replace=False)
bad.loc[idx_c, 'Air temperature [K]'] = 27.0
idx_t = rng.choice(n, 10, replace=False)
bad.loc[idx_t, 'Torque [Nm]'] = -5.0
# 3. Нечисловые значения
idx_s = rng.choice(n, 5, replace=False)
bad['Rotational speed [rpm]'] = bad['Rotational speed [rpm]'].astype(object)
bad.loc[idx_s, 'Rotational speed [rpm]'] = 'н/д'
# 4. Текстовые поля: лишние пробелы, нижний регистр, пустой класс
idx_x = rng.choice(n, 30, replace=False)
bad.loc[idx_x, 'Type'] = ' ' + bad.loc[idx_x, 'Type'].str.lower() + ' '
idx_e = rng.choice(n, 10, replace=False)
bad.loc[idx_e, 'Type'] = np.nan
# 5. Дубликаты: 50 полных копий и 20 записей с повтором UDI
dup_full = bad.sample(50, random_state=10)
dup_key = bad.sample(20, random_state=11).copy()
dup_key['Torque [Nm]'] = dup_key['Torque [Nm]'] + 1
# 6. Запись с утраченными показаниями большинства датчиков
lost = bad.sample(3, random_state=12).copy()
lost[['Air temperature [K]', 'Process temperature [K]', 'Torque [Nm]']] = np.nan
lost['UDI'] = [20001, 20002, 20003]
lost['Product ID'] = ['L90001', 'L90002', 'L90003']
lost['Type'] = 'L'
bad = pd.concat([bad, dup_full, dup_key, lost], ignore_index=True)

df, log, stats = etl.transform(bad)
checks = etl.validate(df)

# Ошибка восстановления относительно эталона по заполненным ячейкам
merged = df.merge(ref, on='udi', suffixes=('', '_ref'))
errors = {}
for c in etl.SENSORS:
    col = {'air_temp_k': 'Air temperature [K]', 'process_temp_k': 'Process temperature [K]',
           'rot_speed_rpm': 'Rotational speed [rpm]', 'torque_nm': 'Torque [Nm]',
           'tool_wear_min': 'Tool wear [min]'}[c]
    filled_udi = set(bad.loc[bad[col].isna() | ~pd.to_numeric(bad[col], errors='coerce')
                             .between(*etl.VALID_RANGE[c]), 'UDI'])
    m = merged['udi'].isin(filled_udi)
    e = (merged.loc[m, c] - merged.loc[m, c + '_ref']).abs()
    errors[c] = {'n': int(m.sum()), 'mae': float(e.mean()), 'std_ref': float(ref[c].std())}

# Сравнение стратегий заполнения: на эталоне скрываются 2 % значений признака,
# восстанавливаются разными способами, считается средняя абсолютная ошибка.
def compare_strategies():
    r = ref.copy()
    cls = r['quality_class']
    omega = 2 * np.pi / 60
    rows = []
    for c in etl.SENSORS:
        idx = rng.choice(len(r), len(r) // 50, replace=False)
        m = r.index.isin(idx)
        true = r.loc[m, c]
        known = r[c].where(~m)
        est = {
            'Среднее': pd.Series(known.mean(), index=true.index),
            'Медиана': pd.Series(known.median(), index=true.index),
            'Медиана по классу': known.groupby(cls, observed=True).transform('median')[m],
        }
        if c in ('air_temp_k', 'process_temp_k', 'tool_wear_min'):
            est['Интерполяция'] = known.interpolate(limit_direction='both')[m]
        if c == 'air_temp_k':
            est['По связи признаков'] = r.loc[m, 'process_temp_k'] - etl.TEMP_DIFF_MED
        if c == 'process_temp_k':
            est['По связи признаков'] = r.loc[m, 'air_temp_k'] + etl.TEMP_DIFF_MED
        if c == 'torque_nm':
            est['По связи признаков'] = etl.POWER_MED / (r.loc[m, 'rot_speed_rpm'] * omega)
        if c == 'rot_speed_rpm':
            est['По связи признаков'] = (etl.POWER_MED / (r.loc[m, 'torque_nm'] * omega)).clip(1, 5000)
        if c == 'tool_wear_min':
            tmp = r.rename(columns={'rnf_ref': 'rnf'})
            tmp.loc[m, c] = np.nan
            filled = {}
            out = etl.handle_missing(tmp, [], filled)
            est['Шаг износа по классу'] = out.loc[m, c]
        for k, v in est.items():
            rows.append((c, k, float((v - true).abs().mean())))
    return rows


strategies = compare_strategies()
for c, k, e in strategies:
    print(f'  {c:15s} {k:22s} MAE {e:8.2f}')

result = {
    'strategies': strategies,
    'rows_in': len(bad), 'rows_out': len(df), 'log': log, 'checks': checks,
    'errors': errors,
    'failure_share_ref': float(ref['machine_failure'].mean()),
    'failure_share_out': float(df['machine_failure'].mean()),
}
print(f'Записей с дефектами: {len(bad)}, после очистки: {len(df)}')
for op, k, _ in log:
    print(f'  {k:>6}  {op}')
print('Проверки:', 'все пройдены' if all(checks.values()) else checks)
for c, e in errors.items():
    print(f"  {c:15s} восстановлено {e['n']:4d}, MAE {e['mae']:.2f} (СКО признака {e['std_ref']:.2f})")
json.dump(result, open(etl.OUT / 'robustness.json', 'w'), ensure_ascii=False, indent=1, default=float)
