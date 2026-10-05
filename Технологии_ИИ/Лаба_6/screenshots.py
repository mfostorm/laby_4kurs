"""Снимки экрана результатов проверочных запросов: выполняет команды в psql и
сохраняет их фактический вывод в виде изображения окна терминала (img/*.png)."""
import os
import subprocess

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

from load_dwh import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER, HERE

IMG = HERE / 'img'
IMG.mkdir(exist_ok=True)
ENV = dict(os.environ, PGPASSWORD=DB_PASSWORD)


def psql(sql):
    out = subprocess.run(['psql', '-h', DB_HOST, '-p', DB_PORT, '-U', DB_USER, '-d', DB_NAME,
                          '-X', '-e', '-c', sql] if '\n' not in sql else
                         ['psql', '-h', DB_HOST, '-p', DB_PORT, '-U', DB_USER, '-d', DB_NAME,
                          '-X', '-e'],
                         input=sql if '\n' in sql else None, env=ENV, capture_output=True,
                         text=True, check=True)
    return out.stdout.rstrip()


def render(text, name, title):
    lines = text.split('\n')
    width = max(len(s) for s in lines)
    w, h = max(6.0, 0.0705 * width + 0.6), 0.152 * len(lines) + 0.6
    fig = plt.figure(figsize=(w, h))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.axis('off')
    ax.add_patch(FancyBboxPatch((0.02, 0.02), w - 0.04, h - 0.04, boxstyle='round,pad=0,rounding_size=0.06',
                                fc='white', ec='0.55', lw=1))
    ax.add_patch(plt.Rectangle((0.02, h - 0.34), w - 0.04, 0.32, fc='0.88', ec='0.55', lw=1))
    for i, c in enumerate(['0.6', '0.7', '0.8']):
        ax.add_patch(plt.Circle((0.18 + 0.17 * i, h - 0.18), 0.05, fc=c, ec='0.5', lw=.5))
    ax.text(w / 2, h - 0.18, title, ha='center', va='center', fontsize=8, family='DejaVu Sans')
    ax.text(0.15, h - 0.45, text, ha='left', va='top', fontsize=7.6, family='DejaVu Sans Mono',
            linespacing=1.32)
    fig.savefig(IMG / name, dpi=200)
    plt.close(fig)


SHOTS = [
    ('01_tables.png', '\\dt+ dwh.*', 'Таблицы хранилища'),
    ('02_counts.png', """SELECT 'dim_equipment' AS table_name, count(*) FROM dwh.dim_equipment
UNION ALL SELECT 'dim_quality_class', count(*) FROM dwh.dim_quality_class
UNION ALL SELECT 'dim_tool', count(*) FROM dwh.dim_tool
UNION ALL SELECT 'dim_failure_type', count(*) FROM dwh.dim_failure_type
UNION ALL SELECT 'dim_batch', count(*) FROM dwh.dim_batch
UNION ALL SELECT 'fact_observation', count(*) FROM dwh.fact_observation
UNION ALL SELECT 'fact_failure_event', count(*) FROM dwh.fact_failure_event;
""", 'Количество записей'),
    ('03_orphans.png', """SELECT count(*) AS orphan_class FROM dwh.fact_observation f
LEFT JOIN dwh.dim_quality_class d ON f.class_key = d.class_key WHERE d.class_key IS NULL;
SELECT count(*) AS orphan_tool FROM dwh.fact_observation f
LEFT JOIN dwh.dim_tool d ON f.tool_key = d.tool_key WHERE d.tool_key IS NULL;
SELECT count(*) AS null_keys FROM dwh.fact_observation
WHERE udi IS NULL OR class_key IS NULL OR tool_key IS NULL OR failure_type_key IS NULL;
""", 'Висячие ссылки и NULL в ключах'),
    ('04_stats.png', """SELECT min(torque_nm) AS min_torque, max(torque_nm) AS max_torque,
       round(avg(torque_nm), 2) AS avg_torque, round(stddev(torque_nm), 2) AS stddev_torque,
       sum(machine_failure) AS failures
FROM dwh.fact_observation;
SELECT * FROM dwh.v_failure_rate_by_class;
""", 'Базовая статистика'),
    ('05_explain.png', """BEGIN;
DROP INDEX dwh.idx_obs_tool;
EXPLAIN ANALYZE SELECT * FROM dwh.fact_observation WHERE tool_key = 57;
ROLLBACK;
EXPLAIN ANALYZE SELECT * FROM dwh.fact_observation WHERE tool_key = 57;
""", 'EXPLAIN ANALYZE до и после индекса'),
]

if __name__ == '__main__':
    for name, sql, title in SHOTS:
        out = psql(sql)
        render(out, name, f'psql - {DB_NAME} - {title}')
        print(name, len(out.split(chr(10))), 'строк')
