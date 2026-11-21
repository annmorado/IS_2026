'use client';
import {useEffect,useRef,useState} from 'react';

const newKey=prefix=>prefix+'-'+crypto.randomUUID();
async function call(path,options){
 const r=await fetch('/api/data/'+path,{credentials:'same-origin',cache:'no-store',...options});
 const body=await r.json().catch(()=>({detail:'No se recibió respuesta JSON'}));
 if(!r.ok)throw new Error(typeof body.detail==='string'?body.detail:`HTTP ${r.status}`);
 return body;
}
export default function DecisionPanel({order,scenario,onApplied}){
 const [rec,setRec]=useState(null);
 const [items,setItems]=useState([]);
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const [word,setWord]=useState('');
 const [ack,setAck]=useState(false);
 const [reason,setReason]=useState('');
 const createKey=useRef(null),confirmKey=useRef(null);
 const [loaded,setLoaded]=useState(false);
 async function load(){
  try{setItems(await call('decisions?order_id='+encodeURIComponent(order.id)));setError('');}
  catch(e){setError(e.message);}finally{setLoaded(true)}
 }
 useEffect(()=>{setRec(null);setItems([]);setLoaded(false);setWord('');setAck(false);setReason('');
   createKey.current=null;confirmKey.current=null;load();
 },[order.id]);
 const scenarioKey=JSON.stringify(scenario);
 useEffect(()=>{setRec(null);createKey.current=null;confirmKey.current=null;setWord('');},[scenarioKey]);
 async function propose(){
  if(!scenario)return;
  if(!createKey.current)createKey.current=newKey('rec');
  setBusy(true);setError('');
  try{
    const body=await call('decisions/recommend',{method:'POST',headers:{
      'Content-Type':'application/json','Idempotency-Key':createKey.current},
      body:JSON.stringify({scenario})});
    setRec(body);createKey.current=null;await load();
  }catch(e){setError(e.message+' · Puedes reintentar con la misma clave, no se duplica la recomendación.');}
  finally{setBusy(false)}
 }
 async function confirm(){
  if(!rec||!ack||word!=='CONFIRMAR')return;
  if(!confirmKey.current)confirmKey.current=newKey('conf');
  setBusy(true);setError('');
  try{
    const body=await call(`decisions/${rec.id}/confirm`,{method:'POST',headers:{
      'Content-Type':'application/json','Idempotency-Key':confirmKey.current},
      body:JSON.stringify({confirmation:'CONFIRMAR',expected_review_revision:rec.expected_review_revision,
        acknowledge_estimates:true, ...(reason.trim()?{exception_reason:reason.trim()}:{})})});
    setRec(body);confirmKey.current=null;await load();onApplied?.();
  }catch(e){setError(e.message+' · Si hubo fallo de red, puedes reintentar sin duplicar la confirmación.');}
  finally{setBusy(false)}
 }
 return <section className="decision-section" aria-label="Decisiones controladas">
  <h3>Decisión humana y trazabilidad</h3>
  <p className="tiny">Primero guarda la propuesta. Guardarla no altera el pedido. Para aplicarla es necesaria una confirmación adicional del propietario.</p>
  {error&&<p className="alert" role="alert">{error}</p>}
  <button className="outline" type="button" onClick={propose} disabled={busy||!scenario||!['draft','pending'].includes(order.status)}>
    {busy?'Procesando…':'Guardar propuesta (sin aplicar)'}</button>
  {rec&&<div className="decision-current">
    <p><b>Recomendación:</b> {rec.id.slice(0,8)} · {rec.status} · motor {rec.engine_version}</p>
    <p><b>Resultado evaluado:</b> {rec.result.explanation.status} · cantidad {rec.result.simulated.quantity} · fecha {rec.result.delivery_date}</p>
    {rec.status==='proposed'&&<div className="decision-confirm">
      <label>Escribe CONFIRMAR para aplicar la cantidad y fecha al pedido<input value={word} onChange={e=>setWord(e.target.value)} autoComplete="off" placeholder="CONFIRMAR"/></label>
      <label>Justificación excepcional si existen restricciones o datos faltantes<textarea value={reason} onChange={e=>{setReason(e.target.value);confirmKey.current=null}} maxLength="500" rows="2" placeholder="Justificación de la decisión informada (mínimo 15 caracteres si hay incertidumbre)"/></label>
      <label className="check"><input type="checkbox" checked={ack} onChange={e=>setAck(e.target.checked)}/> Reconozco que son estimaciones y que no se han descontado otros compromisos</label>
      <p className="tiny">Los precios y capacidades hipotéticos no se aplican como cambios reales. Si los incluiste, el servidor rechazará la confirmación.</p>
      <button className="primary" type="button" disabled={busy||word!=='CONFIRMAR'||!ack}
        onClick={()=>{void confirm()}}>{busy?'Confirmando…':'Confirmar y aplicar al pedido'}</button>
    </div>}
    {rec.status==='applied'&&<p className="sim-safe">Aplicación confirmada y auditada. Estado del pedido: {rec.applied_order_status}.</p>}
  </div>}
  <h3>Historial de recomendaciones</h3>
  {!loaded&&<p className="tiny">Consultando historial…</p>}
  {items.length===0&&loaded&&<p className="tiny">Aún no hay recomendaciones guardadas para este pedido.</p>}
  {items.map(x=><div className="history-item" key={x.id}>
    <b>{x.engine_version} · {x.status} · {x.id.slice(0,8)}</b>
    <small>{new Date(x.created_at).toLocaleString('es-MX')} · cantidad {x.result.simulated.quantity} · entrega {x.result.delivery_date}</small>
    <small>{x.confirmed_by_user_id?'Confirmó '+x.confirmed_by_user_id.slice(0,8):'Sin aprobar'} · datos y resultado guardados sin sobrescritura</small>
  </div>)}
 </section>;
}
