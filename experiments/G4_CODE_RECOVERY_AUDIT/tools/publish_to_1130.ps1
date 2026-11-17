<#
Assemble the published copy of the G4 code-recovery audit and (optionally) commit it
to the 1130-report-materials repository.

What is published:
  * the report and its README
  * every machine-readable evidence file (file table, diffs, signatures, settings,
    chain provenance, start-state audit, 1185 audit + per-route CSV, Validator run)
  * the trusted 08_code snapshot (so the hashes can be re-checked offline)
  * the two probe runs, reduced to the reproducible set (no checkpoints, no
    duplicate root-level routes file)
  * the scripts that produced all of it

What is NOT published:
  * `recovered_G4_1185/` and `probe_current_code/` (74 MB each; they are reproducible
    from the documented steps and the main project)
  * `staging/` (intermediate tarballs)

Usage:
    powershell -NoProfile -ExecutionPolicy Bypass -File tools\publish_to_1130.ps1 `
        [-Repo <path to 1130-report-materials>] [-Commit] [-Push]
#>
param(
    [string]$Repo = 'C:\Users\lihao\Desktop\Graduation Project\work\1130-report-materials',
    [string]$DestRel = 'experiments/G4_CODE_RECOVERY_AUDIT',
    [switch]$Commit,
    [switch]$Push,
    [string]$Proxy = 'http://127.0.0.1:7897'
)

$ErrorActionPreference = 'Stop'
$Audit = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Dest = Join-Path $Repo $DestRel

function Copy-One([string]$relative) {
    $src = Join-Path $Audit $relative
    if (-not (Test-Path $src)) { Write-Host "skip (missing): $relative"; return }
    $target = Join-Path $Dest $relative
    New-Item -ItemType Directory -Force -Path (Split-Path $target) | Out-Null
    Copy-Item $src $target -Force
    Write-Host "  + $relative"
}

function Copy-Tree([string]$relative) {
    $src = Join-Path $Audit $relative
    if (-not (Test-Path $src)) { Write-Host "skip (missing): $relative"; return }
    Get-ChildItem $src -Recurse -File | ForEach-Object {
        $rel = $_.FullName.Substring($Audit.Length + 1)
        $target = Join-Path $Dest $rel
        New-Item -ItemType Directory -Force -Path (Split-Path $target) | Out-Null
        Copy-Item $_.FullName $target -Force
    }
    Write-Host "  + $relative/ ($((Get-ChildItem $src -Recurse -File).Count) files)"
}

Write-Host "publishing to $Dest"
New-Item -ItemType Directory -Force -Path $Dest | Out-Null

# --- report level -----------------------------------------------------------
Copy-One 'G4_CODE_RECOVERY_AUDIT.md'
Copy-One 'README.md'
Copy-One 'audit_g3_start.json'
Copy-One 'audit_1185.json'
Copy-One 'audit_1185_per_route.csv'
Copy-Tree 'audit_g4'
Copy-Tree 'validation_1185_original_code'
Copy-Tree 'trusted_08_code'
Copy-Tree 'tools'

# --- probe runs: keep the reproducible set only -----------------------------
$keep = @('run.log', 'console.log', 'run_meta.json', 'summary.json', 'arm_summary.json',
          'budget_ledger.json', 'config.json', 'crossing_stats.json', 'strategy_stats.json',
          'optimization_history.csv', 'geometry_changes.json', 'manual_u_changes.json',
          'failed_attempts.json', 'failure_taxonomy.json', 'route_scan.json',
          'final_route_scan.json', 'group_attempts.json', 'group_migration.json',
          'migration_matrix.csv', 'new_grouping.json', 'xy_evidence.json',
          'start_snapshot.json', 'validation_run.json', 'validation_summary.json',
          'SHA256.json')
foreach ($probe in @('runs/G4b_repro_1200s', 'runs/G4b_current_code_1200s')) {
    $src = Join-Path $Audit $probe
    if (-not (Test-Path $src)) { Write-Host "skip (missing): $probe"; continue }
    $out = Join-Path $Dest $probe
    New-Item -ItemType Directory -Force -Path $out | Out-Null
    foreach ($name in $keep) {
        $file = Join-Path $src $name
        if (Test-Path $file) { Copy-Item $file (Join-Path $out $name) -Force }
    }
    foreach ($sub in @('best_valid', 'validation')) {
        $dir = Join-Path $src $sub
        if (-not (Test-Path $dir)) { continue }
        New-Item -ItemType Directory -Force -Path (Join-Path $out $sub) | Out-Null
        Get-ChildItem $dir -File | ForEach-Object {
            # best_valid holds routes + assignment + SHA only (no stats duplicates)
            Copy-Item $_.FullName (Join-Path (Join-Path $out $sub) $_.Name) -Force
        }
    }
    $log = Join-Path $Audit ($probe + '.console.log')
    if (Test-Path $log) { Copy-Item $log (Join-Path $Dest ($probe + '.console.log')) -Force }
    Write-Host "  + $probe (reduced)"
}

# --- byte-exact folder marker ----------------------------------------------
$gitattrs = Join-Path $Dest '.gitattributes'
Set-Content -Path $gitattrs -Value "# keep every artifact byte-exact: disable all EOL / text conversion under this folder`n* -text" -Encoding ASCII -NoNewline
Write-Host "  + .gitattributes"

# --- manifest ---------------------------------------------------------------
Push-Location $Audit
try {
    & python (Join-Path $Audit 'tools\build_manifest.py') --root $Dest
}
finally { Pop-Location }

if ($Commit) {
    Push-Location $Repo
    try {
        git add $DestRel
        $msg = @'
Add G4 code-recovery audit (1185 baseline): trusted snapshot diff, chain provenance, independent re-validation, byte-identical reproduction probes

Read-only audit of the code that produced the archived 1185-crossing G4
solution, plus an isolated recovery project.  The production tree
OpticalWaveguideRouter2D was backed up (36,783 files / 6.617 GB, 0 failed)
and verified unchanged afterwards (robocopy list-only: 0 differences).

Findings
  * trusted snapshot 11.9-second-report-all-work@833a009b411c
    g4_xyz_joint_1024/08_code: 25/25 entries self-check OK;
  * current g4/ vs that snapshot: 18 identical, 6 modified, 0 removed,
    0 added; the 6 are the equal-budget patch (+176/-13) and the patch is
    purely additive (its 13 deleted lines are signatures, call sites and
    START_CROSSINGS metadata only -- no algorithm line removed);
  * the two 1130 ablation rounds touched exactly 8 files in the whole
    452-file package (layer2d.py +112/-0, local_reroute.py +1/-0, and the
    6 g4 files); layer2d.py.orig normalises to the blob of a committed
    snapshot, so the pre-ablation file is independently pinned;
  * the published 1185 is not one G4d run: G3 1322 -> G4c_free (1840 s) ->
    1189 -> G4d chain link (1230 s) -> 1185; G4b (1294) sits in an
    unused side branch;
  * 1185 re-validated with the recovered original Validator: PASS,
    0 violations, 1185 crossings / 1124 pairs, min 3D 0.060877 mm;
  * reproduction probes: both the recovered original code and the current
    code, started from the verified G3 optimum with seed 20261104 and the
    original 1200 s budget, produce routes_l3d.json c72b245a... -- byte
    identical to the archived G4b checkpoint (1294 crossings).

Verdict: no G4 regression.  The 2203 of the strict ablation comes from the
start state (3967 vs 1322), the pipeline (one arm vs two chained arms) and
the budget definition, not from code drift.  No production file was modified
and no rollback was performed.
'@
        $msgPath = Join-Path $env:TEMP 'g4_recovery_commit_msg.txt'
        [IO.File]::WriteAllText($msgPath, $msg, (New-Object System.Text.UTF8Encoding($false)))
        git commit -F $msgPath
    }
    finally { Pop-Location }
}

if ($Push) {
    Push-Location $Repo
    try {
        $env:GIT_TERMINAL_PROMPT = '0'
        git -c http.proxy=$Proxy -c http.postBuffer=524288000 push origin main
    }
    finally { Pop-Location }
}

Write-Host 'done'
