# Task 3.1 Setup and Test Script
# UIC Editorial Assistant - Bedrock Configuration

Write-Host "`n============================================================" -ForegroundColor Cyan
Write-Host "UIC Editorial Assistant - Task 3.1: Bedrock Setup" -ForegroundColor Cyan
Write-Host "============================================================`n" -ForegroundColor Cyan

# Step 1: Check Python
Write-Host "[1/4] Checking Python installation..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✓ Python found: $pythonVersion" -ForegroundColor Green
    } else {
        throw "Python not found"
    }
} catch {
    Write-Host "  ✗ Python not installed" -ForegroundColor Red
    Write-Host "`nPlease install Python 3.8+ from: https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "Make sure to check 'Add Python to PATH' during installation`n" -ForegroundColor Yellow
    exit 1
}

# Step 2: Install dependencies
Write-Host "`n[2/4] Installing Python dependencies..." -ForegroundColor Yellow
try {
    python -m pip install -q boto3
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✓ boto3 installed successfully" -ForegroundColor Green
    } else {
        throw "Failed to install boto3"
    }
} catch {
    Write-Host "  ✗ Failed to install dependencies" -ForegroundColor Red
    Write-Host "`nTry manually: python -m pip install boto3`n" -ForegroundColor Yellow
    exit 1
}

# Step 3: Validate AWS credentials
Write-Host "`n[3/4] Validating AWS credentials..." -ForegroundColor Yellow
if (-not $Env:AWS_DEFAULT_REGION) {
    $Env:AWS_DEFAULT_REGION = "us-east-1"
}

$requiredCredentialNames = @(
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN"
)
$missingCredentialNames = @(
    $requiredCredentialNames | Where-Object {
        -not [Environment]::GetEnvironmentVariable($_)
    }
)

if ($missingCredentialNames.Count -gt 0) {
    Write-Host "  AWS credentials are not configured." -ForegroundColor Red
    Write-Host "  Set the workshop credentials in your environment before running this script." -ForegroundColor Yellow
    Write-Host "  Missing: $($missingCredentialNames -join ', ')" -ForegroundColor Yellow
    exit 1
}

Write-Host "  AWS credentials found in the environment" -ForegroundColor Green
Write-Host "  Region: $($Env:AWS_DEFAULT_REGION)" -ForegroundColor Gray# Step 4: Run Bedrock connection test
Write-Host "`n[4/4] Running Bedrock connection test..." -ForegroundColor Yellow
Write-Host "============================================================`n" -ForegroundColor Cyan

python backend/test_bedrock_setup.py

Write-Host "`n============================================================" -ForegroundColor Cyan
Write-Host "Setup script complete!" -ForegroundColor Cyan
Write-Host "============================================================`n" -ForegroundColor Cyan

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Task 3.1 is COMPLETE!" -ForegroundColor Green
    Write-Host "`nNext steps:" -ForegroundColor Yellow
    Write-Host "  - Task 3.2: Prompt Engineering" -ForegroundColor Gray
    Write-Host "  - Task 3.3: LLM Service Implementation" -ForegroundColor Gray
} else {
    Write-Host "⚠ Some tests failed - review the output above" -ForegroundColor Yellow
    Write-Host "`nIf you see 'AccessDeniedException':" -ForegroundColor Yellow
    Write-Host "  1. Go to AWS Console > Bedrock > Model access" -ForegroundColor Gray
    Write-Host "  2. Request access for Claude Haiku and Sonnet" -ForegroundColor Gray
    Write-Host "  3. Re-run this script" -ForegroundColor Gray
}
