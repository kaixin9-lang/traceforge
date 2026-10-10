import asyncio
import json
import os
import socket
import subprocess
from pathlib import Path
from .db import db,uid
from .config import settings
from .security import within,redact

MANIFESTS=['pyproject.toml','requirements.txt','uv.lock','package.json','pom.xml','build.gradle','application.yml','application.yaml','application.properties','docker-compose.yml','compose.yaml','nginx.conf']

def register(name,path,stack='auto'):
    root=Path(path).expanduser().resolve()
    if not root.is_dir():raise ValueError('项目目录不存在')
    forbidden=[Path(root.anchor),Path(os.environ.get('USERPROFILE','C:/Users')),Path(os.environ.get('WINDIR','C:/Windows'))]
    if root in forbidden or root==settings.data_dir.resolve():raise ValueError('请选择具体项目目录')
    record={'id':uid(),'name':name,'path':str(root),'stack':stack,'services':[]}
    db.put('workspace',record['id'],record)
    return record

def workspace(id):
    result=db.get('workspace',id)
    if not result:raise ValueError('项目未注册')
    return result

def files(id):
    root=Path(workspace(id)['path']);result=[]
    for base,dirs,names in os.walk(root):
        dirs[:]=[d for d in dirs if d not in {'.git','.venv','node_modules','.cache','data','dist','target','__pycache__'} and not Path(base,d).is_symlink()]
        for name in names:
            p=Path(base,name)
            if p.is_symlink() or name.startswith('.env'):continue
            if p.suffix.lower() in {'.toml','.txt','.json','.xml','.yaml','.yml','.properties','.conf','.log','.py','.js','.ts','.md'}:
                result.append({'path':str(p.relative_to(root)).replace('\\','/'),'bytes':p.stat().st_size})
            if len(result)>=250:return result
    return result

def read_file(id,relative):
    root=Path(workspace(id)['path']);p=within(root,relative)
    if p.stat().st_size>250_000:raise ValueError('文件过大，请上传选定日志片段')
    return redact(p.read_text(encoding='utf-8',errors='replace'))

def inspect(id):
    info=workspace(id); listing=files(id); snippets=[]
    for f in listing:
        if Path(f['path']).name in MANIFESTS and not f['path'].endswith('uv.lock'):
            snippets.append({'file':f['path'],'content':read_file(id,f['path'])[:18000]})
        if len(snippets)>=12:break
    return {'workspace':info,'files':listing,'manifests':snippets}

async def port_check(port:int):
    if not 1<=port<=65535:raise ValueError('端口必须在1到65535之间')
    try:
        _,writer=await asyncio.wait_for(asyncio.open_connection('127.0.0.1',port),timeout=2)
        writer.close();await writer.wait_closed();return {'port':port,'listening':True}
    except (OSError,asyncio.TimeoutError):return {'port':port,'listening':False}

async def command(args,cwd=None,timeout=20,env=None):
    flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    proc=await asyncio.create_subprocess_exec(*args,cwd=cwd,env=env,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.STDOUT,creationflags=flags)
    async def collect():
        data=bytearray()
        while chunk:=await proc.stdout.read(65536):
            data.extend(chunk)
            if len(data)>1_000_000:
                proc.kill();await proc.wait();raise RuntimeError('命令输出超过1MB限制，执行已停止')
        await proc.wait()
        return bytes(data)
    try:
        output=await asyncio.wait_for(collect(),timeout)
    except asyncio.TimeoutError:
        proc.kill();await proc.wait();raise TimeoutError('命令执行超时')
    if output.startswith(b'w\x00s\x00l\x00'):
        end=output.find(b'\n\x00')
        if end>=0:output=output[end+2:]
    return {'exit_code':proc.returncode,'output':redact(output.decode('utf-8',errors='replace'))[-100000:]}

async def docker(args):
    return await command(['wsl.exe','-d',settings.wsl_distro,'-u','root','--exec','docker',*args],timeout=30)

async def docker_info(name):
    if not name.startswith('traceforge-'):raise ValueError('仅可检查应用管理的 traceforge- 容器')
    state=await docker(['inspect','--format','{{json .State}}',name])
    logs=await docker(['logs','--tail','80',name])
    return {'state':state,'logs':logs}
