param([switch]$SkipBuild,[switch]$WithDemos)
$ErrorActionPreference='Stop'
$taskRoot=Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $taskRoot
$env:PYTHONIOENCODING='utf-8'
$env:LANGGRAPH_STRICT_MSGPACK='true'
New-Item -ItemType Directory -Force (Join-Path $taskRoot 'data') | Out-Null
if(-not (Test-Path '.venv\Scripts\python.exe')) { throw '请先运行 scripts\setup.ps1' }
if(-not $SkipBuild) {
  Push-Location frontend
  npm.cmd run build
  if($LASTEXITCODE -ne 0){throw '前端构建失败'}
  Pop-Location
}
$existing=Get-CimInstance Win32_Process -Filter "name='python.exe'" | Where-Object { $_.CommandLine -match 'uvicorn traceforge.api:app|traceforge.mcp_servers docs' }
$existingBackend=$existing | Where-Object { $_.CommandLine -match 'uvicorn traceforge.api:app' }
$existingDocs=$existing | Where-Object { $_.CommandLine -match 'traceforge.mcp_servers docs' }
$processRecord=@{}
if(Test-Path 'data\processes.json') {
  $saved=Get-Content -LiteralPath 'data\processes.json' -Raw | ConvertFrom-Json
  foreach($property in $saved.PSObject.Properties){$processRecord[$property.Name]=$property.Value}
}
$keepAlive=$null
if($processRecord.wsl){$keepAlive=Get-CimInstance Win32_Process -Filter "ProcessId=$($processRecord.wsl)" -ErrorAction SilentlyContinue}
if(-not ($keepAlive -and $keepAlive.Name -eq 'wsl.exe' -and $keepAlive.CommandLine -match 'sleep infinity')) {
  $alive=Start-Process -FilePath 'wsl.exe' -ArgumentList @('-d','Ubuntu','--exec','sleep','infinity') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $taskRoot 'data\wsl.out.log') -RedirectStandardError (Join-Path $taskRoot 'data\wsl.err.log') -PassThru
  $processRecord.wsl=$alive.Id
  $processRecord | ConvertTo-Json | Set-Content 'data\processes.json'
}
wsl -d Ubuntu -u root --exec systemctl start docker
if($LASTEXITCODE -ne 0){throw 'Docker启动失败，请检查WSL'}
wsl -d Ubuntu -u root --exec docker compose -p traceforge -f /mnt/d/systemDir/Documents/ChatGPT/agent_program/scripts/compose.yaml up -d --wait --wait-timeout 120
if($LASTEXITCODE -ne 0){throw 'Milvus启动失败，请检查 data 日志、etcd连接和Docker网络'}
$taskPython=Join-Path $taskRoot '.venv\Scripts\python.exe'
& $taskPython (Join-Path $PSScriptRoot 'check-milvus.py')
if($LASTEXITCODE -ne 0){throw 'Milvus真实RPC连接未通过，请检查19530端口与容器日志'}
if($WithDemos){
 wsl -d Ubuntu -u root --exec docker compose -p traceforge-demos --env-file /mnt/d/systemDir/Documents/ChatGPT/agent_program/data/demo-secrets.env -f /mnt/d/systemDir/Documents/ChatGPT/agent_program/scripts/demo-compose.yaml up -d
 if($LASTEXITCODE -ne 0){throw '演示服务启动失败'}
}
if(-not $existingDocs) {
  $docs=Start-Process -FilePath $taskPython -ArgumentList @('-m','traceforge.mcp_servers','docs') -WorkingDirectory $taskRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $taskRoot 'data\mcp.out.log') -RedirectStandardError (Join-Path $taskRoot 'data\mcp.err.log') -PassThru
  $processRecord.mcp=$docs.Id
}
if(-not $existingBackend) {
  $backend=Start-Process -FilePath $taskPython -ArgumentList @('-m','uvicorn','traceforge.api:app','--host','127.0.0.1','--port','8000') -WorkingDirectory $taskRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $taskRoot 'data\backend.out.log') -RedirectStandardError (Join-Path $taskRoot 'data\backend.err.log') -PassThru
  $processRecord.backend=$backend.Id
}
$processRecord | ConvertTo-Json | Set-Content data\processes.json
for($i=0;$i -lt 60;$i++) {
 try {Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/session' -TimeoutSec 2 | Out-Null; Write-Host 'TraceForge已启动：http://127.0.0.1:8000';exit 0} catch {Start-Sleep -Seconds 1}
}
throw '后端启动超时，请查看 data\backend.err.log'
