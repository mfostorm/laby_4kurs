"""Тестовые запросы к графу знаний (лаба 8): SPARQL (RDFLib) и алгоритмы на графах (NetworkX).

Граф читается из results/knowledge_graph.ttl.gz (результат build_graph.py).
Результаты - results/queries.json. Запуск: python queries.py
"""
import gzip
import json
import time
from pathlib import Path

import networkx as nx
from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import OWL, RDF

HERE = Path(__file__).resolve().parent
RES = HERE / 'results'
PDM = Namespace('http://example.org/pdm#')
PREFIX = ('PREFIX pdm: <http://example.org/pdm#>\nPREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n'
          'PREFIX owl: <http://www.w3.org/2002/07/owl#>\n')


def local(u):
    return str(u).split('#')[-1]


def load_graph():
    g = Graph()
    with gzip.open(RES / 'knowledge_graph.ttl.gz', 'rb') as f:
        g.parse(data=f.read().decode('utf-8'), format='turtle')
    return g


def to_networkx(g):
    """Проекция RDF-графа: узлы - индивиды, рёбра - объектные свойства между ними."""
    G = nx.MultiDiGraph()
    obj_props = set(g.subjects(RDF.type, OWL.ObjectProperty))
    for s in g.subjects(RDF.type, OWL.NamedIndividual):
        cls = [local(t) for t in g.objects(s, RDF.type) if t != OWL.NamedIndividual]
        G.add_node(local(s), cls=cls[0] if cls else 'Thing')
    for p in obj_props:
        for s, o in g.subject_objects(p):
            if isinstance(o, URIRef) and local(s) in G and local(o) in G:
                G.add_edge(local(s), local(o), type=local(p))
    return G


def sparql(g, q):
    t = time.perf_counter()
    rows = [[local(v) if isinstance(v, URIRef) else (v.toPython() if v is not None else None)
             for v in row] for row in g.query(PREFIX + q)]
    return rows, (time.perf_counter() - t) * 1000


g = load_graph()
G = to_networkx(g)
U = G.to_undirected(as_view=False)
print(f'Граф: {len(g)} триплетов; проекция NetworkX: {G.number_of_nodes()} узлов, {G.number_of_edges()} рёбер')
out = {'graph': {'triples': len(g), 'nodes': G.number_of_nodes(), 'edges': G.number_of_edges()}}

# --- Запрос 1. Все связи заданного узла ------------------------------------------------------
Q1 = """SELECT ?direction ?relation ?neighbour ?type WHERE {
  { pdm:Obs_161 ?relation ?neighbour . BIND("->" AS ?direction) }
  UNION
  { ?neighbour ?relation pdm:Obs_161 . BIND("<-" AS ?direction) }
  ?relation a owl:ObjectProperty .
  ?neighbour a ?type . FILTER(?type != owl:NamedIndividual)
} ORDER BY ?direction ?relation"""
rows, ms = sparql(g, Q1)
out['q1'] = {'sparql': Q1, 'rows': rows, 'ms': ms}
print('Q1:', len(rows), 'связей', rows)

# --- Запрос 2. Кратчайший путь между двумя узлами ------------------------------------------
src, dst = 'S_ProcTemp', 'FE_3237_HDF'
t = time.perf_counter()
path = nx.shortest_path(U, src, dst)
ms_path = (time.perf_counter() - t) * 1000


def describe(p):
    steps = []
    for a, b in zip(p, p[1:]):
        if G.has_edge(a, b):
            steps.append((a, '-' + G.get_edge_data(a, b)[0]['type'] + '->', b))
        else:
            steps.append((a, '<-' + G.get_edge_data(b, a)[0]['type'] + '-', b))
    return steps


# путь только по отношениям базы знаний: без наблюдение - оборудование
KNOW = {'observedOn', 'cycleOnEquipment', 'hasComponent', 'nextObservation', 'usesToolCycle'}
H = nx.Graph()
for a, b, d in G.edges(data=True):
    if d['type'] not in KNOW:
        H.add_edge(a, b)
path_k = nx.shortest_path(H, src, dst)
Q2_SPARQL = """ASK { pdm:FE_3237_HDF pdm:hasFailureType ?ft .
      ?rule pdm:detects ?ft ; pdm:usesParameter/pdm:derivedFrom*/pdm:measuredBy pdm:S_ProcTemp . }"""
ask = bool(g.query(PREFIX + Q2_SPARQL).askAnswer)
out['q2'] = {'src': src, 'dst': dst, 'path': describe(path), 'path_knowledge': describe(path_k),
             'ms': ms_path, 'sparql': Q2_SPARQL, 'ask': ask, 'algorithm': 'BFS (nx.shortest_path, невзвешенный граф)'}
print('Q2:', describe(path))
print('Q2 (знания):', describe(path_k), 'ASK =', ask)

# --- Запрос 3. Топ-10 узлов по степени ------------------------------------------------------
t = time.perf_counter()
deg = sorted(U.degree(), key=lambda x: -x[1])[:10]
out['q3'] = {'rows': [[n, G.nodes[n]['cls'], d] for n, d in deg], 'ms': (time.perf_counter() - t) * 1000}
print('Q3:', out['q3']['rows'])

# --- Запрос 4. Предметная область -------------------------------------------------------------
# 4а. Качество правил: сколько раз сработало и сколько срабатываний подтверждено отказом того же типа
Q4A = """SELECT ?rule (COUNT(DISTINCT ?rf) AS ?fired) (COUNT(DISTINCT ?fe) AS ?confirmed) WHERE {
  ?rf pdm:generatedBy ?r ; pdm:predictsFailureType ?ft ; pdm:concernsObservation ?obs .
  ?r pdm:ruleCode ?rule .
  OPTIONAL { ?obs pdm:hasFailureEvent ?fe . ?fe pdm:hasFailureType ?ft . }
} GROUP BY ?rule ORDER BY ?rule"""
rows, ms = sparql(g, Q4A)
out['q4a'] = {'sparql': Q4A, 'rows': rows, 'ms': ms}
print('Q4a:', rows)

# 4б. Полнота: отказы каждого типа и те из них, которым соответствует прогноз того же типа
Q4B = """SELECT ?code (COUNT(DISTINCT ?fe) AS ?events) (COUNT(DISTINCT ?rf) AS ?predicted) WHERE {
  ?fe a pdm:FailureEvent ; pdm:hasFailureType ?ft ; pdm:occurredDuring ?obs .
  ?ft pdm:failureCode ?code .
  OPTIONAL { ?rf pdm:concernsObservation ?obs ; pdm:predictsFailureType ?ft . }
} GROUP BY ?code ORDER BY ?code"""
rows, ms = sparql(g, Q4B)
out['q4b'] = {'sparql': Q4B, 'rows': rows, 'ms': ms}
print('Q4b:', rows)

# 4в. Отказы по механизму, поражаемому узлу и рекомендуемой работе (путь по графу знаний)
Q4C = """SELECT ?mechanism ?component ?action (COUNT(?fe) AS ?failures) WHERE {
  ?fe pdm:hasFailureType ?ft .
  ?ft a ?mclass . ?mclass rdfs:subClassOf pdm:FailureType ; rdfs:label ?mechanism .
  ?ft pdm:affectsComponent ?c ; pdm:recommendsAction ?a .
  ?c rdfs:label ?component . ?a pdm:actionName ?action .
  FILTER(lang(?mechanism) = "ru" && lang(?component) = "ru")
} GROUP BY ?mechanism ?component ?action ORDER BY DESC(?failures)"""
rows, ms = sparql(g, Q4C)
out['q4c'] = {'sparql': Q4C, 'rows': rows, 'ms': ms}
print('Q4c:', rows)

# 4г. Упреждение правила TWF: за сколько изделий до отказа по износу в том же цикле
#     инструмента правило впервые сработало
Q4D = """SELECT ?cycle ?failPos (MIN(?pos) AS ?firstAlertPos) WHERE {
  ?fe pdm:hasFailureType pdm:TWF ; pdm:occurredDuring ?fobs .
  ?fobs pdm:usesToolCycle ?c ; pdm:positionInCycle ?failPos .
  ?c pdm:cycleNumber ?cycle .
  ?rf pdm:generatedBy pdm:R_TWF ; pdm:concernsObservation ?obs .
  ?obs pdm:usesToolCycle ?c ; pdm:positionInCycle ?pos .
} GROUP BY ?cycle ?failPos ORDER BY ?cycle"""
rows, ms = sparql(g, Q4D)
leads = [r[1] - r[2] for r in rows]
out['q4d'] = {'sparql': Q4D, 'rows': rows, 'ms': ms, 'cycles': len(rows),
              'lead_mean': sum(leads) / len(leads), 'lead_min': min(leads), 'lead_max': max(leads),
              'zero_lead': sum(1 for x in leads if x == 0)}
print('Q4d: циклов', len(rows), 'упреждение среднее', out['q4d']['lead_mean'], 'мин', min(leads), 'макс', max(leads))

# --- Проверка структуры графа по аксиомам онтологии -------------------------------------------
CHECKS = {
    'наблюдение без изделия': 'SELECT (COUNT(?o) AS ?n) WHERE { ?o a pdm:Observation . '
                              'FILTER NOT EXISTS { ?o pdm:processesProduct ?p } }',
    'наблюдение с >1 циклом': 'SELECT (COUNT(DISTINCT ?o) AS ?n) WHERE { ?o pdm:usesToolCycle ?a, ?b . FILTER(?a != ?b) }',
    'изделие с >1 классом': 'SELECT (COUNT(DISTINCT ?p) AS ?n) WHERE { ?p pdm:hasQualityClass ?a, ?b . FILTER(?a != ?b) }',
    'событие без типа': 'SELECT (COUNT(?e) AS ?n) WHERE { ?e a pdm:FailureEvent . '
                        'FILTER NOT EXISTS { ?e pdm:hasFailureType ?t } }',
    'прогноз без правила': 'SELECT (COUNT(?r) AS ?n) WHERE { ?r a pdm:RiskForecast . '
                           'FILTER NOT EXISTS { ?r pdm:generatedBy ?x } }',
    'уровень риска вне перечисления': 'SELECT (COUNT(?r) AS ?n) WHERE { ?r pdm:riskLevel ?l . '
                                      'FILTER(?l NOT IN ("low", "medium", "high")) }',
}
out['checks'] = {k: sparql(g, q)[0][0][0] for k, q in CHECKS.items()}
print('Проверки:', out['checks'])

json.dump(out, open(RES / 'queries.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1, default=str)
