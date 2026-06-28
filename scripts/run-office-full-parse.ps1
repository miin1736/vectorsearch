param(
  [int]$BatchSize = 250
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$dataRoot = "C:\vectorsearch-data\ko-unstructured"
$trainingRoot = Get-ChildItem -LiteralPath (Join-Path $dataRoot "raw") -Directory -Recurse |
  Where-Object {
    $_.Name -eq "Training" -and
    (Test-Path -LiteralPath (Join-Path $_.Parent.FullName "Validation"))
  } |
  Select-Object -First 1
$datasetRoot = if ($trainingRoot) { $trainingRoot.Parent.FullName } else { $null }
if (-not $datasetRoot) {
  throw "Office PDF dataset directory was not found under $dataRoot\raw"
}
$processedRoot = Join-Path $dataRoot "processed\full"
$batchRoot = Join-Path $processedRoot "batches"
$manifest = Join-Path $dataRoot "processed\office_manifest.jsonl"
$logPath = Join-Path $dataRoot "reports\full_parse.log"
$statusPath = Join-Path $dataRoot "reports\full_parse_status.json"

New-Item -ItemType Directory -Force -Path $processedRoot, $batchRoot, (Split-Path $logPath) | Out-Null

Set-Location $repoRoot
. .\scripts\project-env.ps1 | Out-File -FilePath $logPath -Encoding utf8

$total = (Get-Content -LiteralPath $manifest | Measure-Object -Line).Lines
$batchCount = [Math]::Ceiling($total / $BatchSize)

for ($batch = 0; $batch -lt $batchCount; $batch++) {
  $offset = $batch * $BatchSize
  $expected = [Math]::Min($BatchSize, $total - $offset)
  $prefix = "batch_{0:D4}" -f $batch
  $pages = Join-Path $batchRoot "${prefix}_pages.jsonl"
  $blocks = Join-Path $batchRoot "${prefix}_blocks.jsonl"
  $documents = Join-Path $batchRoot "${prefix}_documents.jsonl"
  $completed = if (Test-Path -LiteralPath $documents) {
    (Get-Content -LiteralPath $documents | Measure-Object -Line).Lines
  } else {
    0
  }
  if ($completed -ne $expected) {
    "Starting batch $($batch + 1)/$batchCount offset=$offset count=$expected" |
      Tee-Object -FilePath $logPath -Append
    uv run koreanops-office-parse `
      $datasetRoot `
      $manifest `
      $pages `
      $blocks `
      $documents `
      --offset $offset `
      --limit $expected 2>&1 |
      Tee-Object -FilePath $logPath -Append
    if ($LASTEXITCODE -ne 0) {
      throw "Office PDF parsing failed at batch $batch"
    }
  }
  [pscustomobject]@{
    state = "parsing"
    total_documents = $total
    completed_documents = [Math]::Min(($batch + 1) * $BatchSize, $total)
    completed_batches = $batch + 1
    total_batches = $batchCount
    updated_at = (Get-Date).ToString("o")
  } | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding utf8
}

$mergedFiles = @{
  "*_pages.jsonl" = "pdf_pages_raw.jsonl"
  "*_blocks.jsonl" = "pdf_blocks_cleaned.jsonl"
  "*_documents.jsonl" = "office_documents_normalized.jsonl"
}
foreach ($pattern in $mergedFiles.Keys) {
  $target = Join-Path $processedRoot $mergedFiles[$pattern]
  $targetStream = [System.IO.File]::Open(
    $target,
    [System.IO.FileMode]::Create,
    [System.IO.FileAccess]::Write,
    [System.IO.FileShare]::None
  )
  try {
    foreach ($source in Get-ChildItem -LiteralPath $batchRoot -Filter $pattern |
      Sort-Object Name) {
      $sourceStream = [System.IO.File]::OpenRead($source.FullName)
      try {
        $sourceStream.CopyTo($targetStream)
      } finally {
        $sourceStream.Dispose()
      }
    }
  } finally {
    $targetStream.Dispose()
  }
}

[pscustomobject]@{
  state = "complete"
  total_documents = $total
  completed_documents = $total
  completed_batches = $batchCount
  total_batches = $batchCount
  updated_at = (Get-Date).ToString("o")
} | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding utf8

"Full parse complete: $total documents" | Tee-Object -FilePath $logPath -Append
