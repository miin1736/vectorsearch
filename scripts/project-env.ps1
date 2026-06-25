$env:DATA_ROOT = "C:\vectorsearch-data"
$env:HF_HOME = "C:\vectorsearch-data\models\huggingface"
$env:SENTENCE_TRANSFORMERS_HOME = "C:\vectorsearch-data\models\huggingface\sentence-transformers"
$env:TORCH_HOME = "C:\vectorsearch-data\cache\torch"
$env:OLLAMA_MODELS = "C:\vectorsearch-data\models\ollama"

$ollamaDir = "$env:LOCALAPPDATA\Programs\Ollama"
if (Test-Path "$ollamaDir\ollama.exe") {
  if (($env:PATH -split ';') -notcontains $ollamaDir) {
    $env:PATH = "$ollamaDir;$env:PATH"
  }
}

New-Item -ItemType Directory -Force `
  -Path $env:DATA_ROOT, `
        "$env:DATA_ROOT\raw", `
        "$env:DATA_ROOT\processed", `
        "$env:DATA_ROOT\index", `
        "$env:DATA_ROOT\eval", `
        "$env:DATA_ROOT\reports", `
        $env:HF_HOME, `
        $env:SENTENCE_TRANSFORMERS_HOME, `
        $env:TORCH_HOME, `
        $env:OLLAMA_MODELS | Out-Null

Write-Host "KoreanOps-RAG project environment loaded."
Write-Host "DATA_ROOT=$env:DATA_ROOT"
Write-Host "HF_HOME=$env:HF_HOME"
Write-Host "SENTENCE_TRANSFORMERS_HOME=$env:SENTENCE_TRANSFORMERS_HOME"
Write-Host "TORCH_HOME=$env:TORCH_HOME"
Write-Host "OLLAMA_MODELS=$env:OLLAMA_MODELS"
if (Get-Command ollama -ErrorAction SilentlyContinue) {
  Write-Host "OLLAMA_EXE=$((Get-Command ollama).Source)"
}
