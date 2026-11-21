"""Recomputes field-level precision, recall and F1 on an explicit 50-item
synthetic labelled Spanish set. It is NOT real-world model validation.
"""
import json
from pathlib import Path
from app.modules.ai.extract import extract_fields, FIELDS
from uuid import uuid5, NAMESPACE_DNS

DATA = Path(__file__).resolve().parents[1] / 'datasets' / 'ria002_spanish_labelled_50.jsonl'


def catalog():
    return [{'id':str(uuid5(NAMESPACE_DNS,'nexo-'+sku)), 'name':name, 'sku':sku}
      for sku,name in [('PLY-01','Playera'),('TAZ-01','Taza'),('PAS-01','Pastel'),
                       ('BOL-01','Bolsa'),('INV-01','Invitación')]]


def actual(name,value):
    if name=='product':return value.get('name') if isinstance(value,dict) else value
    return value


def measure(rows):
    totals={field:{'tp':0,'fp':0,'fn':0} for field in FIELDS}
    cats=catalog()
    for row in rows:
        pred=extract_fields(row['text'],cats)['fields']
        for name in FIELDS:
            want=actual(name,row['labels'].get(name)); got=actual(name,pred[name]['value'])
            if name in ('quantity','unit_price_mxn') and want is not None and got is not None:
                from decimal import Decimal
                equal=Decimal(str(want))==Decimal(str(got))
            else:equal=want==got
            if want is not None and got is not None and equal:totals[name]['tp']+=1
            else:
                if got is not None:totals[name]['fp']+=1
                if want is not None:totals[name]['fn']+=1
    metrics={}
    for field,c in totals.items():
        p=c['tp']/(c['tp']+c['fp']) if c['tp']+c['fp'] else 0.
        r=c['tp']/(c['tp']+c['fn']) if c['tp']+c['fn'] else 0.
        f1=2*p*r/(p+r) if p+r else 0.
        metrics[field]={**c,'precision':round(p,4),'recall':round(r,4),'f1':round(f1,4)}
    return metrics


def main():
    rows=[json.loads(line) for line in DATA.read_text(encoding='utf-8').splitlines() if line.strip()]
    if len(rows)!=50:raise AssertionError('Se requieren exactamente 50 ejemplos etiquetados')
    result={'dataset':'synthetic_labelled_demo_not_field_validated',
            'examples':len(rows),'engine':'extract_rules_es_1.0','per_field':measure(rows)}
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
