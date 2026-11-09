"""Семантическая сеть циклов инструмента из всех строк PostgreSQL; python network.py."""
from collections import Counter
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import networkx as nx
import pandas as pd
from sqlalchemy import text

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'tools'))
from pdm_data import engine, save_json, fingerprint

NODE_SOURCES = {
    'Станок': 'dim_equipment', 'Цикл': 'dim_tool',
    'Класс': 'dim_quality_class', 'Отказ': 'dim_failure_type (кроме NONE)',
    'Работа': 'dim_failure_type.recommended_action (уникальные непустые)',
}
EDGE_SOURCES = {
    'HAS-CYCLE': 'fact_observation: DISTINCT equipment_key, tool_key',
    'PROCESSES': 'fact_observation: GROUP BY tool_key, class_key; count(*)',
    'HAS-FAILURE': 'fact_failure_event: GROUP BY tool_key, failure_type_key; count(*)',
    'RECOMMENDS': 'dim_failure_type.recommended_action',
}


def build():
    db = engine()
    with db.connect() as c:
        # Один согласованный снимок: агрегаты не могут относиться к разным загрузкам.
        c.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
        tables = {name: pd.read_sql(text(f'SELECT * FROM dwh.{name} ORDER BY 1'), c)
                  for name in ['dim_equipment', 'dim_tool', 'dim_quality_class',
                               'dim_failure_type', 'fact_observation', 'fact_failure_event']}
    db.dispose()
    g = nx.DiGraph()
    attrs = {}
    def node(key, kind, name, **kw):
        g.add_node(key)
        attrs[key] = dict(node_type=kind, name=name, **kw)
    for r in tables['dim_equipment'].itertuples():
        node(f'E{r.equipment_key}', 'Станок', r.inventory_no)
    for r in tables['dim_tool'].itertuples():
        node(f'C{r.tool_key}', 'Цикл', f'Цикл {r.tool_cycle_no}',
             products=int(r.products_processed), end_reason=r.end_reason)
    for r in tables['dim_quality_class'].itertuples():
        node(f'Q{r.class_key}', 'Класс', r.class_code, osf_limit=int(r.osf_limit))
    actions = {}
    for r in tables['dim_failure_type'].itertuples():
        if r.failure_code == 'NONE':
            continue
        node(f'F{r.failure_type_key}', 'Отказ', r.failure_code,
             description=r.failure_name)
        if pd.notna(r.recommended_action):
            action = actions.setdefault(r.recommended_action, f'A{len(actions)+1}')
            node(action, 'Работа', r.recommended_action)
            g.add_edge(f'F{r.failure_type_key}', action, edge_type='RECOMMENDS', count=1)
    obs, events = tables['fact_observation'], tables['fact_failure_event']
    for (e, t), n in obs.groupby(['equipment_key', 'tool_key']).size().items():
        g.add_edge(f'E{e}', f'C{t}', edge_type='HAS-CYCLE', count=int(n))
    for (t, q), n in obs.groupby(['tool_key', 'class_key']).size().items():
        g.add_edge(f'C{t}', f'Q{q}', edge_type='PROCESSES', count=int(n))
    for (t, f), n in events.groupby(['tool_key', 'failure_type_key']).size().items():
        g.add_edge(f'C{t}', f'F{f}', edge_type='HAS-FAILURE', count=int(n))
    nx.set_node_attributes(g, attrs)
    assert sum(d['count'] for _, _, d in g.edges(data=True)
               if d['edge_type'] == 'PROCESSES') == len(obs)
    assert sum(d['count'] for _, _, d in g.edges(data=True)
               if d['edge_type'] == 'HAS-FAILURE') == len(events)
    return g, {'observations': len(obs), 'failure_events': len(events),
               'observation_sha256': fingerprint(obs),
               'event_sha256': fingerprint(events)}


def analyze(g):
    # Отношения направлены по смыслу; расстояния и сообщества — в слабой,
    # простой невзвешенной проекции. count — частота, а не расстояние.
    u = g.to_undirected()
    components = sorted(nx.connected_components(u), key=len, reverse=True)
    largest = u.subgraph(components[0])
    stats = {'nodes': len(g), 'edges': g.number_of_edges(), 'density_directed': nx.density(g),
             'weak_components': len(components),
             'strong_components': nx.number_strongly_connected_components(g),
             'diameter_largest_undirected': nx.diameter(largest),
             'mean_total_degree': sum(dict(g.degree()).values()) / len(g),
             'max_degree_node': max(g, key=lambda n: (g.degree(n), n)),
             'max_degree': max(dict(g.degree()).values()),
             'clustering_undirected': nx.average_clustering(u)}
    metrics = {'degree': nx.degree_centrality(u),
               'betweenness': nx.betweenness_centrality(u),
               'closeness': nx.closeness_centrality(u),
               'pagerank': nx.pagerank(g, weight=None, tol=1e-12)}
    tops = {k: [[n, g.nodes[n]['name'], float(v)] for n, v in
                sorted(values.items(), key=lambda x: (-x[1], x[0]))[:5]]
            for k, values in metrics.items()}
    communities = sorted(nx.community.louvain_communities(u, seed=10, weight=None),
                         key=lambda s: (-len(s), sorted(s)))
    modularity = nx.community.modularity(u, communities, weight=None)
    groups = []
    for i, nodes in enumerate(communities, 1):
        types = Counter(g.nodes[n]['node_type'] for n in sorted(nodes))
        failures = sorted(g.nodes[n]['name'] for n in nodes
                          if g.nodes[n]['node_type'] == 'Отказ')
        names = sorted(g.nodes[n]['name'] for n in nodes if g.nodes[n]['node_type'] == 'Класс')
        interpretation = ('Циклы и связанные типы отказов: ' + ', '.join(failures) if failures
                          else 'Производственные циклы и классы ' + ', '.join(names))
        groups.append({'id': i, 'size': len(nodes), 'types': dict(types),
                       'nodes': sorted(nodes), 'interpretation': interpretation})
    f = 'F2'  # HDF — ключ справочника из лабы 5
    path = nx.shortest_path(u, 'Q1', 'A2')
    ego = sorted(nx.ego_graph(u, f, radius=2).nodes())
    affected = sorted(g.predecessors(f))
    search = {'shortest': {'source': 'Q1', 'target': 'A2', 'path': path,
                          'names': [g.nodes[n]['name'] for n in path],
                          'edges': len(path)-1},
              'ego': {'center': f, 'radius': 2, 'count': len(ego), 'nodes': ego},
              'hdf_cycles': {'count': len(affected), 'nodes': affected,
                             'events': sum(g[n][f]['count'] for n in affected)}}
    return dict(statistics=stats, centrality=tops, communities=groups,
                modularity=modularity, searches=search)


def visualize(g, result):
    img = HERE / 'img'
    img.mkdir(exist_ok=True)
    # 40 узлов: всё понятийное ядро и наиболее связные циклы, без случайной выборки.
    core = {n for n, d in g.nodes(data=True) if d['node_type'] != 'Цикл'}
    ranked = sorted((n for n in g if n not in core), key=lambda n: (-g.degree(n), n))
    nodes = core | set(ranked[:40-len(core)])
    h = nx.DiGraph()
    h.add_nodes_from((n, g.nodes[n]) for n in sorted(nodes))
    h.add_edges_from((a,b,d) for a,b,d in sorted(g.subgraph(nodes).edges(data=True)))
    colors = dict(zip(NODE_SOURCES, ['#4c78a8', '#9ecae9', '#59a14f', '#e15759', '#f2b04c']))
    # Детерминированные слои: хабы не перекрываются, циклы не стягиваются в комок.
    pos = {}
    for kind,x in [('Станок',0),('Цикл',2.6),('Класс',5.2),('Отказ',8),('Работа',10.8)]:
        members = sorted(n for n in h if h.nodes[n]['node_type']==kind)
        for i,n in enumerate(members):
            pos[n] = (x,0 if len(members)==1 else 5-10*i/(len(members)-1))
    fig, ax = plt.subplots(figsize=(13, 8))
    nx.draw_networkx_edges(h, pos, ax=ax, alpha=.15, arrows=True, arrowsize=7)
    nx.draw_networkx_nodes(h, pos, ax=ax, node_color=[colors[g.nodes[n]['node_type']] for n in h],
                          node_size=[35 + 16*g.degree(n) for n in h], alpha=.95)
    top = sorted(h, key=lambda n: (-g.degree(n), n))[:10]
    nx.draw_networkx_labels(h, pos, ax=ax,
                           labels={n: g.nodes[n]['name'] for n in top}, font_size=9)
    ax.legend(handles=[Line2D([0], [0], marker='o', color='w', label=t,
                              markerfacecolor=c, markersize=9) for t, c in colors.items()],
              loc='lower center', ncol=5)
    ax.set_title('Семантическая сеть: 40 узлов; размеры — степень в полной сети')
    for kind,x in [('Станок',0),('Циклы',2.6),('Классы',5.2),('Отказы',8),('Работы',10.8)]:
        ax.text(x,6.0,kind,ha='center',fontsize=11,fontweight='bold')
    ax.set_ylim(-6.8,6.7)
    ax.set_xlim(-1.8,12.0)
    ax.axis('off')
    fig.tight_layout()
    fig.savefig(img / 'network.png', dpi=300)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.bar([str(x['id']) for x in result['communities']],
           [x['size'] for x in result['communities']], color='#4c78a8')
    ax.set(xlabel='Сообщество Louvain', ylabel='Число узлов',
           title=f"Сообщества в полной сети; модульность Q = {result['modularity']:.3f}")
    fig.tight_layout()
    fig.savefig(img / 'communities.png', dpi=300)
    plt.close(fig)
    result['visualization'] = {'nodes': len(h), 'labels': len(top), 'dpi': 300,
                               'selected_nodes': sorted(nodes)}


def main():
    g, source = build()
    result = analyze(g)
    result['source'] = source
    result['node_types'] = [{'type': t, 'count': n, 'source': NODE_SOURCES[t]}
                           for t, n in Counter(nx.get_node_attributes(g, 'node_type').values()).items()]
    result['edge_types'] = [{'type': t, 'count': n, 'source': EDGE_SOURCES[t]}
                           for t, n in Counter(nx.get_edge_attributes(g, 'edge_type').values()).items()]
    visualize(g, result)
    (HERE / 'results').mkdir(exist_ok=True)
    nx.write_graphml(g, HERE / 'results' / 'semantic_network.graphml')
    save_json(HERE / 'results' / 'analysis.json', result)
    print(result['statistics'])
    print('Louvain:', len(result['communities']), 'Q =', result['modularity'])
    print('Поиск:', result['searches']['shortest']['names'])


if __name__ == '__main__':
    main()
