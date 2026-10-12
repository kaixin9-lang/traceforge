import asyncio
import io
import json
import sys
from pathlib import Path
import httpx
from PIL import Image,ImageDraw,ImageFont
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from traceforge.config import ROOT,settings
from traceforge.db import db
from traceforge.mcp_client import hub
from tests.live_repairs import wait_run

async def main():
    results={}
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8000/api/v1',trust_env=False,timeout=120) as c:
        c.headers['X-Traceforge-Csrf']=(await c.get('/session')).json()['csrf']
        ws=next((x for x in db.list('workspace') if Path(x['path'])==ROOT/'examples'/'host'),None)
        if not ws:ws=(await c.post('/workspaces',json={'name':'宿主机服务演示','path':str(ROOT/'examples'/'host')})).json()
        r=await c.post('/workspaces/'+ws['id']+'/services',json={'kind':'uvicorn','name':'本机API演示','module':'main:app','port':8108,'health_path':'/health'});r.raise_for_status();service=r.json()
        proposal={'kind':'restart','title':'启动演示API','description':'仅启动已登记的本机Uvicorn模板','workspace_id':ws['id'],'service':service['id']}
        run=(await c.post('/actions/propose',json=proposal)).json();old=run['preview']['payload_hash']
        edited=run['preview']['proposal']|{'description':'编辑后审核演示API启动'}
        response=await c.post('/runs/'+run['id']+'/manual-approval',json={'decision':'edit','payload_hash':old,'edited_proposal':edited});response.raise_for_status();new=response.json()
        stale=await c.post('/runs/'+run['id']+'/manual-approval',json={'decision':'approve','payload_hash':old})
        rejected=await c.post('/runs/'+run['id']+'/manual-approval',json={'decision':'reject','payload_hash':new['preview']['payload_hash']});rejected.raise_for_status()
        results['edit_stale_reject']={'passed':stale.status_code==400 and rejected.json()['status']=='completed'}
        run=(await c.post('/actions/propose',json=proposal)).json()
        response=await c.post('/runs/'+run['id']+'/manual-approval',json={'decision':'approve','payload_hash':run['preview']['payload_hash']});response.raise_for_status();finished=await wait_run(c,run['id'])
        async with httpx.AsyncClient(trust_env=False) as raw:health=await raw.get('http://127.0.0.1:8108/health')
        results['managed_host']={'passed':health.status_code==200 and finished['action_result'].get('verification',{}).get('exit_code')==0,'response':health.json(),'service':service['id'],'run_id':run['id']}
        run2=(await c.post('/actions/propose',json=proposal)).json();await c.post('/runs/'+run2['id']+'/manual-approval',json={'decision':'approve','payload_hash':run2['preview']['payload_hash']});again=await wait_run(c,run2['id'])
        results['managed_restart']={'passed':again['action_result'].get('verification',{}).get('exit_code')==0,'run_id':run2['id']}
        forbidden=await c.post('/runs',json={'query':'test'},headers={'Origin':'https://untrusted.example'})
        results['origin_guard']={'passed':forbidden.status_code==403}
        image=Image.new('RGB',(900,210),'white');draw=ImageDraw.Draw(image);font=ImageFont.truetype('C:/Windows/Fonts/consola.ttf',28)
        draw.text((25,35),'FastAPI HTTP 422',font=font,fill='#25314b');draw.text((25,90),'body.name: Field required',font=font,fill='#a04032')
        buffer=io.BytesIO();image.save(buffer,format='PNG');buffer.seek(0)
        response=await c.post('/documents/upload',files={'file':('error-screenshot.png',buffer.getvalue(),'image/png')},data={'index':'false'});response.raise_for_status()
        doc=(await c.get('/documents/'+response.json()['id'])).json()
        results['screenshot_vision']={'passed':'422' in doc['text'] and 'name' in doc['text'],'text':doc['text']}
        await hub.connect()
        async with hub.client.session('docs') as session:
            resources=await session.list_resources();prompts=await session.list_prompts();content=await session.read_resource('traceforge://references/sources')
            prompt=await session.get_prompt('cite_sources',arguments={'question':'FastAPI422'})
            results['mcp_primitives']={'passed':len(resources.resources)>0 and len(prompts.prompts)>0 and bool(content.contents) and bool(prompt.messages),'resources':[x.uri for x in resources.resources],'prompts':[x.name for x in prompts.prompts]}
    (settings.data_dir/'edge-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    print(json.dumps({k:v['passed'] for k,v in results.items()},ensure_ascii=False))

if __name__=='__main__':asyncio.run(main())
