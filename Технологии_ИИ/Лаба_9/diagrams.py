"""Группы правил и схема стадий."""
import json
from pathlib import Path
import subprocess
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from collections import Counter

HERE=Path(__file__).resolve().parent
rules=json.loads((HERE/'rules.json').read_text(encoding='utf-8'))
img=HERE/'img'; img.mkdir(exist_ok=True)
counts=Counter(r['group'] for r in rules)
fig,ax=plt.subplots(figsize=(9,4))
ax.bar(list(counts),list(counts.values()),color=['#4c78a8','#59a14f','#f2b04c','#e15759'])
for i,n in enumerate(counts.values()):
    ax.text(i,n+.1,str(n),ha='center')
ax.set(ylabel='Число правил',ylim=(0,max(counts.values())+2))
fig.tight_layout(); fig.savefig(img/'groups.png',dpi=300); plt.close(fig)
dot='''digraph rules {
rankdir=TB; graph [bgcolor="white"]; node [shape=box,style="rounded,filled",fontname="DejaVu Sans",fillcolor="#eaf1f8"];
a [label="PostgreSQL: телеметрия + пороги\\nметки отказов исключены из входа"];
b [label="Стадия 1: симптомы R001–R008\\nPWF, OSF, HDF, зона TWF, профилактика"];
c [label="Стадия 2: риск R009–R016\\nприоритет → специфичность → ID"];
d [label="Стадия 3: действие R017–R024\\nсохраняется первое приоритетное значение"];
e [label="Результат + трасса + объяснение\\nпо умолчанию прогноз отказа = 0"];
a -> b -> c -> d -> e;
}'''
(img/'rule_flow.dot').write_text(dot,encoding='utf-8')
subprocess.run(['dot','-Tpng','-Gdpi=180',str(img/'rule_flow.dot'),'-o',str(img/'rule_flow.png')],check=True)
