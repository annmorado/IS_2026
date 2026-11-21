// RF-016: unica mutacion POST permitida desde el navegador; no escribe datos reales.
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const editable=new Set(['order_id','product_id','quantity','delivery_date','start_date','resource_id','resource_daily_capacity','unit_price_mxn']);
const numbers={quantity:/^\d{1,12}(?:\.\d{1,3})?$/,resource_daily_capacity:/^\d{1,12}(?:\.\d{1,3})?$/,unit_price_mxn:/^\d{1,12}(?:\.\d{1,2})?$/};
export function validateScenarioInput(payload){
  if(!payload||typeof payload!=='object'||Array.isArray(payload))return null;
  const keys=Object.keys(payload);
  if(keys.length<2||keys.length>editable.size||keys.some(k=>!editable.has(k)))return null;
  if(!uuid.test(payload.order_id||'')||!uuid.test(payload.product_id||''))return null;
  const clean={order_id:payload.order_id,product_id:payload.product_id};
  for(const [k,v] of Object.entries(payload)){
    if(k==='order_id'||k==='product_id')continue;
    if(typeof v!=='string'||v.length>40)return null;
    if(k==='resource_id'){if(!uuid.test(v))return null;}
    else if(k==='delivery_date'||k==='start_date'){
      if(!/^\d{4}-\d{2}-\d{2}$/.test(v))return null;
    }else if(!numbers[k]?.test(v))return null;
    clean[k]=v;
  }
  if('resource_daily_capacity' in clean&&!('resource_id' in clean))return null;
  return clean;
}
