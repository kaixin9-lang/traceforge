import asyncio
import json
import os
import re
import subprocess
import sys
from pathlib import Path
import psutil
from .config import settings
from .db import db,uid
from .workspaces import workspace,docker
from .security import within

async def register(workspace_id,request):
    ws=workspace(workspace_id)
    if not request.health_path.startswith('/') or '?' in request.health_path:raise ValueError('健康检查必须使用固定相对路径')
    if request.kind=='container':
        if not re.fullmatch(r'traceforge-[a-zA-Z0-9_-]+',request.container):raise ValueError('只能登记traceforge-命名的应用管理容器')
        inspected=await docker(['inspect','--format','{{json .Config.Labels}}',request.container])
        if inspected['exit_code']!=0:raise ValueError('容器不存在')
        labels=json.loads(inspected['output'] or '{}') or {}
        if not labels.get('com.docker.compose.project','').startswith('traceforge') and labels.get('traceforge.managed')!='true':raise ValueError('容器没有应用管理标记')
        id=request.container
    else:
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*',request.module):raise ValueError('模块格式应为main:app')
        module=request.module.split(':')[0]
        root=Path(ws['path']);relative='/'.join(module.split('.'))+'.py'
        if not within(root,relative).exists():raise ValueError('项目中没有此Python模块')
        id='traceforge-host-'+uid()[:12]
    record={'id':id,'workspace_id':workspace_id,**request.model_dump(),'pid':None}
    db.put('service',id,record)
    ws['services']=list(dict.fromkeys(ws.get('services',[])+[id]))
    ws.setdefault('health_checks',{})[id]=f'http://127.0.0.1:{request.port}{request.health_path}'
    db.put('workspace',workspace_id,ws)
    return record

def argv(record):
    root=Path(workspace(record['workspace_id'])['path'])
    python=root/'.venv'/'Scripts'/'python.exe' if os.name=='nt' else root/'.venv'/'bin'/'python'
    if not python.exists():python=Path(sys.executable)
    return [str(python),'-m','uvicorn',record['module'],'--host','127.0.0.1','--port',str(record['port'])]

def restart_host(record):
    if record.get('pid'):
        try:
            proc=psutil.Process(record['pid'])
            if abs(proc.create_time()-record.get('created_at',0))>.01:raise ValueError('进程身份已改变，拒绝终止')
            if record['module'] not in proc.cmdline():raise ValueError('进程命令与登记服务不符')
            targets=[*proc.children(recursive=True),proc]
            for p in targets:p.terminate()
            _,alive=psutil.wait_procs(targets,timeout=3)
            for p in alive:p.kill()
        except psutil.NoSuchProcess:pass
    args=argv(record)
    logs=settings.data_dir/'services';logs.mkdir(exist_ok=True)
    safe_env={k:v for k,v in os.environ.items() if not any(x in k.lower() for x in ('key','token','secret','password'))}
    output=(logs/(record['id']+'.log')).open('ab')
    try:
        process=subprocess.Popen(args,cwd=workspace(record['workspace_id'])['path'],env=safe_env,stdout=output,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    finally:output.close()
    record.update(pid=process.pid,created_at=psutil.Process(process.pid).create_time(),argv=args)
    db.put('service',record['id'],record)
    return {'exit_code':0,'output':'已启动登记的Uvicorn服务，PID '+str(process.pid),'pid':process.pid}

def stop_host(record):
    if not record.get('pid'):return
    try:
        proc=psutil.Process(record['pid'])
        if abs(proc.create_time()-record.get('created_at',0))>.01 or record['module'] not in proc.cmdline():raise ValueError('进程身份不符，拒绝停止')
        targets=[*proc.children(recursive=True),proc]
        for p in targets:p.terminate()
        _,alive=psutil.wait_procs(targets,timeout=3)
        for p in alive:p.kill()
    except psutil.NoSuchProcess:pass
    record['pid']=None;db.put('service',record['id'],record)
