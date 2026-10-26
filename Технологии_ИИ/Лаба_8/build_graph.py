"""Построение графа знаний из хранилища PostgreSQL (лабораторная работа 8, вариант 10).

1. Загружается онтология лабы 7 (схема и справочные индивиды: станок, узлы, датчики,
   параметры, типы отказов, правила, виды работ). Примеры наблюдений из лабы 7 не
   загружаются - вместо них граф наполняется полными данными из хранилища.
2. Из схемы dwh (лабы 5-6) извлекаются данные и создаются узлы и рёбра по маппингу.
3. Граф сохраняется в results/knowledge_graph.ttl.gz; статистика - в results/build.json.

Уникальность узлов: каждому узлу соответствует IRI, построенный из бизнес-ключа
(pdm:Obs_161, pdm:Cycle_2 ...). RDF-граф - множество триплетов, поэтому повторное
добавление того же узла или ребра его не дублирует - аналог MERGE в Cypher.

Параметры подключения - как в лабе 6 (DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD).
Запуск: python build_graph.py
"""
import gzip
import json
import os
import time
from decimal import Decimal
from pathlib import Path

import pandas as pd
from rdflib import Graph, Literal, Namespace
from rdflib.namespace import OWL, RDF, XSD
from sqlalchemy import create_engine

HERE = Path(__file__).resolve().parent
ONTO = HERE.parent / 'Лаба_7' / 'ontology' / 'pdm.ttl'
RES = HERE / 'results'
RES.mkdir(exist_ok=True)
PDM = Namespace('http://example.org/pdm#')

URL = 'postgresql+psycopg2://{u}:{p}@{h}:{port}/{db}'.format(
    u=os.getenv('DB_USER', 'postgres'), p=os.getenv('DB_PASSWORD', 'mysecretpassword'),
    h=os.getenv('DB_HOST', 'localhost'), port=os.getenv('DB_PORT', '5432'),
    db=os.getenv('DB_NAME', 'ai_project'))

# Классы, экземпляры которых берутся из хранилища (примеры из лабы 7 отбрасываются)
DATA_CLASSES = [PDM.Observation, PDM.Product, PDM.ToolLifeCycle, PDM.FailureEvent, PDM.RiskForecast]

# --- SQL-запросы к хранилищу: какой узел порождает каждая таблица -----------------------
SQL = {
    'equipment': 'SELECT equipment_key, inventory_no, nominal_power_w, power_min_w, power_max_w '
                 'FROM dwh.dim_equipment',
    'quality_class': 'SELECT class_code, osf_limit, wear_step_min FROM dwh.dim_quality_class',
    'tool_cycle': 'SELECT tool_cycle_no, products_processed, wear_at_end_min, end_reason '
                  'FROM dwh.dim_tool ORDER BY tool_cycle_no',
    'observation': 'SELECT f.udi, f.product_id, q.class_code, e.inventory_no, t.tool_cycle_no, f.cycle_pos, '
                   'f.air_temp_k, f.process_temp_k, f.rot_speed_rpm, f.torque_nm, f.tool_wear_min, '
                   'f.temp_diff_k, f.power_w, f.wear_torque '
                   'FROM dwh.fact_observation f '
                   'JOIN dwh.dim_quality_class q USING (class_key) '
                   'JOIN dwh.dim_equipment e USING (equipment_key) '
                   'JOIN dwh.dim_tool t USING (tool_key) ORDER BY f.udi',
    'failure_event': 'SELECT e.udi, ft.failure_code, e.is_primary '
                     'FROM dwh.fact_failure_event e JOIN dwh.dim_failure_type ft USING (failure_type_key)',
    # Прогнозы: правила вычисляются по порогам из измерений хранилища. Правило HDF - в
    # нестрогой форме (<=), как рекомендовано по итогам лабы 6 (п. 4.4).
    'forecast': """
        SELECT f.udi, r.code
        FROM dwh.fact_observation f
        JOIN dwh.dim_equipment e USING (equipment_key)
        JOIN dwh.dim_quality_class q USING (class_key)
        CROSS JOIN LATERAL (VALUES
            ('HDF', f.temp_diff_k <= e.hdf_temp_diff_min_k AND f.rot_speed_rpm < e.hdf_speed_max_rpm),
            ('PWF', f.power_w < e.power_min_w OR f.power_w > e.power_max_w),
            ('OSF', f.wear_torque > q.osf_limit),
            ('TWF', f.tool_wear_min BETWEEN e.twf_wear_min_min AND e.twf_wear_max_min)
        ) AS r(code, fired)
        WHERE r.fired
        ORDER BY f.udi, r.code""",
}
FT = {'TWF': PDM.TWF, 'HDF': PDM.HDF, 'PWF': PDM.PWF, 'OSF': PDM.OSF, 'RNF': PDM.RNF,
      'UNKNOWN': PDM.UnknownFailure}
RULE = {'HDF': PDM.R_HDF, 'PWF': PDM.R_PWF, 'OSF': PDM.R_OSF, 'TWF': PDM.R_TWF}
CF = {'HDF': Decimal('1.0'), 'PWF': Decimal('1.0'), 'OSF': Decimal('1.0'), 'TWF': Decimal('0.06')}


def dec(x):
    return Literal(Decimal(str(x)), datatype=XSD.decimal)


def integer(x):
    return Literal(int(x), datatype=XSD.integer)


def load_ontology():
    g = Graph()
    g.parse(ONTO)
    drop = {s for c in DATA_CLASSES for s in g.subjects(RDF.type, c)}
    for s in drop:
        g.remove((s, None, None))
        g.remove((None, None, s))
    # списки owl:AllDifferent для удалённых примеров тоже удаляются
    for b in list(g.subjects(RDF.type, OWL.AllDifferent)):
        members = list(g.collection(g.value(b, OWL.distinctMembers)))
        if not members:
            g.remove((b, None, None))
    return g, len(drop)


def import_data(g, data):
    """Создание узлов и рёбер. Повторный вызов не создаёт дублей (идемпотентность)."""
    eq_iri = {}
    for row in data['equipment'].itertuples():
        node = next(g.subjects(PDM.inventoryNumber, Literal(row.inventory_no)), None) \
            or PDM[f'Equipment_{row.equipment_key}']
        eq_iri[row.inventory_no] = node
        g.add((node, RDF.type, PDM.MillingMachine))
        g.set((node, PDM.nominalPowerW, dec(row.nominal_power_w)))
        g.set((node, PDM.powerMinW, dec(row.power_min_w)))
        g.set((node, PDM.powerMaxW, dec(row.power_max_w)))

    for row in data['quality_class'].itertuples():            # SET: значения из хранилища
        node = PDM[f'Class_{row.class_code}']
        g.set((node, PDM.osfLimit, integer(row.osf_limit)))
        g.set((node, PDM.wearStepMin, integer(row.wear_step_min)))

    for row in data['tool_cycle'].itertuples():
        node = PDM[f'Cycle_{row.tool_cycle_no}']
        g.add((node, RDF.type, PDM.ToolLifeCycle))
        g.add((node, RDF.type, OWL.NamedIndividual))
        g.set((node, PDM.cycleNumber, Literal(int(row.tool_cycle_no), datatype=XSD.positiveInteger)))
        g.set((node, PDM.productsProcessed, Literal(int(row.products_processed), datatype=XSD.positiveInteger)))
        g.set((node, PDM.wearAtEndMin, integer(row.wear_at_end_min)))
        g.set((node, PDM.endReason, Literal(row.end_reason)))
        g.add((node, PDM.cycleOnEquipment, next(iter(eq_iri.values()))))

    prev = None
    for row in data['observation'].itertuples():
        obs, prod = PDM[f'Obs_{row.udi}'], PDM[f'Product_{row.product_id}']
        g.add((obs, RDF.type, PDM.Observation))
        g.add((obs, RDF.type, OWL.NamedIndividual))
        g.set((obs, PDM.udi, integer(row.udi)))
        g.set((obs, PDM.positionInCycle, Literal(int(row.cycle_pos), datatype=XSD.positiveInteger)))
        g.set((obs, PDM.airTemperatureK, dec(row.air_temp_k)))
        g.set((obs, PDM.processTemperatureK, dec(row.process_temp_k)))
        g.set((obs, PDM.rotationalSpeedRpm, integer(row.rot_speed_rpm)))
        g.set((obs, PDM.torqueNm, dec(row.torque_nm)))
        g.set((obs, PDM.toolWearMin, integer(row.tool_wear_min)))
        g.set((obs, PDM.temperatureDifferenceK, dec(row.temp_diff_k)))
        g.set((obs, PDM.powerW, dec(row.power_w)))
        g.set((obs, PDM.wearTorque, dec(row.wear_torque)))
        g.add((obs, PDM.observedOn, eq_iri[row.inventory_no]))
        g.add((obs, PDM.usesToolCycle, PDM[f'Cycle_{row.tool_cycle_no}']))
        g.add((obs, PDM.processesProduct, prod))
        g.add((prod, RDF.type, PDM.Product))
        g.add((prod, RDF.type, OWL.NamedIndividual))
        g.set((prod, PDM.productId, Literal(row.product_id)))
        g.add((prod, PDM.hasQualityClass, PDM[f'Class_{row.class_code}']))
        if prev is not None:
            g.add((prev, PDM.nextObservation, obs))
        prev = obs

    for row in data['failure_event'].itertuples():
        obs, fe = PDM[f'Obs_{row.udi}'], PDM[f'FE_{row.udi}_{row.failure_code}']
        g.add((fe, RDF.type, PDM.FailureEvent))
        g.add((fe, RDF.type, OWL.NamedIndividual))
        g.add((fe, PDM.hasFailureType, FT[row.failure_code]))
        g.set((fe, PDM.isPrimary, Literal(bool(row.is_primary))))
        g.add((obs, PDM.hasFailureEvent, fe))
        g.add((fe, PDM.occurredDuring, obs))

    for row in data['forecast'].itertuples():
        rf = PDM[f'RF_{row.udi}_{row.code}']
        g.add((rf, RDF.type, PDM.RiskForecast))
        g.add((rf, RDF.type, OWL.NamedIndividual))
        g.add((rf, PDM.generatedBy, RULE[row.code]))
        g.add((rf, PDM.concernsObservation, PDM[f'Obs_{row.udi}']))
        g.add((rf, PDM.predictsFailureType, FT[row.code]))
        g.set((rf, PDM.riskScore, Literal(CF[row.code], datatype=XSD.decimal)))
        g.set((rf, PDM.riskLevel, Literal('high' if CF[row.code] >= Decimal('0.5') else 'low')))


def main():
    t0 = time.perf_counter()
    engine = create_engine(URL)
    with engine.connect() as conn:
        data = {k: pd.read_sql(q, conn) for k, q in SQL.items()}
    t_extract = time.perf_counter() - t0
    g, dropped = load_ontology()
    onto_triples = len(g)
    # атрибут события «основной подтип» - свойство данных, добавляемое к онтологии лабы 7
    g.add((PDM.isPrimary, RDF.type, OWL.DatatypeProperty))
    g.add((PDM.isPrimary, RDF.type, OWL.FunctionalProperty))

    t = time.perf_counter()
    import_data(g, data)
    t_import = time.perf_counter() - t
    n1 = len(g)
    import_data(g, data)                       # повторный импорт: дублей быть не должно
    n2 = len(g)

    nodes = {c: len(set(g.subjects(RDF.type, PDM[c]))) for c in [
        'MillingMachine', 'Component', 'Spindle', 'Drive', 'CoolingSystem', 'CuttingTool',
        'TemperatureSensor', 'SpeedSensor', 'TorqueSensor', 'WearCounter', 'MonitoredParameter',
        'QualityClass', 'Product', 'ToolLifeCycle', 'Observation', 'FailureEvent',
        'MechanicalFailureType', 'ThermalFailureType', 'ElectricalFailureType', 'RandomFailureType',
        'FailureType', 'ProductionRule', 'RiskForecast', 'MaintenanceAction']}
    edges = {p: len(list(g.subject_objects(PDM[p]))) for p in [
        'observedOn', 'processesProduct', 'hasQualityClass', 'usesToolCycle', 'cycleOnEquipment',
        'nextObservation', 'hasFailureEvent', 'occurredDuring', 'hasFailureType', 'generatedBy',
        'concernsObservation', 'predictsFailureType', 'hasComponent', 'installedOn', 'measuredBy',
        'derivedFrom', 'detects', 'usesParameter', 'affectsComponent', 'recommendsAction']}
    with gzip.open(RES / 'knowledge_graph.ttl.gz', 'wb') as f:
        f.write(g.serialize(format='turtle').encode('utf-8'))
    stats = {'rows': {k: len(v) for k, v in data.items()}, 'nodes': nodes, 'edges': edges,
             'triples_ontology': onto_triples, 'triples': n1, 'triples_after_reimport': n2,
             'dropped_examples': dropped, 'time_extract_s': t_extract, 'time_import_s': t_import,
             'time_total_s': time.perf_counter() - t0,
             'file_kb': (RES / 'knowledge_graph.ttl.gz').stat().st_size / 1024}
    json.dump(stats, open(RES / 'build.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'Строк из хранилища: {stats["rows"]}')
    print(f'Триплетов: онтология {onto_triples}, после импорта {n1}, после повторного импорта {n2}')
    print('Узлы:', nodes)
    print('Рёбра:', edges)
    print(f'Время: извлечение {t_extract:.2f} с, импорт {t_import:.2f} с')


if __name__ == '__main__':
    main()
