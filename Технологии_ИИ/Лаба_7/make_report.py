"""Сборка отчёта по лабе 7 (после reasoning.py и diagrams.py): python make_report.py"""
import json
import sys
from pathlib import Path

import rdflib
from rdflib.namespace import OWL, RDF, RDFS

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'tools'))
from docx_report import Report, num  # noqa: E402

RS = json.load(open(HERE / 'results' / 'reasoning.json', encoding='utf-8'))
ST = RS['stats']
PDM = rdflib.Namespace('http://example.org/pdm#')
g = rdflib.Graph()
g.parse(HERE / 'ontology' / 'pdm.ttl')
IMG = HERE / 'img'


def local(u):
    return str(u).split('#')[1]


def label(u):
    for lab in g.objects(u, RDFS.label):
        if getattr(lab, 'language', None) == 'ru':
            return str(lab)
    return ''


def rng(r):
    if isinstance(r, rdflib.URIRef):
        return local(r).replace('positiveInteger', 'positiveInteger')
    if (r, OWL.oneOf, None) in g:
        vals = list(rdflib.collection.Collection(g, g.value(r, OWL.oneOf)))
        return '{' + ', '.join(str(v) for v in vals) + '}'
    return 'decimal [0..1]'


r = Report()


def nt():
    return r.t + 1


# --- Раздел 1 -------------------------------------------------------------------
r.section('Раздел 1. Цель работы')
r.p('Цель работы - изучить основы символьного подхода в искусственном интеллекте, выполнить '
    'анализ предметной области и спроектировать онтологию, отражающую ключевые понятия '
    'предиктивного обслуживания оборудования и связи между ними.')
r.p('Задачи работы:', keep=True)
r.items(['изучить основные понятия онтологического инжиниринга;',
         'выделить ключевые классы (понятия) предметной области;',
         'определить свойства классов (атрибуты) и отношения между ними;',
         'создать визуальную модель онтологии;',
         'описать онтологию в формализованном виде.'], numbered=True)
r.p('Онтология строится на результатах предыдущих этапов сквозного проекта: сущностях и '
    'фреймах лабы 1, базе продукционных правил, проверенной в лабе 2, циклах инструмента, '
    'выделенных в лабе 4, и хранилище данных лаб 5-6. Онтология описана на языке OWL 2 DL в '
    'синтаксисе Turtle (файл ontology/pdm.ttl, открывается в Protégé). Её непротиворечивость '
    'проверена логическим ризонером HermiT.')

# --- Раздел 2 -------------------------------------------------------------------
r.section('Раздел 2. Анализ понятий предметной области')
r.subsection('2.1. Ключевые понятия')
r.p('Понятия выделены из трёх источников. Из спецификации сущностей лабы 1 взяты '
    'оборудование, узлы, датчики, отказы, правила, прогнозы и объекты процесса ТОиР. Из '
    'хранилища (лабы 5-6) - наблюдения, изделия, классы качества, циклы инструмента и '
    'события отказа. Из анализа правил (лабы 1-2) - контролируемые параметры, включая '
    f'производные. Ключевые классы приведены в таблице {nt()}.')
CLASSES = [
    ['Equipment (Оборудование)', 'Учётная единица оборудования; подклассы MachineTool -> MillingMachine',
     'MILL_01 (AI4I-MILL-01)'],
    ['Component (Узел)', 'Часть оборудования, объект диагностирования и замены; подклассы Spindle, Drive, '
                         'CoolingSystem, CuttingTool', 'Spindle_01, Drive_01, Cooling_01, Tool_01'],
    ['Sensor (Датчик)', 'Источник измерений, установлен на узле; подклассы по измеряемой величине',
     'S_AirTemp, S_ProcTemp, S_Speed, S_Torque, S_Wear'],
    ['MonitoredParameter (Параметр)', 'Измеряемая или производная величина - аргумент правил',
     'P_Torque, P_Power, P_TempDiff, P_WearTorque'],
    ['Product (Изделие)', 'Обрабатываемое изделие', 'Product_M14860, Product_L47340 (10 000)'],
    ['QualityClass (Класс качества)', 'Перечисление L, M, H; задаёт порог перегрузки и шаг износа',
     'Class_L, Class_M, Class_H'],
    ['ToolLifeCycle (Цикл инструмента)', 'Период работы одного инструмента от установки до замены',
     'Cycle_1 (78 изделий, замена после TWF), всего 120'],
    ['Observation (Наблюдение)', 'Снимок телеметрии при обработке одного изделия',
     'Obs_1, Obs_161 (всего 10 000)'],
    ['FailureEvent (Событие отказа)', 'Отказ одного типа в одном наблюдении', 'FE_161_OSF (всего 382)'],
    ['FailureType (Тип отказа)', 'Перечисление типов; подклассы по механизму: механический, тепловой, '
                                 'электрический, случайный', 'TWF, HDF, PWF, OSF, RNF, UnknownFailure'],
    ['ProductionRule (Правило)', 'Правило ЕСЛИ - ТО с коэффициентом уверенности',
     'R_HDF, R_PWF, R_OSF, R_TWF'],
    ['RiskForecast (Прогноз риска)', 'Результат срабатывания правила на наблюдении', 'RF_161, RF_3237'],
    ['MaintenanceAction (Вид работ)', 'Работа, рекомендуемая при типе отказа',
     'A_ReplaceTool, A_CheckCooling, A_DiagnoseDrive'],
    ['MaintenanceRequest (Заявка)', 'Заявка на ремонт по прогнозу', 'появляются в эксплуатации (CMMS)'],
    ['WorkOrder (Наряд)', 'Документ на выполнение работ', 'появляются в эксплуатации (CMMS)'],
    ['MaintenanceRegulation, RepairTeam, SparePart', 'Регламент ТО, ремонтная бригада, запасная часть - '
                                                     'ресурсы планирования', 'появляются в эксплуатации'],
]
r.table('Ключевые понятия (классы) онтологии', ['Понятие (класс)', 'Описание', 'Примеры экземпляров'],
        CLASSES, widths=[4.6, 7.0, 4.9], size=11)
r.p('Последние три строки таблицы - понятия процесса обслуживания. Их экземпляров в наборе '
    'AI4I нет, но они включены в онтологию, поскольку образуют контекст применения прогнозов: '
    'прогноз риска порождает заявку, заявка - наряд, наряд использует бригаду и запасные части. '
    'Именно эти понятия связывают онтологию с генетическим алгоритмом планирования из лабы 1.')
r.p(f'Кроме именованных понятий, в онтологии {len(ST["defined_classes"])} определяемых классов '
    f'(таблица {nt()}). Их экземпляры не указываются вручную, а выводятся ризонером из определения.')
DEF = {
    'FailedObservation': ('Наблюдение с отказом', 'Observation ⊓ ∃hasFailureEvent.FailureEvent'),
    'MechanicalFailureEvent': ('Механический отказ', 'FailureEvent ⊓ ∃hasFailureType.MechanicalFailureType'),
    'ThermalFailureEvent': ('Тепловой отказ', 'FailureEvent ⊓ ∃hasFailureType.ThermalFailureType'),
    'ElectricalFailureEvent': ('Электрический отказ', 'FailureEvent ⊓ ∃hasFailureType.ElectricalFailureType'),
    'DeterministicRule': ('Детерминированное правило', 'ProductionRule ⊓ certaintyFactor = 1,0'),
    'HighRiskForecast': ('Прогноз высокого риска', 'RiskForecast ⊓ riskLevel = "high"'),
    'ConfirmedForecast': ('Подтверждённый прогноз', 'RiskForecast ⊓ ∃concernsObservation.FailedObservation'),
}
r.table('Определяемые классы', ['Класс', 'Смысл', 'Определение (≡)'],
        [[k, v[0], v[1]] for k, v in DEF.items()], widths=[4.4, 4.2, 7.9], size=11)

r.subsection('2.2. Связь понятий с предыдущими этапами проекта')
r.p(f'Соответствие классов онтологии сущностям лабы 1 и объектам хранилища лабы 5 приведено в '
    f'таблице {nt()}. Оно используется в лабе 8 при наполнении графа знаний из хранилища.')
r.table('Соответствие онтологии, концептуальной модели и хранилища',
        ['Класс онтологии', 'Сущность / фрейм лабы 1', 'Объект хранилища (лаба 5)'],
        [['Equipment, MillingMachine', 'EQUIPMENT_TYPE, EQUIPMENT; фрейм «Металлорежущий станок»', 'dim_equipment'],
         ['QualityClass', 'Атрибут класса качества во фрейме', 'dim_quality_class'],
         ['ToolLifeCycle', '- (выделен в лабе 4)', 'dim_tool'],
         ['Observation, Product', 'MEASUREMENT', 'fact_observation (product_id - вырожденное измерение)'],
         ['FailureEvent', 'FAILURE_EVENT', 'fact_failure_event'],
         ['FailureType', 'FAILURE_TYPE', 'dim_failure_type'],
         ['ProductionRule', 'RULE', 'dim_failure_type.rule_condition, пороги в измерениях'],
         ['RiskForecast', 'RISK_FORECAST', 'вычисляется: представление v_rule_check'],
         ['Component, Sensor, MonitoredParameter', 'COMPONENT, SENSOR', 'нет: знания о конструкции станка'],
         ['MaintenanceAction', '- (действия правил лабы 1)', 'dim_failure_type.recommended_action'],
         ['MaintenanceRequest, WorkOrder, ...', 'MAINT_REQUEST, WORK_ORDER, TEAM, SPARE_PART', 'нет данных в источнике']],
        widths=[4.4, 6.2, 5.9], size=11)
r.p('Онтология шире хранилища в двух направлениях. Во-первых, она содержит знания, которых '
    'нет в данных: из каких узлов состоит станок, какой датчик какую величину измеряет, какой узел '
    'поражает каждый тип отказа. Во-вторых, она задаёт смысл, а не только структуру: '
    'иерархии классов, характеристики отношений и аксиомы, из которых ризонер выводит новые '
    'факты.')

# --- Раздел 3 -------------------------------------------------------------------
r.section('Раздел 3. Свойства классов')
dps = []
for p in sorted(g.subjects(RDF.type, OWL.DatatypeProperty), key=lambda u: (
        local(g.value(u, RDFS.domain)), local(u))):
    dps.append([local(g.value(p, RDFS.domain)), local(p), rng(g.value(p, RDFS.range)), label(p)])
r.p(f'В онтологии {ST["data_properties"]} свойств данных (атрибутов). Они перечислены в таблице '
    f'{nt()} вместе с областью определения (классом) и типом значения. Все атрибуты '
    'функциональны: у экземпляра не больше одного значения.')
r.table('Свойства классов (атрибуты)', ['Класс', 'Свойство', 'Тип', 'Описание'], dps,
        widths=[4.1, 4.3, 3.4, 4.7], size=9)
r.p('Для трёх атрибутов тип значения ограничен сильнее базового типа данных. Коэффициент '
    'уверенности правила и оценка риска - десятичные числа в диапазоне [0; 1] (фасеты '
    'xsd:minInclusive и xsd:maxInclusive). Уровень риска и причина завершения цикла принимают '
    'значения только из перечисления. Такие ограничения позволяют ризонеру обнаружить '
    'некорректные данные (п. 6.4).')

# --- Раздел 4 -------------------------------------------------------------------
r.section('Раздел 4. Отношения между классами')
r.p('В онтологии использованы все четыре типа отношений из методических указаний:', keep=True)
r.items([
    '**наследование (is-a)** - иерархии классов: MillingMachine ⊑ MachineTool ⊑ Equipment, '
    'Spindle ⊑ Component, ThermalFailureType ⊑ FailureType и т. д. (рисунок 1);',
    '**часть - целое (part-of)** - транзитивное свойство partOf и его подсвойства componentOf '
    '(узел - станок) и installedOn (датчик - узел);',
    '**ассоциация** - объектные свойства между независимыми понятиями: наблюдение - изделие, '
    'правило - тип отказа, прогноз - наблюдение и т. д.;',
    '**атрибутивное** - свойства данных из раздела 3.'])


def mult(p):
    f = (p, RDF.type, OWL.FunctionalProperty) in g
    inv = (p, RDF.type, OWL.InverseFunctionalProperty) in g
    return {(True, True): 'Один к одному', (True, False): 'Многие к одному',
            (False, True): 'Один ко многим', (False, False): 'Многие ко многим'}[(f, inv)]


ops = []
for p in sorted(g.subjects(RDF.type, OWL.ObjectProperty), key=local):
    d, rr = g.value(p, RDFS.domain), g.value(p, RDFS.range)
    kind = 'часть-целое' if (p, RDFS.subPropertyOf, PDM.partOf) in g or p == PDM.hasComponent else 'ассоциация'
    if p == PDM.partOf:
        ops.append(['partOf', 'любой', 'любой', 'является частью (транзитивно)', 'Многие ко многим'])
        continue
    ops.append([local(p), local(d), local(rr), label(p) + (' (часть - целое)' if kind == 'часть-целое' else ''), mult(p)])
r.p(f'Объектные свойства (отношения) приведены в таблице {nt()}. Множественность определяется '
    'характеристиками свойства: функциональное свойство - не более одного значения, обратно '
    'функциональное - не более одного субъекта для значения.')
r.table('Отношения между классами', ['Отношение', 'От класса', 'К классу', 'Смысл', 'Множественность'],
        ops, widths=[3.4, 4.1, 4.1, 2.9, 2.0], size=9)
r.p('Некоторые отношения дополнительно уточнены характеристиками:', keep=True)
r.items([
    'partOf - транзитивное: если датчик установлен на узле, а узел является частью станка, '
    'то датчик является частью станка (вывод показан в п. 6.3);',
    'hasComponent и componentOf, hasFailureEvent и occurredDuring - взаимно обратные пары;',
    'nextObservation (порядок наблюдений) - функциональное, обратно функциональное, '
    'асимметричное и иррефлексивное: у наблюдения ровно одно следующее, и оно не может '
    'следовать само за собой;',
    'processesProduct - функциональное и обратно функциональное: связь наблюдения и изделия '
    'один к одному, как в наборе AI4I.'])

# --- Раздел 5 -------------------------------------------------------------------
r.section('Раздел 5. Визуальная модель онтологии')
r.p('Визуальная модель построена программой diagrams.py непосредственно из файла онтологии, '
    'поэтому соответствует формальному описанию. Цветом выделены группы понятий: технические '
    'объекты, производство, отказы, база знаний, обслуживание. Иерархия классов приведена на '
    'рисунке 1: сплошные стрелки - наследование (is-a), пунктирные рамки и стрелки - '
    'определяемые классы с их определением.')
r.figure(IMG / 'taxonomy.png', 'Иерархия классов онтологии', width=15.5)
r.p('Классы, их атрибуты и отношения приведены на рисунке 2 (следующая страница). Синим '
    'выделены отношения часть - целое. Из диаграммы видна структура предметной области: '
    'наблюдение связывает оборудование, изделие и цикл инструмента; отказ связан с наблюдением '
    'и типом отказа; правило распознаёт тип отказа по параметрам, которые измеряются датчиками '
    'на узлах; прогноз риска порождает заявку и наряд.')
r.figure_landscape(IMG / 'relations.png', 'Классы, атрибуты и отношения онтологии', width=25.5)

# --- Раздел 6 -------------------------------------------------------------------
r.section('Раздел 6. Формальное описание')
r.subsection('6.1. Состав онтологии')
r.p(f'Онтология описана на языке OWL 2 DL; полный текст - файл ontology/pdm.ttl '
    f'({num(ST["triples"], 0)} RDF-триплетов). Состав онтологии приведён в таблице {nt()}.')
ch = ST['characteristics']
r.table('Состав онтологии', ['Элемент', 'Количество'],
        [['Именованные классы', ST['classes']],
         ['  из них определяемые (≡)', len(ST['defined_classes'])],
         ['  из них заданные перечислением', len(ST['enumerated_classes'])],
         ['Аксиомы наследования между именованными классами', ST['subclass_axioms']],
         ['Ограничения на свойства (owl:Restriction)', ST['restrictions']],
         ['Группы непересекающихся классов', ST['disjoint_groups']],
         ['Объектные свойства (отношения)', ST['object_properties']],
         ['Свойства данных (атрибуты)', ST['data_properties']],
         ['Функциональные свойства', ch['FunctionalProperty']],
         ['Транзитивные / асимметричные / иррефлексивные свойства',
          f"{ch['TransitiveProperty']} / {ch['AsymmetricProperty']} / {ch['IrreflexiveProperty']}"],
         ['Индивиды (справочные и примеры из AI4I)', ST['individuals']]],
        widths=[11.0, 4.0], align='lc')

r.subsection('6.2. Структура классов и связей')
r.p('Ключевые классы и свойства в нотации, близкой к Manchester Syntax:', keep=True)
r.code('''Class: Observation
  SubClassOf: observedOn exactly 1 Equipment,
              processesProduct exactly 1 Product,
              usesToolCycle exactly 1 ToolLifeCycle,
              udi exactly 1
  Properties: udi (integer), airTemperatureK, processTemperatureK, torqueNm,
              temperatureDifferenceK, powerW, wearTorque (decimal),
              rotationalSpeedRpm, toolWearMin (integer), positionInCycle (positiveInteger)
  Relations:  observedOn (Equipment), processesProduct (Product),
              usesToolCycle (ToolLifeCycle), hasFailureEvent (FailureEvent),
              nextObservation (Observation)

Class: MillingMachine
  SubClassOf: MachineTool,
              hasComponent some Spindle, hasComponent some Drive,
              hasComponent some CoolingSystem, hasComponent some CuttingTool

Class: FailureEvent
  SubClassOf: occurredDuring exactly 1 Observation,
              hasFailureType exactly 1 FailureType

Class: ThermalFailureEvent
  EquivalentTo: FailureEvent and (hasFailureType some ThermalFailureType)

Class: QualityClass
  EquivalentTo: {Class_L, Class_M, Class_H}

Class: ProductionRule
  SubClassOf: detects some FailureType, usesParameter some MonitoredParameter,
              certaintyFactor exactly 1
  Properties: ruleCode (string), conditionText (string),
              certaintyFactor (decimal[>= 0.0, <= 1.0])

Class: ConfirmedForecast
  EquivalentTo: RiskForecast and (concernsObservation some FailedObservation)

DisjointClasses: Equipment, Component, Sensor, Product, Observation, FailureEvent, ...
DisjointClasses: Spindle, Drive, CoolingSystem, CuttingTool

ObjectProperty: partOf
  Characteristics: Transitive
ObjectProperty: installedOn
  SubPropertyOf: partOf
  Domain: Sensor   Range: Component   Characteristics: Functional
ObjectProperty: nextObservation
  Domain: Observation   Range: Observation
  Characteristics: Functional, InverseFunctional, Asymmetric, Irreflexive''', size=8)
r.p('Тот же фрагмент в исходном синтаксисе Turtle (класс FailureEvent и отношение '
    'hasFailureType):', keep=True)
r.code('''pdm:FailureEvent a owl:Class ;
    rdfs:subClassOf
        [ a owl:Restriction ; owl:onProperty pdm:occurredDuring ;
          owl:qualifiedCardinality "1"^^xsd:nonNegativeInteger ; owl:onClass pdm:Observation ] ,
        [ a owl:Restriction ; owl:onProperty pdm:hasFailureType ;
          owl:qualifiedCardinality "1"^^xsd:nonNegativeInteger ; owl:onClass pdm:FailureType ] ;
    rdfs:label "Событие отказа"@ru .

pdm:hasFailureType a owl:ObjectProperty , owl:FunctionalProperty ;
    rdfs:domain pdm:FailureEvent ; rdfs:range pdm:FailureType ;
    rdfs:label "имеет тип отказа"@ru .''', size=8)
r.p('Фреймовая парадигма лабы 1 отражена в онтологии напрямую. Фрейм-прототип '
    '«Металлорежущий станок» стал классом MachineTool, слоты фрейма - атрибутами класса, а '
    'наследование значений слотов - наследованием классов и аксиомами: значение порога '
    'перегрузки изделие получает от своего класса качества через отношение hasQualityClass. '
    'Продукционные правила представлены индивидами класса ProductionRule с условием, '
    'коэффициентом уверенности и ссылками на параметры и распознаваемый тип отказа.')

r.subsection('6.3. Проверка ризонером и логический вывод')
r.p('Онтология проверена ризонером HermiT (программа reasoning.py, библиотека owlready2). '
    'Результат: онтология непротиворечива. Ризонер вывёл факты, которые не были записаны '
    f'явно (таблица {nt()}).')
inf_rows = []
for ind, types in sorted(RS['inferred_types'].items()):
    inf_rows.append([ind, ', '.join(types)])
for ind, vals in sorted(RS['inferred_partof'].items()):
    inf_rows.append([ind, 'partOf ' + ', '.join(vals)])
r.table('Факты, выведенные ризонером', ['Индивид', 'Выведено'], inf_rows, widths=[5.0, 11.5], size=10)
r.p('Вывод работает так. Событие FE_3237_HDF имеет тип HDF, а HDF - экземпляр класса '
    'ThermalFailureType; по определению ThermalFailureEvent событие отнесено к тепловым '
    'отказам. Наблюдение Obs_3237 содержит событие отказа и поэтому отнесено к FailedObservation. '
    'Прогноз RF_3237 относится к наблюдению с отказом - значит, он подтверждённый; уровень его '
    'риска high - значит, это прогноз высокого риска. Прогноз RF_78 по правилу TWF тоже '
    'подтверждённый, но низкого риска: коэффициент уверенности этого правила 0,06 (лаба 2). '
    'Датчики установлены на узлах, узлы являются частями станка MILL_01 (через обратное '
    'свойство hasComponent), и по транзитивности partOf ризонер заключил, что все датчики - '
    'части станка. Фрагмент онтологии с индивидами и выведенными типами показан на рисунке 3.')
r.figure(IMG / 'abox.png', 'Фрагмент онтологии с индивидами: наблюдение 161 (отказ OSF); '
                           'красным - типы, выведенные ризонером', width=16.5)

r.subsection('6.4. Обеспечение непротиворечивости')
r.p('Непротиворечивость обеспечивается аксиомами: непересекающимися классами, '
    'функциональными свойствами, ограничениями мощности, перечислениями и ограничениями '
    'типов данных. Чтобы убедиться, что аксиомы действительно работают, в копию онтологии '
    f'вносились заведомо противоречивые утверждения (таблица {nt()}).')
r.table('Проверка обнаружения противоречий', ['Внесённое утверждение', 'Нарушенная аксиома', 'Результат'],
        [[t.split(' (')[0], t.split(' (')[1].rstrip(')') if ' (' in t else '-', v]
         for t, _, v in RS['negative']], widths=[6.6, 5.6, 4.3], size=10)
neg_ok = sum(v == 'обнаружено противоречие' for *_, v in RS['negative'])
r.p(f'Ризонер обнаружил противоречие во всех {neg_ok} случаях из {len(RS["negative"])}. Значит, '
    'онтологию можно использовать как схему проверки данных при наполнении графа знаний: '
    'некорректные факты, например изделие с двумя классами качества или прогноз с '
    'недопустимым уровнем риска, будут отвергнуты.')

# --- Раздел 7 -------------------------------------------------------------------
r.section('Раздел 7. Выводы')
r.p(f'Спроектирована онтология предметной области «Предиктивное обслуживание промышленного '
    f'оборудования»: {ST["classes"]} классов, включая {len(ST["defined_classes"])} определяемых, '
    f'{ST["object_properties"]} отношений, {ST["data_properties"]} атрибутов и {ST["individuals"]} '
    'индивидов. Онтология объединяет пять групп понятий: технические объекты (оборудование, '
    'узлы, датчики, параметры), производство (наблюдения, изделия, классы качества, циклы '
    'инструмента), отказы, базу знаний (правила и прогнозы) и обслуживание.')
r.p('Использованы все типы отношений: наследование, часть - целое с транзитивным свойством, '
    'ассоциации и атрибутивные свойства. Отношения уточнены характеристиками: '
    'функциональностью, обратными свойствами, асимметричностью и иррефлексивностью. '
    'Ограничения мощности, непересекающиеся классы, перечисления и ограничения типов данных '
    'задают аксиомы предметной области.')
r.p('Онтология связана с предыдущими этапами проекта: фреймы и продукционные правила лабы 1 '
    'выражены классами и индивидами, а каждому классу, для которого есть данные, соответствует '
    'объект хранилища лабы 5. Онтология добавляет к данным знания о конструкции станка и смысле '
    'понятий, которых нет в хранилище.')
r.p('Ризонер HermiT подтвердил непротиворечивость онтологии и вывел новые факты: '
    'классификацию отказов по механизму, подтверждённость и уровень риска прогнозов, '
    'детерминированность правил, принадлежность датчиков станку. Все шесть внесённых '
    'противоречий обнаружены. Онтология готова к реализации в виде графа знаний и наполнению '
    'данными из хранилища на следующем этапе.')

r.section('Список использованных источников')
r.items([
    'Гаврилова Т. А. Базы знаний интеллектуальных систем / Т. А. Гаврилова, В. Ф. Хорошевский. - '
    'Санкт-Петербург : Питер, 2000. - 384 с. - ISBN 5-272-00071-4.',
    'Добров Б. В. Онтологии и тезаурусы: модели, инструменты, приложения / Б. В. Добров, '
    'В. В. Иванов, Н. В. Лукашевич, В. Д. Соловьев. - Москва : URSS, 2013. - ISBN 978-5-9963-0007-5.',
    'Люгер Дж. Ф. Искусственный интеллект: стратегии и методы решения сложных проблем / Дж. Ф. '
    'Люгер ; пер. с англ. - 4-е изд. - Москва : Вильямс, 2003. - 864 с. - ISBN 5-8459-0437-4.',
    'Рассел С. Искусственный интеллект: современный подход / С. Рассел, П. Норвиг ; пер. с англ. - '
    '2-е изд. - Москва : Вильямс, 2006. - 1408 с. - ISBN 5-8459-0887-6.',
    'Осипов Г. С. Методы искусственного интеллекта / Г. С. Осипов. - Москва : Физматлит, 2011. - '
    '296 с. - ISBN 978-5-9221-1323-6.',
    'OWL 2 Web Ontology Language Primer (Second Edition) : W3C Recommendation. - URL: '
    'https://www.w3.org/TR/owl2-primer/ (дата обращения: 26.10.2026).',
    'Glimm B. HermiT: An OWL 2 Reasoner / B. Glimm, I. Horrocks, B. Motik, G. Stoilos, Z. Wang // '
    'Journal of Automated Reasoning. - 2014. - Vol. 53, No. 3. - P. 245-269.'], numbered=True)

r.save(HERE / 'Отчёт_Лаба_7_Вариант_10.docx')
print('Отчёт сохранён')
