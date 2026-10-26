"""Визуализация фрагмента графа знаний (лаба 8): подграф вокруг отказов по перегрузке
в цикле инструмента № 2. Разные типы узлов - разными цветами. Запуск: python visualize.py
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import networkx as nx
from matplotlib.lines import Line2D

from queries import G, HERE  # noqa: E402  (загружает граф и проекцию NetworkX)

CENTER = ['Obs_160', 'Obs_161', 'Obs_162']
nodes = set(CENTER)
for o in CENTER:
    nodes |= set(G.successors(o)) | set(G.predecessors(o))
    for n in list(G.successors(o)) + list(G.predecessors(o)):
        if G.nodes[n]['cls'] in ('FailureEvent', 'RiskForecast', 'Product'):
            nodes |= set(G.successors(n))
nodes -= {'Obs_159', 'Obs_163'}
S = G.subgraph(nodes).copy()

PALETTE = {
    'Observation': '#4c78a8', 'Product': '#9ecae9', 'QualityClass': '#72b7b2', 'ToolLifeCycle': '#54a24b',
    'MillingMachine': '#1f3b57', 'FailureEvent': '#e45756', 'MechanicalFailureType': '#9d2f2f',
    'ProductionRule': '#b279a2', 'RiskForecast': '#ff9da6', 'Spindle': '#bab0ac', 'CuttingTool': '#bab0ac',
    'MaintenanceAction': '#f58518',
}
NAMES = {'Observation': 'Наблюдение', 'Product': 'Изделие', 'QualityClass': 'Класс качества',
         'ToolLifeCycle': 'Цикл инструмента', 'MillingMachine': 'Оборудование', 'FailureEvent': 'Событие отказа',
         'MechanicalFailureType': 'Тип отказа', 'ProductionRule': 'Правило', 'RiskForecast': 'Прогноз риска',
         'Spindle': 'Узел', 'CuttingTool': 'Узел', 'MaintenanceAction': 'Вид работ'}

# добавим знания о типах отказов: какие узлы поражает и что рекомендовано
for ft in [n for n in S if G.nodes[n]['cls'] == 'MechanicalFailureType']:
    for _, b, d in G.out_edges(ft, data=True):
        if d['type'] in ('affectsComponent', 'recommendsAction'):
            S.add_node(b, **G.nodes[b])
            S.add_edge(ft, b, **d)
print('Узлов во фрагменте:', S.number_of_nodes(), 'рёбер:', S.number_of_edges())

pos = nx.kamada_kawai_layout(nx.Graph(S))
fig, ax = plt.subplots(figsize=(15, 10.5))
colors = [PALETTE.get(S.nodes[n]['cls'], '#cccccc') for n in S]
nx.draw_networkx_edges(S, pos, ax=ax, edge_color='#888888', arrows=True, arrowsize=12,
                       width=1.0, node_size=1500, connectionstyle='arc3,rad=0.06')
nx.draw_networkx_nodes(S, pos, ax=ax, node_color=colors, node_size=1500, edgecolors='#333333', linewidths=0.8)
labels = {n: n.replace('Product_', 'P_').replace('_', '\n', 1) if len(n) > 9 else n for n in S}
light = {'MillingMachine', 'MechanicalFailureType', 'Observation', 'ProductionRule'}
for n, (x, y) in pos.items():
    ax.text(x, y, labels[n], ha='center', va='center', fontsize=7.5,
            color='white' if S.nodes[n]['cls'] in light else 'black', weight='bold')
elabels = {(a, b): d['type'] for a, b, d in S.edges(data=True)}
nx.draw_networkx_edge_labels(S, pos, edge_labels=elabels, ax=ax, font_size=6.5, font_color='#444444',
                             bbox=dict(boxstyle='round,pad=0.1', fc='white', ec='none', alpha=0.8))
seen = {}
for n in S:
    c = S.nodes[n]['cls']
    seen.setdefault(NAMES.get(c, c), PALETTE.get(c, '#cccccc'))
ax.legend(handles=[Line2D([0], [0], marker='o', color='w', markerfacecolor=col, markeredgecolor='#333333',
                          markersize=12, label=name) for name, col in seen.items()],
          loc='lower left', fontsize=9, frameon=True, title='Типы узлов', title_fontsize=9)
ax.set_title('Фрагмент графа знаний: отказы по перегрузке (OSF) в цикле инструмента № 2', fontsize=12)
ax.axis('off')
plt.tight_layout()
plt.savefig(HERE / 'img' / 'subgraph.png', dpi=170)
print('Сохранено img/subgraph.png')

# --- Схема графа: типы узлов и рёбер с количествами (Graphviz) ------------------------------
import subprocess  # noqa: E402
from collections import Counter  # noqa: E402

GROUP = {'Spindle': 'Component', 'Drive': 'Component', 'CoolingSystem': 'Component', 'CuttingTool': 'Component',
         'TemperatureSensor': 'Sensor', 'SpeedSensor': 'Sensor', 'TorqueSensor': 'Sensor', 'WearCounter': 'Sensor',
         'MechanicalFailureType': 'FailureType', 'ThermalFailureType': 'FailureType',
         'ElectricalFailureType': 'FailureType', 'RandomFailureType': 'FailureType',
         'MillingMachine': 'Equipment'}
COL = {'Observation': '#4c78a8', 'Product': '#9ecae9', 'QualityClass': '#72b7b2', 'ToolLifeCycle': '#54a24b',
       'Equipment': '#1f3b57', 'FailureEvent': '#e45756', 'FailureType': '#9d2f2f', 'ProductionRule': '#b279a2',
       'RiskForecast': '#ff9da6', 'Component': '#bab0ac', 'Sensor': '#d8d0cc', 'MonitoredParameter': '#eeca3b',
       'MaintenanceAction': '#f58518'}
DARK = {'Observation', 'Equipment', 'FailureType', 'ProductionRule', 'FailureEvent', 'ToolLifeCycle'}
cls = {n: GROUP.get(d['cls'], d['cls']) for n, d in G.nodes(data=True)}
ncount = Counter(cls.values())
ecount = Counter((cls[a], d['type'], cls[b]) for a, b, d in G.edges(data=True))
lines = ['digraph schema { rankdir=LR; nodesep=0.35; ranksep=1.1;',
         'node [shape=ellipse, style=filled, fontname="DejaVu Sans", fontsize=11];',
         'edge [fontname="DejaVu Sans", fontsize=9, color="#555555"];']
def fmt(n):
    return f'{n:,}'.replace(',', ' ')


for c, n in ncount.items():
    fc = 'white' if c in DARK else 'black'
    lines.append(f'{c} [label="{c}\\n{fmt(n)}", fillcolor="{COL.get(c, "#cccccc")}", fontcolor="{fc}"];')
for (a, p, b), n in sorted(ecount.items()):
    if p == 'occurredDuring':                 # обратное к hasFailureEvent
        continue
    lines.append(f'{a} -> {b} [label="{p}\\n{fmt(n)}"];')
lines.append('}')
dot = '\n'.join(lines)
subprocess.run(['dot', '-Tpng', '-Gdpi=160', '-o', str(HERE / 'img' / 'schema.png')], input=dot.encode(), check=True)
print('Сохранено img/schema.png')
