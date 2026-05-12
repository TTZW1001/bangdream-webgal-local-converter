param(
    [string]$PythonExe = "py",
    [string]$AppName = "",
    [switch]$OneDir
)

$ErrorActionPreference = "Stop"

function Refresh-WindowsIconCache {
    $ie4uinit = Join-Path $env:SystemRoot "System32\ie4uinit.exe"
    if (Test-Path $ie4uinit) {
        & $ie4uinit -ClearIconCache 2>$null
        & $ie4uinit -show 2>$null
    }

    $explorerProc = Get-Process -Name explorer -ErrorAction SilentlyContinue
    if ($explorerProc) {
        Stop-Process -Name explorer -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 600
    }

    $cachePaths = @(
        (Join-Path $env:LocalAppData "IconCache.db"),
        (Join-Path $env:LocalAppData "Microsoft\Windows\Explorer\iconcache*"),
        (Join-Path $env:LocalAppData "Microsoft\Windows\Explorer\thumbcache*")
    )
    foreach ($cachePath in $cachePaths) {
        Remove-Item -Path $cachePath -Force -ErrorAction SilentlyContinue
    }

    Start-Process explorer.exe
}

if (-not $AppName) {
    $AppName = [string]::Concat([char]37030, [char]37030, "WebGAL", [char]36716, [char]21270, [char]22120)
}

$internalName = "BangDreamWebGALConverter"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$iconSourcePath = Join-Path $projectRoot "icon.ico"
$iconPngPath = Join-Path $projectRoot "icon.png"
$configPath = Join-Path $projectRoot "config"
$distDir = Join-Path $projectRoot "output"
$runId = Get-Date -Format "yyyyMMdd-HHmmss"
$buildRoot = Join-Path $env:TEMP "bangdream-webgal-build"
$buildDir = Join-Path $buildRoot ("pyi-" + $runId)
$specDir = $buildDir
$sourceMirrorDir = Join-Path $buildDir "source"
$tempDistDir = Join-Path $buildDir "dist-temp"
$internalExe = Join-Path $tempDistDir ($internalName + ".exe")
$finalExe = Join-Path $distDir ($AppName + ".exe")
$generatedIconPath = $iconSourcePath
$buildIconPath = Join-Path $buildDir "app-icon.ico"
$mirroredAppPath = Join-Path $sourceMirrorDir "app.py"
$mirroredConfigPath = Join-Path $sourceMirrorDir "config"
$writtenExe = $finalExe

if (-not (Test-Path $configPath)) {
    throw "Missing config directory: $configPath"
}

New-Item -ItemType Directory -Force -Path $distDir | Out-Null
New-Item -ItemType Directory -Force -Path $buildRoot | Out-Null
New-Item -ItemType Directory -Force -Path $buildDir | Out-Null
New-Item -ItemType Directory -Force -Path $sourceMirrorDir | Out-Null
New-Item -ItemType Directory -Force -Path $tempDistDir | Out-Null
Get-ChildItem -Path $distDir -Filter "RCX*.tmp" -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
if (Test-Path $internalExe) {
    Remove-Item -LiteralPath $internalExe -Force -ErrorAction SilentlyContinue
}
if (Test-Path $finalExe) {
    Remove-Item -LiteralPath $finalExe -Force -ErrorAction SilentlyContinue
}

if (-not (Test-Path $iconPngPath)) {
    throw "Missing icon source: $iconPngPath"
}

& $PythonExe ".\prepare_build_icon.py"
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $generatedIconPath)) {
    throw "Failed to generate build icon from icon.png"
}
Copy-Item -LiteralPath $generatedIconPath -Destination $buildIconPath -Force

Copy-Item -LiteralPath (Join-Path $projectRoot "app.py") -Destination $mirroredAppPath -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "src") -Destination (Join-Path $sourceMirrorDir "src") -Recurse -Force
Copy-Item -LiteralPath $configPath -Destination $mirroredConfigPath -Recurse -Force

$sep = ";"
$modeFlag = if ($OneDir) { "--onedir" } else { "--onefile" }

$pyiArgs = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--windowed",
    $modeFlag,
    "--name", $internalName,
    "--icon", $buildIconPath,
    "--distpath", $tempDistDir,
    "--workpath", $buildDir,
    "--specpath", $specDir,
    "--add-data", "$mirroredConfigPath${sep}config",
    $mirroredAppPath
)

Write-Host "Building $AppName ..." -ForegroundColor Cyan
& $PythonExe @pyiArgs

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed. If the old EXE or build cache is locked by Windows Defender, close it and try again."
}

if (-not $OneDir) {
    if (-not (Test-Path $internalExe)) {
        throw "Expected EXE not found: $internalExe"
    }
    & $PythonExe ".\verify_exe_icon.py" $internalExe $buildIconPath
    if ($LASTEXITCODE -ne 0) {
        throw "Final EXE icon verification failed."
    }
    if (Test-Path $finalExe) {
        try {
            Remove-Item -LiteralPath $finalExe -Force -ErrorAction Stop
        }
        catch {
            $writtenExe = Join-Path $distDir ($AppName + "-new.exe")
            if (Test-Path $writtenExe) {
                Remove-Item -LiteralPath $writtenExe -Force -ErrorAction SilentlyContinue
            }
        }
    }
    Copy-Item -LiteralPath $internalExe -Destination $writtenExe -Force
}

Write-Host ""
Write-Host "Build completed." -ForegroundColor Green
Write-Host "Output directory: $distDir"
if (-not $OneDir) {
    Write-Host "EXE file: $writtenExe"
}
Refresh-WindowsIconCache
