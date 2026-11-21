'use client';
import {useEffect,useState} from 'react';
import DecisionPanel from './DecisionPanel.jsx';
const money=value=>new Intl.NumberFormat('es-MX',{style:'currency',currency:'MXN'}).format(Number(value||0));
const future=()=>{const d=new Date();d.setDate(d.getDate()+14);return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;};
async function get(path){const r=await fetch('/api/data/'+path,{cache:'no-store'});const b=await r.json().catch(()=>({detail:'Respuesta inválida'}));if(!r.ok)throw Error(typeof b.detail==='string'?b.detail:'No se pudo consultar el catálogo');return b;}
export default function ScenarioPanel({order}){
 const [products,setProducts]=useState([]),[resources,setResources]=useState([]);
 const [form,setForm]=useState({product_id:'',resource_id:'',quantity:'',delivery_date:'',start_date:'',resource_daily_capacity:'',unit_price_mxn:''});
 const [result,setResult]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 useEffect(()=>{let alive=true;Promise.all([get('products/quotable?limit=100'),get('capacity/resources?limit=100')])
   .then(([p,r])=>{if(alive){setProducts(p);setResources(r);}})
   .catch(e=>{if(alive)setError(e.message)});return()=>{alive=false};},[]);
 useEffect(()=>{setResult(null);setError('');setForm(s=>({...s,quantity:String(order.reviewed_quantity||''),delivery_date:order.reviewed_due_date||future()}));},[order.id,order.reviewed_quantity,order.reviewed_due_date]);
 const change=(key,value)=>{setForm(s=>({...s,[key]:value}));setResult(null)};
 async function simulate(e){e.preventDefault();setBusy(true);setError('');setResult(null);
   const payload={order_id:order.id,product_id:form.product_id};
   for(const key of ['quantity','delivery_date','start_date','resource_id','resource_daily_capacity','unit_price_mxn'])if(form[key].trim())payload[key]=form[key].trim();
   try{
     const r=await fetch('/api/data/simulations/evaluate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),credentials:'same-origin'});
     const body=await r.json().catch(()=>({detail:'Respuesta inválida'}));
     if(!r.ok){const d=body.detail;throw Error(typeof d==='string'?d:`Error ${r.status}`)}
     setResult(body);
   }catch(e){setError(e.message)}finally{setBusy(false)}
 }
 return <section className="panel sim-panel"><div className="panel-heading"><div><h2>Laboratorio de escenarios</h2><p>Simula supuestos, explica restricciones y calcula alternativas sin guardar cambios.</p></div><span className="soft-label">Solo propietario</span></div>
  <form className="sim-form" onSubmit={simulate}>
   <label>Producto<select required value={form.product_id} onChange={e=>change('product_id',e.target.value)}><option value="">Selecciona un producto</option>{products.map(p=><option key={p.id} value={p.id}>{p.name} · {money(p.price_mxn)}</option>)}</select></label>
   <label>Cantidad hipotética<input required inputMode="decimal" value={form.quantity} onChange={e=>change('quantity',e.target.value)} placeholder="25.000"/></label>
   <label>Fecha de entrega<input type="date" required value={form.delivery_date} onChange={e=>change('delivery_date',e.target.value)}/></label>
   <label>Inicio del periodo<input type="date" value={form.start_date} onChange={e=>change('start_date',e.target.value)} title="Si se omite, se usa la fecha actual de la empresa"/></label>
   <label>Recurso para evaluación<select value={form.resource_id} onChange={e=>{setForm(s=>({...s,resource_id:e.target.value,resource_daily_capacity:''}));setResult(null)}}><option value="">Sin recurso (solo precios y materiales)</option>{resources.map(r=><option key={r.id} value={r.id}>{r.name} · {r.daily_capacity} {r.unit}/día</option>)}</select></label>
   <label>Capacidad hipotética por día<input inputMode="decimal" value={form.resource_daily_capacity} onChange={e=>change('resource_daily_capacity',e.target.value)} placeholder="Sin cambio" disabled={!form.resource_id}/></label>
   <label>Precio unitario hipotético (MXN)<input inputMode="decimal" value={form.unit_price_mxn} onChange={e=>change('unit_price_mxn',e.target.value)} placeholder="Usar precio aprobado"/></label>
   <button className="primary" disabled={busy||!form.product_id||!form.quantity||!form.delivery_date}>{busy?'Evaluando…':'Evaluar sin guardar'}</button>
  </form>
  {error&&<p className="alert" role="alert">{error}</p>}
  {result&&<div className="sim-result"><div className="sim-safe">Vista previa · No se alteraron pedidos, precios ni inventario</div><div className="sim-compare">
    <div><small>Escenario original (catálogo)</small>{result.original?<><strong>{money(result.original.revenue_mxn)}</strong><p>Margen bruto estimado: {money(result.original.estimated_gross_margin_mxn)}</p><p>Entrega registrada: {result.original_delivery_date||'Sin fecha'}</p></>:<p>Este pedido aún no tiene cantidad registrada. No existe una línea base comparable.</p>}</div>
    <div><small>Escenario hipotético</small><strong>{money(result.simulated.revenue_mxn)}</strong><p>Margen bruto estimado: {money(result.simulated.estimated_gross_margin_mxn)}</p></div>
  </div><div className="sim-secondary"><b>Entrega:</b> {result.delivery_date}
     {result.capacity&&<p><b>Capacidad bruta:</b> {result.capacity.available_capacity} {result.capacity.unit} · <b>Faltante:</b> {result.capacity.shortage} · No incluye compromisos existentes.</p>}
     {!result.capacity&&<p>Capacidad sin evaluar: selecciona un recurso.</p>}
     {result.materials.length>0&&<div><h3>Materiales hipotéticos</h3>{result.materials.map(x=><p key={x.material_id}>{x.name}: requiere {x.required} {x.unit}, disponible {x.available}, faltante {x.shortage}</p>)}</div>}
     {!result.recipe_configured&&<p>Sin receta: no es posible evaluar suficiencia del inventario.</p>}
  </div>
   <div className="constraint-box" aria-label="Restricciones y alternativas">
     <h3>Restricciones y alternativa calculada</h3>
     <p className="constraint-state">{result.explanation.status==='blocked'?'Restricciones detectadas':result.explanation.status==='not_evaluable'?'Evaluación incompleta':'Sin faltantes en las dimensiones evaluadas'}</p>
     {result.explanation.constraints.map((c,i)=><article key={`${c.code}-${c.material_id||i}`} className={'constraint-item '+c.severity}>
       <b>{c.title}</b><p>{c.explanation}</p>
       {c.shortage!==null&&<p><strong>Faltante: {c.shortage} {c.unit}</strong>{c.missing_product_units!==null&&<> · Equivale a {c.missing_product_units} unidades del producto</>}</p>}
     </article>)}
     {result.explanation.alternative&&<div className="constraint-alternative">
       <b>Alternativa sin aplicar cambios</b>
       <p>Producibles según límites evaluados: <strong>{result.explanation.alternative.units_possible_by_known_limits}</strong> unidades</p>
       <p>Unidades por reprogramar: <strong>{result.explanation.alternative.units_to_reschedule}</strong></p>
       {result.explanation.alternative.extra_workable_days_for_capacity!==null&&<p>Días laborables adicionales por capacidad: <strong>{result.explanation.alternative.extra_workable_days_for_capacity}</strong></p>}
       {result.explanation.alternative.estimated_delivery_date_by_capacity&&<p>Fecha estimada por capacidad bruta: <strong>{result.explanation.alternative.estimated_delivery_date_by_capacity}</strong></p>}
       <p>{result.explanation.alternative.description}</p>
     </div>}
     <p className="tiny">{result.explanation.caveat}</p>
   </div><p className="tiny">Este cálculo es una aproximación. No constituye una cotización aprobada ni una promesa de entrega.</p></div>}
  {result&&<DecisionPanel order={order} scenario={{
     order_id:order.id,product_id:form.product_id,
     ...(form.quantity.trim()?{quantity:form.quantity.trim()}:{}),
     ...(form.delivery_date.trim()?{delivery_date:form.delivery_date.trim()}:{}),
     ...(form.start_date.trim()?{start_date:form.start_date.trim()}:{}),
     ...(form.resource_id.trim()?{resource_id:form.resource_id.trim()}:{}),
     ...(form.resource_daily_capacity.trim()?{resource_daily_capacity:form.resource_daily_capacity.trim()}:{}),
     ...(form.unit_price_mxn.trim()?{unit_price_mxn:form.unit_price_mxn.trim()}:{}),
  }} onApplied={()=>window.location.reload()}/>}
 </section>;
}
