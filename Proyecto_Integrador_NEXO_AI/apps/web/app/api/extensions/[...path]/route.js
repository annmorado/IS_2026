import {extensionPath,validExtensionBody} from '../../../../lib/extensions.mjs';
import {allowedOrigin,apiBase,commonHeaders,sessionToken,upstream} from '../../../../lib/server.mjs';
export const dynamic='force-dynamic';
async function handle(req,context,method){
 const path=extensionPath(method,(await context.params).path,new URL(req.url).search.slice(1));
 if(!path)return Response.json({detail:'Ruta de extensión no autorizada'},{status:404,headers:commonHeaders()});
 if(method!=='GET'&&!allowedOrigin(req))return Response.json({detail:'Origen no autorizado'},{status:403,headers:commonHeaders()});
 const token=await sessionToken();
 if(!token)return Response.json({detail:'Inicia sesión'},{status:401,headers:commonHeaders()});
 try{
  let r;
  if(method==='POST'&&path.startsWith('documents/ocr/proposals?')){
   if(!/^multipart\/form-data;/i.test(req.headers.get('content-type')||''))return Response.json({detail:'Imagen multipart requerida'},{status:415,headers:commonHeaders()});
   if(Number(req.headers.get('content-length')||0)>4*1024*1024+12000)return Response.json({detail:'Imagen demasiado grande'},{status:413,headers:commonHeaders()});
   const input=await req.formData();if([...input.keys()].some(k=>k!=='file'))return Response.json({detail:'Campos inesperados'},{status:422,headers:commonHeaders()});
   const file=input.get('file');
   if(!(file instanceof File)||file.size===0||file.size>4*1024*1024||!['image/png','image/jpeg','image/webp'].includes(file.type))
    return Response.json({detail:'Archivo JPEG, PNG o WebP requerido (máximo 4 MB)'},{status:422,headers:commonHeaders()});
   const upload=new FormData();upload.append('file',file,file.name.slice(0,120));
   r=await fetch(apiBase()+'/'+path,{method:'POST',headers:{Authorization:'Bearer '+token,Accept:'application/json'},
      body:upload,cache:'no-store',redirect:'error'});
  }else{
   let body;
   if(method!=='GET'){
    if(!/^application\/json(?:;|$)/i.test(req.headers.get('content-type')||''))return Response.json({detail:'JSON requerido'},{status:415,headers:commonHeaders()});
    const raw=await req.text();if(raw.length>1800)return Response.json({detail:'Cuerpo demasiado grande'},{status:413,headers:commonHeaders()});
    try{body=JSON.parse(raw)}catch{return Response.json({detail:'JSON inválido'},{status:400,headers:commonHeaders()});}
    if(!validExtensionBody(path,body))return Response.json({detail:'Campos inválidos'},{status:422,headers:commonHeaders()});
   }
   r=await upstream(path,token,{method,body});
  }
  const result=await r.json().catch(()=>({detail:'Respuesta inválida'}));
  const status=[200,201,400,401,403,404,409,410,413,415,422,503].includes(r.status)?r.status:502;
  return Response.json(status<300?result:{detail:result.detail||'Fallo en la operación'},
    {status,headers:commonHeaders()});
 }catch{return Response.json({detail:'FastAPI no responde'},{status:503,headers:commonHeaders()});}
}
export async function GET(req,ctx){return handle(req,ctx,'GET')}
export async function POST(req,ctx){return handle(req,ctx,'POST')}
export async function PUT(req,ctx){return handle(req,ctx,'PUT')}
