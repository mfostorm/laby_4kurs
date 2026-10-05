"""Диаграммы ETL-процесса (лаба 3): общая схема и детальная схема слоя Transform.

Каждая диаграмма описывается один раз (блоки и связи в условных единицах) и
выводится в два формата: PNG для отчёта и .drawio - для редактирования в draw.io
(app.diagrams.net). Запуск: python diagrams.py
"""
from pathlib import Path
from xml.sax.saxutils import escape

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

HERE = Path(__file__).resolve().parent
IMG = HERE / 'img'
IMG.mkdir(exist_ok=True)
PX = 40  # условная единица -> пиксели draw.io

STYLE = {  # заливка, рамка, пунктир, скругление
    'src':   ('#ffffff', '#222222', False, True),
    'ext':   ('#e6e6e6', '#222222', False, True),
    'stg':   ('#f2f2f2', '#222222', False, True),
    'tr':    ('#d9d9d9', '#222222', False, True),
    'tgt':   ('#ffffff', '#222222', False, False),
    'note':  ('#ffffff', '#777777', True, False),
    'group': ('none', '#555555', True, True),
    'plan':  ('#ffffff', '#888888', True, True),
}


class Diagram:
    def __init__(self, name, w, h):
        self.name, self.w, self.h = name, w, h
        self.boxes, self.edges, self.labels = {}, [], []

    def box(self, key, x, y, w, h, text, style='tr', size=8.5, bold_first=False):
        self.boxes[key] = dict(x=x, y=y, w=w, h=h, text=text, style=style, size=size, bold=bold_first)

    def edge(self, a, b, dashed=False, label='', sides=None):
        self.edges.append((a, b, dashed, label, sides))

    def label(self, x, y, text, size=10, bold=True, italic=False):
        self.labels.append((x, y, text, size, bold, italic))

    # --- точки привязки -------------------------------------------------------
    def _port(self, b, side):
        x, y, w, h = b['x'], b['y'], b['w'], b['h']
        return {'r': (x + w, y + h / 2), 'l': (x, y + h / 2),
                'b': (x + w / 2, y + h), 't': (x + w / 2, y)}[side]

    def _auto_sides(self, a, b):
        ax, ay = a['x'] + a['w'] / 2, a['y'] + a['h'] / 2
        bx, by = b['x'] + b['w'] / 2, b['y'] + b['h'] / 2
        if abs(bx - ax) > abs(by - ay):
            return ('r', 'l') if bx > ax else ('l', 'r')
        return ('b', 't') if by > ay else ('t', 'b')

    # --- PNG ------------------------------------------------------------------
    def png(self, path, scale=0.62):
        fig = plt.figure(figsize=(self.w * scale, self.h * scale))
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(0, self.w)
        ax.set_ylim(self.h, 0)
        ax.axis('off')
        order = sorted(self.boxes.values(), key=lambda b: b['style'] != 'group')
        for b in order:
            fc, ec, dashed, rounded = STYLE[b['style']]
            bs = 'round,pad=0,rounding_size=0.18' if rounded else 'square,pad=0'
            ax.add_patch(FancyBboxPatch((b['x'], b['y']), b['w'], b['h'], boxstyle=bs,
                                        fc=fc, ec=ec, lw=1.0, ls='--' if dashed else '-',
                                        zorder=1 if b['style'] == 'group' else 2))
            if b['style'] == 'group':
                ax.text(b['x'] + b['w'] / 2, b['y'] + 0.22, b['text'], ha='center', va='top',
                        fontsize=b['size'], style='italic', color='#333333', zorder=3)
                continue
            lines = b['text'].split('\n')
            if b['bold']:
                ax.text(b['x'] + b['w'] / 2, b['y'] + b['h'] / 2, lines[0] + '\n' * len(lines[1:]),
                        ha='center', va='center', fontsize=b['size'], weight='bold', zorder=3,
                        linespacing=1.25)
                ax.text(b['x'] + b['w'] / 2, b['y'] + b['h'] / 2, '\n' + '\n'.join(lines[1:]),
                        ha='center', va='center', fontsize=b['size'] - 1, color='#333333',
                        zorder=3, linespacing=1.25)
            else:
                ha = 'left' if b['style'] == 'note' else 'center'
                x = b['x'] + 0.12 if ha == 'left' else b['x'] + b['w'] / 2
                ax.text(x, b['y'] + b['h'] / 2, b['text'], ha=ha, va='center',
                        fontsize=b['size'], zorder=3, linespacing=1.25)
        for a, b, dashed, lab, sides in self.edges:
            A, B = self.boxes[a], self.boxes[b]
            sa, sb = sides or self._auto_sides(A, B)
            p, q = self._port(A, sa), self._port(B, sb)
            if sa in 'rl' and sb in 'rl' and abs(p[1] - q[1]) > 0.05:
                mx = (p[0] + q[0]) / 2
                pts = [p, (mx, p[1]), (mx, q[1]), q]
            elif sa in 'bt' and sb in 'bt' and abs(p[0] - q[0]) > 0.05:
                my = (p[1] + q[1]) / 2
                pts = [p, (p[0], my), (q[0], my), q]
            elif sa in 'rl' and sb in 'bt':
                pts = [p, (q[0], p[1]), q]
            elif sa in 'bt' and sb in 'rl':
                pts = [p, (p[0], q[1]), q]
            else:
                pts = [p, q]
            xs, ys = zip(*pts)
            ax.plot(xs[:-1] + (xs[-1],), ys[:-1] + (ys[-1],), color='#333333', lw=1.0,
                    ls='--' if dashed else '-', zorder=1.5)
            ax.annotate('', q, pts[-2], arrowprops=dict(arrowstyle='-|>', color='#333333', lw=1.0,
                                                        shrinkA=0, shrinkB=0), zorder=1.6)
            if lab:
                vertical = abs(pts[-2][0] - q[0]) < 0.05
                lx = q[0] + 0.12 if vertical else (pts[-2][0] + q[0]) / 2
                ly = (pts[-2][1] + q[1]) / 2 if vertical else q[1] - 0.12
                ax.text(lx, ly, lab, ha='left' if vertical else 'center',
                        va='center' if vertical else 'bottom', fontsize=7.5, color='#333333')
        for x, y, t, s, bold, it in self.labels:
            ax.text(x, y, t, ha='center', va='center', fontsize=s,
                    weight='bold' if bold else 'normal', style='italic' if it else 'normal')
        fig.savefig(path, dpi=200)
        plt.close(fig)

    # --- draw.io --------------------------------------------------------------
    def drawio_page(self, page_id):
        cells = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>']
        n = 2
        ids = {}
        for k, b in sorted(self.boxes.items(), key=lambda kv: kv[1]['style'] != 'group'):
            fc, ec, dashed, rounded = STYLE[b['style']]
            style = (f'rounded={int(rounded)};whiteSpace=wrap;html=1;fillColor={fc};strokeColor={ec};'
                     f'dashed={int(dashed)};fontSize={int(b["size"] + 3)};')
            if b['style'] == 'group':
                style += 'verticalAlign=top;fontStyle=2;container=0;'
            if b['style'] == 'note':
                style += 'align=left;spacingLeft=6;'
            text = escape(b['text']).replace('\n', '<br>')
            if b['bold']:
                first, _, rest = text.partition('<br>')
                text = f'<b>{first}</b><br>{rest}'
            ids[k] = n
            cells.append(f'<mxCell id="{n}" value="{escape(text, {chr(34): "&quot;"})}" '
                         f'style="{style}" vertex="1" parent="1"><mxGeometry x="{b["x"] * PX:.0f}" '
                         f'y="{b["y"] * PX:.0f}" width="{b["w"] * PX:.0f}" height="{b["h"] * PX:.0f}" '
                         f'as="geometry"/></mxCell>')
            n += 1
        for a, b, dashed, lab, _ in self.edges:
            style = (f'edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;endArrow=block;endFill=1;'
                     f'dashed={int(dashed)};strokeColor=#333333;')
            cells.append(f'<mxCell id="{n}" value="{escape(lab)}" style="{style}" edge="1" parent="1" '
                         f'source="{ids[a]}" target="{ids[b]}"><mxGeometry relative="1" as="geometry"/>'
                         f'</mxCell>')
            n += 1
        for x, y, t, s, bold, it in self.labels:
            st = f'text;html=1;align=center;verticalAlign=middle;fontSize={s + 3};fontStyle={1 if bold else 2 if it else 0};'
            cells.append(f'<mxCell id="{n}" value="{escape(t)}" style="{st}" vertex="1" parent="1">'
                         f'<mxGeometry x="{(x - 2) * PX:.0f}" y="{(y - 0.3) * PX:.0f}" width="{4 * PX}" '
                         f'height="{0.6 * PX:.0f}" as="geometry"/></mxCell>')
            n += 1
        return (f'<diagram id="{page_id}" name="{escape(self.name)}"><mxGraphModel dx="1200" dy="800" '
                f'grid="1" gridSize="10" page="1" pageWidth="{self.w * PX:.0f}" pageHeight="{self.h * PX:.0f}">'
                f'<root>{"".join(cells)}</root></mxGraphModel></diagram>')


# =============================================================================
# 1. Общая схема ETL-процесса
# =============================================================================
ov = Diagram('Общая схема ETL', 24, 15.2)
for x, t in [(2.3, 'Источники'), (6.9, 'Extract'), (12.0, 'Staging + Transform'), (19.6, 'Load -> Target')]:
    ov.label(x, 0.45, t, size=10)
ov.box('s1', 0.4, 1.3, 3.8, 1.4, 'AI4I 2020 (UCI, id 601)\nZIP-архив с CSV\n10 000 x 14, CC BY 4.0', 'src', bold_first=True)
ov.box('s2', 0.4, 3.4, 3.8, 1.4, 'Справочные данные\nдокументация AI4I,\nбаза правил (лаба 1)', 'src', bold_first=True)
ov.box('s3', 0.4, 5.5, 3.8, 1.4, 'SCADA / CMMS\nтелеметрия и отказы\n(перспектива)', 'plan', bold_first=True)
ov.box('e1', 5.0, 1.3, 3.8, 1.4, 'HTTP GET + unzip\nread_csv(utf-8-sig)\nпроверка схемы, MD5', 'ext', bold_first=True)
ov.box('e2', 5.0, 3.4, 3.8, 1.4, 'Конфигурация\nпороги, диапазоны,\nприоритеты подтипов', 'ext', bold_first=True)
ov.box('e3', 5.0, 5.5, 3.8, 1.4, 'Инкрементная выгрузка\nпо отметке времени\n(перспектива)', 'plan', bold_first=True)
ov.box('gs', 9.7, 0.85, 4.6, 6.45, 'Staging area', 'group', size=9)
ov.box('st1', 10.1, 1.3, 3.8, 1.4, 'stg_raw\nai4i2020.csv - неизменяемая\nкопия источника + MD5', 'stg', bold_first=True)
ov.box('st2', 10.1, 3.4, 3.8, 1.4, 'stg_reference\nконстанты конвейера\n(etl.py)', 'stg', bold_first=True)
ov.box('st3', 10.1, 5.5, 3.8, 1.4, 'stg_increment\nновые партии\n(перспектива)', 'plan', bold_first=True)
ov.box('t1', 10.1, 7.9, 3.8, 1.2, 'Нормализация и типы\nT1-T3: имена, текст, типы', 'tr', bold_first=True)
ov.box('t2', 10.1, 9.6, 3.8, 1.5, 'Очистка\nT4-T7: диапазоны, дубликаты,\nпропуски, флаги выбросов', 'tr', bold_first=True)
ov.box('t3', 10.1, 11.6, 3.8, 1.2, 'Разметка и обогащение\nT8-T9: метки, признаки', 'tr', bold_first=True)
ov.box('v', 10.1, 13.3, 3.8, 1.0, 'Валидация\n8 утверждений', 'ext', bold_first=True)
ov.box('gl', 15.5, 0.85, 8.1, 3.6, 'Промежуточное хранилище (лаба 4)', 'group', size=9)
ov.box('l1', 15.9, 1.4, 3.6, 1.2, 'data_cleaned\n.csv + .parquet', 'tgt', bold_first=True)
ov.box('l2', 19.8, 1.4, 3.5, 1.2, 'quality_report.csv\netl_log.csv', 'tgt', bold_first=True)
ov.box('l3', 19.8, 2.95, 3.5, 1.2, 'etl_stats.json\nметрики, MD5', 'tgt', bold_first=True)
ov.box('gd', 15.5, 5.0, 8.1, 9.3, 'PostgreSQL, схема dwh (лабы 5-6)', 'group', size=9)
for i, (k, t) in enumerate([('d1', 'fact_observation\nнаблюдения, 10 000'),
                            ('d2', 'fact_failure_event\nсобытия отказа'),
                            ('d3', 'dim_quality_class\nкласс (фрейм-прототип)'),
                            ('d4', 'dim_equipment\nоборудование, пороги'),
                            ('d5', 'dim_tool\nциклы инструмента'),
                            ('d6', 'dim_failure_type\nтипы отказа, правила'),
                            ('d7', 'dim_batch\nпартии загрузки')]):
    col, row = (0, i) if i < 4 else (1, i - 4)
    ov.box(k, 15.9 + col * 3.9, 5.6 + row * 2.1, 3.6, 1.5, t, 'tgt', bold_first=True)
ov.box('sch', 0.4, 14.55, 23.2, 0.55,
       'Запуск: по требованию (прототип); в эксплуатации - по таймеру опроса датчиков (БП-1). '
       'Ошибка валидации или загрузки -> откат транзакции, запись в журнал, уведомление', 'note', size=8)
for a, b in [('s1', 'e1'), ('e1', 'st1'), ('s2', 'e2'), ('e2', 'st2')]:
    ov.edge(a, b)
for a, b in [('s3', 'e3'), ('e3', 'st3')]:
    ov.edge(a, b, dashed=True)
ov.edge('gs', 't1', sides=('b', 't'))
ov.edge('t1', 't2')
ov.edge('t2', 't3')
ov.edge('t3', 'v')
ov.edge('v', 'l1', label='to_csv / to_parquet', sides=('r', 'l'))
ov.edge('l1', 'd1', label='COPY', sides=('b', 't'))
ov.png(IMG / 'etl_overview.png')

# =============================================================================
# 2. Детальная схема слоя Transform
# =============================================================================
tr = Diagram('Детальная схема Transform', 20, 18.6)
tr.box('gs', 0.3, 0.4, 4.0, 3.3, 'Staging area', 'group', size=9)
tr.box('raw', 0.6, 0.95, 3.4, 1.0, 'stg_raw\n10 000 x 14', 'stg', bold_first=True)
tr.box('ref', 0.6, 2.25, 3.4, 1.0, 'stg_reference\nпороги, диапазоны', 'stg', bold_first=True)
steps = [
    ('T1', 'T1. Переименование', 'rename -> snake_case', '14 полей: "Air temperature [K]" -> air_temp_k'),
    ('T2', 'T2. Нормализация текста', 'strip, upper', '" m14860 " -> "M14860"; пустой Type -> буква Product ID'),
    ('T3', 'T3. Приведение типов', 'to_numeric, Categorical', 'нечисловое -> NaN; Type -> категория L < M < H'),
    ('T4', 'T4. Допустимые диапазоны', 'between -> NaN', 'T воздуха 273-343 K: 27 K -> NaN; Tпроц >= Tвозд'),
    ('T5', 'T5. Дубликаты', 'drop_duplicates', 'полные, затем по UDI; по EDA ожидается 0'),
    ('T6', 'T6. Пропуски', 'interpolate, P/ω, шаг, медиана', 'T - интерполяция; M = P/ω; износ + 2/3/5; n - медиана'),
    ('T7', 'T7. Выбросы', 'флаги IQR, не удалять', 'is_outlier_speed (418), is_outlier_torque (69)'),
    ('T8', 'T8. Дефекты разметки', 'флаги, failure_mode', 'UNKNOWN (9); приоритет PWF>OSF>HDF>TWF; RNF -> rnf_ref'),
    ('T9', 'T9. Производные признаки', 'формулы правил', 'temp_diff, power, margins, tool_cycle_id, cycle_pos'),
    ('V', 'Валидация', '8 утверждений', 'нет пропусков, ключи уникальны, диапазоны, метки 0/1 ...'),
]
y0 = 0.6
for i, (k, title, sub, note) in enumerate(steps):
    y = y0 + i * 1.62
    tr.box(k, 5.3, y, 4.6, 1.15, f'{title}\n{sub}', 'ext' if k == 'V' else 'tr', bold_first=True)
    tr.box('n' + k, 10.9, y + 0.12, 8.7, 0.9, note, 'note', size=8)
    tr.edge(k, 'n' + k, dashed=True)
    if i:
        tr.edge(steps[i - 1][0], k)
tr.edge('raw', 'T1', sides=('r', 'l'))
tr.edge('ref', 'T4', dashed=True, sides=('b', 'l'))
tr.box('out', 5.3, y0 + 10 * 1.62 + 0.2, 4.6, 1.0, 'Load\n10 000 x 28 -> CSV, Parquet', 'tgt', bold_first=True)
tr.edge('V', 'out')
tr.png(IMG / 'etl_transform.png')

(HERE / 'etl_pipeline.drawio').write_text(
    '<mxfile host="app.diagrams.net">' + ov.drawio_page('overview') + tr.drawio_page('transform')
    + '</mxfile>', encoding='utf-8')
print('Диаграммы: img/etl_overview.png, img/etl_transform.png, etl_pipeline.drawio')
