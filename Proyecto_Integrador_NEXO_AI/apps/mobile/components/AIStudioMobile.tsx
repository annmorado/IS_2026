import React,{useEffect,useState} from 'react';
import {View,Text,TextInput,Pressable,StyleSheet,Alert} from 'react-native';
type Call=(path:string,method?:'GET'|'POST'|'PATCH',body?:Record<string,unknown>)=>Promise<any>;
type Props={call:Call};
const S=StyleSheet.create({card:{padding:14,backgroundColor:'#13293b',borderWidth:1,borderColor:'#346071',borderRadius:13,marginTop:10},
 title:{fontSize:17,color:'#5eead4',fontWeight:'700',marginVertical:8},label:{color:'#e1f4f6',fontSize:13,marginVertical:5},
 hint:{color:'#a1bdcb',fontSize:12,marginVertical:6},input:{padding:11,marginVertical:5,borderColor:'#446a7b',borderWidth:1,borderRadius:8,backgroundColor:'#0a2231',color:'#f8fafc'},
 row:{flexDirection:'row',flexWrap:'wrap',gap:7,marginVertical:8},chip:{padding:10,backgroundColor:'#2b4960',borderRadius:8},selected:{backgroundColor:'#0b7d81'},
 action:{backgroundColor:'#147d85',padding:11,borderRadius:9,marginVertical:6},actionText:{color:'white',textAlign:'center',fontWeight:'700'},
 line:{marginVertical:7,borderBottomWidth:1,borderBottomColor:'#345366',paddingBottom:9}});
function Label({children}:{children:React.ReactNode}){return <Text style={S.label}>{children}</Text>}
function Hint({children}:{children:React.ReactNode}){return <Text style={S.hint}>{children}</Text>}
function Btn({label,onPress}:{label:string,onPress:()=>void}){return <Pressable accessibilityRole="button" onPress={onPress} style={S.action}><Text style={S.actionText}>{label}</Text></Pressable>}
function Input({label,value,onChange,multiline=false}:{label:string,value:string,onChange:(x:string)=>void,multiline?:boolean}){
 return <View><Hint>{label}</Hint><TextInput accessibilityLabel={label} style={[S.input,multiline&&{minHeight:85,textAlignVertical:'top'}]} multiline={multiline}
 value={value} onChangeText={onChange} placeholderTextColor="#93aebf" placeholder={label}/></View>;
}
const EMPTY={product_id:'',quantity:'',unit_price_mxn:'',requested_date:'',notes:''};
export default function AIStudioMobile({call}:Props){
 const [tab,setTab]=useState<'extract'|'voice'|'estimate'>('extract');
 const [notes,setNotes]=useState<any[]>([]),[jobs,setJobs]=useState<any[]>([]),[products,setProducts]=useState<any[]>([]),[resources,setResources]=useState<any[]>([]);
 const [source,setSource]=useState('Necesito 3 playeras, precio unitario $250 para 2026-12-15; nota: estampado azul');
 const [extract,setExtract]=useState<any>(null),[fields,setFields]=useState(EMPTY),[validation,setValidation]=useState<any>(null);
 const [edited,setEdited]=useState(''),[chosenJob,setChosenJob]=useState(''),[quantity,setQuantity]=useState('3'),[resource,setResource]=useState(''),[prediction,setPrediction]=useState<any>(null),[message,setMessage]=useState('');
 async function load(){try{const [n,j,p,r]=await Promise.all([call('/ai/voice-note-options'),call('/ai/transcriptions'),call('/products/quotable?limit=100'),call('/capacity/resources?limit=100')]);
 setNotes(n);setJobs(j);setProducts(Array.isArray(p)?p:p.items||[]);setResources(Array.isArray(r)?r:r.items||[]);}catch(e){setMessage(String(e))}}
 useEffect(()=>{void load()},[]);
 async function run(fn:()=>Promise<void>){setMessage('');try{await fn()}catch(e){setMessage(String(e))}}
 async function transcribe(id:string){await run(async()=>{const x=await call('/ai/transcriptions','POST',{voice_note_id:id});
 setMessage(`Estado: ${x.status}. Actualiza para ver el resultado.`);await load()})}
 async function editJob(){await run(async()=>{await call('/ai/transcriptions/'+chosenJob+'/text','PATCH',{text:edited,confirm:true});await load();setMessage('Revisión humana guardada; sin crear pedidos.')})}
 async function propose(){await run(async()=>{const x=await call('/ai/extractions','POST',{raw_text:source});setExtract(x);
 const f=x.result.fields;setFields({product_id:f.product.value?.id||'',quantity:f.quantity.value||'',
 unit_price_mxn:f.unit_price_mxn.value||'',requested_date:f.requested_date.value||'',notes:f.notes.value||''});
 setValidation(null);setMessage('Propuesta guardada. Revisa los campos pendientes.')})}
 async function validate(){await run(async()=>{const x=await call('/ai/validate','POST',fields);setValidation(x);setMessage(x.valid?'Datos válidos para revisión, NO confirmados':'Corrige los campos indicados.')})}
 async function saveReviewed(){if(!extract||!validation?.valid)return;await run(async()=>{const x=await call('/ai/extractions/'+extract.id+'/review','POST',{...fields,confirm:true});
 setExtract(x);setMessage('Revisión humana registrada, sin confirmar pedidos.')})}
 async function estimate(){await run(async()=>{const x=await call('/ai/estimates','POST',{product_id:fields.product_id,
 quantity,requested_date:fields.requested_date||null,resource_id:resource||null});setPrediction(x);setMessage('Baseline calculado sin reservar capacidad.')})}
 function edit(k:keyof typeof EMPTY,v:string){setFields(p=>({...p,[k]:v}));setValidation(null)}
 return <View style={S.card}><Text style={S.title}>Asistente IA</Text>
 <Hint>Whisper local opcional, reglas de extracción trazables y pronóstico operativo base. Revisión humana obligatoria. Ningún pedido se confirma automáticamente.</Hint>
 <View style={S.row}>{[['extract','Extracción'],['voice','Voz IA'],['estimate','Pronóstico']].map(([id,label])=><Pressable key={id} style={[S.chip,tab===id&&S.selected]} onPress={()=>setTab(id as typeof tab)}><Text style={S.label}>{label}</Text></Pressable>)}</View>
 {!!message&&<Label>{message}</Label>}
 {tab==='voice'&&<View><Hint>Graba y envía tu M4A desde la pestaña Voz. Después inicia la transcripción. Si falta faster-whisper o el modelo, se mostrará un error sin inventar texto.</Hint>
 <Btn label="Actualizar notas y transcripciones" onPress={()=>void load()}/>
 {notes.map(n=><View key={n.id} style={S.line}><Label>Audio {n.id.slice(0,8)} · {n.duration_ms==null?'Duración desconocida':Math.round(n.duration_ms/1000)+'s'}</Label>
 <Btn label="Transcribir este audio" onPress={()=>void transcribe(n.id)}/></View>)}
 {jobs.map(j=><View key={j.id} style={S.line}><Label>{j.status} · {j.engine}</Label>
 {!!j.error_code&&<Hint>Error: {j.error_code}. Sin texto inventado. Intentos: {j.attempt_count}/3</Hint>}
 {j.status==='failed'&&j.attempt_count<3&&<Btn label="Reintentar con Whisper instalado" onPress={()=>void run(async()=>{await call('/ai/transcriptions/'+j.id+'/retry','POST',{});await load()})}/>}
 {!!j.transcript&&<Label>Texto detectado: {j.transcript}</Label>}
 {(j.status==='completed'||j.status==='reviewed')&&<Btn label="Revisar texto" onPress={()=>{setChosenJob(j.id);setEdited(j.reviewed_text||j.transcript||'')}}/>}
 {(j.status==='queued'||j.status==='processing')&&<Btn label="Cancelar tarea" onPress={()=>void run(async()=>{await call('/ai/transcriptions/'+j.id+'/cancel','POST',{});await load()})}/>}</View>)}
 {!!chosenJob&&<View><Input label="Transcripción editable" value={edited} multiline onChange={setEdited}/><Btn label="Guardar texto revisado" onPress={()=>Alert.alert('Revisión humana','¿Guardar tu corrección?',[
 {text:'Cancelar',style:'cancel'},{text:'Guardar',onPress:()=>void editJob()}])}/>
 <Btn label="Pasar texto a extracción" onPress={()=>{setSource(edited);setTab('extract')}}/></View>}
 </View>}
 {tab==='extract'&&<View><Input label="Solicitud en español" value={source} onChange={setSource} multiline/>
 <Btn label="Extraer y guardar propuesta" onPress={()=>void propose()}/>
 {extract&&<View><Hint>Motor: {extract.result.engine_version}; no es un modelo entrenado.</Hint>
 {Object.entries(extract.result.fields).map(([k,v])=><View key={k}><Hint>{k}: {(v as any).origin} · {(v as any).source_fragment||'Pendiente'}</Hint></View>)}
 <Hint>Selecciona producto del catálogo:</Hint><View style={S.row}>{products.slice(0,50).map(p=><Pressable key={p.id} style={[S.chip,fields.product_id===p.id&&S.selected]}
 onPress={()=>edit('product_id',p.id)}><Text style={S.label}>{p.name}</Text></Pressable>)}</View>
 <Input label="Cantidad" value={fields.quantity} onChange={x=>edit('quantity',x)}/>
 <Input label="Precio indicado MXN" value={fields.unit_price_mxn} onChange={x=>edit('unit_price_mxn',x)}/>
 <Input label="Fecha solicitada AAAA-MM-DD" value={fields.requested_date} onChange={x=>edit('requested_date',x)}/>
 <Input label="Observaciones" value={fields.notes} onChange={x=>edit('notes',x)}/>
 <Btn label="Validar datos corregidos sin confirmar" onPress={()=>void validate()}/>
 {validation&&<View><Label>{validation.valid?'Validación correcta, pendiente de revisión final':'Se requiere corrección'}</Label>
 {validation.issues.map((x:any,i:number)=><Hint key={i}>{x.field}: {x.message}</Hint>)}<Hint>Confirmación automática: NO</Hint>
 {validation.valid&&!extract.reviewed&&<Btn label="Guardar revisión humana (sin pedido)" onPress={()=>Alert.alert('Guardar revisión','¿Guardar datos corregidos sin confirmar pedidos?',
 [{text:'Cancelar',style:'cancel'},{text:'Guardar',onPress:()=>void saveReviewed()}])}/>}</View>}</View>}
 </View>}
 {tab==='estimate'&&<View><Hint>Motor base de reglas, no predicción estadística validada. La fecha depende de capacidad disponible y compromisos conocidos.</Hint>
 <Hint>Selecciona producto:</Hint><View style={S.row}>{products.slice(0,50).map(p=><Pressable key={p.id} style={[S.chip,fields.product_id===p.id&&S.selected]}
 onPress={()=>edit('product_id',p.id)}><Text style={S.label}>{p.name}</Text></Pressable>)}</View>
 <Input label="Cantidad" value={quantity} onChange={setQuantity}/>
 <Input label="Fecha solicitada (AAAA-MM-DD)" value={fields.requested_date} onChange={x=>edit('requested_date',x)}/>
 <Hint>Recurso opcional:</Hint><View style={S.row}><Pressable style={[S.chip,resource===''&&S.selected]} onPress={()=>setResource('')}><Text style={S.label}>Sin recurso</Text></Pressable>
 {resources.slice(0,25).map(r=><Pressable key={r.id} style={[S.chip,resource===r.id&&S.selected]} onPress={()=>setResource(r.id)}><Text style={S.label}>{r.name}</Text></Pressable>)}</View>
 <Btn label="Estimar sin comprometer capacidad" onPress={()=>void estimate()}/>
 {prediction&&<View style={S.line}><Label>Motor: {prediction.result.engine_version}</Label><Label>Minutos: {prediction.result.estimated_minutes}</Label>
 <Label>Fecha: {prediction.result.estimated_completion_date||'No estimable'}</Label><Label>Riesgo: {prediction.result.delay_risk}</Label>
 <Hint>Calidad: {prediction.result.quality_status}</Hint>
 {prediction.result.warnings.map((w:string,i:number)=><Hint key={i}>{w}</Hint>)}
 <Hint>Sin cambios en pedidos, precios ni recursos.</Hint></View>}</View>}
 </View>;
}
