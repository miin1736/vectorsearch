$ErrorActionPreference = "Continue"

$repoRoot = Split-Path -Parent $PSScriptRoot
$dataRoot = "C:\vectorsearch-data\ko-unstructured"
$processedRoot = Join-Path $dataRoot "processed\full"
$reportRoot = Join-Path $dataRoot "reports"
$logPath = Join-Path $reportRoot "full_index.log"
$statusPath = Join-Path $reportRoot "full_index_status.json"

New-Item -ItemType Directory -Force -Path $reportRoot | Out-Null
Set-Location $repoRoot
. .\scripts\project-env.ps1 | Out-File -FilePath $logPath -Encoding utf8

$jobs = @(
  @{
    name = "page"
    chunks = Join-Path $processedRoot "chunks_page.jsonl"
    config = "experiments\ko_unstructured_v2\configs\pdf_page.yaml"
  },
  @{
    name = "structure"
    chunks = Join-Path $processedRoot "chunks_structure.jsonl"
    config = "experiments\ko_unstructured_v2\configs\pdf_structure.yaml"
  }
)

foreach ($job in $jobs) {
  [pscustomobject]@{
    state = "qdrant"
    corpus = $job.name
    updated_at = (Get-Date).ToString("o")
  } | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding utf8
  "Indexing $($job.name) into Qdrant" | Tee-Object -FilePath $logPath -Append
  uv run koreanops-index-qdrant $job.chunks --config-path $job.config 2>&1 |
    Tee-Object -FilePath $logPath -Append
  if ($LASTEXITCODE -ne 0) {
    throw "Qdrant indexing failed for $($job.name)"
  }

  [pscustomobject]@{
    state = "opensearch"
    corpus = $job.name
    updated_at = (Get-Date).ToString("o")
  } | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding utf8
  "Indexing $($job.name) into OpenSearch" | Tee-Object -FilePath $logPath -Append
  uv run koreanops-index-opensearch $job.chunks --config-path $job.config 2>&1 |
    Tee-Object -FilePath $logPath -Append
  if ($LASTEXITCODE -ne 0) {
    throw "OpenSearch indexing failed for $($job.name)"
  }
}

[pscustomobject]@{
  state = "complete"
  corpus = "all"
  updated_at = (Get-Date).ToString("o")
} | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding utf8

"Full Page and Structure indexing complete" | Tee-Object -FilePath $logPath -Append
