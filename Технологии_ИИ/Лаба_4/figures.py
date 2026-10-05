"""Рисунки к отчёту по лабе 4 (оформление как в лабе 2: оттенки серого)."""
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import etl

IMG = etl.HERE / 'img'
IMG.mkdir(exist_ok=True)
plt.rcParams.update({'font.size': 9, 'axes.grid': True, 'grid.alpha': .35,
                     'font.family': 'DejaVu Sans'})
TITLES = {'air_temp_k': 'Температура воздуха, K', 'process_temp_k': 'Температура процесса, K',
          'rot_speed_rpm': 'Частота вращения, об/мин', 'torque_nm': 'Крутящий момент, Н·м',
          'tool_wear_min': 'Износ инструмента, мин'}
RAW_COL = {v: k for k, v in etl.RENAME.items()}

raw, df, _, _ = etl.run(save=False)

# --- 1. Схема конвейера ------------------------------------------------------
from matplotlib.patches import FancyBboxPatch  # noqa: E402

def box(a, x, y, text, fc='0.93', w=1.7, h=.62, style='round,pad=0.02,rounding_size=0.12'):
    a.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle=style,
                               fc=fc, ec='black', lw=1))
    a.text(x, y, text, ha='center', va='center', fontsize=8.5)

def arrow(a, p, q):
    a.annotate('', q, p, arrowprops=dict(arrowstyle='-|>', color='0.25', lw=1.1,
                                         shrinkA=0, shrinkB=0))

fig, a = plt.subplots(figsize=(10.5, 4.2))
a.set_xlim(-.3, 11.3); a.set_ylim(-.6, 4.1); a.axis('off')
xs = [.75 + 2.4 * i for i in range(5)]
rows = {3.4: ['ai4i2020.csv\n(UCI, id 601)', 'E. Чтение CSV,\nпроверка схемы',
              'T1. Переименование\nв snake_case', 'T2. Нормализация\nтекстовых полей',
              'T3. Приведение\nтипов'],
        1.9: ['T8. Дефекты\nразметки', 'T7. Выбросы:\nфлаги IQR', 'T6. Пропуски',
              'T5. Дубликаты', 'T4. Допустимые\nдиапазоны'],
        .4: ['T9. Производные\nпризнаки', 'Валидация:\n8 утверждений',
             'L. data_cleaned\n.csv / .parquet', 'L. quality_report\netl_log, stats', '']}
for y, labels in rows.items():
    for x, t in zip(xs, labels):
        if t:
            fc = 'white' if t.startswith(('ai4i', 'L.', 'Вал')) else '0.9'
            box(a, x, y, t, fc=fc)
for i in range(4):
    arrow(a, (xs[i] + .85, 3.4), (xs[i + 1] - .85, 3.4))
    arrow(a, (xs[i + 1] - .85, 1.9), (xs[i] + .85, 1.9))
arrow(a, (xs[4], 3.4 - .31), (xs[4], 1.9 + .31))
arrow(a, (xs[0], 1.9 - .31), (xs[0], .4 + .31))
arrow(a, (xs[0] + .85, .4), (xs[1] - .85, .4))
arrow(a, (xs[1] + .85, .4), (xs[2] - .85, .4))
arrow(a, (xs[2] + .85, .4), (xs[3] - .85, .4))
a.annotate('', (xs[1], -.45), (xs[1], .4 - .31),
           arrowprops=dict(arrowstyle='-|>', color='0.25', lw=1.1, ls='--'))
a.text(xs[1] + .1, -.42, 'нарушение -> останов с ошибкой', fontsize=8, va='center')
a.text(xs[1] + .9, .52, 'да', fontsize=8)
for y, name in [(3.95, 'Extract / Transform'), (2.45, 'Transform (очистка)'), (.95, 'Transform / Validate / Load')]:
    a.text(-.25, y, name, fontsize=8.5, style='italic', color='0.3')
plt.tight_layout()
plt.savefig(IMG / 'etl_pipeline.png', dpi=200)
plt.close()

# --- 2-3. Данные с внесёнными дефектами: до и после очистки -------------------
# воспроизводим тот же набор дефектов, что в test_robustness.py
import test_robustness as tr  # noqa: E402  (запускает тест и печатает результат)
bad, cleaned, ref = tr.bad, tr.df, tr.ref

fig, ax = plt.subplots(1, 5, figsize=(12, 3.8))
for i, c in enumerate(etl.SENSORS):
    before = pd.to_numeric(bad[RAW_COL[c]], errors='coerce').dropna()
    bp = ax[i].boxplot([before, cleaned[c]], widths=.55, patch_artist=True,
                       flierprops={'markersize': 2.5}, medianprops={'color': 'black'})
    for b in bp['boxes']:
        b.set_facecolor('0.85')
    ax[i].set_xticks([1, 2], ['до', 'после'])
    ax[i].set_title(TITLES[c].split(',')[0], fontsize=9)
plt.tight_layout()
plt.savefig(IMG / 'box_before_after.png', dpi=200)
plt.close()

fig, ax = plt.subplots(2, 3, figsize=(12, 6))
for i, c in enumerate(etl.SENSORS):
    a = ax[i // 3][i % 3]
    bins = np.histogram_bin_edges(ref[c], 40)
    a.hist(ref[c], bins=bins, color='0.75', edgecolor='black', linewidth=.3, label='исходные данные')
    a.hist(cleaned[c], bins=bins, histtype='step', color='black', linewidth=1.2,
           label='после внесения дефектов и очистки')
    a.set_title(TITLES[c])
    a.set_ylabel('Частота')
ax[0][0].legend(fontsize=7)
# шестая панель - доля восстановленных значений
a = ax[1][2]
e = tr.errors
names = [TITLES[c].split(',')[0].replace('Температура', 'Т.') for c in etl.SENSORS]
rel = [100 * e[c]['mae'] / e[c]['std_ref'] for c in etl.SENSORS]
a.barh(names, rel, color='0.6', edgecolor='black')
a.set_xlabel('Ошибка восстановления, % от СКО признака')
a.invert_yaxis()
a.set_title('Точность заполнения пропусков')
plt.tight_layout()
plt.savefig(IMG / 'hist_before_after.png', dpi=200)
plt.close()

# --- 4. Сравнение стратегий заполнения ---------------------------------------
st = pd.DataFrame(tr.strategies, columns=['field', 'strategy', 'mae'])
st['rel'] = st.apply(lambda r: 100 * r.mae / ref[r.field].std(), axis=1)
order = ['Среднее', 'Медиана', 'Медиана по классу', 'Интерполяция', 'По связи признаков',
         'Шаг износа по классу']
hatches = ['', '//', '..', 'xx', '\\\\', 'oo']
fig, a = plt.subplots(figsize=(11, 3.8))
w = .14
for j, s in enumerate(order):
    for i, c in enumerate(etl.SENSORS):
        v = st[(st.field == c) & (st.strategy == s)]['rel']
        if len(v):
            a.bar(i + (j - 2.5) * w, v.iloc[0], w, color=str(.3 + .11 * j), edgecolor='black',
                  hatch=hatches[j], label=s if i == 0 or (s == 'Шаг износа по классу') else None)
a.set_xticks(range(5), [TITLES[c] for c in etl.SENSORS], fontsize=8)
a.set_ylabel('MAE, % от СКО признака')
h, l = a.get_legend_handles_labels()
uniq = dict(zip(l, h))
a.legend(uniq.values(), uniq.keys(), fontsize=7, ncol=3)
plt.tight_layout()
plt.savefig(IMG / 'strategies.png', dpi=200)
plt.close()

# --- 5. Производные признаки --------------------------------------------------
ok, fail = df[df.machine_failure == 0], df[df.machine_failure == 1]
fig, ax = plt.subplots(1, 3, figsize=(12, 3.6))
for a, c, title, lines in [
    (ax[0], 'temp_diff_k', 'Разность температур, K', [8.6]),
    (ax[1], 'power_w', 'Мощность привода, Вт', [etl.POWER_MIN, etl.POWER_MAX]),
    (ax[2], 'osf_margin', 'Запас до порога перегрузки, мин·Н·м', [0])]:
    bins = np.histogram_bin_edges(df[c], 40)
    a.hist(ok[c], bins=bins, density=True, color='0.8', edgecolor='black', linewidth=.3,
           label='исправное состояние')
    a.hist(fail[c], bins=bins, density=True, histtype='step', color='black', linewidth=1.4,
           label='отказ')
    for x in lines:
        a.axvline(x, color='black', ls='--', lw=1)
    a.set_title(title)
    a.set_ylabel('Плотность')
    a.xaxis.set_major_locator(plt.MaxNLocator(5))
    a.ticklabel_format(axis='y', style='sci', scilimits=(-3, 3))
ax[0].legend(fontsize=7, loc='upper right')
plt.tight_layout()
plt.savefig(IMG / 'derived.png', dpi=200)
plt.close()

# --- 6. Циклы инструмента -----------------------------------------------------
fig, ax = plt.subplots(1, 2, figsize=(12, 3.8), gridspec_kw={'width_ratios': [2.2, 1]})
part = df[df.udi <= 1500]
ax[0].plot(part.udi, part.tool_wear_min, color='0.35', lw=.8)
t = part[part.twf == 1]
ax[0].scatter(t.udi, t.tool_wear_min, color='black', s=22, zorder=3, label='отказ TWF')
ax[0].axhspan(200, 240, color='0.85', zorder=0, label='зона правила TWF (200-240 мин)')
ax[0].set_xlabel('UDI (порядок наблюдений)')
ax[0].set_ylabel('Износ, мин')
ax[0].set_title('Износ инструмента: первые 1500 наблюдений')
ax[0].legend(fontsize=7, loc='upper left')
last = df.groupby('tool_cycle_id').tail(1).iloc[:-1]       # последний цикл не завершён
ax[1].hist([last[last.twf == 0].tool_wear_min, last[last.twf == 1].tool_wear_min],
           bins=np.arange(190, 260, 5), stacked=True, color=['0.8', '0.2'], edgecolor='black',
           label=['плановая замена', 'замена после отказа TWF'])
ax[1].set_xlabel('Износ в момент замены, мин')
ax[1].set_ylabel('Число циклов')
ax[1].set_title('Завершение циклов инструмента')
ax[1].legend(fontsize=7)
plt.tight_layout()
plt.savefig(IMG / 'tool_cycles.png', dpi=200)
plt.close()

json.dump({'cycles_total': int(df.tool_cycle_id.nunique()),
           'cycles_closed': len(last),
           'cycles_twf': int(last.twf.sum()),
           'cycle_len': df.groupby('tool_cycle_id').size().describe().to_dict(),
           'end_wear_planned': last[last.twf == 0].tool_wear_min.describe().to_dict(),
           'end_wear_twf': last[last.twf == 1].tool_wear_min.describe().to_dict()},
          open(etl.OUT / 'cycles.json', 'w'), ensure_ascii=False, indent=1)
print('Рисунки сохранены в', IMG)
