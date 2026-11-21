'use client';
import {useCallback,useEffect,useRef,useState} from 'react';
import ScenarioPanel from './ScenarioPanel.jsx';
import OperationalOverview from './OperationalOverview.jsx';
import AuditTrail from './AuditTrail.jsx';
import ManagementHub,{JoinInvitation} from './ManagementHub.jsx';
import ExtensionsHub from './ExtensionsHub.jsx';
import AIHub from './AIHub.jsx';
import AdvancedAIHub from './AdvancedAIHub.jsx';

const STATES={draft:'Borrador',pending:'Pendiente',confirmed:'Confirmado',in_progress:'En proceso',completed:'Completado',cancelled:'Cancelado'};
const MONEY=new Intl.NumberFormat('es-MX',{style:'currency',currency:'MXN'});
const money=x=>MONEY.format(Number(x||0));
const dt=x=>x?new Date(x).toLocaleString('es-MX',{dateStyle:'medium',timeStyle:'short'}):'—';
const short=x=>x?x.slice(0,8):'—';
const emptyFilters={q:'',status:'',date_from:'',date_to:'',only_mine:false};
async function json(url,options){
  const response=await fetch(url,{credentials:'same-origin',cache:'no-store',...options});
  const body=await response.json().catch(()=>({detail:'Respuesta inválida del servidor'}));
  if(!response.ok){const e=new Error(body.detail||`Error ${response.status}`);e.status=response.status;throw e;}
  return body;
}

export default function Dashboard(){
  const [person,setPerson]=useState(undefined);
  const [login,setLogin]=useState({organization_id:'',email:'',password:''});
  const [loginBusy,setLoginBusy]=useState(false);
  const [error,setError]=useState('');
  const [pageError,setPageError]=useState('');
  const [filters,setFilters]=useState(emptyFilters);
  const [draft,setDraft]=useState(emptyFilters);
  const [offset,setOffset]=useState(0);
  const [orders,setOrders]=useState({items:[],total:0,has_more:false});
  const [chosen,setChosen]=useState(null);
  const [quotes,setQuotes]=useState([]);
  const [history,setHistory]=useState([]);
  const [documents,setDocuments]=useState({});
  const [lastSync,setLastSync]=useState(null);
  const [loading,setLoading]=useState(false);
  const sequence=useRef(0);
  const chosenRef=useRef(null);
  useEffect(()=>{chosenRef.current=chosen;},[chosen]);

  const reload=useCallback(async({silent=false}={})=>{
    const ticket=++sequence.current;
    if(!silent)setLoading(true);
    const params=new URLSearchParams({limit:'10',offset:String(offset)});
    for(const [key,value] of Object.entries(filters))if(value!==''&&value!==false)params.set(key,String(value));
    try{
      const result=await json('/api/data/orders/search?'+params.toString());
      if(ticket!==sequence.current)return;
      setOrders(result);
      setPageError('');
      const orderId=chosenRef.current;
      if(orderId){
        const match=result.items.find(o=>o.id===orderId);
        if(match)setChosen(orderId);
        const details=await Promise.all([
          json('/api/data/quotes?order_id='+encodeURIComponent(orderId)),
          json('/api/data/orders/'+orderId+'/history')
        ]);
        if(ticket!==sequence.current)return;
        setQuotes(details[0]);setHistory(details[1]);
        const metas=await Promise.all(details[0].filter(q=>q.status==='approved').map(async q=>{
          try{return [q.id,await json('/api/data/quotes/'+q.id+'/document')];}
          catch(e){return [q.id,null];}
        }));
        if(ticket!==sequence.current)return;
        setDocuments(Object.fromEntries(metas));
      }
      setLastSync(new Date());
    }catch(e){
      if(ticket!==sequence.current)return;
      if(e.status===401)setPerson(null);
      setPageError(e.message);
    }finally{if(ticket===sequence.current)setLoading(false);}
  },[filters,offset]);

  useEffect(()=>{
    let active=true;
    json('/api/auth/session').then(p=>{if(active)setPerson(p);})
      .catch(()=>{if(active)setPerson(null);});
    return()=>{active=false;};
  },[]);

  useEffect(()=>{
    if(!person)return;
    reload();
    const timer=setInterval(()=>{if(document.visibilityState==='visible')reload({silent:true});},10000);
    return()=>{clearInterval(timer);sequence.current++;};
  },[person,reload]);

  async function signIn(e){
    e.preventDefault();setError('');setLoginBusy(true);
    try{
      await json('/api/auth/session',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(login)});
      setPerson(await json('/api/auth/session'));
      setLogin(x=>({...x,password:''}));
    }catch(e){setError(e.message);}finally{setLoginBusy(false);}
  }
  async function logout(){
    await fetch('/api/auth/session',{method:'DELETE',credentials:'same-origin'}).catch(()=>{});
    sequence.current++;setPerson(null);setOrders({items:[],total:0,has_more:false});setChosen(null);
    setQuotes([]);setHistory([]);setDocuments({});setError('');
  }
  function openOrder(id){
    setChosen(id);chosenRef.current=id;
    setQuotes([]);setHistory([]);setDocuments({});
    // La selección no debe esperar al siguiente ciclo periódico.
    sequence.current++;
    setLoading(true);
    Promise.all([json('/api/data/quotes?order_id='+encodeURIComponent(id)),json('/api/data/orders/'+id+'/history')])
      .then(async ([q,h])=>{
        if(chosenRef.current!==id)return;
        setQuotes(q);setHistory(h);
        const metadata=await Promise.all(q.filter(x=>x.status==='approved').map(async x=>{
          try{return [x.id,await json('/api/data/quotes/'+x.id+'/document')];}
          catch{return [x.id,null];}
        }));
        if(chosenRef.current===id)setDocuments(Object.fromEntries(metadata));
        setPageError('');
      }).catch(e=>{if(e.status===401)setPerson(null);setPageError(e.message);})
      .finally(()=>setLoading(false));
  }
  const current=orders.items.find(o=>o.id===chosen);
  if(person===undefined)return <main className="center"><div className="spinner"/>Comprobando sesión…</main>;
  if(!person)return <main className="login-layout"><div className="login-panel"><div className="eyebrow">NEXO AI · Plataforma empresarial</div><h1>Tu operación, en un solo lugar.</h1><p>Consulta desde la web los pedidos y cotizaciones creados en tu iPhone. Los datos permanecen en FastAPI y Neon.</p><form onSubmit={signIn} className="login-form"><label>Identificador de la empresa <input required autoComplete="off" value={login.organization_id} onChange={e=>setLogin(x=>({...x,organization_id:e.target.value.trim()}))} placeholder="UUID de la organización"/></label><label>Correo electrónico<input required type="email" autoComplete="username" value={login.email} onChange={e=>setLogin(x=>({...x,email:e.target.value}))} placeholder="correo@empresa.com"/></label><label>Contraseña<input required type="password" autoComplete="current-password" value={login.password} onChange={e=>setLogin(x=>({...x,password:e.target.value}))}/></label>{error&&<div className="alert" role="alert">{error}</div>}<button className="primary" disabled={loginBusy}>{loginBusy?'Validando…':'Entrar al panel'}</button></form><p className="tiny">Sesión de 15 minutos. Nunca almacenamos tu contraseña en el navegador.</p><JoinInvitation/></div><div className="login-art"><span>01 / SINCRONIZACIÓN</span><div className="ornament">N<span>✦</span></div><h2>Lo que guardas en móvil, aparece aquí.</h2><p>Sin copiar datos. Sin segundas bases. Con permisos por organización.</p></div></main>;
  return <main className="shell">
    <aside className="sidebar"><div className="brand">N<span>✦</span>XO<span className="brand-sub">AI</span></div><div className="side-section">ESPACIO DE TRABAJO</div><div className="nav-active">▦ <span>Pedidos y cotizaciones</span></div><div className="side-bottom"><div className="account"><b>{person.email}</b><small>{person.role==='owner'?'Propietario':'Operador'}</small></div><button className="ghost" onClick={logout}>Cerrar sesión</button></div></aside>
    <div className="content"><header className="topbar"><div><div className="eyebrow">OPERACIONES / SINCRONIZACIÓN WEB–MÓVIL</div><h1>Centro de pedidos</h1><p>Información compartida en tiempo real por consultas periódicas a FastAPI + Neon.</p></div><div className="sync-area"><div className="sync-indicator"><span className="dot"/>{lastSync?'Actualizado '+dt(lastSync):'Sin sincronizar'}</div><button onClick={()=>reload()} disabled={loading} className="outline">{loading?'Actualizando…':'↻  Actualizar'}</button></div></header>
      {pageError&&<div className="alert" role="alert">{pageError}</div>}
      <section className="stats"><div className="stat"><span>Coincidencias</span><strong>{orders.total}</strong><small>Según tus filtros</small></div><div className="stat"><span>En esta página</span><strong>{orders.items.length}</strong><small>Máximo 10 solicitudes</small></div><div className="stat"><span>Origen</span><strong>Neon</strong><small>Sin duplicación de datos</small></div><div className="stat"><span>Actualización</span><strong>10 s</strong><small>Y bajo demanda</small></div></section>
      <OperationalOverview/>
      <ManagementHub owner={person.role==='owner'} orders={orders.items}/>
      <section className="panel"><div className="panel-heading"><div><h2>Solicitudes</h2><p>Busca y filtra pedidos creados en la app móvil.</p></div><span className="soft-label">Pedidos sincronizados</span></div><form className="filters" onSubmit={e=>{e.preventDefault();setChosen(null);chosenRef.current=null;setQuotes([]);setHistory([]);setOffset(0);setFilters({...draft});}}><label>Buscar texto<input value={draft.q} onChange={e=>setDraft(s=>({...s,q:e.target.value}))} placeholder="Productos, cliente, pedido…" maxLength="200"/></label><label>Estado<select value={draft.status} onChange={e=>setDraft(s=>({...s,status:e.target.value}))}><option value="">Todos los estados</option>{Object.entries(STATES).map(([v,t])=><option value={v} key={v}>{t}</option>)}</select></label><label>Desde<input type="date" value={draft.date_from} onChange={e=>setDraft(s=>({...s,date_from:e.target.value}))}/></label><label>Hasta<input type="date" value={draft.date_to} onChange={e=>setDraft(s=>({...s,date_to:e.target.value}))}/></label><label className="check"><input type="checkbox" checked={draft.only_mine} onChange={e=>setDraft(s=>({...s,only_mine:e.target.checked}))}/> Solo mis pedidos</label><button className="primary" type="submit">Aplicar filtros</button></form>
        <div className="table-scroll"><table><thead><tr><th>PEDIDO</th><th>CREADO</th><th>ESTADO</th><th>ORIGEN</th><th></th></tr></thead><tbody>{orders.items.map(o=><tr key={o.id} className={chosen===o.id?'selected':''}><td><div className="order-id">#{short(o.id)}</div><div className="truncate" title={o.raw_text}>{o.raw_text}</div></td><td>{dt(o.created_at)}</td><td><span className={'state '+o.status}>{STATES[o.status]||o.status}</span></td><td>{o.source==='manual'?'Manual':'Audio'}</td><td><button className="link" onClick={()=>openOrder(o.id)}>Ver detalle →</button></td></tr>)}{orders.items.length===0&&<tr><td colSpan="5" className="no-results">No hay pedidos para estos filtros.</td></tr>}</tbody></table></div><footer className="pagination"><span>{orders.total===0?'0 resultados':`${offset+1}–${Math.min(offset+orders.items.length,orders.total)} de ${orders.total}`}</span><div><button className="outline" disabled={offset===0} onClick={()=>{setChosen(null);chosenRef.current=null;setOffset(x=>Math.max(0,x-10));}}>Anterior</button><button className="outline" disabled={!orders.has_more} onClick={()=>{setChosen(null);chosenRef.current=null;setOffset(x=>x+10);}}>Siguiente</button></div></footer></section>
      {chosen&&<section className="detail-layout"><div className="panel"><div className="panel-heading"><div><h2>Detalle de pedido <span className="muted">#{short(chosen)}</span></h2><p>{current?.raw_text||'Consulta desde la API compartida'}</p></div><button className="outline" onClick={()=>{setChosen(null);chosenRef.current=null;}}>Cerrar</button></div><div className="detail-fields"><div><span>Estado</span><strong>{STATES[current?.status]||'—'}</strong></div><div><span>Cantidad corregida</span><strong>{current?.reviewed_quantity??'—'}</strong></div><div><span>Fecha de entrega</span><strong>{current?.reviewed_due_date||'—'}</strong></div><div><span>Versión de revisión</span><strong>{current?.review_revision??'—'}</strong></div></div><h3>Historial de estados</h3><div className="timeline">{history.length===0&&<p className="muted">Sin transiciones registradas.</p>}{history.map((e,i)=><div className="history-item" key={e.id||i}><b>{STATES[e.from_status]||e.from_status||'Inicio'} → {STATES[e.to_status]||e.to_status}</b><small>{dt(e.created_at||e.changed_at)} · {short(e.actor_user_id||e.changed_by_user_id)}</small></div>)}</div></div><div className="panel"><div className="panel-heading"><div><h2>Cotizaciones</h2><p>Versiones creadas y aprobadas desde móvil.</p></div><span className="soft-label">Costeo y documentos</span></div>{quotes.length===0&&<div className="empty-quote">Este pedido todavía no tiene cotizaciones.</div>}{quotes.map(q=><article className="quote" key={q.id}><div className="quote-head"><strong>Versión {q.version}</strong><span className={'state '+(q.status==='approved'?'approved':'draft')}>{q.status==='approved'?'Aprobada':'Borrador'}</span></div><div className="quote-price">{money(q.total)} <small>MXN</small></div><div className="quote-math"><span>Subtotal {money(q.subtotal)}</span><span>Descuento {money(q.discount_amount)}</span><span>Impuesto {money(q.tax_amount)}</span></div><div className="line-table">{q.items.map((line,i)=><div key={i}><span>{line.product_name} · {line.quantity} {line.unit}</span><b>{money(line.line_subtotal)}</b></div>)}</div>{documents[q.id]&&<div className="document"><div><b>PDF emitido</b><small>{documents[q.id].folio} · Vigencia {documents[q.id].valid_until}</small></div><a className="outline" href={'/api/data/quotes/'+q.id+'/pdf'} download>Descargar PDF</a></div>}{q.status==='approved'&&!documents[q.id]&&<p className="tiny">Esta cotización está aprobada; aún no se ha emitido su PDF.</p>}</article>)}</div></section>}
      {chosen&&person.role==='owner'&&<AuditTrail orderId={chosen}/>}
      {chosen&&current&&person.role==='owner'&&<ScenarioPanel order={current}/>}
      <ExtensionsHub owner={person.role==='owner'}/>
      <AIHub/>
      <AdvancedAIHub owner={person.role==='owner'}/>
      <footer className="footer">NEXO AI · Consultas autenticadas · Datos de la misma API · No se crean copias desde la web</footer>
    </div>
  </main>;
}
