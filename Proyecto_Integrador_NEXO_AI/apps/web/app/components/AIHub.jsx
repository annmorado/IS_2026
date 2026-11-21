'use client';
import {useEffect,useState} from 'react';
const EMPTY={product_id:'',quantity:'',unit_price_mxn:'',requested_date:'',notes:''};
async function api(path,method='GET',body){
 const r=await fetch('/api/ai/'+path,{method,credentials:'same-origin',cache:'no-store',
  ...(body!==undefined?{headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})});
 const json=await r.json().catch(()=>({detail:'Respuesta inválida'}));
 if(!r.ok)throw Error(typeof json.detail==='string'?json.detail:`Error ${r.status}`);
 return json;
}
async function data(path){const r=await fetch('/api/data/'+path,{cache:'no-store'});
 const x=await r.json().catch(()=>({detail:'Sin datos'}));if(!r.ok)throw Error(x.detail||'Error de catálogo');return x;}
function Block({children,title,info}){return <div className="mg-section"><h3>{title}</h3><p className="tiny">{info}</p>{children}</div>}
function Message({children}){return children?<p role="status" className="tiny" style={{color:'#9bdad6'}}>{children}</p>:null}
export default function AIHub(){
 const [tab,setTab]=useState('extract'),[products,setProducts]=useState([]),[resources,setResources]=useState([]),
 [notes,setNotes]=useState([]),[jobs,setJobs]=useState([]),[draft,setDraft]=useState('Necesito 3 playeras, precio unitario $250 para 2026-12-15; nota: estampado azul'),
 [source,setSource]=useState(null),[values,setValues]=useState(EMPTY),[validation,setValidation]=useState(null),[reviewed,setReviewed]=useState(false),
 [estQty,setEstQty]=useState('3'),[estResource,setEstResource]=useState(''),[prediction,setPrediction]=useState(null),
 [transcriptText,setTranscriptText]=useState(''),[selectedJob,setSelectedJob]=useState(''),[status,setStatus]=useState(''),[busy,setBusy]=useState(false);
 async function load(){try{const [p,r,n,j]=await Promise.all([
 data('products/quotable?limit=100'),data('capacity/resources?limit=100'),api('voice-note-options'),api('transcriptions')]);
 setProducts(Array.isArray(p)?p:p.items||[]);setResources(Array.isArray(r)?r:r.items||[]);setNotes(n);setJobs(j)}catch(e){setStatus(e.message)}}
 useEffect(()=>{void load()},[]);
 async function run(fn){setBusy(true);setStatus('');try{await fn()}catch(e){setStatus(e.message)}finally{setBusy(false)}}
 function update(key,value){setValues(v=>({...v,[key]:value}));setValidation(null)}
 async function extract(e){e.preventDefault();await run(async()=>{const x=await api('extractions','POST',{raw_text:draft});
 setSource(x);const f=x.result.fields;setValues({product_id:f.product.value?.id||'',quantity:f.quantity.value||'',
 unit_price_mxn:f.unit_price_mxn.value||'',requested_date:f.requested_date.value||'',notes:f.notes.value||''});
 setValidation(null);setReviewed(false);setTab('extract');setStatus('Propuesta guardada como borrador; revisa todos los campos.');});}
 async function validate(e){e.preventDefault();await run(async()=>{const x=await api('validate','POST',values);setValidation(x);
 setStatus(x.valid?'Datos válidos para continuar con revisión manual. No se creó ni confirmó un pedido.':'Se requiere corrección antes de confirmar.');});}
 async function saveReview(){if(!source||!validation?.valid)return;await run(async()=>{
 const x=await api('extractions/'+source.id+'/review','POST',{...values,confirm:true});setSource(x);setReviewed(true);
 setStatus('Revisión humana guardada; ningún pedido se confirmó.');});}
 async function predict(e){e.preventDefault();await run(async()=>{const x=await api('estimates','POST',{
 product_id:values.product_id,quantity:estQty,requested_date:values.requested_date||null,resource_id:estResource||null});
 setPrediction(x);setStatus('Se guardó una estimación de reglas; no se aplicaron cambios.');});}
 async function startAudio(noteId){await run(async()=>{const x=await api('transcriptions','POST',{voice_note_id:noteId});
 setStatus('Trabajo '+x.id.slice(0,8)+' · '+x.status+'. Actualiza para ver el resultado.');await refreshJobs()});}
 async function refreshJobs(){setJobs(await api('transcriptions'));}
 async function saveEdited(){await run(async()=>{const x=await api('transcriptions/'+selectedJob+'/text','PATCH',{text:transcriptText,confirm:true});
 setTranscriptText(x.reviewed_text||'');await refreshJobs();setStatus('Texto humano revisado; no se creó pedido.');});}
 return <section className="panel mg-hub"><div className="panel-heading"><div><h2>Asistente IA</h2>
 <p>Voz local, extracción trazable, verificación y estimación operativa. Ningún pedido se confirma automáticamente.</p></div><span className="soft-label">Revisión humana</span></div>
 <div className="mg-tabs">{[['extract','Extracción'],['voice','Transcripción'],['forecast','Pronóstico']].map(([key,label])=>
 <button key={key} className={tab===key?'primary':'outline'} type="button" onClick={()=>setTab(key)}>{label}</button>)}</div>
 <Message>{status}</Message>
 {tab==='voice'&&<Block title="Transcripción de voz en español" info="Primero graba y envía una nota M4A desde el iPhone. Se procesa localmente con faster-whisper; requiere motor instalado en FastAPI. Hasta 60 segundos.">
 <button className="outline" onClick={()=>void run(async()=>{await load();setStatus('Notas y transcripciones actualizadas')})}>Actualizar lista</button>
 <div className="mg-metrics">{notes.map(n=><div key={n.id}><small>{n.created_at?.slice(0,16)||'Nota de voz'} · {n.duration_ms==null?'Duración no informada':Math.round(n.duration_ms/1000)+'s'}</small>
 <button className="outline" disabled={busy||n.duration_ms>60000} onClick={()=>void startAudio(n.id)}>Transcribir {n.id.slice(0,8)}</button></div>)}</div>
 {notes.length===0&&<p>No hay notas de voz enviadas. Graba desde la pestaña Voz del iPhone.</p>}
 <h4>Trabajos</h4>{jobs.map(j=><div className="mg-item" key={j.id}><p><b>{j.id.slice(0,8)}</b> · {j.status} · {j.engine}</p>
 {j.error_code&&<p className="tiny">Error: {j.error_code}. No se inventó ningún contenido. Intentos: {j.attempt_count}/3</p>}
 {j.status==='failed'&&j.attempt_count<3&&<button className="outline" onClick={()=>void run(async()=>{await api('transcriptions/'+j.id+'/retry','POST',{});await refreshJobs();setStatus('Reintento programado')})}>Reintentar con modelo instalado</button>}
 {(j.status==='completed'||j.status==='reviewed')&&<><p className="tiny">Texto automático: {j.transcript}</p>
 <button className="outline" onClick={()=>{setSelectedJob(j.id);setTranscriptText(j.reviewed_text||j.transcript||'')}}>Editar y revisar</button></>}
 {(j.status==='queued'||j.status==='processing')&&<button className="outline" onClick={()=>void run(async()=>{await api('transcriptions/'+j.id+'/cancel','POST',{});await refreshJobs()})}>Cancelar</button>}</div>)}
 {selectedJob&&<div className="mg-item"><label>Texto editable revisado por persona<textarea rows="4" maxLength="5000" value={transcriptText} onChange={e=>setTranscriptText(e.target.value)}/></label>
 <div className="mg-row"><button className="primary" disabled={!transcriptText.trim()} onClick={()=>void saveEdited()}>Guardar revisión</button>
 <button className="outline" onClick={()=>{setDraft(transcriptText);setTab('extract');}}>Usar como texto para extracción</button></div></div>}
 </Block>}
 {tab==='extract'&&<Block title="Extracción y revisión de datos" info="Extractor de reglas español (baseline, no modelo entrenado). Muestra fragmentos exactos y campos pendientes; la validación nunca confirma pedidos.">
 <form className="mg-form" onSubmit={extract}><label>Solicitud en español<textarea rows="4" required minLength="1" maxLength="5000" value={draft} onChange={e=>setDraft(e.target.value)}/></label>
 <button className="primary" disabled={busy}>Extraer y guardar propuesta</button></form>
 {source&&<><p className="tiny">Versión: {source.result.engine_version}; pendientes: {source.result.pending_fields.join(', ')||'ninguno'}</p>
 <div className="mg-metrics">{Object.entries(source.result.fields).map(([name,f])=><div key={name}><small>{name} · {f.origin}</small>
 <strong style={{fontSize:13}}>{f.source_fragment||'Pendiente, revisar'}</strong></div>)}</div>
 <form className="mg-form" onSubmit={validate}><div className="mg-row"><label>Producto del catálogo<select value={values.product_id} onChange={e=>update('product_id',e.target.value)}>
 <option value="">Seleccionar manualmente</option>{products.map(p=><option key={p.id} value={p.id}>{p.name} ({p.sku})</option>)}</select></label>
 <label>Cantidad<input type="text" value={values.quantity} onChange={e=>update('quantity',e.target.value)} placeholder="Ej. 3.000"/></label>
 <label>Precio unitario MXN (opcional)<input value={values.unit_price_mxn} onChange={e=>update('unit_price_mxn',e.target.value)} placeholder="Ej. 250.00"/></label>
 <label>Fecha solicitada<input type="date" value={values.requested_date} onChange={e=>update('requested_date',e.target.value)}/></label></div>
 <label>Observaciones<input value={values.notes} maxLength="500" onChange={e=>update('notes',e.target.value)}/></label>
 <button className="primary" disabled={busy}>Validar datos corregidos (sin confirmar)</button></form>
 {validation&&<div className="mg-item"><b>{validation.valid?'Datos coherentes, sujetos a revisión':'Correcciones requeridas'}</b>
 {validation.issues.map((x,i)=><p key={i}>{x.field}: {x.message}</p>)}<p className="tiny">Pedido confirmado: NO · Cambios aplicados: NO</p>
 {validation.valid&&!source.reviewed&&!reviewed&&<button type="button" className="outline" onClick={()=>{if(window.confirm('¿Guardar estos datos validados como revisión humana, sin crear ni confirmar pedidos?'))void saveReview()}}>Guardar revisión corregida</button>}</div>}</>}
 </Block>}
 {tab==='forecast'&&<Block title="Estimación de cumplimiento" info="Baseline determinista con carga, cantidad, minutos por producto, recurso y asignaciones. No es una predicción estadística validada ni una promesa de entrega.">
 <form className="mg-form" onSubmit={predict}><label>Producto<select required value={values.product_id} onChange={e=>update('product_id',e.target.value)}><option value="">Elegir</option>
 {products.map(p=><option key={p.id} value={p.id}>{p.name} ({p.unit})</option>)}</select></label>
 <div className="mg-row"><label>Cantidad<input required type="text" value={estQty} onChange={e=>setEstQty(e.target.value)}/></label>
 <label>Fecha solicitada<input type="date" value={values.requested_date} onChange={e=>update('requested_date',e.target.value)}/></label>
 <label>Recurso<select value={estResource} onChange={e=>setEstResource(e.target.value)}><option value="">Sin recurso (incertidumbre)</option>
 {resources.map(r=><option key={r.id} value={r.id}>{r.name} · {r.daily_capacity}/{r.unit}</option>)}</select></label></div>
 <button className="primary" disabled={busy}>Evaluar sin comprometer capacidad</button></form>
 {prediction&&<div className="mg-item"><b>Motor: {prediction.result.engine_version}</b><p>Tiempo base: {prediction.result.estimated_minutes} min · Fecha aproximada: {prediction.result.estimated_completion_date||'No calculable'}</p>
 <p>Riesgo: {prediction.result.delay_risk} · Calidad: {prediction.result.quality_status}</p>
 {prediction.result.factors.map((f,i)=><p key={i} className="tiny">{f.name}: {f.value} ({f.source})</p>)}
 {prediction.result.warnings.map((w,i)=><p className="tiny" key={i}>{w}</p>)}<p className="tiny">Cambios aplicados: NO · Garantía contractual: NO</p></div>}
 </Block>}
 </section>;
}
