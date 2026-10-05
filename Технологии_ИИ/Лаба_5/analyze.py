"""Шаги 1-3 лабы 5: анализ очищенных данных и выделение фактов и измерений.

Источник - результат ETL из лабы 4 (../Лаба_4/data/data_cleaned.csv).
"""
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / 'Лаба_4' / 'data' / 'data_cleaned.csv'

df = pd.read_csv(SRC)
print(f'Всего записей: {len(df)}')
print(f'Поля: {df.columns.tolist()}')

# Роль каждого поля: ключ / мера / атрибут (+ флаг)
ROLES = {
    'udi': 'ключ', 'product_id': 'ключ', 'product_serial': 'атрибут',
    'quality_class': 'атрибут', 'tool_cycle_id': 'ключ', 'failure_mode': 'атрибут',
}
for c in df.columns:
    ROLES.setdefault(c, 'мера')

fact_table = {
    'name': 'fact_observation',
    'description': 'Наблюдение за станком при обработке одного изделия',
    'grain': 'одна строка data_cleaned (одно изделие)',
    'measures': ['air_temp_k', 'process_temp_k', 'rot_speed_rpm', 'torque_nm', 'tool_wear_min',
                 'temp_diff_k', 'power_w', 'power_margin', 'wear_torque', 'osf_margin', 'cycle_pos',
                 'machine_failure', 'twf', 'hdf', 'pwf', 'osf', 'rnf_ref', 'n_failure_modes',
                 'failure_type_unknown', 'is_outlier_speed', 'is_outlier_torque'],
    'dimension_keys': ['equipment_key', 'class_key', 'tool_key', 'failure_type_key', 'batch_key'],
    'degenerate': ['udi', 'product_id', 'product_serial'],
}

# Кардинальности будущих измерений и второго факта
events = int(df[['twf', 'hdf', 'pwf', 'osf', 'rnf_ref', 'failure_type_unknown']].sum().sum())
card = {
    'dim_quality_class': int(df['quality_class'].nunique()),
    'dim_tool': int(df['tool_cycle_id'].nunique()),
    'dim_failure_type (встречается)': int(df['failure_mode'].nunique()),
    'fact_observation': len(df),
    'fact_failure_event': events,
}
# osf_limit полностью определяется классом -> атрибут измерения, а не мера факта
dep = df.groupby('quality_class')['osf_limit'].nunique().max() == 1
print('osf_limit функционально зависит от класса:', dep)
print(json.dumps(card, ensure_ascii=False, indent=1))
json.dump({'roles': ROLES, 'fact_table': fact_table, 'card': card},
          open(HERE / 'design.json', 'w'), ensure_ascii=False, indent=1)
