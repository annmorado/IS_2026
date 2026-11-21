import React,{useEffect,useState} from 'react';
import {View,Text,TextInput,Pressable,StyleSheet} from 'react-native';
import {File,Paths} from 'expo-file-system';
import * as Sharing from 'expo-sharing';
const API=(process.env.EXPO_PUBLIC_API_URL||'').replace(/\/+$/,'');
type Call=(path:string,method?:'GET'|'POST'|'PUT'|'PATCH'|'DELETE',body?:Record<string,unknown>)=>Promise<any>;
type Props={call:Call,token:string};
const S=StyleSheet.create({box:{padding:12,borderRadius:14,borderWidth:1,borderColor:'#2d485d',marginVertical:8,backgroundColor:'#13293b'},
  text:{color:'#E2E8F0',fontSize:14,marginVertical:5},heading:{color:'#5EEAD4',fontWeight:'700',fontSize:17,marginVertical:7},
  tiny:{color:'#91AEC4',fontSize:12,marginVertical:4},input:{borderWidth:1,borderColor:'#376078',borderRadius:8,color:'#F8FAFC',backgroundColor:'#0B2030',padding:10,marginVertical:5},
  btn:{backgroundColor:'#137A7F',borderRadius:10,padding:11,marginVertical:4},sub:{backgroundColor:'#345064'},btnText:{color:'white',textAlign:'center',fontWeight:'600'},
  row:{flexDirection:'row',flexWrap:'wrap',gap:7,marginVertical:5},chip:{padding:9,backgroundColor:'#1c4961',borderRadius:9},chipOn:{backgroundColor:'#137A7F'},
  border:{borderBottomWidth:1,borderBottomColor:'#345064',paddingVertical:9},
});
const Input=({hint,value,set,secret=false}:{hint:string,value:string,set:(s:string)=>void,secret?:boolean})=><TextInput
 style={S.input} accessibilityLabel={hint} placeholder={hint} placeholderTextColor="#8ba3b5"
 autoCapitalize="none" autoCorrect={false} secureTextEntry={secret} value={value} onChangeText={set}/>;
const Btn=({title,onPress,secondary=false}:{title:string,onPress:()=>void,secondary?:boolean})=><Pressable onPress={onPress}
 accessibilityRole="button" style={[S.btn,secondary&&S.sub]}><Text style={S.btnText}>{title}</Text></Pressable>;
const Label=({children}:{children:React.ReactNode})=><Text style={S.text}>{children}</Text>;
const today=()=>new Date().toISOString().slice(0,10);

export function JoinInviteMobile({call}:{call:Call}){
 const [open,setOpen]=useState(false),[token,setToken]=useState(''),[pass,setPass]=useState(''),[msg,setMsg]=useState('');
 async function accept(){try{const res=await call('/collaborators/invitations/accept','POST',{token:token.trim(),password:pass});
  setMsg('Invitación aceptada: '+res.email+'. Ahora inicia sesión con tu organización.');setToken('');setPass('');
 }catch(e){setMsg(String(e))}}
 return <View style={S.box}><Btn title="Tengo una invitación" secondary onPress={()=>setOpen(!open)}/>{open&&<>
  <Label>Token de un solo uso</Label><Input hint="Token" value={token} set={setToken}/><Input hint="Contraseña nueva (mínimo 12 caracteres)" value={pass} set={setPass} secret/>
  <Btn title="Activar mi cuenta" onPress={()=>void accept()}/></>}{!!msg&&<Label>{msg}</Label>}</View>;
}

function Team({call}:Props){
 const [users,setUsers]=useState<any[]>([]),[email,setEmail]=useState(''),[perms,setPerms]=useState<string[]>(['orders.read']),
  [token,setToken]=useState(''),[msg,setMsg]=useState('');
 async function load(){try{setUsers(await call('/collaborators/users'))}catch(e){setMsg(String(e))}}
 useEffect(()=>{void load()},[]);
 async function invite(){try{const d=await call('/collaborators/invitations','POST',{email,permissions:perms,expires_hours:24});setToken(d.token);
  setMsg('Invitación válida 24 horas. Copia el token y entrégalo por un canal seguro.');setEmail('');await load();
 }catch(e){setMsg(String(e))}}
 async function suspend(id:string,active:boolean){try{await call('/collaborators/users/'+id+'/suspension','PATCH',{is_active:!active});await load()}catch(e){setMsg(String(e))}}
 return <View style={S.box}><Text style={S.heading}>Colaboradores</Text>
  <Input hint="Correo electrónico" value={email} set={setEmail}/><Label>Permisos del colaborador</Label>
  <View style={S.row}>{['orders.read','orders.write','quotes.read','notifications.read','reports.read','calendar.read','purchasing.read','purchasing.write'].map(v=><Pressable key={v}
  style={[S.chip,perms.includes(v)&&S.chipOn]} onPress={()=>setPerms(p=>p.includes(v)?p.filter(x=>x!==v):[...p,v])}><Text style={S.text}>{perms.includes(v)?'☑':'☐'} {v}</Text></Pressable>)}</View>
  <Btn title="Invitar colaborador" onPress={()=>void invite()}/>
  {!!token&&<Text selectable style={S.text}>Token confidencial: {token}</Text>}{users.map(u=><View key={u.id} style={S.border}>
   <Label>{u.email} · {u.is_active?'activo':'suspendido'}</Label>{u.role!=='owner'&&<Btn title={u.is_active?'Suspender y revocar sesiones':'Reactivar'} secondary onPress={()=>void suspend(u.id,u.is_active)}/>}</View>)}
 {!!msg&&<Label>{msg}</Label>}</View>;
}
function Purchasing({call}:Props){
 const [suppliers,setSuppliers]=useState<any[]>([]),[materials,setMaterials]=useState<any[]>([]),[requests,setRequests]=useState<any[]>([]),
 [code,setCode]=useState(''),[name,setName]=useState(''),[supplier,setSupplier]=useState(''),[material,setMaterial]=useState(''),
 [qty,setQty]=useState(''),[cost,setCost]=useState(''),[msg,setMsg]=useState('');
 async function load(){try{const [s,m,r]=await Promise.all([call('/purchasing/suppliers'),call('/materials?limit=50'),call('/purchasing/requests')]);
 setSuppliers(s);setMaterials(m);setRequests(r);setSupplier(x=>x||s[0]?.id||'');setMaterial(x=>x||m[0]?.id||'');}catch(e){setMsg(String(e))}}
 useEffect(()=>{void load()},[]);
 async function addSupplier(){try{await call('/purchasing/suppliers','POST',{code,name});setCode('');setName('');await load()}catch(e){setMsg(String(e))}}
 async function addRequest(){try{await call('/purchasing/requests','POST',{supplier_id:supplier,material_id:material,quantity:qty,unit_cost_mxn:cost});setQty('');await load();setMsg('Solicitud pendiente de aprobación')}catch(e){setMsg(String(e))}}
 async function decide(id:string,decision:'approve'|'reject'){try{await call('/purchasing/requests/'+id+'/decision','POST',{decision,note:'Decisión explícita del propietario'});await load()}catch(e){setMsg(String(e))}}
 return <View style={S.box}><Text style={S.heading}>Compras</Text>
 <Input hint="Código proveedor" value={code} set={setCode}/><Input hint="Nombre proveedor" value={name} set={setName}/>
 <Btn title="Crear proveedor" onPress={()=>void addSupplier()}/><Label>Selecciona proveedor</Label><View style={S.row}>{suppliers.map(s=><Pressable key={s.id} style={[S.chip,supplier===s.id&&S.chipOn]} onPress={()=>setSupplier(s.id)}><Text style={S.text}>{s.name}</Text></Pressable>)}</View>
 <Label>Selecciona material</Label><View style={S.row}>{materials.map(m=><Pressable key={m.id} style={[S.chip,material===m.id&&S.chipOn]} onPress={()=>setMaterial(m.id)}><Text style={S.text}>{m.name}</Text></Pressable>)}</View>
 <Input hint="Cantidad" value={qty} set={setQty}/><Input hint="Costo MXN por unidad" value={cost} set={setCost}/>
 <Btn title="Solicitar compra" onPress={()=>void addRequest()}/>{requests.map(x=><View key={x.id} style={S.border}><Label>{x.quantity} unidades · ${x.total_mxn} · {x.status}</Label>
 {x.status==='pending'&&<View><Btn title="Aprobar compra" onPress={()=>void decide(x.id,'approve')}/><Btn title="Rechazar compra" secondary onPress={()=>void decide(x.id,'reject')}/></View>}</View>)}
 {!!msg&&<Label>{msg}</Label>}<Text style={S.tiny}>Una aprobación no registra recepción ni suma existencias.</Text></View>;
}
function Calendar({call}:Props){
 const [day,setDay]=useState(today()),[rows,setRows]=useState<any[]>([]),[orders,setOrders]=useState<any[]>([]),
 [resource,setResource]=useState(''),[order,setOrder]=useState(''),[qty,setQty]=useState(''),[msg,setMsg]=useState('');
 async function load(){try{const [d,o]=await Promise.all([call('/scheduling/calendar?day='+day),call('/orders/search?limit=10&offset=0')]);setRows(d.resources);
 setOrders(o.items||[]);setResource(x=>x||d.resources[0]?.resource_id||'')}catch(e){setMsg(String(e))}}
 useEffect(()=>{void load()},[day]);
 async function allocate(){try{await call('/scheduling/allocations','POST',{resource_id:resource,order_id:order,day,quantity:qty});setMsg('Carga registrada');await load()}catch(e){setMsg(String(e))}}
 return <View style={S.box}><Text style={S.heading}>Calendario de carga</Text>
 <Input hint="Fecha AAAA-MM-DD" value={day} set={setDay}/><Btn title="Consultar calendario" secondary onPress={()=>void load()}/>
 {rows.map(r=><View key={r.resource_id} style={S.border}><Label>{r.resource_name}</Label><Label>{r.occupied} / {r.capacity} {r.unit} · restantes {r.remaining}</Label><Text style={S.tiny}>{r.working?'Laborable':'No laborable o bloqueado'}</Text></View>)}
 <Label>Recurso</Label><View style={S.row}>{rows.map(r=><Pressable key={r.resource_id} style={[S.chip,resource===r.resource_id&&S.chipOn]} onPress={()=>setResource(r.resource_id)}><Text style={S.text}>{r.resource_name}</Text></Pressable>)}</View>
 <Label>Pedido confirmado</Label><View style={S.row}>{orders.filter(o=>['confirmed','in_progress'].includes(o.status)).map(o=><Pressable key={o.id} style={[S.chip,order===o.id&&S.chipOn]} onPress={()=>setOrder(o.id)}><Text style={S.text}>{o.id.slice(0,8)}</Text></Pressable>)}</View>
 <Input hint="Cantidad en unidades del recurso" value={qty} set={setQty}/><Btn title="Asignar capacidad" onPress={()=>void allocate()}/>
 {!!msg&&<Label>{msg}</Label>}<Text style={S.tiny}>Se muestran únicamente compromisos asignados explícitamente.</Text></View>;
}
function Alerts({call}:Props){
 const [prefs,setPrefs]=useState({due_soon:false,risk:false,material_shortage:false}),[entries,setEntries]=useState<any[]>([]),[msg,setMsg]=useState('');
 async function load(){try{setPrefs(await call('/notifications/preferences'));setEntries(await call('/notifications/entries'))}catch(e){setMsg(String(e))}}
 useEffect(()=>{void load()},[]);
 async function save(){try{await call('/notifications/preferences','PUT',prefs);setMsg('Preferencias guardadas')}catch(e){setMsg(String(e))}}
 async function scan(){try{const r=await call('/notifications/scan','POST',{});setMsg(`${r.created} alertas nuevas`);await load()}catch(e){setMsg(String(e))}}
 const labels={due_soon:'Fecha próxima',risk:'Entrega vencida',material_shortage:'Material insuficiente'};
 return <View style={S.box}><Text style={S.heading}>Notificaciones</Text><View style={S.row}>{(Object.keys(labels) as (keyof typeof labels)[]).map(k=><Pressable key={k}
  style={[S.chip,prefs[k]&&S.chipOn]} onPress={()=>setPrefs(p=>({...p,[k]:!p[k]}))}><Text style={S.text}>{prefs[k]?'☑':'☐'} {labels[k]}</Text></Pressable>)}</View>
  <Btn title="Guardar preferencias" onPress={()=>void save()}/><Btn title="Evaluar alertas" secondary onPress={()=>void scan()}/>{entries.map(e=><View key={e.id} style={S.border}><Label>{e.kind}: {e.message}</Label></View>)}
 {!!msg&&<Label>{msg}</Label>}<Text style={S.tiny}>Alertas internas bajo demanda, no notificaciones push.</Text></View>;
}
function Reports({call,token}:Props){
 const [data,setData]=useState<any>(null),[status,setStatus]=useState(''),[from,setFrom]=useState(''),[to,setTo]=useState(''),[msg,setMsg]=useState('');
 function query(format=''){const p=new URLSearchParams();if(format)p.set('format',format);if(status)p.set('status',status);if(from)p.set('date_from',from);if(to)p.set('date_to',to);return p.toString()}
 async function load(){try{setData(await call('/reports/summary?'+query()));setMsg('Informe actualizado')}catch(e){setMsg(String(e))}}
 useEffect(()=>{void load()},[]);
 async function download(format:'csv'|'pdf'){
  try{if(!/^https?:\/\//.test(API))throw Error('Configura EXPO_PUBLIC_API_URL');
   const r=await fetch(API+'/reports/export?'+query(format),{headers:{Authorization:'Bearer '+token}});
   if(!r.ok)throw Error('Error exportando: HTTP '+r.status);
   const bytes=new Uint8Array(await r.arrayBuffer());if(bytes.length===0)throw Error('Documento vacío');
   const name='nexo-reporte-'+Date.now()+'.'+format;const file=new File(Paths.cache,name);await file.write(bytes);
   if(await Sharing.isAvailableAsync())await Sharing.shareAsync(file.uri,{mimeType:format==='pdf'?'application/pdf':'text/csv',dialogTitle:'Informe NEXO AI'});
   else await file.preview({title:'Informe NEXO AI'});
   setMsg('Informe generado.');
  }catch(e){setMsg(String(e))}}
 return <View style={S.box}><Text style={S.heading}>Informes</Text>
 <Input hint="Desde AAAA-MM-DD (opcional)" value={from} set={setFrom}/><Input hint="Hasta AAAA-MM-DD (opcional)" value={to} set={setTo}/>
 <View style={S.row}>{['','draft','pending','confirmed','in_progress','completed','cancelled'].map(s=><Pressable key={s} style={[S.chip,status===s&&S.chipOn]} onPress={()=>setStatus(s)}><Text style={S.text}>{s||'Todos'}</Text></Pressable>)}</View>
 <Btn title="Consultar totales" onPress={()=>void load()}/>{data&&<><Label>Pedidos {data.totals.orders} · completados {data.totals.completed}</Label>
 <Label>Ingresos aprobados ${data.totals.revenue_mxn} MXN</Label><Label>Margen bruto ${data.totals.gross_margin_mxn} MXN</Label></>}
 <Btn title="Compartir CSV" onPress={()=>void download('csv')}/><Btn title="Compartir PDF" secondary onPress={()=>void download('pdf')}/>
 {!!msg&&<Label>{msg}</Label>}<Text style={S.tiny}>Totales calculados con cotizaciones aprobadas; no representan cobros.</Text></View>;
}
const tabs=['Equipo','Compras','Calendario','Alertas','Informes'] as const;
export default function ManagementMobile({call,token}:Props){
 const [tab,setTab]=useState<(typeof tabs)[number]>('Alertas');
 return <View><Text style={S.heading}>Gestión empresarial</Text>
 <View style={S.row}>{tabs.map(v=><Pressable key={v} style={[S.chip,tab===v&&S.chipOn]} onPress={()=>setTab(v)}><Text style={S.text}>{v}</Text></Pressable>)}</View>
 {tab==='Equipo'&&<Team call={call} token={token}/>}{tab==='Compras'&&<Purchasing call={call} token={token}/>}
 {tab==='Calendario'&&<Calendar call={call} token={token}/>}{tab==='Alertas'&&<Alerts call={call} token={token}/>}
 {tab==='Informes'&&<Reports call={call} token={token}/>}
 </View>;
}
