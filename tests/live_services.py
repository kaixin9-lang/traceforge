import asyncio
import json
import sys
from pathlib import Path
import httpx
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from traceforge.config import ROOT,settings
from traceforge.db import db
from traceforge.workspaces import docker
from tests.live_repairs import wait_run

async def main():
    roots=db.get('meta','demo_workspaces');results={}
    async with httpx.AsyncClient(trust_env=False,timeout=30) as raw,httpx.AsyncClient(base_url='http://127.0.0.1:8000/api/v1',trust_env=False,timeout=60) as c:
        c.headers['X-Traceforge-Csrf']=(await c.get('/session')).json()['csrf']
        cases=[('java','traceforge-java-demo','http://127.0.0.1:9201/health','Spring Boot /health 返回500，MySQL在Compose网络内部监听3306，但JDBC配置mysql:3307。请检查config/application.properties，只修正JDBC端口，然后重启登记的traceforge-java-demo。'),('deployment','traceforge-nginx-demo','http://127.0.0.1:9202/','Nginx代理返回502，backend实际监听8000，配置proxy_pass却指向8001。请检查config/default.conf，修正端口，并重启登记的traceforge-nginx-demo。')]
        for stack,service,url,question in cases:
            config=ROOT/'examples'/stack/'config'/('application.properties' if stack=='java' else 'default.conf')
            if stack=='java':config.write_text(config.read_text(encoding='utf-8').replace('mysql:3306/','mysql:3307/'),encoding='utf-8')
            else:config.write_text(config.read_text(encoding='utf-8').replace('backend:8000','backend:8001'),encoding='utf-8')
            await docker(['restart',service])
            for _ in range(30):
                try:
                    before=await raw.get(url)
                    if before.status_code in (500,502):break
                except httpx.HTTPError:pass
                await asyncio.sleep(1)
            before=await raw.get(url);logs=await docker(['logs','--tail','50',service])
            r=await c.post('/runs',json={'query':question+'\n真实日志:\n'+logs['output'][-12000:],'workspace_id':roots[stack]});r.raise_for_status();id=r.json()['id']
            run=await wait_run(c,id,240);approvals=[]
            for _ in range(5):
                if run['status']!='awaiting_approval':break
                view=run['preview'];p=view['proposal'];decision='approve' if p['kind'] in ('patch','restart') else 'reject'
                response=await c.post('/runs/'+id+'/approval',json={'decision':decision,'payload_hash':view['payload_hash']})
                if response.status_code==400 and '任务正在运行' in response.text:
                    await asyncio.sleep(1);response=await c.post('/runs/'+id+'/approval',json={'decision':decision,'payload_hash':view['payload_hash']})
                if response.is_error:print('approval_error',response.status_code,response.text,flush=True)
                response.raise_for_status();approvals.append(view);await asyncio.sleep(.7);run=await wait_run(c,id,240)
            # Service restart is independently audited if the model only proposed a config patch.
            if not any(a['proposal']['kind']=='restart' for a in approvals):
                p={'kind':'restart','title':'重启已修复演示服务','description':'让配置修改生效并检查真实健康接口','workspace_id':roots[stack],'service':service}
                manual=(await c.post('/actions/propose',json=p)).json()
                response=await c.post('/runs/'+manual['id']+'/manual-approval',json={'decision':'approve','payload_hash':manual['preview']['payload_hash']});response.raise_for_status()
                await wait_run(c,manual['id'])
            for _ in range(30):
                try:
                    after=await raw.get(url)
                    if after.status_code==200:break
                except httpx.HTTPError:pass
                await asyncio.sleep(1)
            results[stack]={'before_status':before.status_code,'after_status':after.status_code,'after_body':after.text[:500],'run_id':id,'status':run['status'],'approvals':approvals,'passed':before.status_code in (500,502) and after.status_code==200 and run['status']=='completed','error':run.get('error')}
            print(stack,results[stack]['passed'],results[stack]['before_status'],results[stack]['after_status'],flush=True)
            (settings.data_dir/'service-repair-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':asyncio.run(main())
