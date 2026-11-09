"""Загрузка и проверка декларативной базы; никаких eval/exec в условиях."""
import json
import math
import operator
from pathlib import Path

HERE = Path(__file__).resolve().parent
OPS = {'lt': operator.lt, 'le': operator.le, 'gt': operator.gt, 'ge': operator.ge,
       'eq': operator.eq, 'ne': operator.ne}


def load_rules(path=HERE / 'rules.json'):
    rules = json.loads(Path(path).read_text(encoding='utf-8'))
    validate_rules(rules)
    return rules


def validate_rules(rules):
    features = {x['name'] for x in json.loads((HERE / 'features.json').read_text(encoding='utf-8'))}
    seen = set()
    producers = {}
    for r in rules:
        if r['id'] in seen:
            raise ValueError('Повтор идентификатора правила')
        seen.add(r['id'])
        if (type(r['stage']) is not int or r['stage'] not in (1,2,3)
                or type(r['priority']) is not int or not 1 <= r['priority'] <= 100):
            raise ValueError('Некорректная стадия или приоритет')
        if not r['conditions'] or not r['then'] or not r['group'] or not r['explanation'] or not r['basis']:
            raise ValueError('Неполное правило')
        for field in r['then']:
            if field in features:
                raise ValueError('Нельзя изменять входной факт')
            producers.setdefault(field, []).append(r['stage'])
    for r in rules:
        for c in r['conditions']:
            if c['op'] not in OPS and c['op'] != 'absent':
                raise ValueError('Неизвестный оператор')
            fields = [c['field']] + ([c['ref']] if 'ref' in c else [])
            for f in fields:
                if f not in features and f not in producers:
                    raise ValueError('Неизвестный признак: '+f)
                if f in producers and max(producers[f]) >= r['stage']:
                    raise ValueError('Условия читают только завершённые предыдущие стадии')
            if c['op'] == 'absent':
                if r['stage'] == 1:
                    raise ValueError('Отрицание до завершения диагностики')
            elif ('ref' in c) == ('value' in c):
                raise ValueError('Укажите ровно value или ref')
    return True


def matches(rule, facts):
    for c in rule['conditions']:
        field, op = c['field'], c['op']
        if op == 'absent':
            if field in facts:
                return False
            continue
        if field not in facts or ('ref' in c and c['ref'] not in facts):
            return False
        value = facts[c['ref']] if 'ref' in c else c['value']
        if not OPS[op](facts[field], value):
            return False
    return True


def record_to_facts(record):
    facts = {}
    for spec in json.loads((HERE / 'features.json').read_text(encoding='utf-8')):
        name = spec['name']
        if name not in record:
            raise ValueError('Отсутствует входной признак '+name)
        value = record[name]
        if spec['type'] == 'number':
            if isinstance(value, (bool, str)):
                raise ValueError('Ожидалось число: '+name)
            value = float(value)
            low, high = spec['domain']
            if not math.isfinite(value) or not low <= value <= high:
                raise ValueError('Признак вне диапазона: '+name)
        elif value not in spec['domain']:
            raise ValueError('Неизвестное значение: '+name)
        facts[name] = value
    return facts


def condition_text(c):
    signs = dict(lt='<',le='≤',gt='>',ge='≥',eq='=',ne='≠')
    if c['op'] == 'absent':
        return 'нет '+c['field']
    return f"{c['field']} {signs[c['op']]} {c.get('ref', c.get('value'))}"


def rule_text(r):
    return ' И '.join(condition_text(c) for c in r['conditions'])


if __name__ == '__main__':
    from collections import Counter
    import sys
    sys.path.insert(0,str(HERE.parent/'tools'))
    from pdm_data import save_json
    rules = load_rules()
    cases = json.loads((HERE/'test_cases.json').read_text(encoding='utf-8'))
    results = []
    for case in cases:
        facts = record_to_facts(case['facts'])
        got = [r['id'] for r in rules if r['stage']==1 and matches(r, facts)]
        assert got == case['expected_diagnostic'], (case['name'],got)
        results.append(dict(name=case['name'], matched=got, passed=True))
    identical = []
    for i,a in enumerate(rules):
        for b in rules[i+1:]:
            if a['conditions']==b['conditions'] and a['stage']==b['stage'] and a['then']!=b['then']:
                identical.append([a['id'],b['id']])
    assert not identical
    save_json(HERE/'results'/'validation.json',
              dict(rules=len(rules),features=len(json.loads((HERE/'features.json').read_text(encoding='utf-8'))),
                   groups=dict(Counter(r['group'] for r in rules)),
                   identical_conflicts=identical,cases=results))
    print(f'JSON и структура: OK; правил {len(rules)}; тестов {len(results)}/{len(cases)}')
