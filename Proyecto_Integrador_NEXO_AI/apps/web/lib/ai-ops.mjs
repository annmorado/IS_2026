// Explicit API allowlist; no arbitrary automation or side-effect proxy.
const ID='[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}';
const MODEL=new RegExp('^models/'+ID+'/(promote|rollback)$','i');
const RUN=new RegExp('^runs/'+ID+'$','i');
const GETS=new Set(['models','runs','quality']);
const POSTS=new Set(['models/train','forecast','optimize','agent/prepare','agent/attempt-sensitive','quality/refresh','twin']);
export function aiOpsPath(method,segments,query=''){
 if(!Array.isArray(segments)||!segments.length||!segments.every(s=>/^[a-z0-9_-]{1,80}$/i.test(s)))return null;
 const path=segments.join('/');
 if(query){if(method!=='GET'||path!=='runs')return null;
  const q=new URLSearchParams(query);if([...q].length>2||[...q.keys()].some(k=>!['kind','limit'].includes(k)))return null;
  if(q.getAll('kind').length>1||q.getAll('limit').length>1)return null;
  if(q.has('kind')&&!['forecast','optimization','agent','digital_twin'].includes(q.get('kind')))return null;
  if(q.has('limit')&&(!/^\d{1,2}$/.test(q.get('limit'))||+q.get('limit')<1||+q.get('limit')>50))return null;
  return path+'?'+q.toString();
 }
 if(method==='GET'&&(GETS.has(path)||RUN.test(path)))return path;
 if(method==='POST'&&(POSTS.has(path)||MODEL.test(path)))return path;
 return null;
}
const KEYS={
 'models/train':['observations','data_origin','confirm'],
 'forecast':['product_id','resource_id','quantity','requested_date'],
 'optimize':['product_id','resource_id','quantity','requested_date','start_date','shift_minutes'],
 'agent/prepare':['kind','product_id','quantity','customer_text'],
 'agent/attempt-sensitive':['action','confirm'],
 'quality/refresh':[],
 'twin':['product_id','resource_id','quantity','start_date','shifts','interruption_probability','supplier_id','supplier_delay_days','runs','seed']
};
export function validAiOpsBody(method,path,body){
 if(method!=='POST'||!body||typeof body!=='object'||Array.isArray(body))return false;
 if(JSON.stringify(body).length>65000)return false;
 const names=MODEL.test(path)?['confirm']:KEYS[path];
 if(!names||Object.keys(body).some(k=>!names.includes(k)))return false;
 if(MODEL.test(path))return body.confirm===true;
 if(path==='quality/refresh')return Object.keys(body).length===0;
 if(path==='models/train')return body.confirm===true&&['synthetic','real_reviewed'].includes(body.data_origin)
   &&Array.isArray(body.observations)&&body.observations.length>=30&&body.observations.length<=200
   &&body.observations.every(r=>r&&typeof r==='object'&&!Array.isArray(r)
   &&Object.keys(r).length===7&&Object.keys(r).every(k=>['created_on','product_id','quantity','base_minutes_per_unit','promised_minutes','actual_minutes','delayed'].includes(k)));
 if(path==='forecast'||path==='optimize'||path==='twin'||path==='agent/prepare')
   return typeof body.product_id==='string'&&typeof body.quantity==='string';
 if(path==='agent/attempt-sensitive')return typeof body.action==='string'&&typeof body.confirm==='boolean';
 return false;
}
