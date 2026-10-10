import asyncio
import secrets
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from traceforge.config import ROOT,settings
from traceforge.workspaces import register,command,workspace
from traceforge.db import db

async def main():
    secret=settings.data_dir/'demo-secrets.env'
    if not secret.exists():secret.write_text('TF_DEMO_DB_PASSWORD='+secrets.token_urlsafe(20)+'\n',encoding='utf-8')
    roots={}
    for name,stack,folder,services in [('Python 故障演示','python','python',[]),('Node 代理演示','node','node',[]),('Spring Boot 数据源演示','java','java',['traceforge-java-demo']),('Nginx 部署演示','linux','deployment',['traceforge-nginx-demo'])]:
        path=ROOT/'examples'/folder
        previous=next((w for w in db.list('workspace') if Path(w['path'])==path),None)
        record=previous or register(name,str(path),stack)
        record['services']=services;db.put('workspace',record['id'],record);roots[folder]=record['id']
        if folder=='java':record['health_checks']={'traceforge-java-demo':'http://127.0.0.1:9201/health'}
        if folder=='deployment':record['health_checks']={'traceforge-nginx-demo':'http://127.0.0.1:9202/'}
        db.put('workspace',record['id'],record)
    db.put('meta','demo_workspaces',roots)
    print(roots)

if __name__=='__main__':asyncio.run(main())
