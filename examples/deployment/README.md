# Nginx 502 故障

backend 服务运行 Python HTTP server，实际端口是8000。Nginx配置误写成8001，访问9202返回真实502。

在诊断中审核修改 config/default.conf 并重启 `traceforge-nginx-demo`，随后从代理地址验证200响应。
