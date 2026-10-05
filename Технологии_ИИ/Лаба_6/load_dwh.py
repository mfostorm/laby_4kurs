"""Загрузка очищенных данных в хранилище PostgreSQL (лабораторная работа 6, вариант 10).

1. Создаёт схему dwh скриптами из лабы 5 (01_create_schema, 02_reference_data, 03_views).
2. Строит измерения dim_tool, dim_batch и таблицы фактов из data_cleaned.csv (лаба 4).
3. Загружает всё в одной транзакции: измерения - pandas.to_sql, факты - COPY.
4. Сохраняет число загруженных записей в results/load.json.

Параметры подключения берутся из переменных окружения (значения по умолчанию -
как в методических указаниях):
    DB_HOST=localhost DB_PORT=5432 DB_NAME=ai_project DB_USER=postgres DB_PASSWORD=...
Запуск:  python load_dwh.py
"""
import hashlib
import io
import json
import os
import time
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

HERE = Path(__file__).resolve().parent
LAB4 = HERE.parent / 'Лаба_4' / 'data'
LAB5 = HERE.parent / 'Лаба_5' / 'sql'
SRC = LAB4 / 'data_cleaned.csv'
RES = HERE / 'results'
RES.mkdir(exist_ok=True)

DB_NAME = os.getenv('DB_NAME', 'ai_project')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'mysecretpassword')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
URL = f'postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'

CLASS_KEY = {'L': 1, 'M': 2, 'H': 3}                         # из 02_reference_data.sql
FAILURE_KEY = {'NONE': 0, 'TWF': 1, 'HDF': 2, 'OSF': 3, 'PWF': 4, 'RNF': 5, 'UNKNOWN': 9}
EQUIPMENT_KEY = 1


def run_sql_file(conn, path):
    """Выполнить SQL-скрипт целиком (несколько команд) через DBAPI-курсор.
    Курсор вызывается без параметров, поэтому символ % в тексте скрипта безопасен."""
    with conn.connection.dbapi_connection.cursor() as cur:
        cur.execute(path.read_text(encoding='utf-8'))


def copy_df(conn, df, table):
    """Быстрая загрузка DataFrame командой COPY ... FROM STDIN (psycopg2)."""
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False)
    buf.seek(0)
    cols = ', '.join(df.columns)
    raw = conn.connection.dbapi_connection
    with raw.cursor() as cur:
        cur.copy_expert(f'COPY dwh.{table} ({cols}) FROM STDIN WITH (FORMAT csv)', buf)


def build_dim_tool(df):
    g = df.groupby('tool_cycle_id')
    tool = pd.DataFrame({
        'tool_key': g.size().index.astype(int),
        'tool_cycle_no': g.size().index.astype(int),
        'first_udi': g['udi'].min().values,
        'last_udi': g['udi'].max().values,
        'products_processed': g.size().values,
        'wear_at_end_min': g['tool_wear_min'].last().values,
        'end_twf': g['twf'].last().values,
    })
    tool['end_reason'] = 'PLANNED'
    tool.loc[tool['end_twf'] == 1, 'end_reason'] = 'TWF'
    tool.loc[tool.index[-1], 'end_reason'] = 'IN_SERVICE'     # последний цикл не завершён
    return tool.drop(columns='end_twf')


def build_fact_observation(df, batch_key):
    f = pd.DataFrame({
        'udi': df['udi'], 'product_id': df['product_id'], 'product_serial': df['product_serial'],
        'equipment_key': EQUIPMENT_KEY,
        'class_key': df['quality_class'].map(CLASS_KEY),
        'tool_key': df['tool_cycle_id'],
        'failure_type_key': df['failure_mode'].map(FAILURE_KEY),
        'batch_key': batch_key,
    })
    measures = ['air_temp_k', 'process_temp_k', 'rot_speed_rpm', 'torque_nm', 'tool_wear_min',
                'temp_diff_k', 'power_w', 'power_margin', 'wear_torque', 'osf_margin', 'cycle_pos',
                'machine_failure', 'twf', 'hdf', 'pwf', 'osf', 'rnf_ref', 'n_failure_modes',
                'failure_type_unknown', 'is_outlier_speed', 'is_outlier_torque']
    for c in measures:
        f[c] = df[c]
    return f.rename(columns={'power_margin': 'power_margin_w'})


def build_fact_failure_event(df, batch_key):
    """Одна строка на каждый отмеченный подтип отказа (включая RNF и UNKNOWN)."""
    parts = []
    for col, code in [('twf', 'TWF'), ('hdf', 'HDF'), ('pwf', 'PWF'), ('osf', 'OSF'),
                      ('rnf_ref', 'RNF'), ('failure_type_unknown', 'UNKNOWN')]:
        sub = df[df[col] == 1]
        parts.append(pd.DataFrame({
            'udi': sub['udi'], 'equipment_key': EQUIPMENT_KEY,
            'class_key': sub['quality_class'].map(CLASS_KEY), 'tool_key': sub['tool_cycle_id'],
            'failure_type_key': FAILURE_KEY[code], 'batch_key': batch_key,
            'is_primary': (sub['failure_mode'] == code).astype(int),
        }))
    return pd.concat(parts).sort_values(['udi', 'failure_type_key'])


def main():
    t0 = time.perf_counter()
    df = pd.read_csv(SRC)
    md5 = hashlib.md5(SRC.read_bytes()).hexdigest()
    engine = create_engine(URL)
    timings = {}

    # Вся загрузка - одна транзакция: при любой ошибке хранилище остаётся пустым
    with engine.begin() as conn:
        t = time.perf_counter()
        for f in ['01_create_schema.sql', '02_reference_data.sql', '03_views.sql']:
            run_sql_file(conn, LAB5 / f)
        timings['ddl'] = time.perf_counter() - t

        batch_key = conn.execute(text(
            'INSERT INTO dwh.dim_batch (source_name, source_file, source_md5, etl_script) '
            'VALUES (:n, :f, :m, :s) RETURNING batch_key'),
            {'n': 'AI4I 2020 Predictive Maintenance Dataset (cleaned)',
             'f': 'Лаба_4/data/data_cleaned.csv', 'm': md5, 's': 'Лаба_6/load_dwh.py'}).scalar_one()

        t = time.perf_counter()
        dim_tool = build_dim_tool(df)
        dim_tool.to_sql('dim_tool', conn, schema='dwh', if_exists='append', index=False)
        timings['dim_tool'] = time.perf_counter() - t

        t = time.perf_counter()
        fact = build_fact_observation(df, batch_key)
        copy_df(conn, fact, 'fact_observation')
        timings['fact_observation'] = time.perf_counter() - t

        t = time.perf_counter()
        events = build_fact_failure_event(df, batch_key)
        copy_df(conn, events, 'fact_failure_event')
        timings['fact_failure_event'] = time.perf_counter() - t

        conn.execute(text('UPDATE dwh.dim_batch SET rows_loaded = :n WHERE batch_key = :b'),
                     {'n': len(fact), 'b': batch_key})
        conn.exec_driver_sql('ANALYZE')

    counts = {}
    with engine.connect() as conn:
        for tbl in ['dim_equipment', 'dim_quality_class', 'dim_tool', 'dim_failure_type',
                    'dim_batch', 'fact_observation', 'fact_failure_event']:
            counts[tbl] = conn.execute(text(f'SELECT count(*) FROM dwh.{tbl}')).scalar_one()
    expected = {'dim_equipment': 1, 'dim_quality_class': 3, 'dim_tool': len(dim_tool),
                'dim_failure_type': 7, 'dim_batch': 1, 'fact_observation': len(df),
                'fact_failure_event': len(events)}
    total = time.perf_counter() - t0
    print(f'Загрузка завершена за {total:.2f} с')
    for tbl, n in counts.items():
        mark = 'OK' if n == expected[tbl] else f'ожидалось {expected[tbl]}'
        print(f'  {tbl:20s} {n:>6}  {mark}')
    json.dump({'counts': counts, 'expected': expected, 'timings': timings, 'total_s': total,
               'source_md5': md5, 'batch_key': batch_key},
              open(RES / 'load.json', 'w'), ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
