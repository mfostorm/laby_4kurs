"""python test_inference.py — независимые ожидания и проверки механизма."""
import json
from pathlib import Path
from inference import infer, resolve_conflicts
from rulebase import load_rules, validate_rules

HERE = Path(__file__).resolve().parent
CASES = HERE.parent/'Лаба_9'/'test_cases.json'


def main():
    rules = load_rules()
    cases = json.loads(CASES.read_text(encoding='utf-8'))
    covered = set()
    checked = []
    for case in cases:
        original = json.dumps(case['facts'],sort_keys=True)
        result = infer(case['facts'],rules)
        assert result['terminated']=='fixed_point'
        assert all(result['facts'][k]==v for k,v in case['expected'].items()), case['name']
        assert json.dumps(case['facts'],sort_keys=True)==original
        # Порядок хранения базы не должен менять факты.
        assert infer(case['facts'],list(reversed(rules)))['facts']==result['facts']
        # Добавление метки не влияет на прогноз: нет утечки целевой переменной.
        assert infer(case['facts']|{'machine_failure':1,'failure_mode':'PWF'},rules)['facts']==result['facts']
        covered.update(t['rule'] for t in result['trace'] if t['new_facts'])
        checked.append(dict(name=case['name'],passed=True,
                            rules=[t['rule'] for t in result['trace'] if t['new_facts']]))
    assert covered=={r['id'] for r in rules}, ('Нет свидетеля для правил',covered)
    for field,value in [('temp_diff_k',float('nan')),('power_w',float('inf')),
                        ('class_code','X'),('rot_speed_rpm',0)]:
        try:
            infer(cases[0]['facts']|{field:value},rules)
        except ValueError:
            pass
        else:
            raise AssertionError('Недопустимый ввод принят: '+field)
    missing = dict(cases[0]['facts'])
    del missing['power_w']
    try:
        infer(missing,rules)
    except ValueError:
        pass
    else:
        raise AssertionError('Пропущенный признак принят')
    try:
        infer(cases[1]['facts'],rules,max_steps=1)
    except RuntimeError:
        pass
    else:
        raise AssertionError('Лимит вывода не работает')
    a=dict(id='R002',priority=50,conditions=[{},{}])
    b=dict(id='R001',priority=50,conditions=[{}])
    assert resolve_conflicts([b,a])==a  # специфичность
    a['conditions']=[{}]
    assert resolve_conflicts([a,b])==b  # ID
    bad = json.loads(json.dumps(rules))
    bad.append(bad[0])
    try:
        validate_rules(bad)
    except ValueError:
        pass
    else:
        raise AssertionError('Принят дубликат')
    (HERE/'results').mkdir(exist_ok=True)
    (HERE/'results'/'tests.json').write_text(
        json.dumps(dict(cases=checked,covered_rules=sorted(covered),passed=True,
                        additional_checks=['input_unchanged','rule_order','target_leakage',
                        'invalid_input','missing_input','step_limit','specificity','id','duplicates']),
                   ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'OK: {len(cases)} сценариев; {len(covered)}/{len(rules)} правил со свидетелем; '
          'порядок, утечка, нечисловой ввод, лимит, конфликты и дубликаты проверены.')


if __name__=='__main__':
    main()
