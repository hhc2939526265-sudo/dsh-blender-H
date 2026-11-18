# 一键打包（Windows PowerShell）：Blender Addon + DSH 插件 + 完整源码
# 用法：在仓库根目录执行  powershell -ExecutionPolicy Bypass -File scripts/package_all.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$OutDir = Join-Path $Root "packages"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$Manifest = Get-Content (Join-Path $Root "src/dsh_plugin/manifest.json") -Raw | ConvertFrom-Json
$Version = $Manifest.version

function Compress-Directory($Source, $OutFile) {
    if (Test-Path $OutFile) { Remove-Item $OutFile -Force }
    Compress-Archive -Path (Join-Path $Source "*") -DestinationPath $OutFile -Force
}

# 1. Blender Addon
$AddonZip = Join-Path $OutDir "DSH_Blender_Bridge_Addon_v$Version.zip"
Get-ChildItem -Path (Join-Path $Root "src/blender_addon") -Recurse -Directory -Filter "__pycache__" |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Compress-Directory (Join-Path $Root "src/blender_addon") $AddonZip
Write-Host "[OK] Blender Addon: $AddonZip"

# 2. DSH 插件
$PluginZip = Join-Path $OutDir "DSH_Blender_Bridge_Plugin_v$Version.zip"
Compress-Directory (Join-Path $Root "src/dsh_plugin") $PluginZip
Write-Host "[OK] DSH 插件: $PluginZip"

# 3. 完整源码（排除打包产物与缓存）
$SourceZip = Join-Path $OutDir "DSH_Blender_Bridge_Source_v$Version.zip"
$TempSource = Join-Path $Env:TEMP "dsh_bridge_src_$Version"
if (Test-Path $TempSource) { Remove-Item $TempSource -Recurse -Force }
Copy-Item $Root $TempSource -Recurse -Force
$ExcludeDirs = @("packages", "__pycache__", "transfer_cache", "render_output", "logs", "backups")
foreach ($d in $ExcludeDirs) {
    Get-ChildItem -Path $TempSource -Recurse -Directory -Filter $d |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}
Compress-Directory $TempSource $SourceZip
Remove-Item $TempSource -Recurse -Force
Write-Host "[OK] 源码包: $SourceZip"

Write-Host "全部产物位于 $OutDir"
Get-ChildItem $OutDir | Format-Table Name, Length
