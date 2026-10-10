param([switch]$DockerProxy,[switch]$OfflineCorpus)
$ErrorActionPreference='Stop'
$taskRoot=Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $taskRoot
$env:PYTHONIOENCODING='utf-8';$env:LANGGRAPH_STRICT_MSGPACK='true'
$env:UV_CACHE_DIR=Join-Path $taskRoot '.cache\uv'
$env:HTTP_PROXY='';$env:HTTPS_PROXY='';$env:ALL_PROXY=''
uv sync --frozen --index-url https://pypi.tuna.tsinghua.edu.cn/simple
if($LASTEXITCODE -ne 0){throw 'Python依赖安装失败'}
Push-Location frontend
npm.cmd ci --registry=https://registry.npmmirror.com --no-audit --no-fund
npm.cmd run build
npx.cmd playwright install chromium
Pop-Location
if(-not (Test-Path '.env')) {Copy-Item .env.example .env;Write-Host '请在.env配置DEEPSEEK_API_KEY后运行start.ps1'}
wsl -d Ubuntu -u root -- bash /mnt/d/systemDir/Documents/ChatGPT/agent_program/scripts/install-docker.sh
if($DockerProxy){wsl -d Ubuntu -u root -- bash /mnt/d/systemDir/Documents/ChatGPT/agent_program/scripts/configure-docker-proxy.sh}
wsl -d Ubuntu -u root -- bash /mnt/d/systemDir/Documents/ChatGPT/agent_program/scripts/build-sandboxes.sh
& $PSScriptRoot\start.ps1 -SkipBuild
$args=@('scripts/bootstrap.py')
if(-not $OfflineCorpus){$args+='--online'}
& .venv\Scripts\python.exe @args
Write-Host '安装完成。请运行 scripts\health.ps1 查看实际服务状态。'
