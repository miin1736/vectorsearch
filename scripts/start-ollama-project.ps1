. .\scripts\project-env.ps1

Get-Process ollama -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2

$ollama = Get-Command ollama -ErrorAction Stop
$process = Start-Process `
  -FilePath $ollama.Source `
  -ArgumentList "serve" `
  -WindowStyle Hidden `
  -PassThru

Write-Host "Started Ollama server with project model directory."
Write-Host "PID=$($process.Id)"
Write-Host "OLLAMA_MODELS=$env:OLLAMA_MODELS"
