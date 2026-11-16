# -*- coding: utf-8 -*-
<#
G4 multi-arc ablation — one-arm driver (1024 channels).

Runs the *same* G4 trunk for one arm and validates every stage with the frozen
independent Validator:

    stage 1  G4c_free  (joint make-way LNS, 1800 s search budget, seed 20261104)
    stage 2  G4d       (1024-route large-neighbourhood ALNS, 1200 s)

The only difference between the two arms is the environment variable
``G4_ENABLE_MULTI_ARC`` (1 = original G4 grammar, 0 = planar multi-arc banned).
Stage 0 (the conversion of the 197 inherited multi-arc routes) is run
separately by ``convert_multi_arc.py`` for the ablated arm.

Usage:
    pwsh -File tools\run_arm_chain.ps1 -Arm off
    pwsh -File tools\run_arm_chain.ps1 -Arm on
#>
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('on', 'off')]
    [string]$Arm,
    [string]$StartDir = '',
    [int]$G4cSeconds = 1800,
    [int]$G4dSeconds = 1200,
    [int]$Seed = 20261104
)

$ErrorActionPreference = 'Stop'
$project = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
Set-Location $project
$root = Join-Path $project 'experiments\G4_MULTI_ARC_ABLATION_1024'
$g3 = 'outputs\manual_c4_new_connectivity\XYZ_JOINT_G123_1024\best_valid'
$auth = 'outputs\manual_c4_new_connectivity\XYZ_JOINT_G123_1024\baseline_authoritative'
$python = (Get-Command python).Source

if ($Arm -eq 'off') {
    $armRoot = Join-Path $root 'no_multi_arc'
    $env:G4_ENABLE_MULTI_ARC = '0'
    if (-not $StartDir) { $StartDir = Join-Path $armRoot '01_convert' }
} else {
    $armRoot = Join-Path $root 'baseline_rerun'
    $env:G4_ENABLE_MULTI_ARC = '1'
    if (-not $StartDir) { $StartDir = $g3 }
}
New-Item -ItemType Directory -Force $armRoot | Out-Null
$logPath = Join-Path $armRoot 'chain_console.log'
$summaryPath = Join-Path $armRoot 'chain_run.json'

function Write-Log([string]$text) {
    $line = '[' + (Get-Date -Format 'yyyy-MM-ddTHH:mm:ss') + '] ' + $text
    Write-Host $line
    Add-Content -Path $logPath -Value $line -Encoding utf8
}

function Invoke-Python([string[]]$argv, [string]$logFile) {
    $display = 'python ' + ($argv -join ' ')
    Write-Log ('RUN  ' + $display)
    $sw = [diagnostics.stopwatch]::StartNew()
    & $python @argv *> $logFile
    $code = $LASTEXITCODE
    $sw.Stop()
    $seconds = [math]::Round($sw.Elapsed.TotalSeconds, 2)
    Write-Log ('EXIT ' + $code + '  (' + $seconds + 's)  log=' + $logFile)
    if ($code -ne 0) { throw ("command failed: " + $display) }
    return $seconds
}

function Invoke-Validation([string]$runDir, [string]$outDir, [string]$logFile) {
    return (Invoke-Python @('-m', 'four_side_1024.fanout1024.xyzrouter.validate_xyz',
            '--run-dir', $runDir, '--out-dir', $outDir,
            '--manual-policy', 'fully_optimizable',
            '--baseline-dir', $auth) $logFile)
}

if (Test-Path $logPath) { Remove-Item $logPath }
Write-Log ('=' * 78)
Write-Log ('arm=' + $Arm + ' G4_ENABLE_MULTI_ARC=' + $env:G4_ENABLE_MULTI_ARC +
    ' start=' + $StartDir + ' seed=' + $Seed)
Write-Log ('G4c seconds=' + $G4cSeconds + '  G4d seconds=' + $G4dSeconds)

$stages = @()
$g4cDir = Join-Path $armRoot '02_G4c_free'
$g4dDir = Join-Path $armRoot '03_G4d'

# ---------------------------------------------------------------- stage G4c
$seconds = Invoke-Python @('-m', 'four_side_1024.fanout1024.xyzrouter.g4.run_g4_engine',
    '--arm', 'G4c_free', '--seconds', "$G4cSeconds", '--seed', "$Seed",
    '--start-dir', $StartDir, '--out-dir', $g4cDir,
    '--tag', "ablation_$Arm") (Join-Path $armRoot '02_G4c_free.console.log')
$v = Invoke-Validation (Join-Path $g4cDir 'best_valid') (Join-Path $g4cDir 'validation') `
    (Join-Path $armRoot '02_G4c_free.validation.log')
$stages += [ordered]@{ stage = 'G4c_free'; out_dir = $g4cDir; search_seconds = $seconds
    validation_seconds = $v; validation = (Join-Path $g4cDir 'validation\validation.json') }

# ---------------------------------------------------------------- stage G4d
$seconds = Invoke-Python @('-m', 'four_side_1024.fanout1024.xyzrouter.g4.run_g4_engine',
    '--arm', 'G4d', '--seconds', "$G4dSeconds", '--seed', "$Seed",
    '--start-dir', (Join-Path $g4cDir 'best_valid'), '--out-dir', $g4dDir,
    '--tag', "ablation_$Arm") (Join-Path $armRoot '03_G4d.console.log')
$v = Invoke-Validation (Join-Path $g4dDir 'best_valid') (Join-Path $g4dDir 'validation') `
    (Join-Path $armRoot '03_G4d.validation.log')
$stages += [ordered]@{ stage = 'G4d'; out_dir = $g4dDir; search_seconds = $seconds
    validation_seconds = $v; validation = (Join-Path $g4dDir 'validation\validation.json') }

# ------------------------------------------------------------------- summary
$final = Join-Path $g4dDir 'best_valid'
if (-not (Test-Path (Join-Path $final 'routes_l3d.json'))) { $final = $g4cDir + '\best_valid' }
$payload = [ordered]@{
    arm = $Arm
    multi_arc = $env:G4_ENABLE_MULTI_ARC
    start_dir = $StartDir
    seed = $Seed
    g4c_seconds = $G4cSeconds
    g4d_seconds = $G4dSeconds
    final_dir = $final
    stages = $stages
    finished_at = (Get-Date -Format 'yyyy-MM-ddTHH:mm:ss')
}
$payload | ConvertTo-Json -Depth 6 | Set-Content -Path $summaryPath -Encoding utf8
Write-Log ('final=' + $final)
Write-Log 'done'
