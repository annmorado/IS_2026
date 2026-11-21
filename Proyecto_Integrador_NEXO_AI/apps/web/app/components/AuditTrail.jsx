'use client';
import {useEffect,useState} from 'react';
export default function AuditTrail({orderId}){
 const [items,setItems]=useState([]),[error,setError]=useState('');
 useEffect(()=>{let live=true;
   fetch('/api/data/audit/events?entity_id='+encodeURIComponent(orderId)+'&limit=50',{cache:'no-store'})
    .then(async r=>{const b=await r.json();if(!r.ok)throw Error(b.detail||'No se pudo leer auditoría');return b})
    .then(b=>{if(live)setItems(b.items)}).catch(e=>{if(live)setError(e.message)});
   return()=>{live=false};
 },[orderId]);
 return <section className="panel"><h2>Auditoría inmutable</h2>
  {error&&<p className="alert">{error}</p>}
  {items.length===0&&!error&&<p className="tiny">Sin eventos de auditoría de este pedido.</p>}
  {items.map(e=><div className="history-item" key={e.id}><b>{e.action}</b>
    <small>{new Date(e.occurred_at).toLocaleString('es-MX')} · usuario {e.actor_user_id.slice(0,8)}</small>
    <small>Antes: {JSON.stringify(e.before)} · Después: {JSON.stringify(e.after)}</small>
  </div>)}
 </section>;
}
