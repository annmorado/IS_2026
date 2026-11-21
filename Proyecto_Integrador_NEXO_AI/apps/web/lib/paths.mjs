// Lista blanca: el panel web solo puede LEER recursos ya autorizados en FastAPI.
const UUID = '[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}';
const ORD = new RegExp('^orders/'+UUID+'(?:/history)?$', 'i');
const DECISION = new RegExp('^decisions/'+UUID+'$', 'i');
const QUOTE = new RegExp('^quotes/'+UUID+'(?:/document|/pdf)?$', 'i');
const allowedParams = {
  'orders/search': new Set(['q','status','date_from','date_to','only_mine','limit','offset']),
  'quotes': new Set(['order_id']),
  'products/quotable': new Set(['limit']),
  'capacity/resources': new Set(['limit']),
  'operations/summary': new Set(['days']),
  'audit/events': new Set(['entity_type','entity_id','limit','offset']),
  'decisions': new Set(['order_id']),
};

export function allowedApiPath(segments, queryString='') {
  if (!Array.isArray(segments) || segments.length === 0 ||
      !segments.every(s => typeof s==='string' && /^[a-z0-9_-]{1,80}$/i.test(s))) return null;
  const p=segments.join('/');
  if (!(p==='orders/search'||p==='quotes'||p==='products/quotable'||p==='capacity/resources'||p==='operations/summary'||p==='audit/events'||p==='decisions'||DECISION.test(p)||ORD.test(p)||QUOTE.test(p))) return null;
  const inbound=new URLSearchParams(queryString);
  const outbound=new URLSearchParams();
  const allowed=allowedParams[p]||new Set();
  for(const [key,value] of inbound) {
    if(!allowed.has(key) || outbound.has(key) || value.length>300) return null;
    outbound.set(key,value);
  }
  // Para la lista de cotizaciones SIEMPRE se requiere un pedido identificable.
  if((p==='quotes'||p==='decisions') && !new RegExp('^'+UUID+'$','i').test(outbound.get('order_id')||'')) return null;
  if(p==='audit/events'&&outbound.has('entity_id')&&!new RegExp('^'+UUID+'$','i').test(outbound.get('entity_id')||''))return null;
  const q=outbound.toString();
  return p+(q?'?'+q:'');
}
