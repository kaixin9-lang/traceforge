import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from langchain_deepseek import ChatDeepSeek
from langchain_ollama import OllamaEmbeddings
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
import httpx
from .config import settings
from .security import redact

@dataclass
class CallBudget:
    calls: int = 0
    max_calls: int = settings.max_model_calls
    records: list = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def reserve(self):
        async with self.lock:
            if self.calls >= self.max_calls:
                raise RuntimeError('本次任务已达到模型调用预算，请根据已有证据继续排查')
            self.calls += 1

def deepseek_http_options():
    return {'trust_env':False,'proxy':settings.deepseek_proxy_url or None}

def chat_model(thinking=False):
    if not settings.deepseek_api_key:
        raise RuntimeError('请在后端 .env 中配置 DEEPSEEK_API_KEY')
    return ChatDeepSeek(
        model=settings.deepseek_model, api_key=settings.deepseek_api_key,
        api_base='https://api.deepseek.com', timeout=60, max_retries=2,
        max_tokens=4096,
        extra_body={'thinking': {'type': 'enabled' if thinking else 'disabled'}},
        http_client=httpx.Client(**deepseek_http_options()),
        http_async_client=httpx.AsyncClient(**deepseek_http_options()),
    )

async def structured(schema, system, text, budget=None):
    if budget: await budget.reserve()
    start=time.perf_counter()
    model=chat_model()
    response=await model.with_structured_output(schema, method='function_calling', include_raw=True).ainvoke([
        SystemMessage(content=system), HumanMessage(content=redact(text))])
    if budget:
        budget.records.append({'seconds':round(time.perf_counter()-start,3),'usage':response['raw'].usage_metadata,'operation':schema.__name__})
    if response['parsed'] is None:
        raise ValueError('模型结构化输出解析失败: '+str(response.get('parsing_error'))[:200])
    return response['parsed']

async def text_chain(system, text, budget=None):
    if budget: await budget.reserve()
    chain=ChatPromptTemplate.from_messages([('system',system),('human','{input}')]) | chat_model() | StrOutputParser()
    started=time.perf_counter();result=await chain.ainvoke({'input':redact(text)})
    if budget:budget.records.append({'operation':'lcel_text','seconds':round(time.perf_counter()-started,3)})
    return result

def embeddings():
    return OllamaEmbeddings(model=settings.embedding_model,base_url=settings.ollama_url,client_kwargs={'trust_env':False,'timeout':60})

class Reranker:
    def __init__(self):
        self.model=None
        self.device=None
        self.lock=asyncio.Lock()

    def _load(self):
        import torch
        from sentence_transformers import CrossEncoder
        self.device='cuda' if settings.rerank_device == 'cuda' and torch.cuda.is_available() else 'cpu'
        kwargs={'torch_dtype':torch.float16} if self.device=='cuda' else {}
        self.model=CrossEncoder(settings.rerank_model_path,device=self.device,max_length=2048,local_files_only=True,model_kwargs=kwargs)

    def _predict(self,query,documents):
        import torch
        if not self.model:self._load()
        return self.model.predict([(query,d) for d in documents],batch_size=4,activation_fn=torch.nn.Sigmoid(),show_progress_bar=False).tolist()

    async def score(self,query,documents):
        if not documents:return []
        async with self.lock:
            return await asyncio.to_thread(self._predict,query,documents)

reranker=Reranker()

def deepseek_health_error(error):
    kind=type(error).__name__
    result={'ok':False,'error_type':kind}
    if isinstance(error,httpx.HTTPStatusError):
        status=error.response.status_code
        result['status_code']=status
        message={401:'API密钥鉴权失败，请检查后端配置',402:'账户余额不足',403:'API访问被拒绝',
                 429:'请求过于频繁，请稍后重试',500:'服务端错误，请稍后重试',503:'服务繁忙，请稍后重试'}.get(status,f'API返回HTTP {status}')
    elif isinstance(error,httpx.ConnectTimeout):message='网络连接建立超时，请稍后重试'
    elif isinstance(error,httpx.ReadTimeout):message='API响应超时，请稍后重试'
    elif isinstance(error,httpx.TimeoutException):message='请求超时，请稍后重试'
    else:message=f'{kind}：'+(redact(str(error)) or '请求未能完成')
    result['detail']='DeepSeek '+message[:170]
    return result

async def deepseek_health():
    if not settings.deepseek_api_key:
        return {'ok':False,'detail':'尚未配置DEEPSEEK_API_KEY','error_type':'MissingKey','attempts':0}
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(**deepseek_http_options(),timeout=httpx.Timeout(8,connect=5)) as c:
                r=await c.get('https://api.deepseek.com/models',headers={'Authorization':'Bearer '+settings.deepseek_api_key})
                r.raise_for_status()
                names=[m['id'] for m in r.json()['data']]
            available=settings.deepseek_model in names
            result={'ok':available,'detail':settings.deepseek_model if available else f'配置的模型 {settings.deepseek_model} 不在可用模型列表中',
                    'models':names,'attempts':attempt+1,'recovered':attempt>0}
            if not available:result['error_type']='ModelUnavailable'
            return result
        except httpx.HTTPStatusError as e:
            result=deepseek_health_error(e)
            retryable=e.response.status_code in {500,502,503,504}
        except httpx.RequestError as e:
            result=deepseek_health_error(e);retryable=True
        except (ValueError,KeyError,TypeError) as e:
            result=deepseek_health_error(e);retryable=False
        result['attempts']=attempt+1
        if not retryable or attempt==1:
            logging.getLogger(__name__).warning('DeepSeek health failed: %s (attempts=%s)',result['detail'],result['attempts'])
            return result
        await asyncio.sleep(.3)

def milvus_health():
    """Check the configured RPC endpoint; management HTTP alone can be premature."""
    from pymilvus import MilvusClient
    client=None
    try:
        client=MilvusClient(uri=settings.milvus_uri,timeout=3)
        client.list_collections(timeout=3)
        return {'ok':True,'detail':settings.collection}
    except Exception as e:
        return {'ok':False,'detail':redact('Milvus RPC连接失败：'+str(e))[:180]}
    finally:
        if client is not None:client.close()

async def provider_health():
    result={}
    async with httpx.AsyncClient(trust_env=False,timeout=8) as c:
        for name,url in [('ollama',settings.ollama_url+'/api/tags')]:
            try:
                r=await c.get(url);r.raise_for_status();result[name]={'ok':True,'detail':settings.embedding_model if name=='ollama' else settings.collection}
            except Exception as e:result[name]={'ok':False,'detail':redact(str(e))[:180]}
    result['deepseek']=await deepseek_health()
    result['milvus']=await asyncio.to_thread(milvus_health)
    import torch
    result['reranker']={'ok':settings.rerank_model_path and __import__('pathlib').Path(settings.rerank_model_path).exists(),'detail':reranker.device or ('cuda 就绪' if torch.cuda.is_available() else 'cpu'),'cuda':torch.cuda.is_available(),'torch':torch.__version__}
    return result
