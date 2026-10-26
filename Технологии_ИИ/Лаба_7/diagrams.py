"""Визуальная модель онтологии (лаба 7). Все рисунки строятся из ontology/pdm.ttl
(Graphviz), поэтому соответствуют формальному описанию. Запуск после reasoning.py:
python diagrams.py -> img/taxonomy.png, img/relations.png, img/abox.png
"""
import json
import subprocess
from pathlib import Path

import rdflib
from rdflib.namespace import OWL, RDF, RDFS

HERE = Path(__file__).resolve().parent
IMG = HERE / 'img'
IMG.mkdir(exist_ok=True)
PDM = rdflib.Namespace('http://example.org/pdm#')
g = rdflib.Graph()
g.parse(HERE / 'ontology' / 'pdm.ttl')
inferred = json.load(open(HERE / 'results' / 'reasoning.json', encoding='utf-8'))['inferred_types']

# Группы понятий и цвета (используются и в лабе 8)
GROUPS = {
    'Технические объекты': ('#dbe9f6', ['Equipment', 'MachineTool', 'MillingMachine', 'Component', 'Spindle',
                                        'Drive', 'CoolingSystem', 'CuttingTool', 'Sensor', 'TemperatureSensor',
                                        'SpeedSensor', 'TorqueSensor', 'WearCounter', 'MonitoredParameter']),
    'Производство': ('#e2f0d9', ['Product', 'QualityClass', 'ToolLifeCycle', 'Observation', 'FailedObservation']),
    'Отказы': ('#f8dcdc', ['FailureType', 'MechanicalFailureType', 'ThermalFailureType', 'ElectricalFailureType',
                           'RandomFailureType', 'FailureEvent', 'MechanicalFailureEvent', 'ThermalFailureEvent',
                           'ElectricalFailureEvent']),
    'База знаний': ('#e8def3', ['ProductionRule', 'DeterministicRule', 'RiskForecast', 'HighRiskForecast',
                                'ConfirmedForecast']),
    'Обслуживание': ('#fbe5cc', ['MaintenanceAction', 'MaintenanceRequest', 'WorkOrder', 'MaintenanceRegulation',
                                 'RepairTeam', 'SparePart']),
}
COLOR = {c: col for col, cs in GROUPS.values() for c in cs}


def local(u):
    return str(u).split('#')[1]


def label(u):
    for lab in g.objects(u, RDFS.label):
        if getattr(lab, 'language', None) == 'ru':
            return str(lab)
    return local(u)


def render(dot, name):
    (IMG / f'{name}.dot').write_text(dot, encoding='utf-8')
    subprocess.run(['dot', '-Tpng', '-Gdpi=170', '-o', str(IMG / f'{name}.png')],
                   input=dot.encode(), check=True)


classes = sorted(local(c) for c in g.subjects(RDF.type, OWL.Class) if isinstance(c, rdflib.URIRef))
defined = {local(s): o for s, o in g.subject_objects(OWL.equivalentClass)
           if isinstance(s, rdflib.URIRef) and (o, OWL.intersectionOf, None) in g}


def defined_base(cls):
    """Базовый класс и свойство в определении вида Base ⊓ ∃prop.X."""
    node = defined[cls]
    items = list(rdflib.collection.Collection(g, g.value(node, OWL.intersectionOf)))
    base = local(items[0])
    restr = items[1]
    prop = local(g.value(restr, OWL.onProperty))
    filler = g.value(restr, OWL.someValuesFrom)
    if filler is not None:
        return base, f'≡ ∃{prop}.{local(filler)}'
    val = g.value(restr, OWL.hasValue)
    return base, f'≡ {prop} = {val}'


# --- 1. Таксономия (is-a) ---------------------------------------------------------
lines = ['digraph tax { rankdir=LR; nodesep=0.12; ranksep=0.5;',
         'node [shape=box, style="rounded,filled", fontname="DejaVu Sans", fontsize=10, penwidth=1];',
         'edge [color="#444444", arrowhead=empty, arrowsize=0.8];',
         'Thing [label="owl:Thing", fillcolor="#ffffff"];']
for c in classes:
    style = 'rounded,filled,dashed' if c in defined else 'rounded,filled'
    lines.append(f'{c} [label="{c}\\n{label(PDM[c])}", fillcolor="{COLOR.get(c, "#ffffff")}", style="{style}"];')
for c in classes:
    supers = [local(o) for o in g.objects(PDM[c], RDFS.subClassOf) if isinstance(o, rdflib.URIRef)]
    if c in defined:
        base, text = defined_base(c)
        lines.append(f'{base} -> {c} [dir=back, style=dashed, arrowtail=empty, '
                     f'label="{text}", fontname="DejaVu Sans", fontsize=8, fontcolor="#555555"];')
    elif supers:
        for s in supers:
            lines.append(f'{s} -> {c} [dir=back, arrowtail=empty];')
    else:
        lines.append(f'Thing -> {c} [dir=back, arrowtail=empty];')
lines.append('}')
render('\n'.join(lines), 'taxonomy')

# --- 2. Классы, атрибуты и отношения --------------------------------------------------
TOP = ['Equipment', 'Component', 'Sensor', 'MonitoredParameter', 'Product', 'QualityClass', 'ToolLifeCycle',
       'Observation', 'FailureEvent', 'FailureType', 'ProductionRule', 'RiskForecast', 'MaintenanceAction',
       'MaintenanceRequest', 'WorkOrder', 'MaintenanceRegulation', 'RepairTeam', 'SparePart']
attrs = {c: [] for c in TOP}
for p in g.subjects(RDF.type, OWL.DatatypeProperty):
    d = g.value(p, RDFS.domain)
    if d is not None and local(d) in attrs:
        r = g.value(p, RDFS.range)
        rt = local(r).replace('decimal', 'dec').replace('positiveInteger', 'int+').replace('integer', 'int') \
            if isinstance(r, rdflib.URIRef) else 'enum' if (r, OWL.oneOf, None) in g else 'dec[0..1]'
        attrs[local(d)].append(f'{local(p)} : {rt}')
lines = ['digraph rel { rankdir=LR; nodesep=0.3; ranksep=0.9; splines=true;',
         'node [shape=plaintext, fontname="DejaVu Sans", fontsize=9];',
         'edge [fontname="DejaVu Sans", fontsize=8, color="#555555", arrowsize=0.7];']
for c in TOP:
    rows = ''.join(f'<tr><td align="left">{a}</td></tr>' for a in sorted(attrs[c]))
    lines.append(f'{c} [label=<<table border="1" cellborder="0" cellspacing="0" cellpadding="2" '
                 f'bgcolor="{COLOR[c]}"><tr><td><b>{c}</b></td></tr>'
                 f'<tr><td><i>{label(PDM[c])}</i></td></tr>{rows}</table>>];')
SKIP = {'componentOf', 'occurredDuring', 'partOf'}       # обратные / без области определения
for p in sorted(g.subjects(RDF.type, OWL.ObjectProperty)):
    name = local(p)
    if name in SKIP:
        continue
    d, r = g.value(p, RDFS.domain), g.value(p, RDFS.range)
    if d is None or r is None:
        continue
    d, r = local(d), local(r)
    extra = ' ⊑ partOf' if (p, RDFS.subPropertyOf, PDM.partOf) in g else ''
    style = ', style=bold, color="#2f5d8a"' if name in ('hasComponent', 'installedOn') else ''
    lines.append(f'{d} -> {r} [label="{name}{extra}"{style}];')
lines.append('}')
render('\n'.join(lines), 'relations')

# --- 3. Фрагмент с индивидами и выведенными фактами ----------------------------------
FOCUS = ['Obs_161', 'FE_161_OSF', 'OSF', 'RF_161', 'R_OSF', 'Product_L47340', 'Class_L', 'Cycle_2', 'MILL_01',
         'Spindle_01', 'Tool_01', 'A_ReduceFeed', 'P_WearTorque', 'P_Wear', 'P_Torque', 'S_Wear', 'S_Torque',
         'Drive_01']
lines = ['digraph abox { rankdir=LR; nodesep=0.25; ranksep=0.6;',
         'node [shape=box, style="rounded,filled", fontname="DejaVu Sans", fontsize=9];',
         'edge [fontname="DejaVu Sans", fontsize=8, color="#555555", arrowsize=0.7];']
for i in FOCUS:
    types = [local(t) for t in g.objects(PDM[i], RDF.type) if t != OWL.NamedIndividual]
    t0 = types[0]
    inf = inferred.get(i, [])
    inf_txt = ''.join(f'<br/><font color="#a12a2a"><b>⇒ {t}</b></font>' for t in inf)
    lines.append(f'{i} [label=<<b>{i}</b><br/><i>{t0}</i>{inf_txt}>, fillcolor="{COLOR.get(t0, "#ffffff")}"];')
for s, p, o in g:
    if isinstance(s, rdflib.URIRef) and s.startswith(str(PDM)) and isinstance(o, rdflib.URIRef) \
            and local(s) in FOCUS and o.startswith(str(PDM)) and local(o) in FOCUS \
            and p != RDF.type:
        lines.append(f'{local(s)} -> {local(o)} [label="{local(p)}"];')
lines.append('}')
render('\n'.join(lines), 'abox')
print('Готово: img/taxonomy.png, img/relations.png, img/abox.png')
