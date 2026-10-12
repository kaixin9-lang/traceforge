"""Real services smoke; artifacts preserve actual failures rather than hiding them."""
import asyncio
import json
import sys
import time
from pathlib import Path
import httpx
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from traceforge.config import settings

async def main():
    results={}
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8000/api/v1',trust_env=False,timeout=120) as c:
        s=(await c.get('/session')).json();c.headers['X-Traceforge-Csrf']=s['csrf']
        results['health']=(await c.get('/health?refresh=true')).json()
        results['mcp']=(await c.post('/mcp/reconnect',json={})).json()
        response=await c.post('/retrieval',json={'query':'FastAPI POST 返回422且错误指向body.name，应如何定位？','strategy':'hybrid','rerank':True})
        results['retrieval']={'status_code':response.status_code,'body':response.json()}
        response=await c.post('/runs',json={'query':'FastAPI POST /items 返回422，detail.loc是body.name，应该如何排查？','mode':'knowledge'})
        run=response.json();results['run_created']=run
        if 'id' in run:
            for _ in range(180):
                latest=(await c.get('/runs/'+run['id'])).json()
                if latest['status'] not in ('running','queued'):break
                await asyncio.sleep(1)
            results['run']=latest
    (settings.data_dir/'live-smoke.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'retrieval_status':results['retrieval']['status_code'],'run_status':results.get('run',{}).get('status'),'run_error':results.get('run',{}).get('error'),'evidence':len(results.get('run',{}).get('evidence',[]))},ensure_ascii=False))

if __name__=='__main__':asyncio.run(main())
