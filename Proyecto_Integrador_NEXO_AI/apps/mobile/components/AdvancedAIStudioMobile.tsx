/** Mobile read-only plans and human-controlled model monitoring.
 * No app-side action confirms orders, sends messages or buys materials.
 */
import React,{useEffect,useState} from 'react';
import {View,Text,TextInput,Pressable,Alert,StyleSheet,ScrollView} from 'react-native';
type Call=(path:string,method?:string,body?:unknown)=>Promise<any>;
type Item={id:string;name:string;sku?:string};
const C={ink:'#ebf0ff',muted:'#9da9cb',edge:'#293754',bg:'#101b30',accent:'#35c6bd'};
const S=StyleSheet.create({box:{backgroundColor:C.bg,borderRadius:16,borderWidth:1,borderColor:C.edge,padding:12,marginBottom:12},
 text:{color:C.ink,fontSize:14,marginVertical:3},small:{color:C.muted,fontSize:12,marginVertical:4},heading:{color:C.ink,fontSize:18,fontWeight:'700',marginBottom:7},
 row:{flexDirection:'row',flexWrap:'wrap',gap:8,marginVertical:6},chip:{paddingHorizontal:12,paddingVertical:9,borderRadius:10,borderWidth:1,borderColor:C.edge},active:{backgroundColor:'#175c5b',borderColor:C.accent},
 input:{color:C.ink,borderColor:'#475371',borderWidth:1,borderRadius:9,padding:10,marginVertical:6},
 button:{borderRadius:10,padding:12,marginVertical:5,backgroundColor:'#18685f'},label:{color:C.ink,fontWeight:'600'},result:{backgroundColor:'#131f36',padding:10,borderRadius:10,marginTop:8}});
function Chip({title,onPress,chosen=false}:{title:string;onPress:()=>void;chosen?:boolean}){
 return <Pressable accessibilityRole="button" onPress={onPress} style={[S.chip,chosen&&S.active]}><Text style={S.text}>{title}</Text></Pressable>;
}
function Btn({title,onPress,disabled=false}:{title:string;onPress:()=>void;disabled?:boolean}){
 return <Pressable accessibilityRole="button" disabled={disabled} onPress={onPress} style={[S.button,disabled&&{opacity:.4}]}><Text style={S.label}>{title}</Text></Pressable>;
}
function Input({title,value,onChange,keyboardType='default'}:{title:string;value:string;onChange:(s:string)=>void;keyboardType?:'default'|'decimal-pad'|'number-pad'}){
 return <View><Text style={S.small}>{title}</Text><TextInput style={S.input} value={value} onChangeText={onChange} keyboardType={keyboardType} autoCapitalize="none" placeholderTextColor="#64748b"/></View>;
}
const daysAfter=(n:number)=>{const d=new Date();d.setDate(d.getDate()+n);return d.toISOString().slice(0,10)};
export default function AdvancedAIStudioMobile({call}:{call:Call}){
 const [tab,setTab]=useState<'plan'|'agent'|'twin'|'governance'>('plan');
 const [products,setProducts]=useState<Item[]>([]),[resources,setResources]=useState<Item[]>([]);
 const [pid,setPid]=useState(''),[rid,setRid]=useState(''),[quantity,setQuantity]=useState('3'),[due,setDue]=useState(daysAfter(14));
 const [note,setNote]=useState('Preparar cotización revisable'),[draftType,setDraftType]=useState<'quote_draft'|'task_draft'>('quote_draft');
 const [modelList,setModelList]=useState<any[]>([]),[metrics,setMetrics]=useState<any[]>([]),[runs,setRuns]=useState<any[]>([]),[result,setResult]=useState<any>(null),[msg,setMsg]=useState(''),[busy,setBusy]=useState(false);
 const [shifts,setShifts]=useState('1'),[interruptions,setInterruptions]=useState('0.1'),[seed,setSeed]=useState('42');
 async function load(){
  const [p,r]=await Promise.all([call('/products/quotable?limit=100'),call('/capacity/resources?limit=100')]);
  const pl=Array.isArray(p)?p:(p?.items||[]);const rl=Array.isArray(r)?r:(r?.items||[]);
  setProducts(pl);setResources(rl);setPid(v=>v||pl[0]?.id||'');setRid(v=>v||rl[0]?.id||'');
  const [history,versions,quality]=await Promise.all([
   call('/ai-ops/runs'),call('/ai-ops/models').catch(()=>[]),call('/ai-ops/quality').catch(()=>[])]);
  setRuns(history);setModelList(versions);setMetrics(quality);
 }
 useEffect(()=>{void load().catch(e=>setMsg(String(e.message||e)))},[]);
 async function run(fn:()=>Promise<any>){setBusy(true);setMsg('');try{const x=await fn();if(x)setResult(x);await load()}catch(e:any){setMsg(String(e?.message||e))}finally{setBusy(false)}}
 function submit(){if(!pid||(['plan','twin'].includes(tab)&&!rid)){setMsg('Selecciona producto y recurso');return}
  void run(async()=>{
   if(tab==='plan')return call('/ai-ops/optimize','POST',{product_id:pid,resource_id:rid,quantity,requested_date:due});
   if(tab==='agent')return call('/ai-ops/agent/prepare','POST',{kind:draftType,product_id:pid,quantity,customer_text:note});
   return call('/ai-ops/twin','POST',{product_id:pid,resource_id:rid,quantity,shifts:Number(shifts),
     interruption_probability:Number(interruptions),seed:Number(seed),runs:200});
  });}
 function confirmModel(m:any,action:'promote'|'rollback'){
  Alert.alert('Aprobación humana',`¿${action==='promote'?'Activar':'Restaurar'} ${m.version}?`,[
   {text:'Cancelar',style:'cancel'},{text:'Confirmar',onPress:()=>void run(()=>call('/ai-ops/models/'+m.id+'/'+action,'POST',{confirm:true}))}]);
 }
 return <View style={S.box}>
  <Text style={S.heading}>IA avanzada · análisis y simulación</Text>
  <Text style={S.small}>Escenarios y agentes seguros. Solo borradores; ningún pedido, precio o compra se modifica automáticamente.</Text>
  <View style={S.row}>
   <Chip title="Escenarios" chosen={tab==='plan'} onPress={()=>{setTab('plan');setResult(null)}}/>
   <Chip title="Agente" chosen={tab==='agent'} onPress={()=>{setTab('agent');setResult(null)}}/>
   <Chip title="Monte Carlo" chosen={tab==='twin'} onPress={()=>{setTab('twin');setResult(null)}}/>
   <Chip title="Calidad y versiones" chosen={tab==='governance'} onPress={()=>{setTab('governance');setResult(null)}}/>
  </View>
  {!!msg&&<Text style={S.small}>{msg}</Text>}
  {tab!=='governance'&&<View>
    <Text style={S.small}>Producto</Text>
    <View style={S.row}>{products.slice(0,30).map(p=><Chip key={p.id} title={p.name} chosen={pid===p.id} onPress={()=>setPid(p.id)}/>)}</View>
    {tab!=='agent'&&<View><Text style={S.small}>Recurso</Text><View style={S.row}>
      {resources.slice(0,20).map(r=><Chip key={r.id} title={r.name} chosen={rid===r.id} onPress={()=>setRid(r.id)}/>)}</View></View>}
    <Input title="Cantidad" value={quantity} onChange={setQuantity} keyboardType="decimal-pad"/>
    {tab==='plan'&&<Input title="Fecha solicitada (AAAA-MM-DD)" value={due} onChange={setDue}/>}
    {tab==='agent'&&<View><Text style={S.small}>Tipo de borrador</Text><View style={S.row}>
      <Chip title="Cotización" chosen={draftType==='quote_draft'} onPress={()=>setDraftType('quote_draft')}/>
      <Chip title="Tarea" chosen={draftType==='task_draft'} onPress={()=>setDraftType('task_draft')}/>
    </View><Input title="Texto de cliente (solo datos no confiables)" value={note} onChange={setNote}/></View>}
    {tab==='twin'&&<View>
      <Input title="Turnos (1–3)" value={shifts} onChange={setShifts} keyboardType="number-pad"/>
      <Input title="Probabilidad asumida de interrupciones (0–0.5)" value={interruptions} onChange={setInterruptions} keyboardType="decimal-pad"/>
      <Input title="Semilla reproducible" value={seed} onChange={setSeed} keyboardType="number-pad"/>
    </View>}
    <Btn title={busy?'Procesando…':tab==='plan'?'Comparar tres alternativas':tab==='agent'?'Preparar borrador seguro':'Simular Monte Carlo'} disabled={busy||!pid} onPress={submit}/>
    {!!result&&<View style={S.result}>
      <Text style={S.small}>Versión: {result.model_version||'sin modelo'} · Sin ejecución de acciones</Text>
      {tab==='plan'&&result.result?.alternatives?.map((a:any)=><View key={a.alternative}>
        <Text style={S.text}>{a.alternative}: {a.feasible?'Factible':'Restricciones'} · Margen ${a.estimated_gross_margin_mxn}</Text>
        <Text style={S.small}>{(a.restrictions||[]).join(', ')||'Sin restricciones conocidas'}</Text></View>)}
      {tab==='twin'&&<Text style={S.text}>Días P10/P50/P90: {JSON.stringify(result.result?.completion_days)}</Text>}
      {tab==='agent'&&<Text style={S.text}>Borrador: {JSON.stringify(result.result?.draft)}</Text>}
      <Text style={S.small}>Reglas/simulaciones orientativas, no IA causal ni garantía de entrega.</Text>
    </View>}
  </View>}
  {tab==='governance'&&<View>
    <Btn title={busy?'Actualizando…':'Actualizar modelos, calidad y evidencia'} onPress={()=>void run(async()=>{await load();return null})} disabled={busy}/>
    <Btn title="Agregar registro agregado de calidad (propietario)" disabled={busy} onPress={()=>void run(()=>call('/ai-ops/quality/refresh','POST',{}))}/>
    <Text style={S.heading}>Versiones</Text>
    {modelList.map(m=><View key={m.id} style={S.result}>
      <Text style={S.text}>{m.version} · {m.status}</Text>
      <Text style={S.small}>Versión de características: {m.feature_version} · Origen: {m.metrics?.data_origin||'reglas'}</Text>
      {m.status==='candidate'&&!m.synthetic_not_real&&<Btn title="Revisar y aprobar" onPress={()=>confirmModel(m,'promote')}/>}
      {m.status==='archived'&&<Btn title="Restaurar versión" onPress={()=>confirmModel(m,'rollback')}/>}
    </View>)}
    <Text style={S.heading}>Calidad agregada</Text>
    {metrics.slice(0,10).map(m=><View key={m.id} style={S.result}><Text style={S.text}>{m.version}</Text><Text style={S.small}>Revisiones: {m.statistics?.reviewed_extractions} · Campos corregidos: {m.statistics?.corrected_fields_count}</Text></View>)}
    <Text style={S.heading}>Evidencia</Text>
    {runs.slice(0,15).map(r=><Text key={r.id} style={S.small}>{r.kind} · {r.id.slice(0,8)} · {r.model_version}</Text>)}
    <Text style={S.small}>Entrenamiento temporal con archivo JSONL: disponible en el panel web del propietario. Un conjunto sintético nunca activa un modelo.</Text>
  </View>}
 </View>;
}
