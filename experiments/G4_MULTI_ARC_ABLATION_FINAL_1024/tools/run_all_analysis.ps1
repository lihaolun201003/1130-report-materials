<#
Run the complete analysis chain of the FINAL ablation.

Assumes the formal runs already exist under ``runs/``.  Every step is
idempotent: it overwrites its own tables/figures and never touches ``runs/``.

Usage:
    powershell -NoProfile -ExecutionPolicy Bypass -File tools\run_all_analysis.ps1
    powershell ... -File tools\run_all_analysis.ps1 -Seeds "20261104,20261116,20261130"
#>
param(
    [string]$Seeds = '20261104,20261116,20261130',
    [switch]$SkipStage0
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = 'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D'
$Exp = Join-Path $ProjectRoot 'experiments\G4_MULTI_ARC_ABLATION_FINAL_1024'
$Tools = Join-Path $Exp 'tools'
$Runs = Join-Path $Exp 'runs'
$Tables = Join-Path $Exp 'tables'
$Figures = Join-Path $Exp 'figures'
$Logs = Join-Path $Exp 'logs'
New-Item -ItemType Directory -Force -Path $Tables, $Figures, $Logs | Out-Null

Push-Location $ProjectRoot
try {
    Write-Host '=== 1. collect every run (with independent geometry audit) ==='
    & python "$Tools\collect_results.py" --runs-root $Runs --out $Tables --with-audit `
        2>&1 | Tee-Object -FilePath "$Logs\analysis_collect.log"

    Write-Host '=== 2. per-arm statistics and A/B/C judgement ==='
    & python "$Tools\summarize.py" --runs-json "$Tables\runs.json" --prefix c1 `
        --label 'Primary: equal candidate-evaluation budget (d56 = 24000)' `
        2>&1 | Tee-Object -FilePath "$Logs\analysis_summary_c1.log" | Out-Null
    & python "$Tools\summarize.py" --runs-json "$Tables\runs.json" --prefix a1 `
        --label 'Auxiliary: equal wall-clock budget (900 s)' `
        2>&1 | Tee-Object -FilePath "$Logs\analysis_summary_a1.log" | Out-Null

    Write-Host '=== 3. search-progress curves (three cost axes) ==='
    & python "$Tools\plot_search_curves.py" --runs-root $Runs --tag-prefix c1 `
        --title 'Strict common start (3967): equal candidate-evaluation budget (d56 = 24000)' `
        --stem fig_search_curves_c1 2>&1 | Tee-Object -FilePath "$Logs\analysis_curves_c1.log"
    & python "$Tools\plot_search_curves.py" --runs-root $Runs --tag-prefix a1 `
        --title 'Strict common start (3967): equal wall-clock budget (900 s)' `
        --stem fig_search_curves_a1 2>&1 | Tee-Object -FilePath "$Logs\analysis_curves_a1.log"

    Write-Host '=== 4. Stage-0 conversion audit (replay of 197 commits) ==='
    if (-not $SkipStage0) {
        & python "$Tools\analyze_stage0.py" 2>&1 | Tee-Object -FilePath "$Logs\analysis_stage0.log" | Out-Null
    }

    Write-Host '=== 5. repair analysis per seed + gap decomposition ==='
    foreach ($seed in ($Seeds -split ',')) {
        $on = Join-Path $Runs "on\c1_on_$seed\best_valid"
        $off = Join-Path $Runs "off\c1_off_$seed\best_valid"
        if ((Test-Path $on) -and (Test-Path $off)) {
            & python "$Tools\analyze_repair.py" --on $on --off $off `
                --out "$Tables\repair_c1_$seed.json" `
                --csv "$Tables\repair_c1_${seed}_per_route.csv" `
                2>&1 | Tee-Object -FilePath "$Logs\analysis_repair_$seed.log" | Out-Null
        }
    }
    & python "$Tools\analyze_gap.py" --seed 20261104 `
        2>&1 | Tee-Object -FilePath "$Logs\analysis_gap.log"

    Write-Host '=== 6. per-layer crossing distribution + 2R figures ==='
    $StartDir = 'C:\Users\lihao\Desktop\Graduation Project\work\1130-report-materials\G4_MULTI_ARC_ABLATION_1024\no_multi_arc\01_convert'
    & python "$Tools\plot_layers.py" `
        --state ("common_start_3967=" + $StartDir) `
        --state ("ON_seed20261104=" + (Join-Path $Runs 'on\c1_on_20261104\best_valid')) `
        --state ("OFF_seed20261104=" + (Join-Path $Runs 'off\c1_off_20261104\best_valid')) `
        2>&1 | Tee-Object -FilePath "$Logs\analysis_layers.log"
    & python "$Tools\plot_2r.py" 2>&1 | Tee-Object -FilePath "$Logs\analysis_2r.log"
    & python "$Tools\plot_2r_repair.py" --tag c1_20261104 `
        2>&1 | Tee-Object -FilePath "$Logs\analysis_2r_repair.log" | Out-Null

    Write-Host '=== 7. real-route case figures ==='
    & python "$Tools\route_cases.py" `
        --on (Join-Path $Runs 'on\c1_on_20261104\best_valid') `
        --off (Join-Path $Runs 'off\c1_off_20261104\best_valid') `
        2>&1 | Tee-Object -FilePath "$Logs\analysis_cases.log"

    Write-Host '=== 8. Validator summary ==='
    & python "$Tools\make_validation_summary.py" `
        2>&1 | Tee-Object -FilePath "$Logs\analysis_validation.log"

    Write-Host '=== analysis chain finished ==='
    Write-Host 'next: tools\assemble_archive.py --dest <repo>\experiments\G4_MULTI_ARC_ABLATION_FINAL_1024'
    Write-Host '      then tools\build_manifest.py --root <archive>'
}
finally {
    Pop-Location
}
