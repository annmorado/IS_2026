// RF-028–RF-032: strict extensions proxy routes. No generic API write capability.
const UUID='[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}';
const review=new RegExp('^documents/ocr/proposals/'+UUID+'/review$','i');
const revoke=new RegExp('^messaging/consents/'+UUID+'/revoke$','i');
const authorize=new RegExp('^agents/workflows/'+UUID+'/authorize$','i');
const READ=new Set(['subscriptions/me','documents/ocr/proposals','messaging/configuration','messaging/events',
  'messaging/consents','sector-templates/catalog','sector-templates/active','sector-templates/history','agents/workflows']);
const POST=new Set(['subscriptions/start-trial','documents/ocr/proposals','messaging/consents','messaging/send-template','sector-templates/apply','agents/prepare']);
const PUT=new Set(['messaging/configuration']);
export function extensionPath(method,parts,query=''){
 if(!Array.isArray(parts)||!parts.length||!parts.every(p=>/^[a-z0-9_-]{1,80}$/i.test(p)))return null;
 const path=parts.join('/');
 if(method==='GET')return !query&&READ.has(path)?path:null;
 if(method==='POST'&&path==='documents/ocr/proposals'){
  if(!query)return path+'?document_type=invoice';
  const q=new URLSearchParams(query);if([...q].length!==1||q.get('document_type')!=='invoice')return null;
  return path+'?document_type=invoice';
 }
 if(query)return null;
 if(method==='POST'&&(POST.has(path)||review.test(path)||authorize.test(path)||revoke.test(path)))return path;
 if(method==='PUT'&&PUT.has(path))return path;
 return null;
}
const fields={'subscriptions/start-trial':[], 'messaging/configuration':['phone_number_id','enabled'],
 'messaging/send-template':['recipient_e164','template_name','consent_reference','confirm'],
 'messaging/consents':['recipient_e164','evidence_reference','valid_days','confirm'],
 'sector-templates/apply':['code','confirm'],
 'agents/prepare':['agent_kind','order_id','objective']};
export function validExtensionBody(path,body){
 if(!body||typeof body!=='object'||Array.isArray(body))return false;
 const keys=Object.keys(body);if(keys.length>5||JSON.stringify(body).length>1600)return false;
 const accepted=review.test(path)?['vendor','amount_mxn','date','reference','concept','confirm']:
   authorize.test(path)?['confirm']:fields[path];
 if(!accepted||keys.some(k=>!accepted.includes(k)))return false;
 if(path==='subscriptions/start-trial')return keys.length===0;
 if(path==='agents/prepare')return typeof body.objective==='string'&&body.objective.length>=10;
 if(path==='messaging/consents')return body.confirm===true&&typeof body.evidence_reference==='string'&&body.evidence_reference.length>=10;
 if(revoke.test(path))return keys.length===1&&body.confirm===true;
 if(path==='messaging/configuration')return typeof body.phone_number_id==='string'&&typeof body.enabled==='boolean';
 if(path==='messaging/send-template')return body.confirm===true&&typeof body.consent_reference==='string'&&body.consent_reference.length>=10;
 if(path==='sector-templates/apply')return body.confirm===true&&typeof body.code==='string';
 if(authorize.test(path))return keys.length===1&&body.confirm===true;
 if(review.test(path))return body.confirm===true;
 return keys.every(k=>body[k]===null||typeof body[k]==='string');
}
