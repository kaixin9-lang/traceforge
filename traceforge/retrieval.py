import asyncio
import json
import time
import numpy as np
from pydantic import BaseModel
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document
from .knowledge import knowledge
from .providers import embeddings,reranker,structured
from .types import Evidence,RetrievalRequest

class QueryPlan(BaseModel):
    queries: list[str]

def normalize_hits(hits):
    result=[]
    for hit in hits:
        data=dict(hit)
        result.append({'id':str(data.get('id',data.get('pk'))),'score':float(data.get('score',data.get('distance',0))),'entity':dict(data['entity'])})
    return result

def fuse(lists,mode='rrf'):
    merged={}
    for route,hits in lists.items():
        vals=[h['score'] for h in hits];lo=min(vals,default=0);hi=max(vals,default=1)
        for rank,hit in enumerate(hits,1):
            item=merged.setdefault(hit['id'],hit|{'scores':{},'score':0.0})
            item['scores'][route]=hit['score']
            weight=0.6 if route.startswith('dense') else 0.4
            contribution=1/(60+rank) if mode=='rrf' else weight*((hit['score']-lo)/(hi-lo) if hi>lo else 1.0)
            item['score']+=contribution
    return sorted(merged.values(),key=lambda x:(-x['score'],x['id']))

def mmr_order(items,query_vector,limit,lambda_mult=.5):
    if not items:return []
    matrix=np.array([x['entity']['dense'] for x in items],dtype=float)
    matrix=matrix/np.maximum(np.linalg.norm(matrix,axis=1,keepdims=True),1e-9)
    q=np.array(query_vector);q=q/max(np.linalg.norm(q),1e-9)
    sim=matrix@q;selected=[];remaining=set(range(len(items)))
    while remaining and len(selected)<limit:
        idx=max(remaining,key=lambda i:lambda_mult*sim[i]-(1-lambda_mult)*max((matrix[i]@matrix[j] for j in selected),default=0))
        selected.append(idx);remaining.remove(idx)
    return [items[i] for i in selected]

async def retrieve(request:RetrievalRequest,budget=None):
    started=time.perf_counter();query=request.query;queries=[query]
    if request.query_mode!='original':
        instruction={'rewrite':'生成适合检索的关键词查询，保留原文错误码、类名、路径。','hyde':'生成可能的技术解释供检索，不当作证据。','multi':'拆成最多3个互补检索子问题，保留所有错误码。'}[request.query_mode]
        plan=await structured(QueryPlan,instruction+'返回queries列表。',query,budget)
        queries=[query]+plan.queries[:3]
    client=await asyncio.to_thread(knowledge.connect)
    filter_parts=[];params={}
    if request.workspace_id:filter_parts.append('(workspace_id == {ws} or workspace_id == "global")');params['ws']=request.workspace_id
    if request.stack:filter_parts.append('(stack == {stack} or stack == "general")');params['stack']=request.stack
    if request.version:filter_parts.append('(version == {version} or version == "")');params['version']=request.version
    expression=' and '.join(filter_parts)
    fields=['text','document_id','title','source','metadata','dense']
    routes={};warnings=[];qvector=None
    for i,q in enumerate(queries):
        if request.strategy in ('dense','hybrid') or request.mmr:
            try:
                vector=await embeddings().aembed_query(q)
                if qvector is None:qvector=vector
                if request.strategy in ('dense','hybrid'):
                    hits=await asyncio.to_thread(client.search,collection_name=__import__('traceforge.config',fromlist=['settings']).settings.collection,data=[vector],anns_field='dense',limit=20,search_params={'metric_type':'COSINE','params':{'ef':64}},filter=expression,filter_params=params,output_fields=fields)
                    routes[f'dense:{i}']=normalize_hits(hits[0])
            except Exception as e:warnings.append(f'稠密召回不可用：{str(e)[:160]}')
        if request.strategy in ('sparse','hybrid'):
            try:
                hits=await asyncio.to_thread(client.search,collection_name=__import__('traceforge.config',fromlist=['settings']).settings.collection,data=[q],anns_field='sparse',limit=20,search_params={'metric_type':'BM25'},filter=expression,filter_params=params,output_fields=fields)
                routes[f'sparse:{i}']=normalize_hits(hits[0])
            except Exception as e:warnings.append(f'稀疏召回不可用：{str(e)[:160]}')
    items=fuse(routes,request.fusion)[:20]
    before=[{'id':x['id'],'title':x['entity']['title'],'score':x['score'],'scores':x['scores']} for x in items]
    if request.rerank and items:
        try:
            scores=await reranker.score(query,[x['entity']['text'] for x in items])
            for x,score in zip(items,scores):x['scores']['rerank']=score
            items.sort(key=lambda x:-x['scores']['rerank'])
        except Exception as e:warnings.append(f'重排不可用，保留融合排名：{str(e)[:160]}')
    if request.mmr and qvector:items=mmr_order(items,qvector,request.top_k)
    evidence=[]
    for item in items[:request.top_k]:
        e=item['entity'];evidence.append(Evidence(id=item['id'],title=e['title'],content=e['text'],source=e['source'],metadata=e['metadata']|{'document_id':e['document_id']},scores=item['scores']|{'fusion':item['score']}).model_dump())
    def route_public(hits):return [{'id':x['id'],'title':x['entity']['title'],'score':x['score']} for x in hits]
    return {'queries':queries,'routes':{k:route_public(v) for k,v in routes.items()},'before_rerank':before,'evidence':evidence,'warnings':warnings,'elapsed_ms':round((time.perf_counter()-started)*1000),'config':request.model_dump()}

class HybridRetriever(BaseRetriever):
    """LangChain Retriever interface for the explicit Milvus pipeline."""
    def _get_relevant_documents(self,query,*,run_manager):
        raise RuntimeError('FastAPI 使用异步 aget_relevant_documents')
    async def _aget_relevant_documents(self,query,*,run_manager):
        result=await retrieve(RetrievalRequest(query=query))
        return [Document(page_content=e['content'],metadata=e['metadata']|{'source':e['source'],'id':e['id']}) for e in result['evidence']]
