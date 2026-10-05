"""Базовые значения метрик качества прогнозов и оценка «шума» алертов
(лаба 3, вариант 10). Источник - очищенный набор из лабы 4.

Правила базы знаний - из лаб 1-2; правило HDF в нестрогой форме (лаба 6, п. 4.4).
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
df = pd.read_csv(HERE.parent / 'Лаба_4' / 'data' / 'data_cleaned.csv')
fail = df['machine_failure'] == 1

rules = {
    'HDF': (df.temp_diff_k <= 8.6) & (df.rot_speed_rpm < 1380),
    'PWF': (df.power_w < 3500) | (df.power_w > 9000),
    'OSF': df.wear_torque > df.osf_limit,
    'TWF': df.tool_wear_min.between(200, 240),
}
critical = rules['HDF'] | rules['PWF'] | rules['OSF']   # детерминированные правила
info = rules['TWF']                                      # вероятностное правило (CF 0,06)


def quality(alert):
    tp = int((alert & fail).sum())
    return {'alerts': int(alert.sum()), 'tp': tp,
            'recall': tp / int(fail.sum()), 'precision': tp / max(int(alert.sum()), 1)}


res = {'failures': int(fail.sum()), 'records': len(df),
       'critical': quality(critical), 'all': quality(critical | info),
       'per_rule': {k: quality(v) for k, v in rules.items()},
       'missed_all': df[fail & ~(critical | info)]['failure_mode'].value_counts().to_dict()}

# Опережающий индикатор: записи в «предотказной зоне» (запас < 10 % до порога)
near = ((df.osf_margin >= 0) & (df.osf_margin < 0.1 * df.osf_limit)) | \
       ((df.power_margin >= 0) & (df.power_margin < 550))
res['near_zone'] = {'records': int(near.sum()), 'failures': int((near & fail).sum()),
                    'rate': float(fail[near].mean())}

# Подавление шума: 1) без обработки - уведомление на каждую запись со сработавшим правилом;
# 2) дедупликация - одно уведомление на (цикл инструмента, правило);
# 3) + приоритизация - TWF уходит в ежедневную сводку, оперативно - только критичные.
x = df[critical | info].copy()
x['rule'] = np.select([rules['HDF'][x.index], rules['PWF'][x.index], rules['OSF'][x.index]],
                      ['HDF', 'PWF', 'OSF'], 'TWF')
dedup = x.groupby(['tool_cycle_id', 'rule']).size()
crit_dedup = int(dedup.drop('TWF', level='rule').shape[0])
res['noise'] = {
    'raw': int(len(x)),
    'dedup': int(len(dedup)),
    'operational': crit_dedup,
    'digest_twf': int(dedup.xs('TWF', level='rule').shape[0]),
    'per_1000': {
        'raw': 1000 * len(x) / len(df),
        'dedup': 1000 * len(dedup) / len(df),
        'operational': 1000 * crit_dedup / len(df)},
}
# сколько отказов покрыто оперативными уведомлениями после дедупликации
res['noise']['recall_kept'] = res['critical']['recall']
res['unpredicted_per_1000'] = 1000 * int((fail & ~(critical | info)).sum()) / len(df)
res['failures_per_1000'] = 1000 * int(fail.sum()) / len(df)
print(json.dumps(res, ensure_ascii=False, indent=1))
json.dump(res, open(HERE / 'baseline.json', 'w'), ensure_ascii=False, indent=1)
