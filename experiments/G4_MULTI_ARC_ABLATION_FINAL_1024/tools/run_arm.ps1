<#
One arm run of the strict common-start ablation (G4c_free engine).

The *only* algorithm variable is the environment variable
G4_ENABLE_MULTI_ARC (1 = multi-arc ON, 0 = OFF).  Everything else -- start
state, seed, stage schedule, counted budget, wall safety net, validator policy
-- is given on the command line and must be identical between the two arms.

Example:

    powershell -NoProfile -File run_arm.ps1 -Arm on -Tag c1_seed20261104 `
        -Seed 20261104 -CountedD56 48000 -CountedChecks 7400 -Seconds 21600
#>
param(
    [Parameter(Mandatory = $true)][ValidateSet('on', 'off')][string]$Arm,
    [Parameter(Mandatory = $true)][string]$Tag,
    [int]$Seed = 20261104,
    [string]$StartDir = '',
    [string]$OutRoot = '',
    [double]$Seconds = 21600,
    [int]$CountedD56 = 0,
    [int]$CountedChecks = 0,
    [switch]$SkipValidator
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = 'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D'
$ExpRoot = Join-Path $ProjectRoot 'experiments\G4_MULTI_ARC_ABLATION_FINAL_1024'
if (-not $StartDir) {
    $StartDir = 'C:\Users\lihao\Desktop\Graduation Project\work\1130-report-materials\G4_MULTI_ARC_ABLATION_1024\no_multi_arc\01_convert'
}
if (-not $OutRoot) { $OutRoot = Join-Path $ExpRoot 'runs' }
$OutDir = Join-Path $OutRoot "$Arm\$Tag"

# --- the single changed variable -------------------------------------------
if ($Arm -eq 'on') { $env:G4_ENABLE_MULTI_ARC = '1' } else { $env:G4_ENABLE_MULTI_ARC = '0' }

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$console = Join-Path $OutDir 'console.log'
$startedAt = (Get-Date).ToString('o')

$arguments = @(
    '-m', 'four_side_1024.fanout1024.xyzrouter.g4.run_g4_engine',
    '--arm', 'G4c_free',
    '--seconds', "$Seconds",
    '--seed', "$Seed",
    '--start-dir', $StartDir,
    '--out-dir', $OutDir,
    '--tag', $Tag
)
if ($CountedD56 -gt 0) { $arguments += @('--counted-d56-budget', "$CountedD56") }
if ($CountedChecks -gt 0) { $arguments += @('--counted-checks-guard', "$CountedChecks") }

$banner = @(
    ('=' * 78),
    "arm=$Arm tag=$Tag seed=$Seed counted_d56=$CountedD56 counted_checks=$CountedChecks",
    "G4_ENABLE_MULTI_ARC=$env:G4_ENABLE_MULTI_ARC",
    "start=$StartDir",
    "out=$OutDir",
    "started_at=$startedAt",
    "python=$(python -c 'import sys; print(sys.executable)')",
    ('=' * 78)
)
$banner | Tee-Object -FilePath $console -Append | ForEach-Object { $_ }

Push-Location $ProjectRoot
try {
    & python @arguments 2>&1 | Tee-Object -FilePath $console -Append
    $engineExit = $LASTEXITCODE
}
finally {
    Pop-Location
}
$finishedAt = (Get-Date).ToString('o')

# --- independent Validator as a fresh process ------------------------------
$validatorExit = $null
if (-not $SkipValidator) {
    $valOut = Join-Path $OutDir 'validation_final'
    $valLog = Join-Path $OutDir 'validation_final.log'
    Push-Location $ProjectRoot
    try {
        & python -m four_side_1024.fanout1024.xyzrouter.validate_xyz `
            --run-dir (Join-Path $OutDir 'best_valid') `
            --out-dir $valOut `
            --manual-policy fully_optimizable `
            --baseline-dir 'outputs\manual_c4_new_connectivity\XYZ_JOINT_G123_1024\baseline_authoritative' `
            2>&1 | Tee-Object -FilePath $valLog -Append
        $validatorExit = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
}

$meta = [ordered]@{
    arm                  = $Arm
    tag                  = $Tag
    seed                 = $Seed
    g4_enable_multi_arc  = $env:G4_ENABLE_MULTI_ARC
    start_dir            = $StartDir
    out_dir              = $OutDir
    counted_d56_budget   = $CountedD56
    counted_checks_guard = $CountedChecks
    wall_safety_net      = $Seconds
    started_at           = $startedAt
    finished_at          = $finishedAt
    engine_exit          = $engineExit
    validator_exit       = $validatorExit
    python               = (& python -c 'import sys; print(sys.executable)')
    host                 = $env:COMPUTERNAME
}
$meta | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $OutDir 'run_meta.json') -Encoding UTF8
$meta | ConvertTo-Json -Depth 4
exit $engineExit
