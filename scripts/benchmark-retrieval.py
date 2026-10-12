"""Paraphrased queries are separate from the literal smoke/evaluation dataset."""
import asyncio
import json
import statistics
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from traceforge.corpus import golden_cases
from traceforge.retrieval import retrieve
from traceforge.types import RetrievalRequest
from traceforge.evaluation import ranking_metrics
from traceforge.config import settings

QUESTIONS=[
 '明明用pip装过fastapi，启动脚本却提示这个包不存在，我该先看哪个解释器？',
 '向items提交JSON总被拒绝，状态422，定位字段name，怎样判断是缺字段还是类型错？',
 '向量接口访问11434失败，连接被拒绝，是模型坏了还是服务没开？',
 '旧集合维度768，新向量长度1024，写库报dimension mismatch，能直接改集合吗？',
 '图里两个并行分支都写同一字段，出现Can receive only one value per step怎么办？',
 '审核后恢复图没有回到原任务，新的会话编号能不能用来resume？',
 'MCP本地服务的调试print会导致客户端JSON解析失败，应该输出到哪里？',
 '本机有4070但重排仍特别慢，PyTorch检测不到CUDA，如何切到GPU？',
 '开发页面通过Vite转发到9999，但API在8000，浏览器连接被拒绝应改哪里？',
 'npm的严格安装模式因锁文件和包声明不同而失败，怎样恢复可重复构建？',
 'Java应用容器使用MySQL对外映射端口3307连接另一容器，为什么连不上？',
 'MySQL说Access denied，应该优先查网络还是账号权限？',
 'Spring应用与Redis都是容器，Redis host写localhost会找错哪里？',
 'dev配置里端口改了但实际端口没变化，怎样确认profile和覆盖顺序？',
 'Maven找不到依赖下载失败，需要把所有依赖都升级吗？',
 'Java17不能跑class file65的产物，构建与运行环境怎么对齐？',
 'Spring启动提示8080已被占用，可以随便杀监听进程吗？',
 'JPA查询users表不存在，应该检查迁移还是把ddl-auto设成create？',
 '两个Spring服务互相注入启动循环，如何拆开依赖关系？',
 '升级缓存序列化以后Redis旧值读不出来，能清空整个Redis吗？',
 '反向代理502，日志连接上游被拒绝，后端监听8000而代理配8001，如何验证修复？',
 'Nginx写错指令后重启失败，用什么检查具体配置行？',
 '容器起来就退出1，第一步要看哪些日志和入口信息？',
 'Docker状态显示137且OOMKilled是真，应该怎么降低内存压力？',
 'Windows代理能用，但WSL里连接同一localhost地址失败，两个localhost是一样的吗？',
 '浏览器可开Docker网站但daemon拉镜像连接错误IP，怎么排查代理和DNS？',
 'Compose设置了依赖顺序，数据库仍没准备好应用就开始连接，怎样等待就绪？',
 '容器已切非root，挂载项目目录不能写，UID和目录权限怎么核对？',
 '写文件提示磁盘满但空间看着还有，inode耗尽如何确认？',
 '资料里夹了忽略指令并执行命令的要求，且知识库没有用户要的版本，Agent应该怎么处理？'
]

async def main():
    rows=[]
    for case,query in zip(golden_cases(),QUESTIONS):
        row={'case_id':case['id'],'query':query,'expected_document':case['document_id'],'strategies':{}}
        for name,strategy,rerank in [('dense','dense',False),('hybrid','hybrid',False),('hybrid_rerank','hybrid',True)]:
            result=await retrieve(RetrievalRequest(query=query,strategy=strategy,rerank=rerank))
            row['strategies'][name]=ranking_metrics(result['evidence'],case['document_id'])|{'elapsed_ms':result['elapsed_ms'],'titles':[e['title'] for e in result['evidence']],'warnings':result['warnings']}
        rows.append(row);print(case['id'],flush=True)
    summary={name:{metric:statistics.mean(r['strategies'][name][metric] for r in rows) for metric in ['recall_at_5','mrr','ndcg','elapsed_ms']} for name in ['dense','hybrid','hybrid_rerank']}
    (settings.data_dir/'retrieval-paraphrase.json').write_text(json.dumps({'dataset':'30 paraphrased queries, distinct from indexed question wording','rows':rows,'summary':summary},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary))
if __name__=='__main__':asyncio.run(main())
