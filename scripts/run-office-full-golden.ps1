$ErrorActionPreference = "Continue"

$repoRoot = Split-Path -Parent $PSScriptRoot
$dataRoot = "C:\vectorsearch-data\ko-unstructured"
$evalRoot = Join-Path $dataRoot "eval\full"
$reportRoot = Join-Path $dataRoot "reports"
$logPath = Join-Path $reportRoot "full_golden.log"
$statusPath = Join-Path $reportRoot "full_golden_status.json"

New-Item -ItemType Directory -Force -Path $evalRoot, $reportRoot | Out-Null
Set-Location $repoRoot
. .\scripts\project-env.ps1 | Out-File -FilePath $logPath -Encoding utf8

[pscustomobject]@{
  state = "generating"
  target_questions = 300
  updated_at = (Get-Date).ToString("o")
} | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding utf8

uv run koreanops-office-build-golden `
  (Join-Path $evalRoot "oracle_documents.jsonl") `
  (Join-Path $evalRoot "oracle_pages.jsonl") `
  (Join-Path $evalRoot "golden_questions_candidates.jsonl") `
  --sample-size 300 `
  --use-ollama `
  --resume 2>&1 |
  Tee-Object -FilePath $logPath -Append

if ($LASTEXITCODE -ne 0) {
  [pscustomobject]@{
    state = "failed"
    exit_code = $LASTEXITCODE
    updated_at = (Get-Date).ToString("o")
  } | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding utf8
  exit $LASTEXITCODE
}

[pscustomobject]@{
  state = "complete"
  target_questions = 300
  updated_at = (Get-Date).ToString("o")
} | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding utf8
