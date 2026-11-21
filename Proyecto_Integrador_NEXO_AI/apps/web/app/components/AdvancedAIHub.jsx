'use client';
import {useEffect,useState} from 'react';

async function api(path,method='GET',body){
 const r=await fetch('/api/ai-ops/'+path,{method,credentials:'same-origin',cache:'no-store',
   ...(body!==undefined?{headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})});
 const x=await r.json().catch(()=>({detail:'Error de respuesta'}));
 if(!r.ok)throw Error(typeof x.detail==='string'?x.detail:JSON.stringify(x.detail)||'Error '+r.status);
 return x;
}
async function catalog(path){
 const r=await fetch('/api/data/'+path,{cache:'no-store'});const x=await r.json().catch(()=>({}));
 if(!r.ok)throw Error(x.detail||'No se pudo consultar el catálogo');return Array.isArray(x)?x:x.items||[];
}
function Part({title,note,children}){return <div className="mg-section"><h3>{title}</h3><p className="tiny">{note}</p>{children}</div>}
function Result({value}){return value?<pre className="mg-item" style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere',fontSize:12,maxHeight:430,overflowY:'auto'}}>{JSON.stringify(value,null,2)}</pre>:null}
const dateIn=n=>{const x=new Date();x.setDate(x.getDate()+n);return x.toISOString().slice(0,10)};

export default function AdvancedAIHub({owner=false}){
 const [tab,setTab]=useState('optimization');const [products,setProducts]=useState([]),[resources,setResources]=useState([]);
 const [product,setProduct]=useState(''),[resource,setResource]=useState(''),[quantity,setQuantity]=useState('3'),[due,setDue]=useState(dateIn(14));
 const [kind,setKind]=useState('quote_draft'),[message,setMessage]=useState(''),[r,setR]=useState(null),[busy,setBusy]=useState(false);
 const [models,setModels]=useState([]),[quality,setQuality]=useState([]),[runs,setRuns]=useState([]);
 const [seed,setSeed]=useState('42'),[shifts,setShifts]=useState('1'),[prob,setProb]=useState('0.1'),[steps,setSteps]=useState('200');
 const [instructions,setInstructions]=useState('Preparar cotización para revisión humana.'),[file,setFile]=useState(null),[dataOrigin,setDataOrigin]=useState('synthetic');
 async function refresh(){const [p,c]=await Promise.all([catalog('products/quotable?limit=100'),catalog('capacity/resources?limit=100')]);
  setProducts(p);setResources(c);setProduct(v=>v||p[0]?.id||'');setResource(v=>v||c[0]?.id||'');
  const [m,q,e]=await Promise.all([owner?api('models'):Promise.resolve([]),owner?api('quality'):Promise.resolve([]),api('runs')]);
  setModels(m);setQuality(q);setRuns(e);
 }
 useEffect(()=>{void refresh().catch(e=>setMessage(e.message))},[owner]);
 async function run(fn){setBusy(true);setMessage('');try{const result=await fn();if(result)setR(result);await refresh();}catch(e){setMessage(e.message)}finally{setBusy(false)}}
 const base={product_id:product,resource_id:resource,quantity,requested_date:due};
 const action=tab==='forecast'?'forecast':tab==='optimization'?'optimize':tab==='agent'?'agent/prepare':'twin';
 async function submit(e){e.preventDefault();if(!product)return;await run(()=>{
  if(tab==='forecast')return api(action,'POST',{...base,resource_id:resource||null});
  if(tab==='optimization')return api(action,'POST',{...base,shift_minutes:480});
  if(tab==='agent')return api(action,'POST',{kind,product_id:product,quantity,customer_text:instructions});
  return api(action,'POST',{product_id:product,resource_id:resource,quantity,
   seed:Number(seed),shifts:Number(shifts),runs:Number(steps),interruption_probability:Number(prob)});
 })}
 async function train(e){e.preventDefault();if(!owner||!file)return;
  await run(async()=>{
   if(file.size>60000)throw Error('Máximo 60 KB de JSONL');
   const text=await file.text();let observations;
   try{observations=text.trim().startsWith('[')?JSON.parse(text):text.trim().split(/\r?\n/).filter(Boolean).map(JSON.parse)}
   catch{throw Error('JSONL inválido')}
   if(!Array.isArray(observations)||observations.length<30||observations.length>200)throw Error('30–200 observaciones etiquetadas');
   if(!window.confirm('¿Entrenar candidato exclusivamente con las observaciones indicadas, sin desplegarlo?'))return;
   return api('models/train','POST',{observations,data_origin:dataOrigin,confirm:true});
  });}
 async function approve(m,what){if(!owner||!window.confirm(`¿${what==='promote'?'Aprobar despliegue':'Restaurar versión archivada'} ${m.version}?`))return;
  await run(()=>api(`models/${m.id}/${what}`,'POST',{confirm:true}));}
 const headings=[['optimization','Escenarios'],['forecast','Pronóstico'],['agent','Agente'],['twin','Gemelo digital'],['models','Modelos'],['quality','Calidad'],['runs','Evidencia']];
 return <section className="panel mg-hub"><div className="panel-heading"><div><h2>IA avanzada</h2>
 <p>Evaluación temporal, alternativas factibles y agentes supervisados. Nada modifica pedidos, compras o precios.</p></div><span className="soft-label">Análisis supervisado</span></div>
 <div className="mg-tabs">{headings.map(([k,t])=><button key={k} type="button" className={tab===k?'primary':'outline'} onClick={()=>{setTab(k);setR(null)}}>{t}</button>)}</div>
 {message&&<p role="status" className="tiny">{message}</p>}
 {['optimization','forecast','agent','twin'].includes(tab)&&<Part title={headings.find(x=>x[0]===tab)?.[1]} note="Todas las estimaciones son orientativas. El usuario debe revisar el catálogo, la capacidad y los límites antes de decidir.">
 <form className="mg-form" onSubmit={submit}><div className="mg-row"><label>Producto<select value={product} required onChange={e=>setProduct(e.target.value)}>
 <option value="">Seleccionar</option>{products.map(p=><option key={p.id} value={p.id}>{p.name} · {p.sku}</option>)}</select></label>
 {tab!=='agent'&&<label>Recurso<select value={resource} required={tab!=='forecast'} onChange={e=>setResource(e.target.value)}>
 <option value="">Sin recurso</option>{resources.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>}
 <label>Cantidad<input type="number" min="0.001" step="0.001" value={quantity} required onChange={e=>setQuantity(e.target.value)}/></label>
 {['forecast','optimization'].includes(tab)&&<label>Fecha solicitada<input type="date" value={due} required={tab==='optimization'} onChange={e=>setDue(e.target.value)}/></label>}</div>
 {tab==='agent'&&<><label>Tipo de borrador<select value={kind} onChange={e=>setKind(e.target.value)}><option value="quote_draft">Cotización</option><option value="task_draft">Tarea</option></select></label>
 <label>Texto externo no confiable (solo contexto)<textarea value={instructions} rows="2" maxLength="1000" onChange={e=>setInstructions(e.target.value)}/></label></>}
 {tab==='twin'&&<div className="mg-row"><label>Turnos<input type="number" min="1" max="3" value={shifts} onChange={e=>setShifts(e.target.value)}/></label>
 <label>Interrupciones asumidas (0–0.5)<input type="number" min="0" max="0.5" step="0.01" value={prob} onChange={e=>setProb(e.target.value)}/></label>
 <label>Simulaciones<input type="number" min="100" max="500" value={steps} onChange={e=>setSteps(e.target.value)}/></label>
 <label>Semilla<input type="number" min="0" value={seed} onChange={e=>setSeed(e.target.value)}/></label></div>}
 <button type="submit" disabled={busy||!product||(tab!=='agent'&&tab!=='forecast'&&!resource)} className="primary">{busy?'Calculando…':tab==='optimization'?'Comparar tres opciones':tab==='forecast'?'Estimar con incertidumbre':tab==='agent'?'Preparar borrador seguro':'Simular Monte Carlo'}</button></form>
 {r&&<><p className="tiny">Evidencia {r.id?.slice(0,8)} · versión {r.model_version} · sin efectos operativos.</p>
 {tab==='optimization'&&r.result?.alternatives?<div className="mg-metrics">{r.result.alternatives.map(x=><div key={x.alternative}>
 <small>{x.alternative} · {x.due_date}</small><strong>{x.feasible?'FACTIBLE':'RESTRICCIONES'}</strong>
 <p>Margen bruto: ${x.estimated_gross_margin_mxn}</p><p className="tiny">{x.restrictions.join(', ')||'Sin restricciones conocidas'}</p>
 <p className="tiny">Duración: {x.schedule.total_estimated_minutes} minutos</p></div>)}</div>:null}
 <Result value={r.result}/></>}
 </Part>}
 {tab==='models'&&<Part title="Registro y entrenamiento temporal" note="Solo propietario. El conjunto sintético no puede activar versiones. El entrenamiento utiliza fecha de creación, datos disponibles entonces y etiqueta real de duración; el test permanece separado.">
 {!owner?<p>Solo el propietario puede administrar modelos.</p>:<>
 <form className="mg-form" onSubmit={train}><label>Archivo JSONL etiquetado (30–200 filas; máximo 60 KB)<input type="file" accept=".jsonl,.json" onChange={e=>setFile(e.target.files?.[0]||null)}/></label>
 <label>Origen<select value={dataOrigin} onChange={e=>setDataOrigin(e.target.value)}><option value="synthetic">Sintético (solo pruebas)</option><option value="real_reviewed">Real revisado (requiere evidencia)</option></select></label>
 <button className="primary" disabled={!file||busy}>Evaluar y registrar candidato, SIN desplegar</button></form>
 {models.map(m=><div className="mg-item" key={m.id}><b>{m.version}</b> · {m.status} · {m.engine_kind}
 <p className="tiny">Feature {m.feature_version} · SHA {m.config_sha256.slice(0,18)} · origen {m.metrics.data_origin||'no evaluado'}</p>
 {m.metrics.test&&<p className="tiny">TEST MAE candidato: {m.metrics.test.candidate.MAE_minutes} / baseline: {m.metrics.test.baseline.MAE_minutes}; F1: {m.metrics.test.candidate.F1}; prevalencia: {m.metrics.test.candidate.prevalence}</p>}
 {m.status==='candidate'&&<button className="outline" disabled={busy||m.synthetic_not_real} onClick={()=>approve(m,'promote')}>Evaluar y aprobar despliegue</button>}
 {m.status==='archived'&&<button className="outline" disabled={busy} onClick={()=>approve(m,'rollback')}>Restaurar versión</button>}</div>)}
 </>}
 <Result value={r}/></Part>}
 {tab==='quality'&&<Part title="Monitoreo por versión" note="Cuenta revisiones, campos corregidos y agregados; no muestra texto de clientes. Cambios de volumen no son pruebas de drift estadístico.">
 {owner?<><button className="primary" disabled={busy} onClick={()=>run(()=>api('quality/refresh','POST',{}))}>Actualizar estadísticas</button>
 {quality.map(x=><div key={x.id} className="mg-item"><b>{x.version}</b><Result value={x.statistics}/></div>)}</>:<p>Solo propietario.</p>}
 <Result value={r}/></Part>}
 {tab==='runs'&&<Part title="Evidencia inmutable" note="Conserva versión, configuración y cálculo sin ejecutar herramientas sensibles.">
 <button className="outline" onClick={()=>run(async()=>{const x=await api('runs');setRuns(x)})}>Actualizar evidencia</button>
 {runs.map(x=><div key={x.id} className="mg-item"><b>{x.kind} · {x.id.slice(0,8)}</b><p className="tiny">{x.model_version} · SHA {x.configuration_sha256.slice(0,16)}</p>
 <button className="outline" onClick={()=>setR(x)}>Ver cálculos y supuestos</button></div>)}<Result value={r}/></Part>}
 <p className="tiny">Los resultados de evaluación sobre datos sintéticos no validan la exactitud real. El reentrenamiento se mantiene bajo control de aprobación y rollback.</p>
 </section>;
}
