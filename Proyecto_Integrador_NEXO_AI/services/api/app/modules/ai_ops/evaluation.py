"""RIA-006/007 reproducible chronological evaluation. No post-delivery feature leakage.

Only creation-time fields are accepted. The whole calendar date is kept within
one split to prevent inter-day contamination. Report metrics are computed on
held-out TEST observations, never validation or train records.
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import math
from statistics import median

FEATURE_VERSION='duration_at_order_v1'
ALLOWED={'created_on','product_id','quantity','base_minutes_per_unit',
         'promised_minutes','actual_minutes','delayed'}
REQUIRED=ALLOWED


def normalized(rows):
    if not isinstance(rows,list) or not 30<=len(rows)<=2000:
        raise ValueError('Se requieren de 30 a 2000 observaciones etiquetadas')
    out=[]
    for i,r in enumerate(rows):
        if not isinstance(r,dict) or set(r)!=REQUIRED:
            raise ValueError('Campos no autorizados o faltantes en observación '+str(i))
        try:
            day=date.fromisoformat(r['created_on'])
            if day.isoformat()!=r['created_on']:raise ValueError()
            vals={k:float(r[k]) for k in ('quantity','base_minutes_per_unit','promised_minutes','actual_minutes')}
            if not all(math.isfinite(v) for v in vals.values()):raise ValueError()
            if vals['quantity']<=0 or vals['quantity']>100000 or vals['base_minutes_per_unit']<=0 or vals['actual_minutes']<=0 or vals['promised_minutes']<=0:raise ValueError()
            if type(r['delayed']) is not bool:raise ValueError()
            if r['delayed'] != (vals['actual_minutes']>vals['promised_minutes']):raise ValueError('Etiqueta de retraso incoherente')
            if not isinstance(r['product_id'],str) or not 1<=len(r['product_id'])<=80:raise ValueError()
        except (KeyError, TypeError, ValueError, OverflowError):
            raise ValueError('Observación inválida '+str(i)) from None
        out.append({'created_on':day.isoformat(),'product_id':r['product_id'],'delayed':r['delayed'],**vals})
    return sorted(out,key=lambda x:x['created_on'])


def _metrics(rows,pred):
    a=[r['actual_minutes'] for r in rows];p=[float(pred(r)) for r in rows]
    mae=round(sum(abs(x-y) for x,y in zip(a,p))/len(rows),4)
    tp=fp=fn=tn=0
    for r,y in zip(rows,p):
        predicted=y>r['promised_minutes'];actual=r['delayed']
        if predicted and actual:tp+=1
        elif predicted and not actual:fp+=1
        elif not predicted and actual:fn+=1
        else:tn+=1
    precision=tp/(tp+fp) if tp+fp else 0.0
    recall=tp/(tp+fn) if tp+fn else 0.0
    f1=2*precision*recall/(precision+recall) if precision+recall else 0.0
    return {'MAE_minutes':mae,'precision':round(precision,4),'recall':round(recall,4),
            'F1':round(f1,4),'prevalence':round((tp+fn)/len(rows),4),
            'confusion':{'tp':tp,'fp':fp,'fn':fn,'tn':tn},'test_count':len(rows)}


def evaluate_temporal(rows):
    rows=normalized(rows)
    days=sorted({x['created_on'] for x in rows})
    if len(days)<6:raise ValueError('Se requieren al menos seis fechas distintas')
    left=days[max(1,int(len(days)*.6))-1]
    middle=days[max(2,int(len(days)*.8))-1]
    train=[r for r in rows if r['created_on']<=left]
    val=[r for r in rows if left<r['created_on']<=middle]
    test=[r for r in rows if r['created_on']>middle]
    if min(map(len,(train,val,test)))<5:raise ValueError('Cada partición debe contener cinco observaciones o más')
    train_groups=defaultdict(list)
    for x in train:train_groups[x['product_id']].append(x['actual_minutes']/x['quantity'])
    # Minimum 5 samples for a specific SKU: otherwise baseline, no guessed coverage.
    factors={k:round(median(v),6) for k,v in train_groups.items() if len(v)>=5}
    counts={k:len(v) for k,v in train_groups.items()}
    def baseline(x):return x['quantity']*x['base_minutes_per_unit']
    def model(x):return x['quantity']*factors.get(x['product_id'],x['base_minutes_per_unit'])
    validation_baseline=_metrics(val,baseline);validation_model=_metrics(val,model)
    test_baseline=_metrics(test,baseline);test_model=_metrics(test,model)
    digest=sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    # This report never contains individual observations or client text.
    report={'engine_kind':'per_product_median_from_train_only','feature_version':FEATURE_VERSION,
      'dataset_sha256':digest,'split':{
      'train_end':left,'validation_start':val[0]['created_on'],'validation_end':middle,'test_start':test[0]['created_on'],
      'train_count':len(train),'validation_count':len(val),'test_count':len(test)},
      'validation':{'baseline':validation_baseline,'candidate':validation_model},
      'test':{'baseline':test_baseline,'candidate':test_model},
      'deployment_approved':False,'time_split':True,'no_post_delivery_features':True,
      'caution':'Si el dataset es sintético, los resultados NO validan desempeño real'}
    config={'feature_version':FEATURE_VERSION,'engine_kind':'per_product_median_from_train_only',
      'factors_minutes_per_unit':factors,'training_counts':counts,'training_end':left,
      'dataset_sha256':digest,'training_observations':len(train)}
    return report,config
