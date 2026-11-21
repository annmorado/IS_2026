'use client';
import {useEffect,useState} from 'react';
export default function OperationalOverview(){
 const [data,setData]=useState(null),[error,setError]=useState('');
 async function reload(){
  try{
   const r=await fetch('/api/data/operations/summary?days=7',{cache:'no-store'});
   const body=await r.json();if(!r.ok)throw Error(body.detail||'Error del panel');
   setData(body);setError('');
  }catch(e){setError(e.message)}
 }
 useEffect(()=>{reload();const t=setInterval(()=>{if(document.visibilityState==='visible')reload()},10000);return()=>clearInterval(t)},[]);
 return <section className="panel ops-panel" aria-label="Panel operativo">
  <div className="panel-heading"><div><h2>Panel operativo</h2><p>Indicadores reales del backend, no estimaciones del navegador.</p></div><button className="outline" onClick={()=>{void reload()}}>Actualizar</button></div>
  {error&&<p className="alert">{error}</p>}
  {data&&<><div className="ops-grid">
    <div><small>Pedidos abiertos</small><strong>{data.open_orders}</strong></div>
    <div><small>Compromisos próximos (7 días)</small><strong>{data.due_soon}</strong></div>
    <div><small>Compromisos vencidos</small><strong>{data.overdue}</strong></div>
    <div><small>Confirmados / en proceso</small><strong>{data.committed_orders}</strong></div>
   </div>
   <h3>Capacidad bruta hoy ({data.today})</h3>
   {data.capacity_resources.length===0&&<p className="tiny">No hay recursos activos.</p>}
   {data.capacity_resources.map(r=><p key={r.id} className="tiny">{r.name}: {r.available_capacity_today} {r.unit} disponibles hoy ({r.working_today?'día hábil':'no laborable o bloqueado'})</p>)}
   <p className="tiny">{data.capacity_caveat}</p>
   {data.alerts.map(a=><p key={a.code} className="notice">{a.severity==='warning'?'Advertencia: ':'Información: '}{a.message}</p>)}
  </>}
 </section>;
}
