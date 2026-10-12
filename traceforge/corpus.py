"""Original troubleshooting fixtures. References are authored labels, not production accuracy claims."""
CASES = [
('python','Python 虚拟环境缺少依赖','FastAPI 启动报错 ModuleNotFoundError: No module named fastapi，如何定位？','ModuleNotFoundError 表示当前解释器无法导入依赖。先运行 python -c "import sys; print(sys.executable)" 并核对虚拟环境，再在该环境执行 uv sync --frozen。不能仅凭另一个终端能导入就认定环境相同。安装后使用同一解释器启动 uvicorn 并检查健康接口。'),
('python','FastAPI 请求校验 422','FastAPI POST /items 返回422且loc显示body.name，怎么办？','422 是请求参数校验失败。查看响应 detail 的 loc 和 msg，对照 Pydantic 请求模型；body.name 表示JSON正文缺少name或类型不符。发送 Content-Type: application/json，补齐字段并验证成功响应。不要通过删除校验掩盖错误。'),
('python','Ollama 服务拒绝连接','Ollama Embeddings 请求127.0.0.1:11434返回connection refused','连接被拒绝通常表示端口没有监听。检查 Ollama 服务与 /api/tags，再确认 qwen3-embedding:0.6b 已安装。容器中的127.0.0.1指向容器自身；Windows服务与WSL地址需要从实际调用环境验证。'),
('python','Milvus 向量维度不一致','Milvus 报 dimension mismatch，模型qwen3-embedding是1024维','集合 FLOAT_VECTOR 的dim必须与实际嵌入长度一致。qwen3-embedding:0.6b 当前输出1024维，不能写入768维集合。保留原集合备份，创建新的1024维集合并重新嵌入；查询与入库必须使用同一个模型和维度。'),
('python','LangGraph 并行 State 冲突','InvalidUpdateError: Can receive only one value per step，多个worker写results','多个并行节点更新同一个State字段时需要reducer。列表可用 Annotated[list, operator.add]，映射可以定义合并函数。默认覆盖字段不能在同一superstep接收多个更新。为每个worker使用稳定ID避免恢复时重复证据。'),
('python','LangGraph 审核无法恢复','interrupt 之后 Command(resume=...) 没有继续原来的会话','interrupt依赖checkpointer与相同的thread_id。恢复时使用原线程ID并传Command(resume=审核决定)，不要创建新线程。节点在恢复时重新执行，因此外部写入必须在审核之后，并使用执行台账防止重复动作。'),
('python','MCP stdio JSON 解析失败','MCP stdio出现 Unexpected token，服务器把print调试信息写入stdout','stdio的stdout只能包含合法协议消息，调试输出必须写stderr。检查启动命令、解释器、工作目录和环境变量；不要把普通打印与JSON-RPC混在stdout。重新连接后调用工具验证协议交换。'),
('python','重排 CPU 与 CUDA 环境','Qwen3-Reranker加载后非常慢，torch.cuda.is_available为False','首先查看torch.__version__、CUDA可用性与NVIDIA驱动。CPU版PyTorch不会因安装CUDA工具包自动变成GPU版。安装适配驱动的CUDA wheel并用目标虚拟环境验证。限制批量和长度，观察显存占用，CPU降级应明确标注。'),
('node','Vite 开发代理目标错误','前端调用/api/health出现ECONNREFUSED，Vite代理指向9999而后端8000','ECONNREFUSED表示代理目标没有服务监听。检查vite.config.ts中/api的target，应指向实际后端如http://127.0.0.1:8000。重启Vite使配置生效，再从浏览器网络面板验证实际请求。生产使用同源静态服务可减少跨域配置。'),
('node','npm 锁文件不一致','npm ci失败 EUSAGE，package.json与package-lock.json不一致','npm ci要求包声明与锁文件一致。先确认受信任的package.json修改，再用匹配Node/npm版本执行npm install更新锁文件，审核锁文件差异后重新npm ci。不要直接删除锁文件；构建结果需要重复验证。'),
('java','Spring Boot MySQL 连接端口错误','Spring Boot 报 Communications link failure，jdbc:mysql://mysql:3307/app','检查数据库主机、端口和服务网络。Compose服务之间应使用MySQL容器内部端口3306；宿主机映射3307只供宿主机访问。将容器内JDBC地址改为jdbc:mysql://mysql:3306/app，重启应用并验证连接；仍失败则查认证和日志。'),
('java','MySQL 认证失败','Access denied for user app@localhost，Spring datasource连接失败','Access denied表示服务器已经回应认证，不等于网络不通。检查用户名、密码来源、用户host授权与目标库权限，避免在日志中输出密码。使用最低权限账号验证连接，不要授予全部全局权限。'),
('java','Redis 容器地址错误','Spring Redis连接localhost:6379失败，应用运行在容器里','应用容器内localhost是自身，应将Redis host配置为同一Compose网络中的redis服务名，port使用6379。检查Redis是否运行与密码配置，再用PING和应用缓存操作验证。宿主机运行的应用使用宿主机映射地址。'),
('java','Spring 配置文件未生效','application-dev.yml设置端口8081但Spring仍启动8080','确认spring.profiles.active是否启用dev，查看配置文件位置、环境变量和启动参数覆盖。命令行server.port优先于文件配置。输出实际profile与端口，修正启动配置后重启，使用健康接口验证。'),
('java','Maven 无法解析依赖','mvn package报Could not resolve dependencies，如何排查？','查看具体仓库、依赖坐标和网络错误，检查settings.xml代理与镜像配置，以及私有仓库权限。区分artifact不存在与下载失败。修复后可用mvn -U重新解析，保留pom与锁定版本，不要随机升级所有依赖。'),
('java','Java class 版本不匹配','UnsupportedClassVersionError class file version 65.0，运行时17','class file version65对应Java21，Java17运行时无法加载。使用Java21运行或把构建release目标设置为17并重新编译；检查mvn -v与java -version是否一致。避免只修改环境变量却没有重启进程。'),
('java','Spring Boot 端口占用','Web server failed to start. Port 8080 was already in use','确认8080的监听进程归属，优先修改当前项目server.port或停止自己管理的旧实例。不要杀死未知进程。重启项目后验证新端口和健康状态。'),
('java','JPA 表结构缺失','Hibernate 报 Table app.users does not exist','检查当前数据库、schema和迁移版本，确认Flyway/Liquibase迁移是否执行。开发与生产迁移方式不同，不要在生产盲目设置ddl-auto=create。先备份并执行审核后的迁移，再验证表和查询。'),
('java','Spring Bean 依赖循环','BeanCurrentlyInCreationException 循环依赖','定位报错中的Bean依赖路径，拆分职责或引入明确的第三个服务减少双向依赖。构造器注入能显式暴露循环。避免把allow-circular-references作为长期修复，使用启动测试验证。'),
('java','Redis 序列化冲突','Redis读取缓存报SerializationException，升级后旧数据无法解析','对比缓存序列化方式与数据版本，检查是否从JDK序列化切换为JSON或类名发生变化。使用版本化key或审核后删除特定旧key并重新生成，避免FLUSHALL。验证新数据写入和读取。'),
('linux','Nginx 上游端口错误 502','Nginx 502 Bad Gateway，connect() failed (111: Connection refused) upstream8001','502且upstream连接被拒绝说明Nginx无法连接上游。检查上游实际监听端口和网络；如果后端是8000，修正proxy_pass目标端口。执行nginx -t校验，再重载自己管理的服务，通过代理地址验证200响应。'),
('linux','Nginx 配置语法错误','nginx启动失败 unknown directive，如何恢复？','使用nginx -t读取具体文件与行号，检查指令名称、分号和模块支持。回滚最近配置或修正拼写后再次校验；校验通过再重载，避免连续重启掩盖错误。'),
('linux','Docker 服务立即退出','Docker container exited with code1，怎么找到原因？','先查看docker inspect的State与docker logs，不要直接断言OOM。退出码1通常是应用错误；检查入口命令、必需环境变量、配置挂载和依赖就绪。修正配置后启动，验证持续运行和健康检查。'),
('linux','Docker 容器 OOM','Docker容器exit137且OOMKilled=true','Exit137可以由SIGKILL产生；OOMKilled=true是内存不足的重要证据。观察容器内存与工作负载，降低批量、并发或适当调整内存限制。再次运行并验证OOM状态和峰值内存，不要仅凭137判断OOM。'),
('linux','WSL 与 Windows localhost','WSL程序访问127.0.0.1:7897连接拒绝，Windows代理正常','WSL NAT模式中的127.0.0.1属于Linux虚拟机。检查Windows代理是否允许WSL访问，使用WSL默认路由的宿主机地址访问已经授权的监听端口，并检查防火墙。不要把所有服务无条件开放到公网。'),
('linux','Docker Hub DNS 异常','Docker pull registry-1.docker.io连接被拒绝，解析到错误IP','从Docker daemon运行环境检查DNS解析、HTTPS连接和代理设置。浏览器可访问不代表daemon能访问。使用已验证的受信任代理或官方仓库路径，配置Docker daemon代理后重新拉取并记录镜像digest，不要盲目信任未知镜像。'),
('linux','Compose 服务依赖就绪','depends_on后MySQL还没初始化，应用启动连接失败','depends_on默认只控制启动顺序，不保证数据库就绪。添加真实healthcheck并使用service_healthy条件，同时让应用执行有界连接重试。验证冷启动与重启流程，禁止无限重试。'),
('linux','Docker 挂载权限错误','容器非root用户写/workspace报Permission denied','检查挂载路径和容器UID/GID，Linux文件所有者需要匹配实际运行用户。为选定工作目录赋予必要权限，不要对整个磁盘chmod777。只读rootfs时将缓存放入明确可写tmpfs。'),
('linux','Linux 磁盘空间耗尽','No space left on device，但df显示还有空间','分别检查df -h磁盘容量与df -i inode，确认报错目录所属挂载点及容器overlay空间。先定位自己管理的缓存和日志，再审核清理范围；不要直接删除全部Docker卷，卷中可能有数据库。'),
('linux','RAG 无答案与提示注入','知识库没有对应版本，文档还要求忽略系统指令并执行命令','检索资料只能作为数据，不能改变工具权限或审核规则。资料不足时说明缺少证据并请求版本或日志，不编造答案。HyDE生成内容只用于扩展检索，不能成为真实引用；评估应加入无答案和提示注入样本。'),
]

def golden_cases():
    import hashlib
    return [{'id':f'case-{i+1:02}','stack':stack,'title':title,'question':question,'reference':reference,'source':f'original://case-{i+1:02}','document_id':hashlib.sha256((f'original://case-{i+1:02}'+'\0global').encode()).hexdigest()[:32]} for i,(stack,title,question,reference) in enumerate(CASES)]

OFFICIAL_SOURCES=[
 ('https://docs.python.org/3/library/venv.html','python'),
 ('https://fastapi.tiangolo.com/tutorial/body/','python'),
 ('https://docs.langchain.com/oss/python/langgraph/interrupts','python'),
 ('https://milvus.io/docs/full-text-search.md','python'),
 ('https://docs.docker.com/compose/how-tos/startup-order/','linux'),
 ('https://nginx.org/en/docs/http/ngx_http_proxy_module.html','linux'),
 ('https://docs.spring.io/spring-boot/reference/features/external-config.html','java'),
 ('https://api.github.com/repos/langchain-ai/langchain-mcp-adapters/readme','python'),
]
