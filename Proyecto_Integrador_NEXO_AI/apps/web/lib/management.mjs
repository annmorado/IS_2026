// RF-023..027: explicit deny-by-default allow-list for owner/staff management.
const UUID='[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}';
const collab=new RegExp('^collaborators/users/'+UUID+'/(?:permissions|suspension)$','i');
const purchase=new RegExp('^purchasing/requests/'+UUID+'/decision$','i');
const alloc=new RegExp('^scheduling/allocations/'+UUID+'$','i');
const READ=new Set(['collaborators/users','collaborators/permissions','purchasing/suppliers',
  'purchasing/requests','scheduling/calendar','notifications/preferences','notifications/entries',
  'reports/summary','reports/export','materials']);
const WRITE={POST:new Set(['collaborators/invitations','collaborators/invitations/accept',
  'purchasing/suppliers','purchasing/requests','scheduling/allocations','notifications/scan']),
  PUT:new Set(['notifications/preferences']),PATCH:new Set(),DELETE:new Set()};
const ALLOWED_KEYS=new Map([
 ['scheduling/calendar',new Set(['day'])],['reports/summary',new Set(['date_from','date_to','status'])],
 ['reports/export',new Set(['format','date_from','date_to','status'])],['materials',new Set(['limit'])]
]);
export function managementPath(method,segments,query=''){
  if(!Array.isArray(segments)||!segments.length||!segments.every(x=>typeof x==='string'&&/^[a-z0-9_-]{1,80}$/i.test(x)))return null;
  const path=segments.join('/');
  if(method==='GET'){
    if(!READ.has(path))return null;
    const input=new URLSearchParams(query),output=new URLSearchParams();
    for(const [k,v] of input){if(!ALLOWED_KEYS.get(path)?.has(k)||output.has(k)||v.length>50)return null;output.set(k,v);}
    if(path==='scheduling/calendar'&&!/^\d{4}-\d{2}-\d{2}$/.test(output.get('day')||''))return null;
    if(path==='reports/export'&&!['csv','pdf'].includes(output.get('format')))return null;
    if(path==='materials'&&!['50','100'].includes(output.get('limit')))return null;
    if(output.has('status')&&!/^(draft|pending|confirmed|in_progress|completed|cancelled)$/.test(output.get('status')))return null;
    for(const key of ['date_from','date_to'])if(output.has(key)&&!/^\d{4}-\d{2}-\d{2}$/.test(output.get(key)))return null;
    return path+(output.size?'?'+output.toString():'');
  }
  if(query)return null;
  if(method==='PATCH'&&collab.test(path))return path;
  if(method==='POST'&&purchase.test(path))return path;
  if(method==='DELETE'&&alloc.test(path))return path;
  return WRITE[method]?.has(path)?path:null;
}
export function validManagementBody(path,method,obj){
  if(!obj||typeof obj!=='object'||Array.isArray(obj))return false;
  const keys=Object.keys(obj);if(keys.length>8)return false;
  const fields={
    'collaborators/invitations':['email','permissions','expires_hours'],
    'collaborators/invitations/accept':['token','password'],
    'purchasing/suppliers':['code','name','contact_email'],
    'purchasing/requests':['supplier_id','material_id','quantity','unit_cost_mxn','comment'],
    'scheduling/allocations':['resource_id','order_id','day','quantity'],
    'notifications/preferences':['due_soon','risk','material_shortage'],
    'notifications/scan':[],
  };
  let allowed=fields[path];
  if(collab.test(path)&&method==='PATCH')allowed=path.endsWith('permissions')?['permissions']:['is_active'];
  if(purchase.test(path)&&method==='POST')allowed=['decision','note'];
  if(allowed===undefined)return false;
  if(keys.some(k=>!allowed.includes(k)))return false;
  if(path==='notifications/scan')return keys.length===0;
  if(path==='notifications/preferences')return keys.length===3&&keys.every(k=>typeof obj[k]==='boolean');
  return JSON.stringify(obj).length<=4096;
}
