# 可复现 Python 配置故障

程序需要标准库 `json`，配置误写为 `jsno`。执行 `python demo.py` 会产生真实 ModuleNotFoundError。

在工作台关联这个目录，提交日志。审核修复 config.json，然后在 Python 命令容器执行 `python demo.py` 复验。
