# Node 前端连接配置故障

后端实际地址是127.0.0.1:8000，代理配置故意指向9999。运行 `node demo.mjs` 可复现配置检查失败。

审核修正config.json，在Node容器执行 `node demo.mjs` 复验。这是代理配置契约测试；工作台自身的真实前后端连接另由Playwright验证。
