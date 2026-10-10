import asyncio
import inspect
import json
import math
import statistics
import time
from openai import AsyncOpenAI
import httpx
from ragas.llms import llm_factory
from ragas.embeddings.base import BaseRagasEmbedding
from ragas.metrics.collections import ContextPrecision,ContextRecall,ContextEntityRecall,Faithfulness,AnswerRelevancy,NoiseSensitivity
from .config import settings
from .db import db
from .corpus import golden_cases
from .retrieval import retrieve
from .providers import embeddings,text_chain,deepseek_http_options
from .types import RetrievalRequest
from .security import redact

class OllamaRagasEmbedding(BaseRagasEmbedding):
    def embed_text(self,text,**kwargs):return embeddings().embed_query(text)
    async def aembed_text(self,text,**kwargs):return await embeddings().aembed_query(text)

def ranking_metrics(evidence,document_id):
    positions=[i for i,e in enumerate(evidence,1) if e['metadata'].get('document_id')==document_id]
    return {'recall_at_5':float(bool(positions)),'mrr':1/min(positions) if positions else 0,'ndcg':1/math.log2(min(positions)+1) if positions else 0}

class Evaluator:
    def __init__(self):self.tasks={};self.lock=asyncio.Lock();self.explicit_cancel=set()
    def launch(self,id,request):
        self.tasks[id]=asyncio.create_task(self.run(id,request))
    async def run(self,id,request):
        async with self.lock:
            job=db.get('evaluation',id);job.update(status='running',rows=job.get('rows',[]),progress=job.get('progress',0));db.put('evaluation',id,job)
            client=AsyncOpenAI(api_key=settings.deepseek_api_key,base_url='https://api.deepseek.com',http_client=httpx.AsyncClient(**deepseek_http_options()),max_retries=2,timeout=60)
            judge=llm_factory(settings.deepseek_model,client=client,max_tokens=8192,extra_body={'thinking':{'type':'disabled'}})
            metrics=[ContextPrecision(judge),ContextRecall(judge),ContextEntityRecall(judge),Faithfulness(judge),AnswerRelevancy(judge,OllamaRagasEmbedding()),NoiseSensitivity(judge)]
            semaphore=asyncio.Semaphore(2)
            async def score(metric,sample):
                async with semaphore:
                    for attempt in range(3):
                        try:
                            args={k:v for k,v in sample.items() if k in inspect.signature(metric.ascore).parameters}
                            value=await asyncio.wait_for(metric.ascore(**args),timeout=100)
                            number=float(value.value)
                            return metric.name,{'value':number if math.isfinite(number) else None,'error':None if math.isfinite(number) else '评估返回非有限数值'}
                        except Exception as e:
                            error=redact(str(e))[:500]
                            if attempt<2:await asyncio.sleep(attempt+1)
                    return metric.name,{'value':None,'error':error}
            try:
                for index,case in enumerate(golden_cases()[:request.limit]):
                    if any(r['case']['id']==case['id'] for r in job['rows']):continue
                    row={'case':case,'retrieval':{},'ragas':{}}
                    for strategy,rerank in [('dense',False),('hybrid',False),('hybrid_rerank',True)]:
                        try:
                            result=await retrieve(RetrievalRequest(query=case['question'],strategy='dense' if strategy=='dense' else 'hybrid',rerank=rerank))
                            row['retrieval'][strategy]=ranking_metrics(result['evidence'],case['document_id'])|{'elapsed_ms':result['elapsed_ms'],'warnings':result['warnings'],'evidence_ids':[e['id'] for e in result['evidence']]}
                            if rerank:contexts=[e['content'] for e in result['evidence']];row['ordered_evidence']=result['evidence']
                        except Exception as e:row['retrieval'][strategy]={'error':redact(str(e))[:500]}
                    if 'ordered_evidence' in row:
                        response=await text_chain('只根据给定上下文回答问题，简洁说明定位和修复步骤。没有依据则明确说明。',json.dumps({'question':case['question'],'context':contexts},ensure_ascii=False))
                        row['sample']={'user_input':case['question'],'retrieved_contexts':contexts,'response':response,'reference':case['reference']}
                        if request.ragas:row['ragas']=dict(await asyncio.gather(*(score(m,row['sample']) for m in metrics)))
                    job['rows'].append(row);job['progress']=round((index+1)/request.limit*100);db.put('evaluation',id,job)
                summary={}
                if request.ragas:
                    for row in job['rows']:
                        if 'sample' not in row:continue
                        missing=[m for m in metrics if row['ragas'].get(m.name,{}).get('value') is None]
                        if missing:
                            row['ragas'].update(dict(await asyncio.gather(*(score(m,row['sample']) for m in missing))))
                            db.put('evaluation',id,job)
                for strategy in ['dense','hybrid','hybrid_rerank']:
                    values=[r['retrieval'].get(strategy,{}) for r in job['rows']]
                    summary[strategy]={key:statistics.mean([x[key] for x in values if key in x]) if any(key in x for x in values) else None for key in ['recall_at_5','mrr','ndcg','elapsed_ms']}
                    latency=sorted(x['elapsed_ms'] for x in values if 'elapsed_ms' in x)
                    summary[strategy].update(successful_samples=len(latency),p50_ms=statistics.median(latency) if latency else None,p95_ms=latency[max(0,math.ceil(len(latency)*.95)-1)] if latency else None)
                summary['ragas']={m.name:{'value':statistics.mean(vals) if vals else None,'successful_samples':len(vals),'failed_samples':len(job['rows'])-len(vals)} for m in metrics for vals in [[r['ragas'].get(m.name,{}).get('value') for r in job['rows'] if r['ragas'].get(m.name,{}).get('value') is not None]]}
                job.update(status='completed',summary=summary,finished=time.time(),model=settings.deepseek_model,embedding=settings.embedding_model,collection=settings.collection)
            except asyncio.CancelledError:job.update(status='cancelled' if id in self.explicit_cancel else 'interrupted')
            except Exception as e:job.update(status='failed',error=redact(str(e))[:800])
            finally:
                db.put('evaluation',id,job);await client.close()

evaluator=Evaluator()
