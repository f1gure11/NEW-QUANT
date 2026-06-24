param(
  [string]$HostName = "154.222.31.222",
  [string]$User = "root",
  [int]$Port = 22,
  [string]$RemoteDir = "/opt/okx-quant",
  [switch]$IncludeEnv
)

$ErrorActionPreference = "Stop"
$ScriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { [System.IO.Path]::GetDirectoryName($MyInvocation.MyCommand.Path) }
$Root = [System.IO.Directory]::GetParent($ScriptDir).FullName
[System.IO.Directory]::SetCurrentDirectory($Root)

foreach ($cmd in @("ssh", "scp")) {
  if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
    throw "$cmd not found. Install OpenSSH client first."
  }
}

$remote = "$User@$HostName"
$zip = Join-Path $env:TEMP "okx_quant_deploy_$(Get-Date -Format yyyyMMddHHmmss).zip"

$items = @(
  "auto_grid_bot.py",
  "dashboard_server.py",
  "okx_client.py",
  "test_okx_connection.py",
  "web",
  "data/okx/grid_bot_runtime_config.json",
  "data/okx/re_grid_bot_runtime_config.json",
  "deploy",
  "scripts/server_setup.sh",
  "scripts/install_services.sh",
  ".env.example",
  "DEPLOY_SERVER.md"
)

if ($IncludeEnv) {
  $items += ".env"
  Write-Host "Including .env. Make sure OKX API has no withdraw permission."
} else {
  Write-Host "Not including .env. Use -IncludeEnv when you intentionally copy credentials."
}

if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path $items -DestinationPath $zip -Force

ssh -p $Port $remote "mkdir -p /tmp/okx-quant-deploy '$RemoteDir'"
scp -P $Port $zip "${remote}:/tmp/okx-quant-deploy/package.zip"
ssh -p $Port $remote "python3 - <<'PY'
import zipfile, pathlib
remote = pathlib.Path('$RemoteDir')
remote.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile('/tmp/okx-quant-deploy/package.zip') as z:
    z.extractall(remote)
(remote / 'data' / 'okx').mkdir(parents=True, exist_ok=True)
PY
chmod +x '$RemoteDir/scripts/server_setup.sh' '$RemoteDir/scripts/install_services.sh'
chown -R okxbot:okxbot '$RemoteDir' 2>/dev/null || true"

Remove-Item $zip -Force
Write-Host "Uploaded to ${remote}:$RemoteDir"
