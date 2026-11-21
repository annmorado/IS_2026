import React,{useEffect,useState} from 'react';
import {View,Text,TextInput,Pressable,StyleSheet,Alert} from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import {File} from 'expo-file-system';
type Call=(path:string,method?:'GET'|'POST'|'PUT'|'PATCH'|'DELETE',body?:Record<string,unknown>)=>Promise<any>;
type Props={call:Call,upload:(file:File)=>Promise<any>};
const S=StyleSheet.create({card:{padding:12,borderRadius:14,borderWidth:1,borderColor:'#2d485d',marginVertical:9,backgroundColor:'#13293b'},
 text:{color:'#E2E8F0',fontSize:14,marginVertical:5},title:{color:'#5EEAD4',fontWeight:'700',fontSize:17,marginVertical:7},
 hint:{color:'#91AEC4',fontSize:12,marginVertical:4},field:{borderWidth:1,borderColor:'#376078',borderRadius:8,color:'#F8FAFC',backgroundColor:'#0B2030',padding:10,marginVertical:5},
 button:{backgroundColor:'#137A7F',borderRadius:10,padding:12,marginVertical:5},secondary:{backgroundColor:'#345064'},buttonText:{color:'white',textAlign:'center',fontWeight:'700'},
 row:{flexDirection:'row',flexWrap:'wrap',gap:7,marginVertical:5},chip:{padding:9,backgroundColor:'#1c4961',borderRadius:9},active:{backgroundColor:'#137A7F'},
 divider:{borderBottomWidth:1,borderBottomColor:'#345064',paddingVertical:8}});
function Label({children}:{children:React.ReactNode}){return <Text style={S.text}>{children}</Text>}
function Hint({children}:{children:React.ReactNode}){return <Text style={S.hint}>{children}</Text>}
function Input({label,value,onChange}:{label:string,value:string,onChange:(s:string)=>void}){return <View><Hint>{label}</Hint><TextInput style={S.field} accessibilityLabel={label}
 placeholder={label} placeholderTextColor="#8ba3b5" autoCapitalize="none" value={value} onChangeText={onChange}/></View>}
function Button({label,onPress,secondary=false}:{label:string,onPress:()=>void,secondary?:boolean}){return <Pressable accessibilityRole="button" onPress={onPress} style={[S.button,secondary&&S.secondary]}><Text style={S.buttonText}>{label}</Text></Pressable>}
function Chip({name,onPress,selected}:{name:string,onPress:()=>void,selected:boolean}){return <Pressable onPress={onPress} style={[S.chip,selected&&S.active]}><Text style={S.text}>{name}</Text></Pressable>}
function Plans({call}:Props){
 const [data,setData]=useState<any>(null),[msg,setMsg]=useState('');
 async function load(){try{setData(await call('/subscriptions/me'))}catch(e){setMsg(String(e))}}
 useEffect(()=>{void load()},[]);
 async function trial(){try{setData(await call('/subscriptions/start-trial','POST',{}));setMsg('Prueba de 7 días activada; no se hicieron cobros.')}catch(e){setMsg(String(e))}}
 return <View style={S.card}><Text style={S.title}>Planes y límites</Text>
 {data&&<><Label>Plan: {data.plan} · Estado: {data.status}</Label>
 <Label>OCR {data.usage.ocr}/{data.limits.ocr} · Agentes {data.usage.agents}/{data.limits.agents}</Label>
 <Hint>El plan no bloquea pedidos ni cotizaciones. Sin facturación automática.</Hint>
 {data.trial_available&&<Button label="Activar prueba de 7 días" onPress={()=>Alert.alert('Prueba sin cobro','¿Activar ahora?',
  [{text:'Cancelar',style:'cancel'},{text:'Activar',onPress:()=>void trial()}])}/>}</>}
 {!!msg&&<Label>{msg}</Label>}</View>;
}
function OCR({call,upload}:Props){
 const [rows,setRows]=useState<any[]>([]),[selected,setSelected]=useState<any>(null),[vendor,setVendor]=useState(''),[amount,setAmount]=useState(''),
 [concept,setConcept]=useState(''),[msg,setMsg]=useState(''),[busy,setBusy]=useState(false);
 async function load(){try{setRows(await call('/documents/ocr/proposals'))}catch(e){setMsg(String(e))}}
 useEffect(()=>{void load()},[]);
 async function pick(){try{const perm=await ImagePicker.requestMediaLibraryPermissionsAsync();if(!perm.granted)throw Error('Permiso de fotografías requerido');
 const r=await ImagePicker.launchImageLibraryAsync({mediaTypes:['images'],quality:0.8,allowsEditing:false});
 if(r.canceled||!r.assets[0])return;
 const asset=r.assets[0];const file=new File(asset.uri);
 if(!file.exists||file.size===0||file.size>4*1024*1024)throw Error('Se requiere imagen válida de máximo 4 MB');
 setBusy(true);const d=await upload(file);setMsg('Propuesta OCR recibida. Revisa antes de guardar.');await load();choose(d);
 }catch(e){setMsg(String(e))}finally{setBusy(false)}}
 function choose(d:any){setSelected(d);const f=d.reviewed||d.extracted?.suggested_fields||{};setVendor(f.vendor||'');setAmount(f.amount_mxn||'');setConcept(f.concept||'')}
 async function review(){if(!selected)return;try{await call('/documents/ocr/proposals/'+selected.id+'/review','POST',{
 vendor:vendor||null,amount_mxn:amount||null,concept:concept||null,confirm:true});setMsg('Revisión humana guardada, sin crear factura.');setSelected(null);await load()
 }catch(e){setMsg(String(e))}}
 return <View style={S.card}><Text style={S.title}>OCR asistido</Text>
 <Hint>Selecciona una foto de factura/nota/etiqueta. Necesitas Tesseract en FastAPI; nunca crea compras o facturas automáticamente.</Hint>
 <Button label={busy?'Extrayendo texto…':'Seleccionar foto y extraer propuesta'} onPress={()=>{if(!busy)void pick()}}/>
 {rows.map(x=><View key={x.id} style={S.divider}><Button secondary label={`${x.filename} · ${x.status} · ${Math.round((x.extracted?.confidence||0)*100)}%`} onPress={()=>choose(x)}/></View>)}
 {selected&&<View><Label>Texto detectado: {selected.extracted?.raw_text||'Sin texto'}</Label>
 <Hint>Confianza aproximada: {Math.round((selected.extracted?.confidence||0)*100)}%; monto: {selected.extracted?.field_confidence?.amount_mxn==null?'sin detectar':Math.round(selected.extracted.field_confidence.amount_mxn*100)+'%'}. Revisa cada campo.</Hint>
 {selected.status==='proposed'&&<><Input label="Proveedor" value={vendor} onChange={setVendor}/><Input label="Monto MXN" value={amount} onChange={setAmount}/>
 <Input label="Concepto" value={concept} onChange={setConcept}/><Button label="Guardar revisión humana" onPress={()=>void review()}/></>}
 </View>}{!!msg&&<Label>{msg}</Label>}</View>;
}
function Messaging({call}:Props){
 const [config,setConfig]=useState<any>(null),[phone,setPhone]=useState(''),[enabled,setEnabled]=useState(false),[msg,setMsg]=useState(''),
 [recipient,setRecipient]=useState(''),[evidence,setEvidence]=useState(''),[consents,setConsents]=useState<any[]>([]);
 async function load(){try{const c=await call('/messaging/configuration');setConfig(c);setPhone(c.phone_number_id||'');setEnabled(c.enabled);setConsents(await call('/messaging/consents'))}catch(e){setMsg(String(e))}}
 useEffect(()=>{void load()},[]);
 async function save(){try{await call('/messaging/configuration','PUT',{phone_number_id:phone,enabled});setMsg('Configuración guardada sin enviar mensajes');await load()}catch(e){setMsg(String(e))}}
 async function register(){try{await call('/messaging/consents','POST',{recipient_e164:recipient,evidence_reference:evidence,valid_days:90,confirm:true});
 setMsg('Consentimiento registrado sin enviar mensajes');setRecipient('');setEvidence('');await load()}catch(e){setMsg(String(e))}}
 async function revoke(id:string){try{await call('/messaging/consents/'+id+'/revoke','POST',{confirm:true});setMsg('Consentimiento revocado');await load()}catch(e){setMsg(String(e))}}
 return <View style={S.card}><Text style={S.title}>Mensajería oficial</Text>
 <Hint>Solo WhatsApp Cloud API con credenciales de la empresa, consentimiento documentado y autorización explícita. Sin mensajes automáticos.</Hint>
 <Label>{config?.credentials_present?'Credenciales configuradas':'Sin credenciales oficiales del servidor'}</Label>
 <Input label="ID de número de WhatsApp Business (Meta)" value={phone} onChange={setPhone}/>
 <Button secondary label={enabled?'Configuración habilitada':'Configuración deshabilitada'} onPress={()=>setEnabled(x=>!x)}/>
 <Button label="Guardar configuración" onPress={()=>void save()}/>
 <Input label="Destinatario (+52...)" value={recipient} onChange={setRecipient}/><Input label="Folio evidencia de consentimiento" value={evidence} onChange={setEvidence}/>
 <Button label="Registrar consentimiento (90 días)" onPress={()=>Alert.alert('Consentimiento','¿Cuentas con un comprobante del permiso?',
 [{text:'Cancelar',style:'cancel'},{text:'Registrar',onPress:()=>void register()}])}/>
 {consents.map(x=><View key={x.id} style={S.divider}><Label>Destinatario terminado en {x.recipient_tail} · {x.active?'vigente':'inactivo'}</Label>
 {x.active&&<Button secondary label="Revocar consentimiento" onPress={()=>void revoke(x.id)}/>}</View>)}
 {!!msg&&<Label>{msg}</Label>}</View>;
}
function Templates({call}:Props){
 const [catalog,setCatalog]=useState<any[]>([]),[active,setActive]=useState<any>(null),[history,setHistory]=useState<any[]>([]),
 [code,setCode]=useState(''),[msg,setMsg]=useState('');
 async function load(){try{const [c,a,h]=await Promise.all([call('/sector-templates/catalog'),call('/sector-templates/active'),call('/sector-templates/history')]);
 setCatalog(c);setActive(a);setHistory(h);setCode(v=>v||c[0]?.code||'')}catch(e){setMsg(String(e))}}
 useEffect(()=>{void load()},[]);
 async function apply(){try{await call('/sector-templates/apply','POST',{code,confirm:true});setMsg('Plantilla aplicada para configuraciones futuras.');await load()}catch(e){setMsg(String(e))}}
 return <View style={S.card}><Text style={S.title}>Plantillas por sector</Text><Label>Actual: {active?.code||'Ninguna'}</Label>
 <View style={S.row}>{catalog.map(x=><Chip key={x.code} name={x.config.name} selected={code===x.code} onPress={()=>setCode(x.code)}/>)}</View>
 <Hint>El cambio no modifica pedidos históricos, precios ni compromisos ya aceptados.</Hint>
 <Button label="Aplicar plantilla" onPress={()=>Alert.alert('Cambiar sector','¿Aplicar solo a configuraciones futuras?',
 [{text:'Cancelar',style:'cancel'},{text:'Confirmar',onPress:()=>void apply()}])}/>
 {history.slice(0,6).map((x,i)=><Hint key={i}>Versión {x.version}: {x.config.name}</Hint>)}{!!msg&&<Label>{msg}</Label>}</View>;
}
function Agents({call}:Props){
 const [kind,setKind]=useState('capacity_planner'),[objective,setObjective]=useState('Evaluar capacidad sin modificar pedidos reales'),
 [rows,setRows]=useState<any[]>([]),[msg,setMsg]=useState('');
 async function load(){try{setRows(await call('/agents/workflows'))}catch(e){setMsg(String(e))}}
 useEffect(()=>{void load()},[]);
 async function prepare(){try{await call('/agents/prepare','POST',{agent_kind:kind,objective});setMsg('Plan preparado sin ejecutar acciones externas');await load()}catch(e){setMsg(String(e))}}
 async function authorize(id:string){try{await call('/agents/workflows/'+id+'/authorize','POST',{confirm:true});setMsg('Plan de lectura autorizado');await load()}catch(e){setMsg(String(e))}}
 return <View style={S.card}><Text style={S.title}>Agentes supervisados</Text>
 <Hint>Reglas deterministas y consultas de lectura. No usa LLM; no compra, confirma ni envía mensajes.</Hint>
 <View style={S.row}>{[['capacity_planner','Capacidad'],['material_advisor','Materiales'],['followup_drafter','Seguimiento']].map(([id,t])=><Chip key={id} name={t} selected={kind===id} onPress={()=>setKind(id)}/>)}</View>
 <Input label="Objetivo" value={objective} onChange={setObjective}/><Button label="Preparar plan sin ejecutar" onPress={()=>void prepare()}/>
 {rows.map(x=><View key={x.id} style={S.divider}><Label>{x.agent_kind} · {x.status}</Label>
 <Hint>{x.result?.observations?.join(' ')}</Hint><Hint>Acciones productivas: ninguna</Hint>
 {x.status==='prepared'&&<Button secondary label="Autorizar plan de lectura" onPress={()=>Alert.alert('Autorización','¿Autorizar solamente un plan de lectura?',
 [{text:'Cancelar',style:'cancel'},{text:'Autorizar',onPress:()=>void authorize(x.id)}])}/>}</View>)}{!!msg&&<Label>{msg}</Label>}</View>;
}
const TABS=[['plans','Planes'],['ocr','OCR'],['messages','Mensajería'],['templates','Sectores'],['agents','Agentes']] as const;
export default function ExtensionsMobile(props:Props){
 const [tab,setTab]=useState<(typeof TABS)[number][0]>('plans');
 return <View><Text style={S.title}>Inteligencia y extensiones</Text>
 <View style={S.row}>{TABS.map(([key,name])=><Chip key={key} name={name} selected={tab===key} onPress={()=>setTab(key)}/>)}</View>
 {tab==='plans'&&<Plans {...props}/>}{tab==='ocr'&&<OCR {...props}/>}{tab==='messages'&&<Messaging {...props}/>}
 {tab==='templates'&&<Templates {...props}/>}{tab==='agents'&&<Agents {...props}/>}
 </View>;
}
