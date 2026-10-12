import argparse
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from traceforge.corpus import golden_cases,OFFICIAL_SOURCES
from traceforge.knowledge import knowledge,fetch_public
from traceforge.config import settings

async def main(online):
    results=[]
    for case in golden_cases():
        record=knowledge.add(case['title'],'# '+case['title']+'\n\n## 故障现象\n'+case['question']+'\n\n## 定位与处理\n'+case['reference'],case['source'],case['stack'])
        result=await knowledge.ingest(record)
        results.append({'source':case['source'],'status':result['status'],'error':result.get('error')})
        print(case['id'],result['status'],flush=True)
    if online:
        for url,stack in OFFICIAL_SOURCES:
            try:
                title,text,source=await fetch_public(url)
                record=knowledge.add(title,text[:200000],source,stack)
                result=await knowledge.ingest(record);results.append({'source':source,'status':result['status'],'error':result.get('error')})
            except Exception as e:results.append({'source':url,'status':'failed','error':str(e)})
            print(url,results[-1]['status'],flush=True)
    (settings.data_dir/'bootstrap-result.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--online',action='store_true');args=parser.parse_args();asyncio.run(main(args.online))
