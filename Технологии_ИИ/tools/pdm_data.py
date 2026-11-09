"""Общий read-only доступ к хранилищу лабораторных 9–11. Пароли не журналируются."""
import os
from pathlib import Path
import hashlib
import json

import pandas as pd
from sqlalchemy import URL, create_engine, text


def engine():
    return create_engine(URL.create('postgresql+psycopg2',
        username=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD', 'mysecretpassword'),
        host=os.getenv('DB_HOST', 'localhost'), port=int(os.getenv('DB_PORT', '5432')),
        database=os.getenv('DB_NAME', 'ai_project')))


def observations():
    """Метки сохранены для оценки, но record_to_facts не передаёт их механизму вывода."""
    sql = '''SELECT f.*, q.class_code, q.osf_limit,
      e.power_min_w, e.power_max_w, e.hdf_temp_diff_min_k, e.hdf_speed_max_rpm,
      e.twf_wear_min_min, e.twf_wear_max_min
      FROM dwh.fact_observation f
      JOIN dwh.dim_quality_class q USING (class_key)
      JOIN dwh.dim_equipment e USING (equipment_key) ORDER BY f.udi'''
    db = engine()
    try:
        with db.connect() as conn:
            return pd.read_sql(text(sql), conn)
    finally:
        db.dispose()


def fingerprint(df):
    """Отпечаток значений выборки без временных меток соединения и секретов."""
    return hashlib.sha256(df.to_csv(index=False).encode()).hexdigest()


def save_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
