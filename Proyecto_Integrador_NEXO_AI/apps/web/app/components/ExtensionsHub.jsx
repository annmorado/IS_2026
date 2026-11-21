'use client';
import {useEffect,useState} from 'react';
const ROOT='/api/extensions/';
async function api(path,method='GET',body){
 const response=await fetch(ROOT+path,{method,credentials:'same-origin',cache:'no-store',
  ...(body!==undefined?{headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})});
 const data=await response.json().catch(()=>({detail:'Respuesta inválida'}));
 if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail||'HTTP '+response.status));
 return data;
}
function Msg({text}){return text?<p className="notice" role="status">{text}</p>:null}
function Block({title,info,children}){return <div className="mg-section"><h3>{title}</h3><p className="muted">{info}</p>{children}</div>}
function Plans(){
 const [data,setData]=useState(null),[msg,setMsg]=useState('');
 async function load(){try{setData(await api('subscriptions/me'))}catch(e){setMsg(e.message)}}
 useEffect(()=>{void load()},[]);
 async function trial(){if(!window.confirm('¿Activar una prueba única de 7 días? No se efectuará ningún cobro.'))return;
  try{setData(await api('subscriptions/start-trial','POST',{}));setMsg('Prueba activada sin cargos.')}catch(e){setMsg(e.message)}}
 return <Block title="Planes y cuotas" info="Límites mensuales por organización. Los pedidos y cotizaciones existentes siguen disponibles.">
 {data&&<><div className="mg-item"><strong>Plan: {data.plan} · Estado: {data.status}</strong>
  <p>OCR {data.usage.ocr}/{data.limits.ocr} · Planes de agentes {data.usage.agents}/{data.limits.agents} · Mensajes {data.usage.messaging}/{data.limits.messaging}</p>
  <p className="tiny">{data.notice}</p></div>{data.trial_available&&<button className="outline" onClick={trial}>Activar prueba gratuita de 7 días</button>}</>}
 <Msg text={msg}/></Block>;
}
function OCR(){
 const [file,setFile]=useState(null),[items,setItems]=useState([]),[selected,setSelected]=useState(''),
 [fields,setFields]=useState({vendor:'',amount_mxn:'',date:'',reference:'',concept:''}),[msg,setMsg]=useState(''),[busy,setBusy]=useState(false);
 async function load(){try{setItems(await api('documents/ocr/proposals'))}catch(e){setMsg(e.message)}}
 useEffect(()=>{void load()},[]);
 async function upload(e){e.preventDefault();if(!file)return;setBusy(true);setMsg('');
  try{const fd=new FormData();fd.append('file',file);const r=await fetch(ROOT+'documents/ocr/proposals?document_type=invoice',{
   method:'POST',credentials:'same-origin',body:fd});const data=await r.json();if(!r.ok)throw Error(data.detail||'No se pudo leer la foto');
   setMsg('OCR ejecutado: revisa los campos propuestos. No se creó una factura.');setFile(null);await load();selectItem(data);
  }catch(e){setMsg(e.message)}finally{setBusy(false)}}
 function selectItem(item){setSelected(item.id);const f=item.reviewed||item.extracted?.suggested_fields||{};setFields({vendor:f.vendor||'',amount_mxn:f.amount_mxn||'',date:f.date||'',reference:f.reference||'',concept:f.concept||''})}
 async function save(e){e.preventDefault();try{const payload={...Object.fromEntries(Object.entries(fields).filter(([,v])=>v!=='').map(([k,v])=>[k,v])),confirm:true};
  await api('documents/ocr/proposals/'+selected+'/review','POST',payload);setMsg('Revisión humana guardada. Sin escritura en pedidos o inventario.');await load();setSelected('')
 }catch(e){setMsg(e.message)}}
 const item=items.find(x=>x.id===selected);
 return <Block title="OCR con revisión humana" info="Sube JPEG/PNG/WebP (máximo 4 MB). El OCR necesita Tesseract instalado en el servidor FastAPI.">
 <form className="mg-form" onSubmit={upload}><label>Fotografía de factura, nota o etiqueta<input type="file" accept="image/png,image/jpeg,image/webp" required
  onChange={e=>setFile(e.target.files?.[0]||null)}/></label><button className="primary" disabled={busy||!file}>{busy?'Leyendo foto…':'Extraer propuesta, sin guardar operación'}</button></form>
 <Msg text={msg}/><h4>Documentos propuestos</h4>{items.map(x=><button key={x.id} className="outline" onClick={()=>selectItem(x)}>{x.filename} · {x.status} · {Math.round((x.extracted?.confidence||0)*100)}% confianza</button>)}
 {item&&<div className="mg-item"><strong>Texto detectado (solo referencia)</strong><p>{item.extracted.raw_text||'Sin texto'}</p>
 <p className="tiny">Confianza global aproximada: {Math.round((item.extracted.confidence||0)*100)}%. Monto: {item.extracted.field_confidence?.amount_mxn==null?'sin detectar':Math.round(item.extracted.field_confidence.amount_mxn*100)+'%'}; fecha: {item.extracted.field_confidence?.date==null?'sin detectar':Math.round(item.extracted.field_confidence.date*100)+'%'}. No es una probabilidad calibrada. Corrige cada campo.</p>
 {item.status==='proposed'?<form className="mg-form" onSubmit={save}>
 {Object.entries({vendor:'Proveedor',amount_mxn:'Monto MXN',date:'Fecha AAAA-MM-DD',reference:'Referencia',concept:'Concepto'}).map(([k,label])=><label key={k}>{label}<input type={k==='date'?'date':'text'} value={fields[k]} onChange={e=>setFields(p=>({...p,[k]:e.target.value}))}/></label>)}
 <button className="primary">Guardar revisión humana</button></form>:<p>Documento revisado. Ninguna factura ni compra fue creada automáticamente.</p>}</div>}
 </Block>;
}
function Messaging(){
 const [data,setData]=useState(null),[phone,setPhone]=useState(''),[enabled,setEnabled]=useState(false),[msg,setMsg]=useState(''),
 [recipient,setRecipient]=useState(''),[evidence,setEvidence]=useState(''),[consents,setConsents]=useState([]);
 async function load(){try{const x=await api('messaging/configuration');setData(x);setPhone(x.phone_number_id||'');setEnabled(x.enabled);setConsents(await api('messaging/consents'))}catch(e){setMsg(e.message)}}
 useEffect(()=>{void load()},[]);
 async function save(e){e.preventDefault();try{await api('messaging/configuration','PUT',{phone_number_id:phone,enabled});setMsg('Configuración guardada; ningún mensaje enviado.');await load()}catch(e){setMsg(e.message)}}
 async function saveConsent(e){e.preventDefault();if(!window.confirm('¿Confirmas que cuentas con prueba documentada de consentimiento del destinatario?'))return;
 try{await api('messaging/consents','POST',{recipient_e164:recipient,evidence_reference:evidence,valid_days:90,confirm:true});setRecipient('');setEvidence('');setMsg('Consentimiento registrado por 90 días. No se envió ningún mensaje.');await load()}catch(e){setMsg(e.message)}}
 async function revoke(id){if(!window.confirm('¿Revocar el consentimiento?'))return;try{await api('messaging/consents/'+id+'/revoke','POST',{confirm:true});setMsg('Consentimiento revocado');await load()}catch(e){setMsg(e.message)}}
 return <Block title="Mensajería oficial" info="WhatsApp Cloud API. Sin credenciales oficiales específicas de esta empresa y consentimiento, no se envía ningún mensaje.">
 <p className="tiny">Esta etapa configura el canal y valida bloqueos; no configura webhooks ni envíos automáticos.</p>
 <p>{data?.credentials_present?'Credenciales del servidor detectadas':'Sin credenciales oficiales para esta organización'} · {data?.enabled?'Habilitado':'Deshabilitado'}</p>
 <form className="mg-form" onSubmit={save}><label>ID oficial del número de WhatsApp Business<input required pattern="[0-9]{5,40}" value={phone} onChange={e=>setPhone(e.target.value)} placeholder="ID de Meta (no es número telefónico)"/></label>
 <label className="mg-check"><input type="checkbox" checked={enabled} onChange={e=>setEnabled(e.target.checked)}/> Habilitar configuración (no envía nada)</label>
 <button className="primary">Guardar configuración</button></form>
 <form className="mg-form" onSubmit={saveConsent}><h4>Registrar consentimiento acreditado (no envía mensajes)</h4>
 <label>Destinatario E.164<input required pattern="\+[1-9][0-9]{7,14}" value={recipient} onChange={e=>setRecipient(e.target.value)} placeholder="+5215512345678"/></label>
 <label>Referencia de la prueba de consentimiento<input required minLength={10} value={evidence} onChange={e=>setEvidence(e.target.value)} placeholder="Folio de opt-in / registro firmado"/></label>
 <button className="outline">Registrar consentimiento por 90 días</button></form>
 <h4>Consentimientos vigentes y revocados</h4>
 {consents.map(x=><div className="mg-item" key={x.id}>Destinatario terminado en {x.recipient_tail} · {x.active?'Vigente':'Inactivo'}
 {x.active&&<button className="outline" onClick={()=>revoke(x.id)}>Revocar</button>}</div>)}
 <Msg text={msg}/></Block>;
}
function Templates(){
 const [catalog,setCatalog]=useState([]),[active,setActive]=useState(null),[history,setHistory]=useState([]),[selected,setSelected]=useState(''),[msg,setMsg]=useState('');
 async function load(){try{const [c,a,h]=await Promise.all([api('sector-templates/catalog'),api('sector-templates/active'),api('sector-templates/history')]);setCatalog(c);setActive(a);setHistory(h);setSelected(p=>p||c[0]?.code||'')}catch(e){setMsg(e.message)}}
 useEffect(()=>{void load()},[]);
 async function apply(){if(!window.confirm('¿Aplicar esta plantilla solamente a configuraciones futuras? El historial no cambiará.'))return;
  try{const a=await api('sector-templates/apply','POST',{code:selected,confirm:true});setMsg('Plantilla '+a.code+' aplicada en versión '+a.version);await load()}catch(e){setMsg(e.message)}}
 return <Block title="Plantillas por sector" info="Campos sugeridos para futuras operaciones. No modifica los registros históricos ni los precios aprobados.">
 <p>Plantilla activa: <strong>{active?.code||'Sin plantilla'} {active?.version?'v'+active.version:''}</strong></p>
 <label>Elegir sector<select value={selected} onChange={e=>setSelected(e.target.value)}>{catalog.map(x=><option value={x.code} key={x.code}>{x.config.name}</option>)}</select></label>
 {catalog.filter(x=>x.code===selected).map(x=><p className="tiny" key={x.code}>Campos sugeridos: {x.config.fields.join(', ')}</p>)}
 <button className="primary" disabled={!selected} onClick={apply}>Aplicar plantilla con confirmación</button>
 <Msg text={msg}/><h4>Versiones históricas</h4>{history.map((x,i)=><p className="tiny" key={i}>Versión {x.version}: {x.config.name}</p>)}
 </Block>;
}
function Agents(){
 const [kind,setKind]=useState('capacity_planner'),[objective,setObjective]=useState('Evaluar restricciones sin modificar pedidos ni recursos'),
 [items,setItems]=useState([]),[msg,setMsg]=useState('');
 async function load(){try{setItems(await api('agents/workflows'))}catch(e){setMsg(e.message)}}
 useEffect(()=>{void load()},[]);
 async function prepare(e){e.preventDefault();try{await api('agents/prepare','POST',{agent_kind:kind,objective});setMsg('Plan preparado. No se ejecutó ninguna acción externa.');await load()}catch(e){setMsg(e.message)}}
 async function authorize(id){if(!window.confirm('¿Autorizar este plan solamente de lectura? Nunca compra, envía mensajes ni confirma pedidos.'))return;
  try{await api('agents/workflows/'+id+'/authorize','POST',{confirm:true});setMsg('Plan de solo lectura autorizado.');await load()}catch(e){setMsg(e.message)}}
 return <Block title="Agentes supervisados" info="Agentes deterministas que preparan planes y delegan consultas de solo lectura. No usan un modelo de lenguaje ni ejecutan compras o mensajes.">
 <form className="mg-form" onSubmit={prepare}><label>Agente<select value={kind} onChange={e=>setKind(e.target.value)}>
 <option value="capacity_planner">Planificador de capacidad</option><option value="material_advisor">Asesor de materiales</option><option value="followup_drafter">Borrador de seguimiento</option></select></label>
 <label>Objetivo<input required minLength="10" maxLength="300" value={objective} onChange={e=>setObjective(e.target.value)}/></label><button className="primary">Preparar plan sin ejecutar</button></form>
 <Msg text={msg}/>{items.map(x=><div key={x.id} className="mg-item"><strong>{x.agent_kind} · {x.status}</strong>
 <p className="tiny">Motor: {x.engine_version} · Acciones externas: ninguna</p><p>{x.result.observations.join(' ')}</p>
 <p className="tiny">Herramientas: {x.result.steps.map(s=>s.tool+' ('+s.mode+')').join(', ')}</p>
 {x.status==='prepared'&&<button className="outline" onClick={()=>authorize(x.id)}>Autorizar plan de lectura</button>}</div>)}
 </Block>;
}
const TABS=[['plans','Planes'],['ocr','OCR'],['msg','Mensajería'],['templates','Plantillas'],['agents','Agentes']];
export default function ExtensionsHub({owner}){
 const [tab,setTab]=useState('plans');if(!owner)return null;
 return <section className="panel mg-hub"><div className="panel-heading"><div><h2>Inteligencia y extensiones</h2>
 <p>Planes, lectura de documentos, conexiones oficiales y automatización supervisada.</p></div><span className="soft-label">Herramientas integradas</span></div>
 <div className="mg-tabs">{TABS.map(([id,label])=><button type="button" key={id} className={tab===id?'primary':'outline'} onClick={()=>setTab(id)}>{label}</button>)}</div>
 {tab==='plans'&&<Plans/>}{tab==='ocr'&&<OCR/>}{tab==='msg'&&<Messaging/>}{tab==='templates'&&<Templates/>}{tab==='agents'&&<Agents/>}
 </section>;
}
