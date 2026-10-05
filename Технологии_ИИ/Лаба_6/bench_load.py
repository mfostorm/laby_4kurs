"""Сравнение способов загрузки (лаба 6, п. 6.2.2 методических указаний).

Одни и те же 10 000 строк fact_observation загружаются во временную таблицу
четырьмя способами; каждый способ повторяется 3 раза, берётся медиана.
"""
import json
import statistics
import time

import pandas as pd
from sqlalchemy import create_engine, text

from load_dwh import RES, SRC, URL, build_fact_observation, copy_df

engine = create_engine(URL)
fact = build_fact_observation(pd.read_csv(SRC), 1)
rows = [tuple(None if pd.isna(v) else (v.item() if hasattr(v, 'item') else v) for v in r)
        for r in fact.itertuples(index=False)]
cols = ', '.join(fact.columns)
ph = ', '.join(['%s'] * len(fact.columns))


def prepare(conn):
    conn.exec_driver_sql('DROP TABLE IF EXISTS dwh.tmp_load')
    conn.exec_driver_sql('CREATE TABLE dwh.tmp_load AS SELECT * FROM dwh.fact_observation WHERE false')
    conn.exec_driver_sql('ALTER TABLE dwh.tmp_load DROP COLUMN observation_key')


def m_insert_each(conn):
    with conn.connection.dbapi_connection.cursor() as cur:
        for r in rows:
            cur.execute(f'INSERT INTO dwh.tmp_load ({cols}) VALUES ({ph})', r)


def m_insert_multi(conn):
    fact.to_sql('tmp_load', conn, schema='dwh', if_exists='append', index=False,
                method='multi', chunksize=1000)


def m_to_sql(conn):
    fact.to_sql('tmp_load', conn, schema='dwh', if_exists='append', index=False)


def m_copy(conn):
    copy_df(conn, fact, 'tmp_load')


METHODS = [('INSERT по одной строке', m_insert_each),
           ('pandas.to_sql (executemany)', m_to_sql),
           ('INSERT множественный (to_sql, method=multi)', m_insert_multi),
           ('COPY FROM STDIN', m_copy)]
res = {}
for name, fn in METHODS:
    times = []
    for _ in range(3):
        with engine.begin() as conn:
            prepare(conn)
            t = time.perf_counter()
            fn(conn)
            times.append(time.perf_counter() - t)
            n = conn.execute(text('SELECT count(*) FROM dwh.tmp_load')).scalar_one()
            assert n == len(fact), (name, n)
    res[name] = statistics.median(times)
    print(f'{name:45s} {res[name]:.3f} с')
with engine.begin() as conn:
    conn.exec_driver_sql('DROP TABLE dwh.tmp_load')
json.dump(res, open(RES / 'bench_load.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
