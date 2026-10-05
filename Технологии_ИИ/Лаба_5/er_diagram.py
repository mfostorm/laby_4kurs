"""ER-диаграмма хранилища: строится по тексту sql/01_create_schema.sql (Graphviz).

Запуск: python er_diagram.py  ->  img/er_diagram.png
"""
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
DDL = (HERE / 'sql' / '01_create_schema.sql').read_text(encoding='utf-8')
(HERE / 'img').mkdir(exist_ok=True)


def parse(ddl):
    tables = {}
    for name, body in re.findall(r'CREATE TABLE (\w+) \((.*?)\n\);', ddl, re.S):
        cols = []
        for line in body.split('\n'):
            line = line.split('--')[0].strip().rstrip(',')
            m = re.match(r'([a-z_0-9]+)\s+([A-Z]+(?:\(\d+(?:,\d+)?\))?)', line)
            if not m or m.group(1) in ('check', 'unique'):
                continue
            col, typ = m.groups()
            ref = re.search(r'REFERENCES (\w+)', line)
            tags = []
            if 'PRIMARY KEY' in line:
                tags.append('PK')
            if ref:
                tags.append('FK')
            if 'UNIQUE' in line and 'PRIMARY' not in line:
                tags.append('UK')
            cols.append((col, typ.lower(), tags, ref.group(1) if ref else None))
        tables[name] = cols
    return tables


def label(name, cols):
    head = '#d9d9d9' if name.startswith('fact') else '#efefef'
    rows = [f'<tr><td bgcolor="{head}" colspan="3"><b>{name}</b></td></tr>']
    for col, typ, tags, _ in cols:
        t = ', '.join(tags)
        c = f'<b>{col}</b>' if 'PK' in tags else (f'<i>{col}</i>' if 'FK' in tags else col)
        rows.append(f'<tr><td align="left" port="{col}_w">{c}</td>'
                    f'<td align="left"><font color="#555555">{typ}</font></td>'
                    f'<td align="left" port="{col}_e">{t}</td></tr>')
    return ('<<table border="1" cellborder="0" cellspacing="0" cellpadding="3">'
            + ''.join(rows) + '</table>>')


T = parse(DDL)
lines = ['digraph er {', 'rankdir=LR; nodesep=0.35; ranksep=1.3; splines=true;',
         'node [shape=plaintext, fontname="DejaVu Sans", fontsize=10];',
         'edge [color="#333333", arrowhead=none, fontname="DejaVu Sans", fontsize=9];']
for name, cols in T.items():
    lines.append(f'{name} [label={label(name, cols)}];')
lines += ['{rank=same; dim_equipment; dim_quality_class; dim_tool; dim_failure_type; dim_batch}',
          '{rank=min; fact_observation}', '{rank=max; fact_failure_event}']
for name, cols in T.items():
    for col, _, tags, ref in cols:
        if not ref:
            continue
        target_col = 'udi' if ref == 'fact_observation' else col
        if name == 'fact_observation':
            # измерение (1) -> факт (М): «вилка» у факта
            lines.append(f'{name}:{col}_e:e -> {ref}:{target_col}_w:w '
                         '[dir=both, arrowtail=crow, arrowhead=tee];')
        else:
            lines.append(f'{ref}:{target_col}_e:e -> {name}:{col}_w:w '
                         '[dir=both, arrowtail=tee, arrowhead=crow];')
lines.append('}')
dot = '\n'.join(lines)
(HERE / 'img' / 'er_diagram.dot').write_text(dot, encoding='utf-8')
subprocess.run(['dot', '-Tpng', '-Gdpi=170', '-o', str(HERE / 'img' / 'er_diagram.png')],
               input=dot.encode(), check=True)
subprocess.run(['dot', '-Tsvg', '-o', str(HERE / 'img' / 'er_diagram.svg')],
               input=dot.encode(), check=True)
print({k: len(v) for k, v in T.items()})
