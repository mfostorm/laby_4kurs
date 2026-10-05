"""Проверка целостности хранилища (лаба 6, шаг 4).

1. Проверочные запросы sql/05_checks.sql -> results/checks.json.
2. Сверка с источником: статистики в БД и в data_cleaned.csv.
3. Негативные тесты: заведомо некорректные вставки должны быть отклонены СУБД,
   а после отката транзакции хранилище не должно измениться.
"""
import json
import re

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from load_dwh import HERE, RES, SRC, URL

engine = create_engine(URL)
sql = (HERE / 'sql' / '05_checks.sql').read_text(encoding='utf-8')
blocks = re.split(r"\\echo '--- (.+?)'\n", sql)[1:]
checks = {}
with engine.connect() as conn:
    conn.exec_driver_sql('SET search_path TO dwh')
    for title, query in zip(blocks[::2], blocks[1::2]):
        res = conn.execute(text(query.strip().rstrip(';')))
        checks[title] = {'columns': list(res.keys()),
                         'rows': [[str(v) for v in row] for row in res]}
        print(title)
        for row in checks[title]['rows']:
            print('   ', row)

# --- сверка с источником -------------------------------------------------------
df = pd.read_csv(SRC)
with engine.connect() as conn:
    db = pd.read_sql('SELECT * FROM dwh.v_observation ORDER BY udi', conn)
compare = {}
for c in ['air_temp_k', 'process_temp_k', 'rot_speed_rpm', 'torque_nm', 'tool_wear_min',
          'power_w', 'wear_torque', 'machine_failure']:
    compare[c] = {'csv_sum': float(df[c].sum()), 'db_sum': float(db[c].astype(float).sum()),
                  'equal': bool((df[c].values == db[c].astype(float).values).all())}
compare['failure_mode'] = {'equal': bool((df['failure_mode'].values == db['failure_mode'].values).all())}
print('Сверка с CSV:', all(v['equal'] for v in compare.values()))

# --- негативные тесты -----------------------------------------------------------
GOOD = ("INSERT INTO dwh.fact_observation (udi, product_id, product_serial, equipment_key, class_key, "
        "tool_key, failure_type_key, batch_key, air_temp_k, process_temp_k, rot_speed_rpm, torque_nm, "
        "tool_wear_min, temp_diff_k, power_w, power_margin_w, wear_torque, osf_margin, cycle_pos, "
        "machine_failure, twf, hdf, pwf, osf, rnf_ref, n_failure_modes, failure_type_unknown, "
        "is_outlier_speed, is_outlier_torque) VALUES ({udi}, '{pid}', 99999, 1, {cls}, 1, 0, 1, "
        "{air}, 310.0, 1500, 40.0, 10, 10.0, 6283.2, 2716.8, 400.0, 10600.0, 1, "
        "{mf}, 0, 0, 0, 0, 0, 0, 0, 0, 0)")
TESTS = [
    ('Несуществующий класс качества (class_key = 99)',
     GOOD.format(udi=20001, pid='X20001', cls=99, air=300.0, mf=0)),
    ('Температура 27 K вместо 300 K (ошибка единиц)',
     GOOD.format(udi=20002, pid='X20002', cls=1, air=27.0, mf=0)),
    ('Отказ без подтипа и без флага failure_type_unknown',
     GOOD.format(udi=20003, pid='X20003', cls=1, air=300.0, mf=1)),
    ('Повтор UDI существующего наблюдения',
     GOOD.format(udi=1, pid='X20004', cls=1, air=300.0, mf=0)),
    ('Повторная загрузка того же файла (тот же MD5)',
     "INSERT INTO dwh.dim_batch (source_name, source_file, source_md5, etl_script) "
     "SELECT source_name, source_file, source_md5, etl_script FROM dwh.dim_batch LIMIT 1"),
    ('Событие отказа для несуществующего наблюдения',
     "INSERT INTO dwh.fact_failure_event (udi, equipment_key, class_key, tool_key, failure_type_key, "
     "batch_key, is_primary) VALUES (99999, 1, 1, 1, 1, 1, 1)"),
]
negative = []
with engine.connect() as conn:
    before = conn.execute(text('SELECT count(*) FROM dwh.fact_observation')).scalar_one()
for title, stmt in TESTS:
    try:
        with engine.begin() as conn:            # транзакция: при ошибке - откат
            conn.execute(text(stmt))
        negative.append((title, 'ПРИНЯТО (ошибка проверки!)', ''))
    except DBAPIError as e:
        err = type(e.orig).__name__
        msg = str(e.orig).split('\n')[0]
        negative.append((title, err, msg))
with engine.connect() as conn:
    after = conn.execute(text('SELECT count(*) FROM dwh.fact_observation')).scalar_one()
print('Негативные тесты:')
for t, err, msg in negative:
    print(f'  {t}: {err} - {msg}')
print(f'Строк в fact_observation до тестов {before}, после {after}')

# --- граница правила HDF: точная арифметика NUMERIC против float -------------------
raw_diff = df['process_temp_k'] - df['air_temp_k']
edge = (df['temp_diff_k'] == 8.6) & (df['rot_speed_rpm'] < 1380)
hdf_edge = {
    'edge_rows': int(edge.sum()), 'edge_hdf': int(df.loc[edge, 'hdf'].sum()),
    'edge_hdf_float_below': int((edge & (raw_diff < 8.6) & (df['hdf'] == 1)).sum()),
    'edge_float_below': int((edge & (raw_diff < 8.6)).sum()),
    'lt': [int(((df.temp_diff_k < 8.6) & (df.rot_speed_rpm < 1380)).sum()),
           int(((df.temp_diff_k < 8.6) & (df.rot_speed_rpm < 1380) & (df.hdf == 1)).sum())],
    'le': [int(((df.temp_diff_k <= 8.6) & (df.rot_speed_rpm < 1380)).sum()),
           int(((df.temp_diff_k <= 8.6) & (df.rot_speed_rpm < 1380) & (df.hdf == 1)).sum())],
}
print('Граница HDF:', hdf_edge)

json.dump({'checks': checks, 'compare': compare, 'negative': negative,
           'rows_before': before, 'rows_after': after, 'hdf_edge': hdf_edge},
          open(RES / 'checks.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
