import asyncio
import json
import os
import secrets
import hashlib
import time
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI,UploadFile,File,Form,HTTPException,Request,Response
from fastapi.responses import StreamingResponse,FileResponse,JSONResponse
from fastapi.staticfiles import StaticFiles
from .config import settings,ROOT
from .db import db,uid,SQLiteStore
from .security import redact
from .types import RunRequest,WorkspaceRequest,URLImport,RetrievalRequest,ApprovalDecision,EvaluationRequest,RepairProposal,RetrievalResponse,RunRecord,ServiceRegistration
from .knowledge import knowledge,parse_file,fetch_public
from .providers import provider_health,reranker
from .mcp_client import hub
from .graph import runner
from .evaluation import evaluator
from . import workspaces,actions

os.environ.setdefault('LANGGRAPH_STRICT_MSGPACK','true')
csrf=secrets.token_urlsafe(32)
background=set()
health_cache={}

def schedule(coro):
    task=asyncio.create_task(coro);background.add(task);task.add_done_callback(background.discard);return task

@asynccontextmanager
async def lifespan(app):
    await runner.start()
    schedule(hub.connect())
    for doc in db.list('document'):
        if doc['status'] in ('queued','indexing'):schedule(knowledge.ingest(doc))
    for job in db.list('evaluation'):
        if job['status'] in ('running','queued','interrupted'):
            evaluator.launch(job['id'],EvaluationRequest(limit=job['limit'],ragas=job['ragas']))
    yield
    for task in list(background):task.cancel()
    for task in evaluator.tasks.values():task.cancel()
    await asyncio.gather(*background,*evaluator.tasks.values(),return_exceptions=True)
    await runner.close()

app=FastAPI(title='TraceForge API',version='0.1.0',lifespan=lifespan)

@app.middleware('http')
async def origin_guard(request:Request,call_next):
    origin=request.headers.get('origin')
    if origin and origin not in {'http://127.0.0.1:8000','http://localhost:8000','http://127.0.0.1:5173','http://localhost:5173'}:
        return JSONResponse({'detail':'Origin 不在本机应用范围'},status_code=403)
    if request.method not in ('GET','HEAD','OPTIONS') and request.url.path.startswith('/api/'):
        if request.headers.get('x-traceforge-csrf')!=csrf:
            return JSONResponse({'detail':'会话已过期，请刷新工作台'},status_code=403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff';response.headers['X-Frame-Options']='DENY'
    return response

@app.exception_handler(ValueError)
async def value_error(request,exc):return JSONResponse({'detail':redact(str(exc))},status_code=400)

@app.exception_handler(Exception)
async def service_error(request,exc):
    return JSONResponse({'detail':'服务调用失败：'+redact(str(exc))[:800]},status_code=503)

@app.get('/api/v1/session')
async def session():return {'csrf':csrf,'version':'0.1.0'}

@app.get('/api/v1/health')
async def health(refresh:bool=False):
    if refresh or time.time()-health_cache.get('at',0)>30:
        checks=await provider_health();checks['mcp']=hub.status
        health_cache.update(at=time.time(),checks=checks)
    return health_cache['checks']|{'app':{'ok':True,'detail':'TraceForge 0.1.0'}}

@app.get('/api/v1/config')
async def config():
    return {'model':settings.deepseek_model,'embedding':settings.embedding_model,'dimension':1024,'reranker_path':settings.rerank_model_path,'device':reranker.device or settings.rerank_device,'milvus':settings.milvus_uri,'max_model_calls':settings.max_model_calls,'max_iterations':settings.max_iterations,'data_dir':str(settings.data_dir),'key_configured':bool(settings.deepseek_api_key)}

@app.get('/api/v1/workspaces')
async def list_workspaces():return db.list('workspace')

@app.post('/api/v1/workspaces')
async def add_workspace(request:WorkspaceRequest):return workspaces.register(request.name,request.path,request.stack)

@app.get('/api/v1/workspaces/{id}/files')
async def workspace_files(id:str):return await asyncio.to_thread(workspaces.files,id)

@app.post('/api/v1/workspaces/{id}/services')
async def register_service(id:str,request:ServiceRegistration):
    from .services import register
    return await register(id,request)

@app.get('/api/v1/workspaces/{id}/services')
async def list_services(id:str):
    ws=workspaces.workspace(id)
    return [{'id':name,'health_url':ws.get('health_checks',{}).get(name),**(db.get('service',name) or {'kind':'container','name':name})} for name in ws.get('services',[])]

@app.get('/api/v1/workspaces/{id}/file')
async def workspace_file(id:str,path:str):return {'path':path,'text':await asyncio.to_thread(workspaces.read_file,id,path)}

@app.post('/api/v1/workspaces/{id}/preferences')
async def preferences(id:str,request:Request):
    workspaces.workspace(id);value=redact(await request.json())
    await SQLiteStore().aput(('workspace',id),'preferences',value);return {'ok':True}

@app.get('/api/v1/documents')
async def documents():return [{k:v for k,v in d.items() if k!='text'} for d in db.list('document')]

@app.get('/api/v1/documents/{id}')
async def document(id:str):
    result=db.get('document',id)
    if not result:raise HTTPException(404,'文档不存在')
    return result

@app.post('/api/v1/documents/upload')
async def upload(file:UploadFile=File(...),stack:str=Form('general'),workspace_id:str=Form('global'),index:bool=Form(True)):
    content=await file.read(25_000_001)
    if len(content)>25_000_000:raise ValueError('文件超过25MB限制')
    filename=Path(file.filename or 'upload.txt').name
    if Path(filename).suffix.lower() in {'.png','.jpg','.jpeg','.webp'}:text=await knowledge.screenshot(filename,content)
    else:text=await asyncio.to_thread(parse_file,filename,content)
    if not text.strip():raise ValueError('文件未提取到内容')
    record=knowledge.add(filename,text,'upload://'+hashlib.sha256(content).hexdigest()[:32]+'/'+filename,stack,workspace_id)
    if index:schedule(knowledge.ingest(record))
    else:record['status']='attachment';db.put('document',record['id'],record)
    return {k:v for k,v in record.items() if k!='text'}

@app.put('/api/v1/documents/{id}/text')
async def edit_document(id:str,request:Request):
    record=db.get('document',id)
    if not record:raise HTTPException(404,'文档不存在')
    text=(await request.json()).get('text','')
    if not isinstance(text,str) or not text.strip():raise ValueError('请提供非空文本')
    updated=knowledge.add(record['title'],text,record['source'],record['stack'],record['workspace_id'],record.get('version',''))
    schedule(knowledge.ingest(updated));return {'id':id,'status':'queued'}

@app.post('/api/v1/documents/import')
async def import_url(request:URLImport):
    title,text,url=await fetch_public(request.url)
    record=knowledge.add(title,text,url,request.stack,request.workspace_id,request.version)
    schedule(knowledge.ingest(record));return {k:v for k,v in record.items() if k!='text'}

@app.post('/api/v1/documents/{id}/reindex')
async def reindex(id:str):
    record=db.get('document',id)
    if not record:raise HTTPException(404,'文档不存在')
    schedule(knowledge.ingest(record));return {'status':'queued'}

@app.delete('/api/v1/documents/{id}')
async def delete_document(id:str):await knowledge.delete(id);return {'ok':True}

@app.post('/api/v1/retrieval',response_model=RetrievalResponse)
async def retrieval(request:RetrievalRequest):return await __import__('traceforge.retrieval',fromlist=['retrieve']).retrieve(request)

@app.get('/api/v1/runs')
async def runs():return [{k:v for k,v in r.items() if k not in {'evidence','retrievals','model_records'}} for r in db.list('run')]

@app.post('/api/v1/runs')
async def new_run(request:RunRequest):
    if request.workspace_id:workspaces.workspace(request.workspace_id)
    for id in request.attachment_ids:
        if not db.get('document',id):raise ValueError('附件不存在')
    thread=request.thread_id or uid()
    if any(r['thread_id']==thread and r['status'] in ('running','awaiting_approval','interrupted') for r in db.list('run')):raise ValueError('当前会话仍有未结束任务')
    id=uid();record=redact(request.model_dump())|{'id':id,'thread_id':thread,'status':'running','created':time.time(),'report':'','model_calls':0,'evidence':[]}
    db.put('run',id,record);runner.launch(id);return record

@app.get('/api/v1/runs/{id}',response_model=RunRecord)
async def get_run(id:str):
    record=db.get('run',id)
    if not record:raise HTTPException(404,'任务不存在')
    return record

@app.get('/api/v1/runs/{id}/events')
async def events(id:str,request:Request,after:int=0):
    if not db.get('run',id):raise HTTPException(404,'任务不存在')
    after=max(after,int(request.headers.get('last-event-id','0')))
    async def stream():
        cursor=after
        while not await request.is_disconnected():
            items=db.events(id,cursor)
            for item in items:
                cursor=item['seq'];yield f'id: {cursor}\nevent: {item["event"]}\ndata: {json.dumps(item["data"],ensure_ascii=False)}\n\n'
            run=db.get('run',id)
            if not items and run['status'] in ('completed','failed','cancelled','interrupted','limited'):break
            yield ': keep-alive\n\n';await asyncio.sleep(.4)
    return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

@app.post('/api/v1/runs/{id}/approval')
async def approve(id:str,request:ApprovalDecision):
    active=runner.tasks.get(id)
    if active and not active.done() and (db.get('run',id) or {}).get('status')=='awaiting_approval':
        try:await asyncio.wait_for(asyncio.shield(active),timeout=8)
        except asyncio.TimeoutError:raise ValueError('审核状态仍在保存，请稍后重试')
    run=db.get('run',id)
    if not run or run['status']!='awaiting_approval' or not run.get('preview'):raise ValueError('当前没有待审核动作')
    if request.payload_hash!=run['preview']['payload_hash']:raise ValueError('审核内容已过期，请刷新任务')
    decision={'decision':request.decision,'payload_hash':request.payload_hash}
    if request.decision=='edit':
        if not request.edited_proposal:raise ValueError('修改审核需要新的提案')
        if request.edited_proposal.workspace_id!=run.get('workspace_id'):raise ValueError('修改提案不能切换项目')
        decision['proposal']=actions.preview(request.edited_proposal)['proposal']
    runner.launch(id,decision);return {'status':'resuming'}

@app.post('/api/v1/runs/{id}/resume')
async def resume(id:str):
    run=db.get('run',id)
    if not run or run['status'] not in ('interrupted','failed'):raise ValueError('仅可恢复已中断或失败任务')
    runner.launch(id,'restart');return {'status':'resuming'}

@app.post('/api/v1/runs/{id}/cancel')
async def cancel(id:str):
    run=db.get('run',id)
    if not run:raise HTTPException(404,'任务不存在')
    task=runner.tasks.get(id)
    if task and not task.done():task.cancel()
    else:db.put('run',id,run|{'status':'cancelled','preview':None});db.event(id,'done',{'status':'cancelled'})
    return {'status':'cancelled'}

@app.get('/api/v1/actions')
async def action_history():return db.actions()

@app.post('/api/v1/actions/preview')
async def action_preview(proposal:RepairProposal):return actions.preview(proposal)

@app.post('/api/v1/actions/{id}/rollback')
async def rollback(id:str):return await asyncio.to_thread(actions.rollback,id)

@app.post('/api/v1/actions/{id}/artifact-preview')
async def artifact_preview(id:str,request:Request):
    record=next((a for a in db.actions() if a['id']==id),None)
    if not record:raise ValueError('执行记录不存在')
    index=(await request.json()).get('index',0);artifact=record['value'].get('artifacts',[])[index]
    proposal=RepairProposal(kind='patch',title='应用容器执行结果',description='从隔离副本生成的文件变更，需要再次审核',workspace_id=record['value']['proposal']['workspace_id'],file=artifact['file'],replacement=artifact['replacement'],expected_hash=artifact['expected_hash'])
    return actions.preview(proposal)

@app.post('/api/v1/actions/propose')
async def manual_propose(proposal:RepairProposal):
    view=actions.preview(proposal);id=uid()
    record={'id':id,'thread_id':uid(),'mode':'manual','query':proposal.title,'workspace_id':proposal.workspace_id,'status':'awaiting_approval','preview':view,'created':time.time(),'report':proposal.description,'model_calls':0}
    db.put('run',id,record);return record

@app.post('/api/v1/runs/{id}/manual-approval')
async def manual_approve(id:str,request:ApprovalDecision):
    run=db.get('run',id)
    if not run or run.get('mode')!='manual' or run['status']!='awaiting_approval':raise ValueError('没有手动审核动作')
    if request.payload_hash!=run['preview']['payload_hash']:raise ValueError('审核内容已过期')
    if request.decision=='reject':run.update(status='completed',preview=None);db.put('run',id,run);return run
    if request.decision=='edit':
        if not request.edited_proposal or request.edited_proposal.workspace_id!=run['workspace_id']:raise ValueError('修改提案不能切换项目')
        run['preview']=actions.preview(request.edited_proposal);db.put('run',id,run);return run
    run['status']='running';db.put('run',id,run)
    async def finish():
        result=await actions.execute(id,run['preview']);run.update(action_result=result,status='completed',preview=None);db.put('run',id,run);db.event(id,'action',result);db.event(id,'done',{'status':'completed'})
    schedule(finish());return {'status':'running'}

@app.get('/api/v1/mcp')
async def mcp_status():return hub.status

@app.post('/api/v1/mcp/reconnect')
async def mcp_reconnect():return await hub.connect()

@app.get('/api/v1/evaluations')
async def evaluations():return [{k:v for k,v in j.items() if k!='rows'} for j in db.list('evaluation')]

@app.get('/api/v1/evaluations/{id}')
async def evaluation(id:str):
    result=db.get('evaluation',id)
    if not result:raise HTTPException(404,'评估任务不存在')
    return result

@app.get('/api/v1/evaluations/{id}/export')
async def evaluation_export(id:str):
    result=await evaluation(id)
    return Response(json.dumps(result,ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="evaluation-{id}.json"'})

@app.post('/api/v1/evaluations')
async def new_evaluation(request:EvaluationRequest):
    id=uid();record={'id':id,'status':'queued','progress':0,'limit':request.limit,'ragas':request.ragas,'created':time.time()}
    db.put('evaluation',id,record);evaluator.launch(id,request);return record

@app.post('/api/v1/evaluations/{id}/cancel')
async def cancel_evaluation(id:str):
    task=evaluator.tasks.get(id)
    if task:evaluator.explicit_cancel.add(id);task.cancel()
    return {'status':'cancelled'}

@app.post('/api/v1/evaluations/{id}/resume')
async def resume_evaluation(id:str):
    job=db.get('evaluation',id)
    if not job or job['status'] not in ('failed','interrupted','cancelled'):raise ValueError('评估没有中断或失败')
    task=evaluator.tasks.get(id)
    if task and not task.done():raise ValueError('评估仍在运行')
    evaluator.explicit_cancel.discard(id)
    evaluator.launch(id,EvaluationRequest(limit=job['limit'],ragas=job['ragas']))
    return {'status':'resuming'}

@app.post('/api/v1/evaluations/{id}/retry-failed')
async def retry_failed_metrics(id:str):
    job=db.get('evaluation',id)
    if not job or job['status']!='completed':raise ValueError('仅可重试已结束评估中的失败指标')
    job['status']='interrupted';db.put('evaluation',id,job)
    evaluator.launch(id,EvaluationRequest(limit=job['limit'],ragas=job['ragas']))
    return {'status':'retrying_failed_metrics'}

@app.get('/api/v1/graph')
async def graph():return {'mermaid':runner.graph.get_graph().draw_mermaid(),'nodes':['receive','plan','logs','project','docs','gather','draft','evaluate','improve','narrate','prepare','review','execute','verify','archive']}

dist=ROOT/'frontend'/'dist'
if (dist/'assets').exists():app.mount('/assets',StaticFiles(directory=str(dist/'assets')),name='assets')

@app.get('/{path:path}',include_in_schema=False)
async def frontend(path:str):
    if path.startswith('api/'):raise HTTPException(404,'接口不存在')
    if (dist/'index.html').exists():return FileResponse(dist/'index.html')
    return JSONResponse({'detail':'请先构建前端：cd frontend; npm run build'},status_code=503)
