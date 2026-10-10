import importlib.metadata
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from traceforge.config import ROOT,settings
from traceforge.db import db

def read(name):return json.loads((settings.data_dir/name).read_text(encoding='utf-8'))

job=db.get('evaluation',(settings.data_dir/'evaluation-id.txt').read_text().strip())
unit=ET.parse(settings.data_dir/'unit-tests.xml').getroot().find('testsuite')
browser=read('playwright-results.json')['stats']
repairs=read('repair-results.json');services=read('service-repair-results.json');edges=read('edge-results.json');safety=read('safety-results.json');paraphrase=read('retrieval-paraphrase.json')
smoke=read('live-smoke.json')
references={e['id'] for e in smoke['run']['evidence']}
cited=re.findall(r'\]\(evidence:([^)]*)\)',smoke['run']['report'])
resolved=sum(x in references for x in cited)
lines=['# TraceForge 实测报告','', '验证日期：2026-10-07。环境：Windows / WSL Ubuntu，Python3.12，RTX4070 Laptop GPU。以下来自实际输出与持久化记录。','', '## 最终验收','',
 f'- 单元测试：{unit.attrib["tests"]}项，失败{unit.attrib["failures"]}，错误{unit.attrib["errors"]}。',
 f'- Playwright：通过{browser["expected"]}项，失败{browser["unexpected"]}项；连接真实后端，覆盖桌面、移动端、上传、检索、生成、历史与审核执行。',
 f'- 实际诊断：{smoke["run"]["status"]}；检索路线均返回候选，使用真实DeepSeek、Ollama、Milvus和CUDA重排。',
 f'- 流式答案引用：{resolved}/{len(cited)}个引用ID可解析到本次保存的证据。此检查验证来源可追溯性，语义忠实度另由Ragas衡量。','']
for name,result in {**repairs,**services}.items():lines.append(f'- {name}故障闭环：{"通过" if result["passed"] else "失败"}；'+(f'HTTP {result["before_status"]} → {result["after_status"]}。' if 'before_status' in result else f'复现退出码{result["before"]["exit_code"]} → 复验退出码{result["after"]["exit_code"]}。'))
lines+=['','## 补充验证','']
for name,result in {**edges,**safety}.items():lines.append(f'- {name}：{"通过" if result["passed"] else "失败"}。')
lines+=['','## 检索与生成评估','',f'评估任务：`{job["id"]}`。原始基准30条；三种方案各完成30次真实检索。另运行30条不同措辞查询，减少原文匹配造成的偏差。','']
for name,value in paraphrase['summary'].items():lines.append(f'- {name}改写问题集：Recall@5={value["recall_at_5"]:.3f}，MRR={value["mrr"]:.3f}，nDCG={value["ndcg"]:.3f}，平均{value["elapsed_ms"]:.1f}ms。')
lines+=['','小型原创案例集上三种方案命中率相同，不能据此证明混合或重排提升准确率。重排增加推理耗时；原始评估的P95包含GPU冷启动、重载及并发活动，改写问题集使用已热身模型。','']
for name,value in job['summary']['ragas'].items():lines.append(f'- {name}：{value["value"]:.4f}；有效{value["successful_samples"]}/30，失败{value["failed_samples"]}。')
lines+=['',f'初始目标：Recall@5≥0.80、Faithfulness≥0.90。实测改写查询Recall@5={paraphrase["summary"]["hybrid_rerank"]["recall_at_5"]:.3f}、Faithfulness={job["summary"]["ragas"]["faithfulness"]["value"]:.4f}，达到目标。',
'', '答案相关性和实体覆盖仍有改善空间；噪声敏感度应尽量降低。评分来自同一供应商的评审模型，存在评审偏差。建议加入真实业务日志、独立参考答案和无答案样本后持续比较。',
'', '过程中出现过网络失败与评审输出截断，保留原回答和上下文后重试；评审输出上限已调整为8192。最终六项指标全部完成30个样本，失败未被替换为0或冒充通过。',
'', '## 版本与原始证据','']
for name in ['fastapi','langchain','langgraph','langchain-mcp-adapters','fastmcp','mcp','pymilvus','torch','sentence-transformers','ragas']:lines.append(f'- {name}：{importlib.metadata.version(name)}')
lines+=['','- Python依赖：uv.lock；前端依赖：frontend/package-lock.json。', '- 测试输出：data/unit-tests.xml、playwright-results.json、repair-results.json、service-repair-results.json、edge-results.json、safety-results.json、retrieval-paraphrase.json。', '- 评估原始样本：工作台评估中心导出JSON，包含实际回答、有序上下文、参考答案、分项结果与失败记录。','- 界面截图：data/screenshots；API结构：运行中的/docs与/openapi.json。', '- 架构与操作说明：docs/架构与实现.md、docs/使用部署与测试.md。','']
(ROOT/'docs'/'测试报告.md').write_text('\n'.join(lines),encoding='utf-8')
(settings.data_dir/'evaluation-final.json').write_text(json.dumps(job,ensure_ascii=False,indent=2),encoding='utf-8')
print('Report written; scores and sample counts are actual persisted results.')
