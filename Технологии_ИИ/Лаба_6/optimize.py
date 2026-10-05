"""Оптимизация запросов индексами (лаба 6, шаг 5).

Для набора типовых запросов выполняется EXPLAIN (ANALYZE) до и после создания
индексов из sql/04_indexes.sql. Каждый запрос выполняется 7 раз, берётся медиана
времени выполнения.

Таблица из 10 000 строк целиком помещается в несколько страниц памяти, поэтому
выигрыш от индексов на ней мал. Чтобы оценить поведение при объёме из
нефункционального требования № 6 лабы 1 (2 млн записей), дополнительно создаётся
нагрузочная копия fact_observation в отдельной схеме bench: исходные 10 000 строк,
размноженные 200 раз со сдвигом udi. Это тестовые данные, в хранилище они не
попадают.
"""
import json
import statistics

from sqlalchemy import create_engine, text

from load_dwh import HERE, RES, URL, run_sql_file

engine = create_engine(URL)

QUERIES = {
    'Q1': ('История цикла инструмента (карточка, СИ-2)',
           'SELECT * FROM {t} WHERE tool_key = 57'),
    'Q2': ('Журнал отказов',
           'SELECT udi, failure_type_key FROM {t} WHERE machine_failure = 1'),
    'Q3': ('Отказы класса H (панель мониторинга)',
           'SELECT count(*) FROM {t} WHERE class_key = 3 AND machine_failure = 1'),
    'Q4': ('Кандидаты на замену инструмента: износ 230-240 мин',
           'SELECT udi, tool_wear_min FROM {t} WHERE tool_wear_min BETWEEN 230 AND 240'),
    'Q5': ('Доля отказов по классам (агрегация всей таблицы)',
           'SELECT class_key, avg(machine_failure) FROM {t} GROUP BY class_key'),
}
BENCH_INDEXES = [
    'CREATE INDEX ON bench.fact_observation (tool_key)',
    'CREATE INDEX ON bench.fact_observation (class_key, machine_failure)',
    'CREATE INDEX ON bench.fact_observation (udi) WHERE machine_failure = 1',
    'CREATE INDEX ON bench.fact_observation (tool_wear_min)',
    'ANALYZE bench.fact_observation',
]
DROP_DWH = ['idx_obs_tool', 'idx_obs_failure_type', 'idx_event_type', 'idx_event_tool',
            'idx_obs_class_failure', 'idx_obs_failures', 'idx_obs_wear']


def explain(conn, sql, runs=7):
    times, plan = [], None
    for _ in range(runs):
        res = conn.execute(text('EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) ' + sql)).scalar_one()
        p = res[0]
        times.append(p['Execution Time'])
        plan = p['Plan']
    def scans(p):
        out = [p] if 'Scan' in p['Node Type'] else []
        for c in p.get('Plans', []):
            out += scans(c)
        return out
    sc = scans(plan)
    txt = conn.execute(text('EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF, SUMMARY OFF) ' + sql)).scalars().all()
    return {'ms': statistics.median(times),
            'node': ' + '.join(dict.fromkeys(s['Node Type'] for s in sc)),
            'index': next((s.get('Index Name') for s in sc if s.get('Index Name')), None),
            'rows': plan.get('Actual Rows'), 'text': txt}


def measure(conn, table):
    return {k: explain(conn, q.format(t=table)) for k, (_, q) in QUERIES.items()}


def size(conn, rel):
    return conn.execute(text(f"SELECT pg_size_pretty(pg_total_relation_size('{rel}'))")).scalar_one()


result = {'queries': {k: v[0] for k, v in QUERIES.items()},
          'sql': {k: v[1].format(t='fact_observation') for k, v in QUERIES.items()}}
with engine.begin() as conn:
    conn.exec_driver_sql('SET search_path TO dwh')
    for i in DROP_DWH:                                   # идемпотентность: исходное состояние
        conn.exec_driver_sql(f'DROP INDEX IF EXISTS dwh.{i}')
    conn.exec_driver_sql('ANALYZE dwh.fact_observation')
    result['size_before'] = size(conn, 'dwh.fact_observation')
    result['dwh_before'] = measure(conn, 'dwh.fact_observation')

    run_sql_file(conn, HERE / 'sql' / '04_indexes.sql')
    result['dwh_after'] = measure(conn, 'dwh.fact_observation')
    result['size_after'] = size(conn, 'dwh.fact_observation')
    result['indexes'] = [list(r) for r in conn.execute(text(
        "SELECT indexname, pg_size_pretty(pg_relation_size(format('dwh.%I', indexname)::regclass)), "
        "indexdef FROM pg_indexes WHERE schemaname = 'dwh' AND tablename LIKE 'fact%' "
        "ORDER BY tablename, indexname"))]

    # нагрузочная копия 2 млн строк
    conn.exec_driver_sql('DROP SCHEMA IF EXISTS bench CASCADE; CREATE SCHEMA bench')
    conn.exec_driver_sql(
        'CREATE TABLE bench.fact_observation AS '
        'SELECT (g * 10000 + f.udi) AS udi, f.class_key, f.tool_key + g * 120 AS tool_key, '
        'f.failure_type_key, f.machine_failure, f.tool_wear_min, f.air_temp_k, f.torque_nm, '
        'f.rot_speed_rpm FROM dwh.fact_observation f CROSS JOIN generate_series(0, 199) g')
    conn.exec_driver_sql('ANALYZE bench.fact_observation')
    result['bench_rows'] = conn.execute(text('SELECT count(*) FROM bench.fact_observation')).scalar_one()
    result['bench_before'] = measure(conn, 'bench.fact_observation')
    for s in BENCH_INDEXES:
        conn.exec_driver_sql(s)
    result['bench_after'] = measure(conn, 'bench.fact_observation')
    conn.exec_driver_sql('DROP SCHEMA bench CASCADE')

for k in QUERIES:
    b, a = result['dwh_before'][k], result['dwh_after'][k]
    bb, ba = result['bench_before'][k], result['bench_after'][k]
    print(f"{k}: 10 тыс. {b['ms']:.3f} -> {a['ms']:.3f} мс ({b['node']} -> {a['node']}); "
          f"2 млн {bb['ms']:.2f} -> {ba['ms']:.2f} мс ({bb['node']} -> {ba['node']})")
json.dump(result, open(RES / 'optimize.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
