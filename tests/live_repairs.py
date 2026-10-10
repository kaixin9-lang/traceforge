import asyncio
import json
import sys
from pathlib import Path
import httpx
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from traceforge.config import settings,ROOT
from traceforge.db import db
from traceforge.types import RepairProposal
from traceforge import actions

async def wait_run(c,id,seconds=180):
    for _ in range(seconds):
        r=(await c.get('/runs/'+id)).json()
        if r['status'] not in ('running','queued'):return r
        await asyncio.sleep(1)
    raise TimeoutError('运行未在时间预算内结束')

async def main():
    workspaces=db.get('meta','demo_workspaces');results={}
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8000/api/v1',trust_env=False,timeout=60) as c:
        c.headers['X-Traceforge-Csrf']=(await c.get('/session')).json()['csrf']
        samples=[('python','python demo.py','ModuleNotFoundError: No module named jsno。demo.py按约定应加载标准库json；请只修正config.json，复验python demo.py。'),('node','node demo.mjs','前端代理配置检查失败，ECONNREFUSED proxy target9999，但后端是8000。请只修正config.json，复验node demo.mjs。')]
        for stack,before_cmd,question in samples:
            config_path=ROOT/'examples'/stack/'config.json'
            config_path.write_text(json.dumps({'module':'jsno'} if stack=='python' else {'proxyTarget':'http://127.0.0.1:9999'}),encoding='utf-8')
            before=await actions.sandbox(RepairProposal(kind='sandbox',title='复现故障',description='只在演示副本中执行',workspace_id=workspaces[stack],command=before_cmd,runtime=stack),'reproduce-'+stack+'-'+__import__('uuid').uuid4().hex[:8])
            response=await c.post('/runs',json={'query':question+'\n真实日志：'+before['output'],'workspace_id':workspaces[stack]});response.raise_for_status();id=response.json()['id']
            run=await wait_run(c,id)
            records=[]
            for _ in range(4):
                if run['status']!='awaiting_approval':break
                view=run['preview'];proposal=view['proposal']
                if proposal['kind'] not in ('patch','sandbox') or proposal.get('network'):
                    r=await c.post('/runs/'+id+'/approval',json={'decision':'reject','payload_hash':view['payload_hash']})
                else:r=await c.post('/runs/'+id+'/approval',json={'decision':'approve','payload_hash':view['payload_hash']})
                if r.status_code==400 and '任务正在运行' in r.text:
                    await asyncio.sleep(1)
                    r=await c.post('/runs/'+id+'/approval',json={'decision':'approve' if proposal['kind'] in ('patch','sandbox') else 'reject','payload_hash':view['payload_hash']})
                r.raise_for_status();records.append(view);await asyncio.sleep(.7);run=await wait_run(c,id)
            after=await actions.sandbox(RepairProposal(kind='sandbox',title='验证修复',description='在演示副本执行验证',workspace_id=workspaces[stack],command=before_cmd,runtime=stack),'verify-'+stack+'-'+__import__('uuid').uuid4().hex[:8])
            results[stack]={'before':before,'run_id':id,'run':run,'approvals':records,'after':after,'passed':before['exit_code']!=0 and run['status']=='completed' and after['exit_code']==0}
            print(stack,'passed',results[stack]['passed'],run.get('error'),flush=True)
            (settings.data_dir/'repair-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    return results

if __name__=='__main__':asyncio.run(main())
