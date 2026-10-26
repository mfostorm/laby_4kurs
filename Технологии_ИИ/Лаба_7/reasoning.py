"""Проверка онтологии ризонером HermiT (через owlready2) и статистика (лаба 7).

1. Онтология ontology/pdm.ttl загружается, ризонер проверяет непротиворечивость
   и выводит новые факты (типы индивидов, значения свойств).
2. Негативные тесты: в копию онтологии добавляется заведомо противоречивое
   утверждение - ризонер должен его обнаружить.
3. Статистика онтологии сохраняется в results/ontology_stats.json.
Требуется Java (HermiT). Запуск: python reasoning.py
"""
import json
import tempfile
from pathlib import Path

import owlready2 as owl
import rdflib
from rdflib.namespace import OWL, RDF, RDFS

HERE = Path(__file__).resolve().parent
TTL = HERE / 'ontology' / 'pdm.ttl'
RES = HERE / 'results'
RES.mkdir(exist_ok=True)
PDM = rdflib.Namespace('http://example.org/pdm#')


def to_ntriples(graph):
    tmp = tempfile.NamedTemporaryFile(suffix='.nt', delete=False)
    graph.serialize(tmp.name, format='nt', encoding='utf-8')
    return tmp.name


def load(graph):
    """Загрузить rdflib-граф в отдельный мир owlready2."""
    world = owl.World()
    onto = world.get_ontology('file://' + to_ntriples(graph)).load(format='ntriples')
    return world, onto


def reason(world):
    with world.get_ontology('http://example.org/pdm#'):
        owl.sync_reasoner_hermit(world, infer_property_values=True, debug=0)


base = rdflib.Graph()
base.parse(TTL)

# --- статистика ---------------------------------------------------------------
def named(t):
    return {s for s in base.subjects(RDF.type, t) if isinstance(s, rdflib.URIRef)}


classes = named(OWL.Class)
stats = {
    'triples': len(base),
    'classes': len(classes),
    'object_properties': len(named(OWL.ObjectProperty)),
    'data_properties': len(named(OWL.DatatypeProperty)),
    'individuals': len(named(OWL.NamedIndividual)),
    'subclass_axioms': sum(1 for s, o in base.subject_objects(RDFS.subClassOf)
                           if isinstance(s, rdflib.URIRef) and isinstance(o, rdflib.URIRef)),
    'restrictions': len(set(base.subjects(RDF.type, OWL.Restriction))),
    'defined_classes': sorted(str(s).split('#')[1] for s, o in base.subject_objects(OWL.equivalentClass)
                              if s in classes and (o, OWL.intersectionOf, None) in base),
    'enumerated_classes': sorted(str(s).split('#')[1] for s, o in base.subject_objects(OWL.equivalentClass)
                                 if s in classes and (o, OWL.oneOf, None) in base),
    'disjoint_groups': len(set(base.subjects(RDF.type, OWL.AllDisjointClasses))),
    'characteristics': {str(c).split('#')[1]: len(named(c)) for c in
                        [OWL.FunctionalProperty, OWL.InverseFunctionalProperty, OWL.TransitiveProperty,
                         OWL.AsymmetricProperty, OWL.IrreflexiveProperty]},
}
print('Статистика:', stats)

# --- вывод на исходной онтологии ----------------------------------------------
world, onto = load(base)
before = {i.name: sorted(c.name for c in i.is_a if isinstance(c, owl.ThingClass))
          for i in onto.individuals()}
before_partof = {i.name: sorted(x.name for x in getattr(i, 'partOf', []))
                 for i in onto.individuals() if i.name.startswith('S_')}
reason(world)
inferred_types, inferred_props = {}, {}
for i in onto.individuals():
    now = sorted(c.name for c in i.is_a if isinstance(c, owl.ThingClass))
    new = sorted(set(now) - set(before.get(i.name, [])))
    if new:
        inferred_types[i.name] = new
for i in onto.individuals():
    if i.name.startswith('S_') or i.name.endswith('_01'):
        vals = sorted(x.name for x in i.partOf)
        new = sorted(set(vals) - set(before_partof.get(i.name, [])))
        if new:
            inferred_props[i.name] = new
classified = {c.name: [s.name for s in c.is_a if isinstance(s, owl.ThingClass)]
              for c in onto.classes() if c.name in ('MechanicalFailureEvent', 'ThermalFailureEvent',
                                                    'ElectricalFailureEvent', 'FailedObservation',
                                                    'HighRiskForecast', 'ConfirmedForecast',
                                                    'DeterministicRule')}
members = {c.name: sorted(i.name for i in c.instances()) for c in onto.classes()
           if c.name in classified}
print('Онтология непротиворечива')
for k, v in inferred_types.items():
    print(f'  {k}: выведены типы {v}')
for k, v in inferred_props.items():
    print(f'  {k}: выведено partOf {v}')


# --- негативные тесты -----------------------------------------------------------
def with_triples(extra_ttl):
    g = rdflib.Graph()
    g += base
    g.parse(data='@prefix pdm: <http://example.org/pdm#> .\n'
                 '@prefix owl: <http://www.w3.org/2002/07/owl#> .\n'
                 '@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n' + extra_ttl, format='turtle')
    return g


TESTS = [
    ('Изделие с двумя классами качества (функциональное свойство)',
     'pdm:Product_M14860 pdm:hasQualityClass pdm:Class_H .'),
    ('Узел одновременно шпиндель и привод (непересекающиеся классы)',
     'pdm:Spindle_01 a pdm:Drive .'),
    ('Коэффициент уверенности 1,5 (вне диапазона 0..1)',
     'pdm:R_X a pdm:ProductionRule ; pdm:detects pdm:HDF ; pdm:usesParameter pdm:P_TempDiff ; '
     'pdm:certaintyFactor "1.5"^^xsd:decimal .'),
    ('Наблюдение, следующее само за собой (иррефлексивное свойство)',
     'pdm:Obs_1 pdm:nextObservation pdm:Obs_1 .'),
    ('Уровень риска "critical" (не из перечисления low/medium/high)',
     'pdm:RF_X a pdm:RiskForecast ; pdm:generatedBy pdm:R_HDF ; pdm:concernsObservation pdm:Obs_1 ; '
     'pdm:riskLevel "critical" .'),
    ('Новый класс качества "X" (класс закрыт перечислением L, M, H)',
     'pdm:Class_X a pdm:QualityClass , owl:NamedIndividual ; pdm:classCode "X" . '
     '[] a owl:AllDifferent ; owl:distinctMembers ( pdm:Class_X pdm:Class_L pdm:Class_M pdm:Class_H ) .'),
]
negative = []
for title, ttl in TESTS:
    w, _ = load(with_triples(ttl))
    try:
        reason(w)
        verdict = 'противоречие НЕ обнаружено'
    except owl.OwlReadyInconsistentOntologyError:
        verdict = 'обнаружено противоречие'
    negative.append((title, ttl, verdict))
    print(f'  {title}: {verdict}')

json.dump({'stats': stats, 'consistent': True, 'inferred_types': inferred_types,
           'inferred_partof': inferred_props, 'defined_members': members, 'negative': negative},
          open(RES / 'reasoning.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
