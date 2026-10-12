import {useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {GitBranch,Play,Loader2} from 'lucide-react';
import {api,post,Json} from './api';

export default function RagComparison({query,workspace,act}:{query:string,workspace:string,act:(fn:()=>Promise<any>)=>Promise<any>}){
 const [mode,setMode]=useState('knowledge'),[id,setId]=useState('');
 const run=useQuery({queryKey:['rag-comparison',id],queryFn:()=>api<Json>('/runs/'+id),enabled:!!id,refetchInterval:q=>(q.state.data as Json)?.status==='running'?1000:false});
 return <section className="panel" style={{marginTop:25}}><div className="panel-heading"><GitBranch size={17}/><h2>RAG 架构实验</h2><span>固定检索与 Agent 自主调查</span></div><div className="command-compose"><select aria-label="RAG架构" value={mode} onChange={e=>setMode(e.target.value)}><option value="knowledge">2-Step RAG 知识问答</option><option value="diagnose">Agentic RAG 故障调查</option></select><p style={{fontSize:11,color:'#7b8daa',flex:1}}>使用上方问题运行完整生成流程，比较调用次数、证据与答案。</p><button className="secondary" disabled={!query||run.data?.status==='running'} onClick={async()=>{const r=await act(()=>post('/runs',{query,mode,workspace_id:workspace||null}));if(r)setId(r.id)}}><Play size={14}/>生成并比较</button></div>{run.data&&<><div className="result-summary"><span>{run.data.status==='running'?<Loader2 className="spin" size={14}/>:null}{run.data.status==='running'?'正在生成':run.data.status==='awaiting_approval'?'有修复提案，请在工作台审核':'生成结束'}</span><span>{run.data.model_calls} 次模型调用</span><span>{run.data.evidence.length} 条证据</span></div><div className="markdown"><Markdown remarkPlugins={[remarkGfm]}>{run.data.report}</Markdown></div>{run.data.error&&<div className="inline-error">{run.data.error}</div>}</>}</section>
}
