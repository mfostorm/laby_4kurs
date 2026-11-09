"""Проверка источника, сохранения сети и аналитики; запуск: python test_network.py."""
from pathlib import Path
import json
import networkx as nx
from PIL import Image
from network import build, analyze

HERE=Path(__file__).resolve().parent


def main():
    g,source=build()
    saved=nx.read_graphml(HERE/'results'/'semantic_network.graphml')
    d=json.loads((HERE/'results'/'analysis.json').read_text(encoding='utf-8'))
    assert source==d['source']
    assert source['observations']==10000 and source['failure_events']==382
    assert set(g)==set(saved) and set(g.edges)==set(saved.edges)
    assert all(g.nodes[n]==saved.nodes[n] for n in g)
    assert all(g[a][b]==saved[a][b] for a,b in g.edges)
    actual=analyze(g)
    assert actual['statistics']==d['statistics']
    assert actual['centrality']==d['centrality']
    assert actual['searches']==d['searches']
    # Идентичность состава сообществ; порядок ключей в JSON не имеет значения.
    assert actual['communities']==d['communities']
    assert abs(actual['modularity']-d['modularity'])<1e-12
    nodes=set().union(*(set(c['nodes']) for c in d['communities']))
    assert nodes==set(g) and sum(c['size'] for c in d['communities'])==len(g)
    assert d['visualization']['nodes']==40 and d['visualization']['labels']==10
    with Image.open(HERE/'img'/'network.png') as image:
        assert all(abs(x-300)<1 for x in image.info['dpi'])
    print('OK: все строки БД, round-trip GraphML, точные метрики, 3 запроса, '
          'разбиение Louvain и PNG 300 dpi.')


if __name__=='__main__':
    main()
