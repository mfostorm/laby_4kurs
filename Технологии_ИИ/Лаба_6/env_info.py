"""Сохраняет версии ПО машины, на которой выполнялась лаба, в results/env.json
(используется make_report.py для таблицы версий)."""
import json
import platform

import pandas as pd
import psycopg2
import sqlalchemy
from sqlalchemy import create_engine, text

from load_dwh import RES, URL

with create_engine(URL).connect() as conn:
    server = conn.execute(text('SHOW server_version')).scalar_one().split()[0]
env = {'postgresql': server, 'python': platform.python_version(), 'pandas': pd.__version__,
       'sqlalchemy': sqlalchemy.__version__, 'psycopg2': psycopg2.__version__.split()[0],
       'os': platform.platform()}
json.dump(env, open(RES / 'env.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(env)
