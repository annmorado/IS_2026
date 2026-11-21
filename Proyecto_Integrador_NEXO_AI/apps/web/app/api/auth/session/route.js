import {NextResponse} from 'next/server';
import {cookies} from 'next/headers';
import {COOKIE,allowedOrigin,commonHeaders,sessionToken,upstream} from '../../../../lib/server.mjs';

export const dynamic='force-dynamic';
const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
function reply(obj,status=200){return NextResponse.json(obj,{status,headers:commonHeaders()});}

export async function GET(){
  const token=await sessionToken();
  if(!token) return reply({detail:'Inicia sesión'},401);
  try{
    const r=await upstream('auth/me',token);
    if(!r.ok) return reply({detail:'Sesión vencida o sin permisos'},r.status===403?403:401);
    return reply(await r.json());
  }catch{return reply({detail:'No hay conexión con FastAPI'},503);}
}

export async function POST(req){
  if(!allowedOrigin(req))return reply({detail:'Origen no autorizado'},403);
  const length=Number(req.headers.get('content-length')||0);
  if(length>4096) return reply({detail:'Solicitud demasiado grande'},413);
  let data;
  try{data=await req.json();}catch{return reply({detail:'JSON inválido'},400);}
  if(!data||typeof data!=='object'||Object.keys(data).sort().join(',')!=='email,organization_id,password'||
    typeof data.organization_id!=='string'||!UUID.test(data.organization_id)||
    typeof data.email!=='string'||data.email.length>254||
    typeof data.password!=='string'||!data.password||data.password.length>1024)
      return reply({detail:'Datos de inicio de sesión inválidos'},400);
  try{
    const r=await upstream('auth/login','',{method:'POST',body:data});
    if(!r.ok)return reply({detail:'Credenciales inválidas o cuenta no disponible'},r.status===429?429:401);
    const body=await r.json();
    if(typeof body.access_token!=='string'||body.token_type!=='bearer')return reply({detail:'Respuesta de autenticación inválida'},502);
    const response=reply({status:'authenticated'});
    response.cookies.set(COOKIE,body.access_token,{httpOnly:true,secure:process.env.NODE_ENV==='production',
      sameSite:'strict',path:'/',maxAge:Math.max(1,Math.min(900,Number(body.expires_in)||900))});
    return response;
  }catch{return reply({detail:'No hay conexión con FastAPI'},503);}
}

export async function DELETE(req){
  if(!allowedOrigin(req))return reply({detail:'Origen no autorizado'},403);
  const token=await sessionToken();
  if(token){try{await upstream('auth/logout',token,{method:'POST'});}catch{}}
  const response=reply({status:'signed_out'});
  response.cookies.set(COOKIE,'',{httpOnly:true,secure:process.env.NODE_ENV==='production',
    sameSite:'strict',path:'/',maxAge:0});
  return response;
}
