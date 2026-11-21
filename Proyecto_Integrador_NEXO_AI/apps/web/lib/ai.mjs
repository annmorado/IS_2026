// RIA-001..005: narrow proxy; never expose a generic authenticated write pipe.
const ID='[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}';
const ONE=new RegExp('^(transcriptions|extractions)/'+ID+'$','i');
const CANCEL=new RegExp('^transcriptions/'+ID+'/cancel$','i');
const RETRY=new RegExp('^transcriptions/'+ID+'/retry$','i');
const EDIT=new RegExp('^transcriptions/'+ID+'/text$','i');
const REVIEW=new RegExp('^extractions/'+ID+'/review$','i');
const READ=new Set(['voice-note-options','transcriptions','extractions','estimates']);
const POST=new Set(['transcriptions','extractions','validate','estimates']);
export function aiPath(method,segments,query='') {
 if(!Array.isArray(segments)||!segments.length||!segments.every(s=>/^[a-z0-9_-]{1,80}$/i.test(s)))return null;
 const p=segments.join('/');
 if(query){if(method!=='GET'||!['transcriptions','extractions','estimates'].includes(p))return null;
  const q=new URLSearchParams(query);if([...q].length!==1||q.getAll('limit').length!==1||!/^\d{1,2}$/.test(q.get('limit')||''))return null;
  const limit=Number(q.get('limit'));if(limit<1||limit>50)return null;return p+'?limit='+limit;
 }
 if(method==='GET'&&(READ.has(p)||ONE.test(p)))return p;
 if(method==='POST'&&(POST.has(p)||CANCEL.test(p)||RETRY.test(p)||REVIEW.test(p)))return p;
 if(method==='PATCH'&&EDIT.test(p))return p;
 return null;
}
const KEYS={'transcriptions':['voice_note_id'],'extractions':['raw_text'],
 'validate':['product_id','quantity','unit_price_mxn','requested_date','notes'],
 'estimates':['product_id','quantity','requested_date','resource_id']};
export function validAiBody(method,path,body){
 if(!body||typeof body!=='object'||Array.isArray(body))return false;
 if(JSON.stringify(body).length>6000)return false;
 const fields=EDIT.test(path)?['text','confirm']:(CANCEL.test(path)||RETRY.test(path))?[]:REVIEW.test(path)?[...KEYS.validate,'confirm']:KEYS[path];
 if(!fields||Object.keys(body).some(k=>!fields.includes(k)))return false;
 if(CANCEL.test(path)||RETRY.test(path))return Object.keys(body).length===0;
 if(REVIEW.test(path))return body.confirm===true&&Object.keys(body).length>=4&&Object.entries(body).every(([k,v])=>k==='confirm'||v===null||typeof v==='string');
 if(EDIT.test(path))return body.confirm===true&&typeof body.text==='string'&&body.text.length>0&&body.text.length<=5000;
 if(path==='extractions')return typeof body.raw_text==='string'&&body.raw_text.length>0&&body.raw_text.length<=5000;
 if(path==='transcriptions')return typeof body.voice_note_id==='string'&&new RegExp('^'+ID+'$','i').test(body.voice_note_id);
 if(path==='estimates')return typeof body.product_id==='string'&&typeof body.quantity==='string';
 if(path==='validate')return Object.values(body).every(v=>v===null||typeof v==='string');
 return false;
}
