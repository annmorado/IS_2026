// RF-018/021/022: lista blanca de decisiones; no permite elegir tenant, actor ni estado.
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const money=/^\d{1,12}(?:\.\d{1,3})?$/;
const idKey=/^[A-Za-z0-9._:\-]{8,128}$/;
export function validKey(value){return typeof value==='string'&&idKey.test(value)}
export function validateRecommend(body){
 if(!body||typeof body!=='object'||Array.isArray(body)||Object.keys(body).join(',')!=='scenario')return null;
 const s=body.scenario;
 if(!s||typeof s!=='object'||Array.isArray(s))return null;
 const keys=new Set(['order_id','product_id','quantity','delivery_date','start_date','resource_id','resource_daily_capacity','unit_price_mxn']);
 if(Object.keys(s).some(k=>!keys.has(k)))return null;
 if(!uuid.test(s.order_id||'')||!uuid.test(s.product_id||''))return null;
 const safe={order_id:s.order_id,product_id:s.product_id};
 for(const [k,v] of Object.entries(s)){
  if(k==='order_id'||k==='product_id')continue;
  if(typeof v!=='string'||v.length>40)return null;
  if(k==='resource_id'){if(!uuid.test(v))return null}
  else if(k==='delivery_date'||k==='start_date'){if(!/^\d{4}-\d{2}-\d{2}$/.test(v))return null}
  else if(k==='unit_price_mxn'){if(!/^\d{1,12}(?:\.\d{1,2})?$/.test(v))return null}
  else if(!money.test(v))return null;
  safe[k]=v;
 }
 if('resource_daily_capacity' in safe&&!('resource_id' in safe))return null;
 return {scenario:safe};
}
export function validateConfirm(body){
 if(!body||typeof body!=='object'||Array.isArray(body))return null;
 const keys=new Set(['confirmation','expected_review_revision','acknowledge_estimates','exception_reason']);
 if(Object.keys(body).some(k=>!keys.has(k)))return null;
 if(body.confirmation!=='CONFIRMAR'||body.acknowledge_estimates!==true)return null;
 if(!Number.isInteger(body.expected_review_revision)||body.expected_review_revision<0)return null;
 if(body.exception_reason!==undefined&&(typeof body.exception_reason!=='string'||body.exception_reason.length>500))return null;
 return {confirmation:'CONFIRMAR',expected_review_revision:body.expected_review_revision,
   acknowledge_estimates:true,...(body.exception_reason?{exception_reason:body.exception_reason}:{})};
}
export function writableDecisionPath(segments){
 if(!Array.isArray(segments))return null;
 const path=segments.join('/');
 if(path==='decisions/recommend')return path;
 if(segments.length===3&&segments[0]==='decisions'&&uuid.test(segments[1])&&segments[2]==='confirm')return path;
 return null;
}
