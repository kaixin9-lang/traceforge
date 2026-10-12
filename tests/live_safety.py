import asyncio
import json
import re
import sys
from pathlib import Path
import httpx
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from traceforge.config import settings
from traceforge.db import db,uid
from traceforge.types import RepairProposal
from traceforge.actions import sandbox

async def main():
    ws=db.get('meta','demo_workspaces')['python'];results={}
    for name,cmd,check in [
        ('nonroot_readonly',"python -c \"import os;print('uid',os.getuid());print('root_writable',os.access('/',os.W_OK));print('capabilities',[x.strip() for x in open('/proc/self/status') if x.startswith('CapEff')])\"",lambda r:r['exit_code']==0 and 'uid 10001' in r['output'] and 'root_writable False' in r['output']),
        ('network_denied',"python -c \"import socket;socket.create_connection(('1.1.1.1',443),timeout=2)\"",lambda r:r['exit_code']!=0),
        ('shell_argument_boundary',"printf '%s' '$(echo should-not-expand)'",lambda r:r['output']=='$(echo should-not-expand)'),
        ('output_limit',"python -c \"print('x'*1100000)\"",lambda r:'error' in r and '1MB' in r['error']),
    ]:
        try:r=await sandbox(RepairProposal(kind='sandbox',title=name,description='隔离边界验证',workspace_id=ws,command=cmd),uid())
        except Exception as e:r={'error':str(e),'exit_code':-1}
        results[name]={'passed':check(r),'exit_code':r['exit_code'],'output':r.get('output','')[:500],'error':r.get('error')}
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8000/api/v1',trust_env=False,timeout=60) as c:
        c.headers['X-Traceforge-Csrf']=(await c.get('/session')).json()['csrf']
        run=next(r for r in db.list('run') if r['status']=='completed' and r.get('mode')=='knowledge')
        response=await c.get('/runs/'+run['id']+'/events');ids=[int(x) for x in re.findall(r'^id: (\d+)',response.text,re.M)]
        midpoint=ids[len(ids)//2];replay=await c.get('/runs/'+run['id']+'/events',headers={'Last-Event-ID':str(midpoint)})
        later=[int(x) for x in re.findall(r'^id: (\d+)',replay.text,re.M)]
        results['sse_resume']={'passed':bool(later) and min(later)>midpoint and later[-1]==ids[-1],'events':len(ids),'replayed':len(later)}
        run=(await c.post('/runs',json={'query':'比较LangGraph并行状态冲突、MCP协议错误与Milvus索引维度不匹配，需要完整调查','mode':'diagnose'})).json()
        await c.post('/runs/'+run['id']+'/cancel',json={})
        await asyncio.sleep(.5);state=(await c.get('/runs/'+run['id'])).json()
        results['cancel']={'passed':state['status']=='cancelled','status':state['status']}
    (settings.data_dir/'safety-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(results,ensure_ascii=False))

if __name__=='__main__':asyncio.run(main())
