import asyncio
import json
import hashlib
from pathlib import Path
import pytest
from traceforge.security import within,redact,public_url
from traceforge.db import Database,SQLiteStore
from traceforge.knowledge import split_document,parse_file
from traceforge.retrieval import fuse,normalize_hits
from traceforge.types import RepairProposal
from traceforge import actions,workspaces

def test_paths_block_absolute_and_escape(tmp_path):
    for path in ['../secret.txt','C:/Windows/system.ini','/etc/passwd','.env','.git/config','node_modules/index.js']:
        with pytest.raises(ValueError):within(tmp_path,path)
    assert within(tmp_path,'config/app.json')==tmp_path/'config'/'app.json'

def test_redaction_preserves_error_identifiers():
    text='ModuleNotFoundError E-4213 key=other sk-abcdefghijklmnop password="supersecret" "api_key":"sensitive"'
    result=redact(text)
    assert 'supersecret' not in result and 'sensitive' not in result and 'sk-abc' not in result
    assert 'ModuleNotFoundError E-4213' in result

def test_private_urls_rejected():
    for url in ['http://example.com','https://127.0.0.1','https://localhost','https://user:pass@example.com','https://example.com:8000']:
        with pytest.raises(ValueError):public_url(url)

def test_fusion_includes_partial_route_and_stable_rank():
    d={'dense:0':[{'id':'a','score':.9,'entity':{}},{'id':'b','score':.5,'entity':{}}],'sparse:0':[{'id':'b','score':5,'entity':{}}]}
    assert fuse(d)[0]['id']=='b'
    assert [x['id'] for x in fuse({'dense:0':d['dense:0'],'sparse:0':[]})]==['a','b']
    result=fuse({'dense:0':[{'id':'a','score':.4,'entity':{}},{'id':'b','score':.4,'entity':{}}]},'weighted')
    assert all(x['score']==.6 for x in result)

def test_milvus_primary_key_and_distance_normalization():
    from pymilvus.client.search_result import Hit
    raw=Hit({'pk':'chunk-1','distance':.87,'entity':{'text':'evidence'}},pk_name='pk')
    assert normalize_hits([raw])==[{'id':'chunk-1','score':.87,'entity':{'text':'evidence'}}]

def test_chunk_metadata_and_size():
    text='# 总标题\n\n## 故障\n'+('错误 E-4213 与 ModuleNotFoundError。\n'*120)
    chunks=split_document(text,{'source':'original://test'})
    assert len(chunks)>1
    assert all(len(c.page_content)<=1000 for c in chunks)
    assert all(c.metadata['source']=='original://test' and c.metadata['h1']=='总标题' for c in chunks)

@pytest.mark.asyncio
async def test_store_survives_restart_and_preserves_empty_value(tmp_path):
    database=Database(tmp_path/'db.sqlite');store=SQLiteStore(database)
    await store.aput(('projects','a'),'empty',{})
    await store.aput(('projects','b'),'pref',{'stack':'java'})
    new=SQLiteStore(Database(tmp_path/'db.sqlite'))
    item=await new.aget(('projects','a'),'empty')
    assert item.value=={}
    created=item.created_at
    await new.aput(('projects','a'),'empty',{'x':1})
    assert (await new.aget(('projects','a'),'empty')).created_at==created
    assert len(await new.asearch(('projects',),filter={'stack':'java'}))==1
    assert ('projects','a') in await new.alist_namespaces(prefix=('projects',))

def test_action_claim_is_durable_and_unique(tmp_path):
    path=tmp_path/'db.sqlite';database=Database(path)
    first,ok=database.claim_action('run','same',{'command':'approved'})
    second,again=Database(path).claim_action('run','same',{'command':'approved'})
    assert ok and not again and first==second

@pytest.mark.asyncio
async def test_patch_approval_staleness_idempotence_and_rollback(tmp_path,monkeypatch):
    database=Database(tmp_path/'db.sqlite');monkeypatch.setattr(actions,'db',database);monkeypatch.setattr(workspaces,'db',database)
    project=tmp_path/'project';project.mkdir();config=project/'config.json';config.write_text('{"port":9999}')
    ws=workspaces.register('Test',str(project))
    proposal=RepairProposal(kind='patch',title='Fix port',description='Restore expected port',workspace_id=ws['id'],file='config.json',replacement='{"port":8000}')
    view=actions.preview(proposal)
    config.write_text('{"port":7000}')
    with pytest.raises(ValueError):await actions.execute('run',view)
    config.write_text('{"port":9999}')
    result=await actions.execute('run',view)
    assert result['exit_code']==0 and json.loads(config.read_text())['port']==8000
    replay=await actions.execute('run',view)
    assert replay['replayed'] and replay['id']==result['id']
    # Already completed actions replay before mutation preconditions; a new edit must never apply twice.
    assert database.actions()[0]['status']=='succeeded'
    actions.rollback(result['id'])
    assert json.loads(config.read_text())['port']==9999

def test_secret_config_patch_not_exposed(tmp_path,monkeypatch):
    database=Database(tmp_path/'db.sqlite');monkeypatch.setattr(workspaces,'db',database)
    project=tmp_path/'project';project.mkdir();(project/'app.properties').write_text('password=private123\nport=80')
    ws=workspaces.register('Private',str(project))
    with pytest.raises(ValueError):actions.preview(RepairProposal(kind='patch',title='x',description='x',workspace_id=ws['id'],file='app.properties',replacement='port=81'))
