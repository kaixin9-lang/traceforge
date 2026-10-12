import asyncio
import difflib
import hashlib
import json
import os
import shutil
import subprocess
import httpx
from pathlib import Path
from .config import settings
from .db import db,uid
from .security import within,digest,redact
from .types import RepairProposal
from .workspaces import workspace,command,docker

def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ''

def preview(proposal:RepairProposal):
    ws=workspace(proposal.workspace_id);root=Path(ws['path'])
    payload=proposal.model_dump();before='';diff=''
    if proposal.kind=='patch':
        path=within(root,proposal.file)
        if path.exists() and path.stat().st_size>250000:raise ValueError('配置补丁文件过大')
        if not path.exists():raise ValueError('补丁只修改已有项目文件')
        if path.suffix.lower() not in {'.json','.toml','.yaml','.yml','.properties','.conf','.txt','.xml','.py','.js','.ts'}:raise ValueError('此文件类型不允许补丁')
        before=path.read_text(encoding='utf-8',errors='replace')
        try:
            if path.suffix=='.json':json.loads(proposal.replacement)
            elif path.suffix=='.toml':__import__('tomllib').loads(proposal.replacement)
            elif path.suffix in ('.yml','.yaml'):__import__('yaml').safe_load(proposal.replacement)
            elif path.suffix=='.py':compile(proposal.replacement,str(path),'exec')
        except (ValueError,SyntaxError) as e:raise ValueError('修复后的配置语法无效：'+str(e)[:200])
        if redact(before)!=before:raise ValueError('文件包含敏感字段，不能提交完整内容给模型，请手动修改或拆出非敏感配置')
        current=file_hash(path)
        if proposal.expected_hash and proposal.expected_hash!=current:raise ValueError('文件已改变，请重新生成修复方案')
        payload['expected_hash']=current
        diff=''.join(difflib.unified_diff(before.splitlines(True),proposal.replacement.splitlines(True),fromfile=proposal.file,tofile=proposal.file))
    if proposal.kind=='dependencies':
        commands={'python':['uv','sync','--frozen'],'node':['npm.cmd' if os.name=='nt' else 'npm','ci','--ignore-scripts'],'java':None}
        args=commands[proposal.runtime]
        if args is None:raise ValueError('Java 依赖恢复请在 Java 命令容器中执行 mvn')
        lock=root/('uv.lock' if proposal.runtime=='python' else 'package-lock.json')
        if not lock.exists():raise ValueError('依赖恢复需要项目锁文件')
        payload['command']=' '.join(args)
        payload['network']=True
    if proposal.kind=='restart':
        if proposal.service not in ws.get('services',[]):raise ValueError('只能重启该项目已登记的应用管理服务')
        registered=db.get('service',proposal.service)
        if registered and registered['kind']=='uvicorn':
            from .services import argv
            payload['command']=subprocess.list2cmdline(argv(registered))
        if ws.get('health_checks',{}).get(proposal.service):payload['verify_command']='HTTP GET '+ws['health_checks'][proposal.service]
    if proposal.kind=='sandbox' and not proposal.command.strip():raise ValueError('命令不能为空')
    return {'proposal':payload,'workspace':{'id':ws['id'],'name':ws['name'],'path':ws['path']},'diff':diff,'before':before,'payload_hash':digest(payload),'limits':{'cpu':2,'memory':'2GiB','timeout_seconds':180,'network':proposal.network},'rollback':'配置补丁可恢复备份；依赖和命令操作按执行记录处理'}

async def sandbox(proposal,action_id,verify=False):
    root=Path(workspace(proposal.workspace_id)['path'])
    staging=settings.data_dir/'sandbox'/action_id
    if staging.exists():raise ValueError('执行副本已存在，禁止重复运行')
    def ignored(folder,names):
        return [n for n in names if n in {'.git','.venv','node_modules','.cache','data','target','dist','__pycache__'} or n.startswith('.env') or n.lower().endswith(('.pem','.key')) or Path(folder,n).is_symlink()]
    await asyncio.to_thread(shutil.copytree,root,staging,ignore=ignored)
    for p in staging.rglob('*'):
        if p.is_file() and p.stat().st_size<=250000:
            try:
                text=p.read_text(encoding='utf-8')
                cleaned=redact(text)
                if cleaned!=text:p.write_text(cleaned,encoding='utf-8')
            except (UnicodeError,OSError):pass
    originals={str(p.relative_to(staging)).replace('\\','/'):p.read_bytes() for p in staging.rglob('*') if p.is_file() and p.stat().st_size<=250000}
    winpath=staging.resolve().as_posix()
    mapped=await command(['wsl.exe','-d',settings.wsl_distro,'--exec','wslpath','-a',winpath])
    mount=next((line.strip() for line in mapped['output'].replace('\x00','').splitlines() if line.strip().startswith('/mnt/')),None)
    if not mount:raise ValueError('WSL 路径转换失败')
    name='traceforge-job-'+action_id[:12]
    args=['wsl.exe','-d',settings.wsl_distro,'-u','root','--exec','docker','run','--rm','--name',name,'--label','traceforge.managed=true','--user','10001:10001','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges','--pids-limit','128','--cpus','2','--memory','2g','--network','bridge' if proposal.network else 'none','--tmpfs','/tmp:rw,nosuid,size=256m','-e','HOME=/tmp','-e','PYTHONDONTWRITEBYTECODE=1','-v',mount+':/workspace:rw','-w','/workspace',f'traceforge-{proposal.runtime}:1','/bin/bash','-lc',proposal.command]
    try:result=await command(args,timeout=180)
    except BaseException:
        await docker(['rm','-f',name]);raise
    differences=[]
    for p in staging.rglob('*'):
        if p.is_symlink() or not p.is_file() or p.stat().st_size>250000:continue
        rel=str(p.relative_to(staging)).replace('\\','/')
        previous=originals.get(rel,b'');updated=p.read_bytes()
        if previous!=updated:
            try:
                new_text=updated.decode('utf-8');old_text=previous.decode('utf-8')
                differences.append({'file':rel,'replacement':redact(new_text),'expected_hash':hashlib.sha256(previous).hexdigest() if previous else '', 'diff':redact(''.join(difflib.unified_diff(old_text.splitlines(True),new_text.splitlines(True),fromfile=rel,tofile=rel)))})
            except UnicodeDecodeError:continue
    return result|{'artifacts':differences[:30],'sandbox_path':str(staging)}

async def execute(run_id,view):
    proposal=RepairProposal(**view['proposal'])
    if digest(view['proposal'])!=view['payload_hash']:raise ValueError('提案内容与审核哈希不匹配')
    prior=next((x for x in db.actions() if x['run_id']==run_id and x['hash']==view['payload_hash']),None)
    if prior:
        if prior['status']=='executing':raise RuntimeError('之前执行状态未确认，已阻止自动重试，请检查执行记录')
        return prior['value']|{'id':prior['id'],'replayed':True,'action_status':prior['status']}
    # Revalidate before any mutation. Client approval never bypasses filesystem preconditions.
    current=preview(proposal)
    if current['payload_hash']!=view['payload_hash']:raise ValueError('审核内容已经过期')
    action_id,claimed=db.claim_action(run_id,view['payload_hash'],view)
    if not claimed:
        existing=next(x for x in db.actions() if x['id']==action_id)
        if existing['status']=='executing':raise RuntimeError('之前执行状态未确认，已阻止自动重试，请检查执行记录')
        return existing['value']|{'id':action_id,'replayed':True}
    ws=workspace(proposal.workspace_id);root=Path(ws['path']);backup=None
    try:
        if proposal.kind=='patch':
            path=within(root,proposal.file)
            backup=settings.data_dir/'backups'/action_id/path.name
            backup.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,backup)
            tmp=path.with_name(path.name+'.traceforge-tmp')
            tmp.write_text(proposal.replacement,encoding='utf-8');os.replace(tmp,path)
            result={'exit_code':0,'output':'配置补丁已应用','backup':str(backup),'file':proposal.file,'after_hash':file_hash(path)}
        elif proposal.kind=='dependencies':
            args=['uv','sync','--frozen'] if proposal.runtime=='python' else ['npm.cmd' if os.name=='nt' else 'npm','ci','--ignore-scripts']
            safe_env={k:v for k,v in os.environ.items() if not any(s in k.lower() for s in ['key','password','secret','token'])}
            result=await command(args,cwd=str(root),timeout=180,env=safe_env)
        elif proposal.kind=='restart':
            registered=db.get('service',proposal.service)
            if registered and registered['kind']=='uvicorn':
                from .services import restart_host
                result=await asyncio.to_thread(restart_host,registered)
            else:result=await docker(['restart',proposal.service])
        else:result=await sandbox(proposal,action_id)
        health_url=ws.get('health_checks',{}).get(proposal.service) if proposal.kind=='restart' else None
        if health_url:
            async with httpx.AsyncClient(trust_env=False,timeout=5) as c:
                verification={'exit_code':1,'output':'服务尚未就绪','source':'registered_service'}
                for _ in range(30):
                    try:
                        response=await c.get(health_url)
                        verification.update(exit_code=0 if response.is_success else 1,output=f'HTTP {response.status_code}: '+redact(response.text)[:2000])
                        if response.is_success:break
                    except httpx.HTTPError as e:verification['output']=str(e)[:300]
                    await asyncio.sleep(.5)
            result['verification']=verification
        elif proposal.verify_command:
            # Verification commands are arbitrary too: always run in a separate isolated copy.
            verification=proposal.model_copy(update={'kind':'sandbox','command':proposal.verify_command,'network':False})
            result['verification']=await sandbox(verification,action_id+'-verify',True)
        result.update(id=action_id,proposal=proposal.model_dump(),payload_hash=view['payload_hash'],diff=view['diff'])
        success=result['exit_code']==0 and result.get('verification',{}).get('exit_code',0)==0
        db.action_finish(action_id,'succeeded' if success else 'failed',result)
        return result
    except BaseException as e:
        result={'id':action_id,'exit_code':-1,'error':redact(str(e)),'backup':str(backup) if backup else None,'proposal':proposal.model_dump(),'diff':view['diff']}
        db.action_finish(action_id,'failed',result)
        if isinstance(e,asyncio.CancelledError):raise
        return result

def rollback(action_id):
    record=next((x for x in db.actions() if x['id']==action_id),None)
    if not record:raise ValueError('执行记录不存在')
    data=record['value'];proposal=RepairProposal(**data['proposal'])
    if proposal.kind!='patch' or not data.get('backup'):raise ValueError('此操作不支持自动回滚')
    target=within(Path(workspace(proposal.workspace_id)['path']),proposal.file)
    if file_hash(target)!=data['after_hash']:raise ValueError('文件在修复后又被修改，请手动比较备份')
    shutil.copy2(data['backup'],target)
    db.action_finish(action_id,'rolled_back',data|{'rolled_back':True})
    return {'ok':True,'file':proposal.file}
