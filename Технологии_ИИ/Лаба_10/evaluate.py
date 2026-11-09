"""Оценка на всех 10 000 наблюдениях PostgreSQL, без обучения и подбора порогов."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from inference import infer, explain, load_rules
HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'tools'))
from pdm_data import observations, fingerprint, save_json


def metrics(y,p):
    y,p=np.asarray(y,dtype=bool),np.asarray(p,dtype=bool)
    tp,tn=int((y&p).sum()),int((~y&~p).sum())
    fp,fn=int((~y&p).sum()),int((y&~p).sum())
    precision=tp/(tp+fp) if tp+fp else 0.
    recall=tp/(tp+fn) if tp+fn else 0.
    return dict(n=len(y),tp=tp,tn=tn,fp=fp,fn=fn,accuracy=(tp+tn)/len(y),
                precision=precision,recall=recall,
                f1=2*precision*recall/(precision+recall) if precision+recall else 0.)


def main():
    start=time.perf_counter()
    rules=load_rules()
    df=observations()
    results=[infer(row,rules) for row in df.to_dict('records')]
    pred=[int(r['facts']['predicted_failure']) for r in results]
    twf=[int(r['facts'].get('twf_risk',False)) for r in results]
    selected=Counter(t['rule'] for r in results for t in r['trace'] if t['new_facts'])
    baseline=metrics(df.machine_failure,pred)
    or_twf=metrics(df.machine_failure,[a or b for a,b in zip(pred,twf)])
    zero=metrics(df.machine_failure,[0]*len(df))
    subtype={}
    for label,flag in [('pwf','pwf_risk'),('osf','osf_risk'),('hdf','hdf_risk'),('twf','twf_risk')]:
        subtype[label]=metrics(df[label],[r['facts'].get(flag,False) for r in results])
    examples=[]
    used=set()
    for name,mask in [
        ('PWF',df.pwf==1),('OSF',(df.osf==1)&(df.pwf==0)),
        ('HDF',(df.hdf==1)&(df.temp_diff_k<8.6)),
        ('Риск TWF без отказа',(df.tool_wear_min.between(200,240))&(df.machine_failure==0)),
        ('Нет известных признаков',(df.machine_failure==0)&(df.tool_wear_min<180))]:
        candidates=[i for i in df.index[mask] if i not in used]
        if candidates:
            i=candidates[0]; used.add(i)
            examples.append(dict(title=name,udi=int(df.loc[i,'udi']),result=results[i],
                                 explanation=explain(results[i])))
    errors=[]
    wrong=np.array(pred)!=df.machine_failure.to_numpy()
    for name,mask,cause,remedy in [
        ('Граница HDF',(df.hdf==1)&(df.temp_diff_k==8.6),
         'NUMERIC хранит 8,6 точно; правило < 8,6 не воспроизводит погрешность исходных float.',
         'Сохранить исходную точность в ETL либо отдельно согласовать <= и оценить ложные срабатывания.'),
        ('Стохастический TWF',df.twf==1,
         'Зона износа — предупреждение; случайный факт отказа не определяется текущими показаниями.',
         'Добавить историю обслуживания/вибрации; оценивать калиброванный риск, а не объявлять всю зону отказом.'),
        ('Неуказанный тип',df.failure_type_unknown==1,
         'Метка положительна без объясняющего подтипа; в разрешённых входах нет соответствующего симптома.',
         'Разобрать первичную разметку; получить дополнительные датчики и экспертные правила.')]:
        ids=list(df.index[mask&wrong])
        if ids:
            i=ids[0]
            errors.append(dict(title=name,udi=int(df.loc[i,'udi']),target=int(df.loc[i,'machine_failure']),
                               result=results[i],cause=cause,remedy=remedy,explanation=explain(results[i])))
    output=pd.DataFrame(dict(udi=df.udi,target=df.machine_failure,prediction=pred,
                             risk=[r['facts']['risk_level'] for r in results],
                             action=[r['facts']['action'] for r in results],
                             applied=[r['applied_count'] for r in results],
                             rule_ids=[';'.join(t['rule'] for t in r['trace'] if t['new_facts']) for r in results]))
    res=HERE/'results'; res.mkdir(exist_ok=True)
    output.to_csv(res/'predictions.csv',index=False)
    save_json(res/'evaluation.json',dict(
        source='PostgreSQL: fact_observation JOIN dim_quality_class JOIN dim_equipment; ORDER BY udi',
        source_sha256=fingerprint(df),
        rules_sha256=hashlib.sha256((HERE.parent/'Лаба_9'/'rules.json').read_bytes()).hexdigest(),
        python=platform.python_version(),metrics=baseline,with_twf=or_twf,always_negative=zero,
        subtype=subtype,average_applied=sum(r['applied_count'] for r in results)/len(results),
        average_selected=sum(len(r['trace']) for r in results)/len(results),
        coverage=dict(selected),risk_counts=dict(Counter(r['facts']['risk_level'] for r in results)),
        examples=examples,errors=errors,seconds=time.perf_counter()-start))
    save_json(res/'examples.json',examples)
    img=HERE/'img'; img.mkdir(exist_ok=True)
    fig,ax=plt.subplots(figsize=(6,5))
    cm=np.array([[baseline['tn'],baseline['fp']],[baseline['fn'],baseline['tp']]])
    ax.imshow(cm,cmap='Blues')
    for (i,j),v in np.ndenumerate(cm):
        ax.text(j,i,str(v),ha='center',va='center',fontsize=18,
                color='white' if v>cm.max()/2 else 'black')
    ax.set(xticks=[0,1],yticks=[0,1],xticklabels=['Нет','Отказ'],yticklabels=['Нет','Отказ'],
           xlabel='Прогноз системы',ylabel='Истинная метка',title='Матрица ошибок: 10 000 наблюдений')
    fig.tight_layout(); fig.savefig(img/'confusion.png',dpi=300); plt.close(fig)
    fig,ax=plt.subplots(figsize=(9,4))
    names=['Без TWF в прогнозе','Включая зону TWF','Всегда «нет отказа»']
    for j,(label,color) in enumerate([('precision','#4c78a8'),('recall','#59a14f'),('f1','#e15759')]):
        ax.bar(np.arange(3)+(j-1)*.22,[100*m[label] for m in [baseline,or_twf,zero]],
               width=.22,color=color,label=label)
    ax.set(xticks=range(3),xticklabels=names,ylabel='%',ylim=(0,110))
    ax.legend(); fig.tight_layout(); fig.savefig(img/'comparison.png',dpi=300); plt.close(fig)
    print('Метрики:',baseline)
    print('С TWF:',or_twf)
    print('Разбор ошибок:',[(e['title'],e['udi']) for e in errors])


if __name__=='__main__':
    main()
