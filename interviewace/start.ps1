# InterviewAce - Secure Setup & Launch Script
# This script prompts you to enter your API key securely
# and starts the application without ever leaking the key.

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  InterviewAce - Secure Setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Prompt for API key securely
$apiKey = Read-Host -Prompt "Enter your Google AI Studio API Key"

if ([string]::IsNullOrWhiteSpace($apiKey)) {
    Write-Host "ERROR: No API key provided. Exiting." -ForegroundColor Red
    exit 1
}

# Write to both .env files
$envContent = "GOOGLE_API_KEY=$apiKey`nGOOGLE_GENAI_USE_VERTEXAI=FALSE`n"
Set-Content -Path ".\.env" -Value $envContent -NoNewline
Set-Content -Path ".\app\.env" -Value $envContent -NoNewline

Write-Host ""
Write-Host "API key saved to .env and app/.env" -ForegroundColor Green
Write-Host ""

# Set SSL cert for Windows
$env:SSL_CERT_FILE = (python -m certifi)

# Activate venv and start
Write-Host "Starting InterviewAce server..." -ForegroundColor Yellow
Write-Host "Open http://localhost:8080 in your browser" -ForegroundColor Yellow
Write-Host ""

& ".\venv\Scripts\Activate.ps1"
Set-Location -Path ".\app"
python main.py
