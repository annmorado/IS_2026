import {managementPath,validManagementBody} from '../../../../lib/management.mjs';
import {allowedOrigin,commonHeaders,sessionToken,upstream} from '../../../../lib/server.mjs';
export const dynamic='force-dynamic';
async function handle(req,context,method){
  const segments=(await context.params).path;
  const p=managementPath(method,segments,new URL(req.url).search.slice(1));
  if(!p)return Response.json({detail:'Ruta de gestión no autorizada'},{status:404,headers:commonHeaders()});
  if(method!=='GET'&&!allowedOrigin(req))return Response.json({detail:'Origen no autorizado'},{status:403,headers:commonHeaders()});
  const isAccept=method==='POST'&&p==='collaborators/invitations/accept';
  const token=isAccept?'':await sessionToken();
  if(!isAccept&&!token)return Response.json({detail:'Inicia sesión'},{status:401,headers:commonHeaders()});
  let body;
  if(method!=='GET'&&method!=='DELETE'){
    if(!/^application\/json(?:;|$)/i.test(req.headers.get('content-type')||''))return Response.json({detail:'JSON requerido'},{status:415,headers:commonHeaders()});
    try{const raw=await req.text();if(raw.length>4096)throw Error('large');body=JSON.parse(raw);
      if(!validManagementBody(p,method,body))return Response.json({detail:'Campos inválidos'},{status:422,headers:commonHeaders()});
    }catch{return Response.json({detail:'JSON inválido'},{status:400,headers:commonHeaders()});}
  }
  try{
    const response=await upstream(p,token,{method,body});
    const isFile=method==='GET'&&p.startsWith('reports/export?')&&response.ok;
    if(isFile){
      const pdf=p.includes('format=pdf');const type=pdf?'application/pdf':'text/csv; charset=utf-8';
      return new Response(response.body,{status:200,headers:{...commonHeaders(type),
        'Content-Disposition':response.headers.get('content-disposition')||'attachment; filename="reporte"'}});
    }
    const result=await response.json().catch(()=>({detail:'Respuesta inválida'}));
    const status=[200,201,400,401,403,404,409,410,415,422].includes(response.status)?response.status:502;
    return Response.json(status<300?result:{detail:result.detail||'Error de operación'},{status,headers:commonHeaders()});
  }catch{return Response.json({detail:'FastAPI no responde'},{status:503,headers:commonHeaders()});}
}
export async function GET(req,context){return handle(req,context,'GET');}
export async function POST(req,context){return handle(req,context,'POST');}
export async function PATCH(req,context){return handle(req,context,'PATCH');}
export async function PUT(req,context){return handle(req,context,'PUT');}
export async function DELETE(req,context){return handle(req,context,'DELETE');}
