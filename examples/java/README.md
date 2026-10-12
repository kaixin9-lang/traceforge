# Spring Boot / MySQL 数据源故障

MySQL 服务在 Compose 网络内监听 3306，application.properties 故意配置成 3307。访问 `/health` 会触发真实 JDBC 连接异常。

修正 JDBC 端口并审核重启 `traceforge-java-demo`，再次请求健康接口，成功响应应包含 database=1。数据库口令仅由演示环境文件注入。
