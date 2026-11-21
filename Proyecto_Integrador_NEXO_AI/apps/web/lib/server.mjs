import 'server-only';
import {cookies} from 'next/headers';
import {allowedOrigin} from './origin.mjs';
export {allowedOrigin};

export const COOKIE='nexo_web_session';

export function apiBase() {
  const value=(process.env.NEXO_API_BASE_URL||'http://127.0.0.1:8000/api/v1').replace(/\/$/,'');
  // No confiar en una URL HTTP externa en produccion.
  const url=new URL(value);
  if(!['http:','https:'].includes(url.protocol)) throw new Error('API URL invalida');
  if(process.env.NODE_ENV==='production' && url.protocol!=='https:' && !['127.0.0.1','localhost'].includes(url.hostname))
    throw new Error('La API remota de produccion exige HTTPS');
  return value;
}

export async function sessionToken(){ return (await cookies()).get(COOKIE)?.value||''; }

export async function upstream(path,token,{method='GET',body,extraHeaders={}}={}) {
  const options={method,cache:'no-store',redirect:'error',
    headers:{Accept:'application/json',...(token?{Authorization:'Bearer '+token}:{}),...(body?{'Content-Type':'application/json'}:{}),...extraHeaders},
    ...(body?{body:JSON.stringify(body)}:{})};
  return fetch(apiBase()+'/'+path,options);
}

export function commonHeaders(contentType='application/json'){
  return {'Cache-Control':'private, no-store, max-age=0','Pragma':'no-cache','Vary':'Cookie',
          'X-Content-Type-Options':'nosniff','Content-Type':contentType};
}
