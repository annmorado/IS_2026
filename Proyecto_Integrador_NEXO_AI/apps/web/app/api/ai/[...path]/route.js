import {aiPath,validAiBody} from '../../../../lib/ai.mjs';
import {allowedOrigin,commonHeaders,sessionToken,upstream} from '../../../../lib/server.mjs';
export const dynamic='force-dynamic';
async function handle(req,ctx,method){
 const p=aiPath(method,(await ctx.params).path,new URL(req.url).search.slice(1));
 if(!p)return Response.json({detail:'Ruta de IA no autorizada'},{status:404,headers:commonHeaders()});
 if(method!=='GET'&&!allowedOrigin(req))return Response.json({detail:'Origen no autorizado'},{status:403,headers:commonHeaders()});
 const token=await sessionToken();if(!token)return Response.json({detail:'Sesión requerida'},{status:401,headers:commonHeaders()});
 try{
  let body;
  if(method!=='GET'){
   if(!/^application\/json(?:;|$)/i.test(req.headers.get('content-type')||''))
    return Response.json({detail:'Solo JSON'},{status:415,headers:commonHeaders()});
   const raw=await req.text();if(raw.length>6500)return Response.json({detail:'Solicitud demasiado grande'},{status:413,headers:commonHeaders()});
   try{body=JSON.parse(raw);}catch{return Response.json({detail:'JSON inválido'},{status:400,headers:commonHeaders()});}
   if(!validAiBody(method,p,body))return Response.json({detail:'Campos no permitidos'},{status:422,headers:commonHeaders()});
  }
  const r=await upstream('ai/'+p,token,{method,body});
  const data=await r.json().catch(()=>({detail:'Respuesta inválida'}));
  const status=[200,201,202,400,401,403,404,409,413,415,422,503].includes(r.status)?r.status:502;
  return Response.json(status<300?data:{detail:data.detail||'Error de IA'}, {status,headers:commonHeaders()});
 }catch{return Response.json({detail:'FastAPI no responde'},{status:503,headers:commonHeaders()});}
}
export async function GET(req,ctx){return handle(req,ctx,'GET')}
export async function POST(req,ctx){return handle(req,ctx,'POST')}
export async function PATCH(req,ctx){return handle(req,ctx,'PATCH')}
