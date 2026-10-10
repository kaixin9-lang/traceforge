# TraceForge 故障诊断工作台

通过日志、项目检查与知识检索定位故障，审核修复后执行，并保存证据与复验结果。支持 Python / Agent 开发、Node 前端、Java / Spring Boot 和 Docker / Nginx 部署排查。

## 打开与启动

完整启动步骤、开发模式与端口报错处理见 [项目启动指南](D:/systemDir/Documents/ChatGPT/agent_program/docs/项目启动指南.md)。

本机入口：[TraceForge 工作台](http://127.0.0.1:8000/)。API 文档：[接口文档](http://127.0.0.1:8000/docs)。

开机后先确认 Ollama 已打开，再在 PowerShell 中进入项目根目录并启动服务：

```powershell
cd D:\systemDir\Documents\ChatGPT\agent_program
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1 -SkipBuild
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\health.ps1
```

停止服务：

```powershell
.\scripts\stop.ps1
```

停止保留模型、SQLite、Milvus 数据卷、修复备份和案例。独立 Python 环境、前端依赖与镜像已在本机准备；首次在新环境安装可运行 `scripts/setup.ps1`。Docker Hub 需要现有本机代理时使用 `-DockerProxy`。安装脚本按现有 WSL Ubuntu 和本机 CUDA 环境设计。

如果页面还在，但提交诊断提示“无法连接本机后端”（旧版本显示 `Failed to fetch`），说明浏览器请求未能连接 API。运行启动命令，等出现“TraceForge已启动”后刷新工作台；仅打开浏览器页面不会启动后端。健康检查可进一步确认 DeepSeek、Ollama、Milvus 与 MCP 的状态。

## 配置

将 `.env.example` 复制为 `.env`，配置后端 `DEEPSEEK_API_KEY`。本机已配置用户提供的密钥；代码、前端构建、文档与命令容器均不包含该值。

复用现有 Ollama `qwen3-embedding:0.6b` 与 `D:/python_program/RAG_Agent/models/Qwen3-Reranker-0.6B`。默认大模型 `deepseek-flash`。修改模型或路径后重启后端；更换嵌入维度需要新建集合并重新索引。

本机DeepSeek使用已有`127.0.0.1:7897`代理，运行时保持代理开启；后端`.env`中的`DEEPSEEK_PROXY_URL`控制该连接路径。其他环境留空可使用直连。连接配置同时用于健康检查、实际模型调用和Ragas评估。

## 一次完整诊断

1. 在“项目与工具”登记项目目录，或先使用不关联项目的知识问答。
2. 在“知识库”上传文档、日志，或导入公开 HTTPS 资料；等状态变为“已索引”。
3. 在工作台提交报错，可同时上传日志或截图。
4. 点击证据引用，查看实际原文；“工作流”和“事件”展示执行节点。
5. 有修复提案时检查文件差异、命令、目录与网络权限，再批准、修改或拒绝。
6. 查看执行退出码和复验输出；配置补丁可从执行记录回滚。

“检索实验”可比较召回方式、查询改写、HyDE、融合、重排和 MMR。“评估中心”保存固定案例的检索指标和六项 Ragas 结果，可导出 JSON。

## 学习与验证

- [架构与实现](docs/架构与实现.md)：模块、数据流、API、MCP、状态、持久化、课程知识点映射。
- [使用部署与测试](docs/使用部署与测试.md)：操作、演示项目、部署、恢复与排错。
- `docs/测试报告.md`：实施结束时生成的真实验证结果。

```powershell
.venv\Scripts\python.exe -m pytest -q
cd frontend
npm.cmd run build
npm.cmd run test:e2e
```

30 条原创参考案例来自 `traceforge/corpus.py`，公开资料保留原始链接。它们作为可复现的学习基准，可继续添加自己的故障样本与人工参考答案。

交互参考 [Agent Chat UI](https://github.com/langchain-ai/agent-chat-ui)，检索实验参考 [RAG from Scratch](https://github.com/langchain-ai/rag-from-scratch)，MCP 接入使用 [LangChain MCP adapters](https://github.com/langchain-ai/langchain-mcp-adapters)。业务代码与视觉设计独立编写。
