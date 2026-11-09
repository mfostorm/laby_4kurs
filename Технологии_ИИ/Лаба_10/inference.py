"""Прямой стратифицированный вывод: признаки → риск → рекомендация."""
from copy import deepcopy
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent/'Лаба_9'))
from rulebase import load_rules, matches, record_to_facts, condition_text


def match_rules(facts, rules, fired, stage):
    return [r for r in rules if r['stage']==stage and r['id'] not in fired and matches(r,facts)]


def resolve_conflicts(applicable):
    """Больший приоритет, затем больше условий, затем лексикографически меньший ID."""
    return min(applicable, key=lambda r: (-r['priority'], -len(r['conditions']), r['id']))


def apply_rule(rule, facts):
    """Первое заключение о поле сохраняется, несовместимые записываются в трассу."""
    added, blocked = {}, {}
    for key,value in rule['then'].items():
        if key not in facts:
            facts[key] = value
            added[key] = value
        elif facts[key] != value:
            blocked[key] = {'retained': facts[key], 'rejected': value}
    return added, blocked


def infer(record, rules=None, max_steps=100):
    rules = load_rules() if rules is None else rules
    facts = record_to_facts(record)  # Разрешённый список, целевые метки отброшены.
    original = deepcopy(facts)
    fired, trace = set(), []
    for stage in (1,2,3):
        while True:
            applicable = match_rules(facts,rules,fired,stage)
            if not applicable:
                break
            if len(trace) >= max_steps:
                raise RuntimeError('Превышен лимит вывода; результат не завершён')
            selected = resolve_conflicts(applicable)
            premises = []
            for c in selected['conditions']:
                premises.append({'condition': condition_text(c),
                                 'observed': facts.get(c['field'], '<отсутствует>'),
                                 'threshold': facts[c['ref']] if 'ref' in c else c.get('value')})
            new, blocked = apply_rule(selected,facts)
            fired.add(selected['id'])
            trace.append(dict(rule=selected['id'],stage=stage,
                              conflict_set=[r['id'] for r in applicable],
                              explanation=selected['explanation'],premises=premises,
                              new_facts=new,blocked=blocked))
            # Даже если правило ничего не добавило, оно помечено сработавшим.
            # Проверяем оставшиеся; иначе конфликт мог бы остановить полезный вывод.
    assert all(facts[k]==v for k,v in original.items())
    facts.setdefault('predicted_failure',False)
    if 'risk_level' not in facts or 'action' not in facts:
        raise RuntimeError('База не покрывает ситуацию')
    return {'facts':facts,'trace':trace,
            'applied_count':sum(bool(t['new_facts']) for t in trace),
            'terminated':'fixed_point'}


def explain(result):
    facts = result['facts']
    lines = [f"UDI {int(facts['udi'])}: риск={facts['risk_level']}; действие={facts['action']}; "
             f"прогноз отказа={facts['predicted_failure']}."]
    for t in result['trace']:
        if not t['new_facts'] and not t['blocked']:
            continue
        conditions = '; '.join(f"{p['condition']} (факт: {p['observed']})" for p in t['premises'])
        lines.append(f"{t['rule']}: {conditions}. {t['explanation']} Новые факты: {t['new_facts']}.")
        if t['blocked']:
            lines.append(f"  Сохранено более приоритетное заключение: {t['blocked']}.")
    if not facts['predicted_failure']:
        lines.append('Условия PWF/OSF/HDF не доказаны: прогноз 0 по замкнутому миру; '
                     'это не исключает TWF и неуказанный тип отказа.')
    return '\n'.join(lines)
