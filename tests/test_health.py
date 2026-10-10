import httpx
import pytest
import pymilvus

from traceforge import providers

@pytest.fixture(autouse=True)
def isolated_deepseek_config(monkeypatch):
    monkeypatch.setattr(providers.settings,'deepseek_api_key','sk-test-health-placeholder')
    monkeypatch.setattr(providers.settings,'deepseek_proxy_url','')


@pytest.mark.asyncio
async def test_http_success_does_not_hide_milvus_rpc_failure(monkeypatch):
    """Regression: management HTTP said OK while Milvus could not reach etcd."""
    async_client=httpx.AsyncClient
    transport=httpx.MockTransport(lambda request: httpx.Response(
        200,json={'data':[{'id':providers.settings.deepseek_model}]},request=request))
    monkeypatch.setattr(providers.httpx,'AsyncClient',
        lambda **kwargs: async_client(transport=transport,**kwargs))
    closed=[]

    class UnreadyMilvus:
        def __init__(self,**kwargs):pass
        def list_collections(self,**kwargs):raise TimeoutError('etcd is unreachable')
        def close(self):closed.append(True)

    monkeypatch.setattr(pymilvus,'MilvusClient',UnreadyMilvus)
    checks=await providers.provider_health()
    assert checks['ollama']['ok'] and checks['deepseek']['ok']
    assert checks['milvus']['ok'] is False
    assert 'etcd is unreachable' in checks['milvus']['detail']
    assert closed==[True]


def test_milvus_health_uses_configured_rpc_endpoint(monkeypatch):
    endpoint='http://127.0.0.1:29530'
    monkeypatch.setattr(providers.settings,'milvus_uri',endpoint)
    seen=[]

    class ReadyMilvus:
        def __init__(self,uri,timeout):seen.append(uri)
        def list_collections(self,timeout):return []
        def close(self):seen.append('closed')

    monkeypatch.setattr(pymilvus,'MilvusClient',ReadyMilvus)
    assert providers.milvus_health()['ok'] is True
    assert seen==[endpoint,'closed']


def mock_deepseek(monkeypatch,handler):
    async_client=httpx.AsyncClient
    transport=httpx.MockTransport(handler)
    monkeypatch.setattr(providers.httpx,'AsyncClient',
        lambda **kwargs: async_client(transport=transport,**kwargs))
    monkeypatch.setattr(providers.settings,'deepseek_api_key','sk-test-health-placeholder')


@pytest.mark.asyncio
async def test_deepseek_recovers_from_one_empty_connect_timeout(monkeypatch):
    calls=[]
    def handler(request):
        calls.append(request.url)
        if len(calls)==1:raise httpx.ConnectTimeout('',request=request)
        return httpx.Response(200,json={'data':[{'id':providers.settings.deepseek_model}]},request=request)
    mock_deepseek(monkeypatch,handler)
    check=await providers.deepseek_health()
    assert check['ok'] and check['recovered'] and check['attempts']==2
    assert len(calls)==2


@pytest.mark.asyncio
@pytest.mark.parametrize('error_type',[httpx.ConnectTimeout,httpx.ReadTimeout])
async def test_deepseek_persistent_empty_timeout_has_useful_detail(monkeypatch,error_type):
    calls=[]
    def handler(request):
        calls.append(request.url)
        raise error_type('',request=request)
    mock_deepseek(monkeypatch,handler)
    check=await providers.deepseek_health()
    assert not check['ok'] and check['error_type']==error_type.__name__
    assert '超时' in check['detail'] and check['attempts']==2
    assert len(calls)==2


@pytest.mark.asyncio
@pytest.mark.parametrize('status',[401,402,403])
async def test_deepseek_auth_or_account_failure_is_not_retried(monkeypatch,status):
    calls=[]
    def handler(request):
        calls.append(request.url)
        return httpx.Response(status,json={'error':{'message':'sk-test-health-placeholder'}},request=request)
    mock_deepseek(monkeypatch,handler)
    check=await providers.deepseek_health()
    assert not check['ok'] and check['status_code']==status and check['attempts']==1
    assert len(calls)==1 and 'sk-test-health-placeholder' not in check['detail']


@pytest.mark.asyncio
async def test_deepseek_missing_model_is_reported_explicitly(monkeypatch):
    mock_deepseek(monkeypatch,lambda request:httpx.Response(200,json={'data':[{'id':'other-model'}]},request=request))
    check=await providers.deepseek_health()
    assert not check['ok'] and check['error_type']=='ModelUnavailable'
    assert providers.settings.deepseek_model in check['detail']
