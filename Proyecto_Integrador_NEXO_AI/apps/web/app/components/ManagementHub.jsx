'use client';
import {useEffect,useState} from 'react';
const ROOT='/api/management/';
const nowDate=()=>new Date().toLocaleDateString('en-CA');
async function api(path,method='GET',body){
 const r=await fetch(ROOT+path,{method,credentials:'same-origin',cache:'no-store',
  ...(body!==undefined?{headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})});
 const data=await r.json().catch(()=>({detail:'Respuesta inválida'}));
 if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:'Error '+r.status);
 return data;
}
function Feedback({text}){return text?<p className="notice" role="status">{text}</p>:null}
function Shell({title,description,children}){return <div className="mg-section"><h3>{title}</h3><p className="muted">{description}</p>{children}</div>}

export function JoinInvitation(){
 const [token,setToken]=useState(''),[password,setPassword]=useState(''),[message,setMessage]=useState(''),[busy,setBusy]=useState(false);
 async function join(e){e.preventDefault();setBusy(true);setMessage('');try{
 const result=await api('collaborators/invitations/accept','POST',{token:token.trim(),password});
 setMessage('Cuenta activada para '+result.email+'. Inicia sesión con el identificador de tu empresa.');setToken('');setPassword('');
 }catch(e){setMessage(e.message)}finally{setBusy(false)}}
 return <details className="join-form"><summary>Tengo una invitación para colaborar</summary>
  <form className="mg-form" onSubmit={join}><label>Token de invitación<input value={token} onChange={e=>setToken(e.target.value)} required autoComplete="off"/></label>
  <label>Crea una contraseña (mínimo 12 caracteres)<input type="password" autoComplete="new-password" minLength={12} required value={password} onChange={e=>setPassword(e.target.value)}/></label>
  <button className="primary" disabled={busy}>{busy?'Activando…':'Aceptar invitación'}</button></form><Feedback text={message}/></details>;
}

function UserRow({person,all,onChange}){
 const [selection,setSelection]=useState(person.permissions||[]),[msg,setMsg]=useState('');
 const owner=person.role==='owner';
 async function updatePerm(){try{await api('collaborators/users/'+person.id+'/permissions','PATCH',{permissions:selection});setMsg('Permisos guardados');onChange();}catch(e){setMsg(e.message)}}
 async function setActive(){try{await api('collaborators/users/'+person.id+'/suspension','PATCH',{is_active:!person.is_active});setMsg('Estado actualizado');onChange()}catch(e){setMsg(e.message)}}
 return <div className="mg-item"><div className="mg-flex"><div><strong>{person.email}</strong><p className="tiny">{person.role} · {person.is_active?'Activo':'Suspendido'}</p></div>
 {!owner&&<button className="outline" onClick={setActive}>{person.is_active?'Suspender':'Reactivar'}</button>}</div>
 {!owner&&<details><summary>Editar permisos específicos</summary><div className="mg-checks">{all.map(p=><label key={p} className="mg-check"><input type="checkbox" checked={selection.includes(p)} onChange={e=>setSelection(prev=>e.target.checked?[...prev,p]:prev.filter(x=>x!==p))}/>{p}</label>)}</div><button className="outline" onClick={updatePerm}>Guardar permisos</button></details>}<Feedback text={msg}/></div>
}
function Team(){
 const [users,setUsers]=useState([]),[all,setAll]=useState([]),[email,setEmail]=useState(''),[perms,setPerms]=useState(['orders.read']),
 [secret,setSecret]=useState(''),[message,setMessage]=useState('');
 async function load(){try{const [u,p]=await Promise.all([api('collaborators/users'),api('collaborators/permissions')]);setUsers(u);setAll(p);}catch(e){setMessage(e.message)}}
 useEffect(()=>{void load()},[]);
 async function create(e){e.preventDefault();try{const data=await api('collaborators/invitations','POST',{email,permissions:perms,expires_hours:24});setSecret(data.token);setMessage('Invitación creada: '+email+'. Comparte el token por un canal privado; no se envió automáticamente.');setEmail('');}catch(e){setMessage(e.message)}}
 return <Shell title="Equipo y permisos" description="Invitaciones de 24 horas, activación por token y suspensión de sesiones.">
 <form className="mg-form" onSubmit={create}><label>Correo del colaborador<input type="email" required value={email} onChange={e=>setEmail(e.target.value)}/></label>
 <div className="mg-checks">{all.map(p=><label className="mg-check" key={p}><input type="checkbox" checked={perms.includes(p)} onChange={e=>setPerms(prev=>e.target.checked?[...prev,p]:prev.filter(x=>x!==p))}/>{p}</label>)}</div>
 <button className="primary">Crear invitación de un solo uso</button></form>
 {secret&&<div className="notice"><strong>Token visible una sola vez</strong><p className="mg-token">{secret}</p><button className="outline" onClick={()=>navigator.clipboard.writeText(secret)}>Copiar token</button></div>}
 <Feedback text={message}/>
 <h4>Colaboradores</h4>{users.map(u=><UserRow key={u.id} person={u} all={all} onChange={load}/>)}
 </Shell>;
}
function Purchasing({owner}){
 const [suppliers,setSuppliers]=useState([]),[materials,setMaterials]=useState([]),[requests,setRequests]=useState([]),
 [sName,setSName]=useState(''),[sCode,setSCode]=useState(''),[supplier,setSupplier]=useState(''),[material,setMaterial]=useState(''),
 [quantity,setQuantity]=useState(''),[unitCost,setUnitCost]=useState(''),[note,setNote]=useState(''),[msg,setMsg]=useState('');
 async function load(){try{const [s,m,r]=await Promise.all([api('purchasing/suppliers'),api('materials?limit=50'),api('purchasing/requests')]);
 setSuppliers(s);setMaterials(m);setRequests(r);setSupplier(x=>x||s[0]?.id||'');setMaterial(x=>x||m[0]?.id||'')
 }catch(e){setMsg(e.message)}}
 useEffect(()=>{void load()},[]);
 async function submitSupplier(e){e.preventDefault();try{await api('purchasing/suppliers','POST',{code:sCode,name:sName});setMsg('Proveedor creado');setSName('');setSCode('');await load()}catch(e){setMsg(e.message)}}
 async function submitPurchase(e){e.preventDefault();try{await api('purchasing/requests','POST',{supplier_id:supplier,material_id:material,quantity,unit_cost_mxn:unitCost});setMsg('Solicitud pendiente de aprobación');setQuantity('');await load()}catch(e){setMsg(e.message)}}
 async function decide(id,decision){try{await api('purchasing/requests/'+id+'/decision','POST',{decision,note:note||'Decisión explícita del propietario'});setMsg('Decisión registrada');await load()}catch(e){setMsg(e.message)}}
 return <Shell title="Proveedores y compras" description="La aprobación no incrementa automáticamente las existencias; la recepción es una operación separada.">
 {owner&&<form className="mg-form" onSubmit={submitSupplier}><h4>Alta de proveedor</h4><div className="mg-row"><input required placeholder="Código (ej. PROV01)" value={sCode} onChange={e=>setSCode(e.target.value)}/><input required placeholder="Razón social" value={sName} onChange={e=>setSName(e.target.value)}/><button className="primary">Crear proveedor</button></div></form>}
 <form className="mg-form" onSubmit={submitPurchase}><h4>Solicitar abastecimiento</h4><div className="mg-row"><label>Proveedor<select required value={supplier} onChange={e=>setSupplier(e.target.value)}>{suppliers.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
 <label>Material<select required value={material} onChange={e=>setMaterial(e.target.value)}>{materials.map(m=><option key={m.id} value={m.id}>{m.name} ({m.unit})</option>)}</select></label>
 <label>Cantidad<input required inputMode="decimal" value={quantity} onChange={e=>setQuantity(e.target.value)} placeholder="10.000"/></label>
 <label>Costo unitario MXN<input required inputMode="decimal" value={unitCost} onChange={e=>setUnitCost(e.target.value)} placeholder="25.50"/></label></div>
 <button className="primary" disabled={!supplier||!material}>Solicitar compra</button></form>
 {owner&&<label>Nota de decisión<input value={note} onChange={e=>setNote(e.target.value)} placeholder="Motivo de la aprobación/rechazo"/></label>}
 <Feedback text={msg}/><h4>Solicitudes registradas</h4>{requests.map(r=><div key={r.id} className="mg-item"><div className="mg-flex"><div><strong>{r.quantity} unidades · ${r.total_mxn} MXN</strong><p className="tiny">{r.status} · {r.id.slice(0,8)}</p></div>
 {owner&&r.status==='pending'&&<div className="mg-row"><button className="outline" onClick={()=>decide(r.id,'approve')}>Aprobar</button><button className="outline" onClick={()=>decide(r.id,'reject')}>Rechazar</button></div>}</div></div>)}</Shell>;
}
function Calendar({owner,orders}){
 const [day,setDay]=useState(nowDate()),[data,setData]=useState(null),[resource,setResource]=useState(''),[order,setOrder]=useState(''),[qty,setQty]=useState(''),[msg,setMsg]=useState('');
 async function load(){try{const d=await api('scheduling/calendar?day='+encodeURIComponent(day));setData(d);setResource(x=>x||d.resources[0]?.resource_id||'')}catch(e){setMsg(e.message)}}
 useEffect(()=>{void load()},[day]);
 async function allocate(e){e.preventDefault();try{await api('scheduling/allocations','POST',{resource_id:resource,order_id:order,day,quantity:qty});setMsg('Asignación registrada');setQty('');await load()}catch(e){setMsg(e.message)}}
 async function remove(id){try{await api('scheduling/allocations/'+id,'DELETE');setMsg('Asignación cancelada');await load()}catch(e){setMsg(e.message)}}
 return <Shell title="Calendario de carga" description="Ocupación y capacidad restante por recurso y día, solo para asignaciones explícitas."><label>Fecha <input type="date" value={day} onChange={e=>setDay(e.target.value)}/></label>
 <Feedback text={msg}/>{data?.resources.map(r=><div className="mg-item" key={r.resource_id}><strong>{r.resource_name}</strong><p>{r.occupied} / {r.capacity} {r.unit} ocupadas · <strong>{r.remaining} restantes</strong></p>
 {!r.working&&<p className="tiny">Día no laborable o bloqueado</p>}{r.allocations.map(a=><p className="tiny" key={a.id}>Pedido {a.order_id.slice(0,8)} · {a.quantity} {r.unit} {owner&&<button className="link" onClick={()=>remove(a.id)}>Cancelar</button>}</p>)}</div>)}
 {owner&&<form onSubmit={allocate} className="mg-form"><h4>Asignar un pedido confirmado</h4><div className="mg-row"><label>Recurso<select value={resource} onChange={e=>setResource(e.target.value)}>{data?.resources.map(r=><option key={r.resource_id} value={r.resource_id}>{r.resource_name}</option>)}</select></label>
 <label>Pedido<select required value={order} onChange={e=>setOrder(e.target.value)}><option value="">Seleccionar…</option>{orders.filter(o=>['confirmed','in_progress'].includes(o.status)).map(o=><option key={o.id} value={o.id}>{o.id.slice(0,8)} · {o.status}</option>)}</select></label>
 <label>Unidades del recurso<input required value={qty} onChange={e=>setQty(e.target.value)} placeholder="1.000"/></label></div><button className="primary" disabled={!resource||!order}>Reservar capacidad</button></form>}
 <p className="tiny">{data?.notice}</p></Shell>;
}
function Notifications(){
 const [prefs,setPrefs]=useState({due_soon:false,risk:false,material_shortage:false}),[entries,setEntries]=useState([]),[msg,setMsg]=useState('');
 async function load(){try{const [p,e]=await Promise.all([api('notifications/preferences'),api('notifications/entries')]);setPrefs(p);setEntries(e);}catch(e){setMsg(e.message)}}
 useEffect(()=>{void load()},[]);
 async function save(){try{await api('notifications/preferences','PUT',prefs);setMsg('Preferencias guardadas')}catch(e){setMsg(e.message)}}
 async function scan(){try{const r=await api('notifications/scan','POST',{});setMsg(`${r.created} nueva(s) alerta(s); ${r.signals_evaluated} eventos evaluados.`);await load()}catch(e){setMsg(e.message)}}
 const labels={due_soon:'Fecha próxima (7 días)',risk:'Riesgo por entrega vencida',material_shortage:'Material insuficiente'};
 return <Shell title="Alertas configurables" description="Alertas internas bajo demanda. No se envían mensajes push ni correos."><div className="mg-checks">
 {Object.entries(labels).map(([k,v])=><label className="mg-check" key={k}><input type="checkbox" checked={prefs[k]} onChange={e=>setPrefs(x=>({...x,[k]:e.target.checked}))}/>{v}</label>)}</div>
 <div className="mg-row"><button className="primary" onClick={save}>Guardar preferencias</button><button className="outline" onClick={scan}>Evaluar alertas ahora</button></div>
 <Feedback text={msg}/><h4>Notificaciones internas</h4>{entries.length===0&&<p className="tiny">No hay alertas emitidas.</p>}{entries.map(e=><div className="mg-item" key={e.id}><strong>{labels[e.kind]||e.kind}</strong><p>{e.message}</p><p className="tiny">{e.created_at||''}</p></div>)}</Shell>;
}
function Reports(){
 const [filters,setFilters]=useState({date_from:'',date_to:'',status:''}),[data,setData]=useState(null),[msg,setMsg]=useState('');
 function query(includeFormat=''){const q=new URLSearchParams();if(includeFormat)q.set('format',includeFormat);Object.entries(filters).forEach(([k,v])=>{if(v)q.set(k,v)});return q.toString()}
 async function load(){try{setData(await api('reports/summary?'+query()));setMsg('Reporte actualizado')}catch(e){setMsg(e.message)}}
 useEffect(()=>{void load()},[]);
 return <Shell title="Informes exportables" description="Reportes de pedidos, cumplimiento y márgenes. Los ingresos corresponden a cotizaciones aprobadas, no a cobros.">
 <div className="mg-row"><label>Desde<input type="date" value={filters.date_from} onChange={e=>setFilters(x=>({...x,date_from:e.target.value}))}/></label><label>Hasta<input type="date" value={filters.date_to} onChange={e=>setFilters(x=>({...x,date_to:e.target.value}))}/></label>
 <label>Estado<select value={filters.status} onChange={e=>setFilters(x=>({...x,status:e.target.value}))}><option value="">Todos</option>{['draft','pending','confirmed','in_progress','completed','cancelled'].map(s=><option key={s} value={s}>{s}</option>)}</select></label></div>
 <div className="mg-row"><button className="primary" onClick={load}>Aplicar filtros</button><a className="outline" href={ROOT+'reports/export?'+query('csv')} download>Exportar CSV</a><a className="outline" href={ROOT+'reports/export?'+query('pdf')} download>Exportar PDF</a></div>
 <Feedback text={msg}/>{data&&<><div className="mg-metrics"><div><small>Pedidos</small><strong>{data.totals.orders}</strong></div><div><small>Completados</small><strong>{data.totals.completed}</strong></div><div><small>Puntuales</small><strong>{data.totals.on_time}</strong></div><div><small>Ingresos aprobados MXN</small><strong>${data.totals.revenue_mxn}</strong></div><div><small>Margen bruto MXN</small><strong>${data.totals.gross_margin_mxn}</strong></div></div>
 <div className="table-scroll"><table><thead><tr><th>Pedido</th><th>Estado</th><th>Cumplimiento</th><th>Ingreso</th></tr></thead><tbody>{data.rows.slice(0,25).map(o=><tr key={o.order_id}><td>{o.order_id.slice(0,8)}</td><td>{o.status}</td><td>{o.compliance}</td><td>${o.revenue_mxn}</td></tr>)}</tbody></table></div><p className="tiny">{data.notice}</p></>}</Shell>;
}
const TABS=[['team','Equipo'],['purch','Compras'],['calendar','Calendario'],['alerts','Alertas'],['reports','Informes']];
export default function ManagementHub({owner,orders=[]}){
 const [tab,setTab]=useState(owner?'team':'alerts');
 return <section className="panel management" aria-label="Gestión empresarial">
  <div className="panel-heading"><div><h2>Centro de gestión</h2><p>Colaboradores, abastecimiento, recursos, alertas e informes sobre la misma organización.</p></div></div>
  <div className="mg-tabs">{TABS.filter(([id])=>owner||!['team'].includes(id)).map(([id,name])=><button type="button" key={id} className={tab===id?'primary':'outline'} onClick={()=>setTab(id)}>{name}</button>)}</div>
  {tab==='team'&&owner&&<Team/>}{tab==='purch'&&<Purchasing owner={owner}/>}{tab==='calendar'&&<Calendar owner={owner} orders={orders}/>}
  {tab==='alerts'&&<Notifications/>}{tab==='reports'&&<Reports/>}
 </section>;
}
