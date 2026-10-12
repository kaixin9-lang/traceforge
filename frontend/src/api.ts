import type {components} from './schema';
export type RunInput = components['schemas']['RunRequest'];
export type ApprovalInput = components['schemas']['ApprovalDecision'];
export type RepairInput = components['schemas']['RepairProposal'];
export type Json = Record<string, any>;
let csrf='';
async function request(url:string,options:RequestInit={}):Promise<Response>{
  try{return await fetch(url,options)}
  catch(error){
    if(error instanceof TypeError)throw new Error('无法连接本机后端。请运行 scripts\\start.ps1，确认出现“TraceForge 已启动”后重试；如果刚重启过服务，请刷新页面。');
    throw error;
  }
}
export async function api<T=any>(path:string,options:RequestInit={}):Promise<T>{
  if (!csrf) {
    const response=await request('/api/v1/session');
    if(!response.ok)throw new Error('无法获取后端会话，请确认 TraceForge 服务已正常启动。');
    const session=await response.json();
    if(typeof session.csrf!=='string'||!session.csrf)throw new Error('后端会话响应异常，请确认正在访问 http://127.0.0.1:8000。');
    csrf=session.csrf;
  }
  const headers=new Headers(options.headers);
  if(options.body && !(options.body instanceof FormData))headers.set('Content-Type','application/json');
  headers.set('X-Traceforge-Csrf',csrf);
  const response=await request('/api/v1'+path,{...options,headers});
  const data=await response.json();
  if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));
  return data;
}
export const post=(path:string,data:unknown={})=>api(path,{method:'POST',body:JSON.stringify(data)});
export const pretty=(x:any)=>JSON.stringify(x,null,2);
