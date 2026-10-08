# PowerShell Script to initialize GitHub Secrets and Variables by reading settings from .env file

$ErrorActionPreference = "Stop"
$EnvFile = ".env"

# 1. Verify Prerequisites
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-Error "❌ GitHub CLI ('gh') is not installed. Please install it from https://cli.github.com/"
}

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    Write-Error "❌ Google Cloud SDK ('gcloud') is not installed."
}

# 2. Load .env File
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectRoot = Split-Path -Parent $ScriptDir
$EnvFile = Join-Path $ProjectRoot ".env"

if (Test-Path $EnvFile) {
    Write-Host "📄 Loading environment variables from .env file..."
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#")) {
            $parts = $line.Split("=", 2)
            if ($parts.Count -eq 2) {
                [System.Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim())
            }
        }
    }
}
else {
    Write-Error "❌ .env file not found at $EnvFile"
}

# 3. Read & Validate Required Variables from .env
$ProjectId = $env:GOOGLE_CLOUD_PROJECT
$ProjectName = if ($env:PROJECT_NAME) { $env:PROJECT_NAME } else { "sre-agent" }
# Service account created by deployment/terraform/single-project (also used by GitHub Actions)
$AppServiceAccount = if ($env:APP_SERVICE_ACCOUNT) { $env:APP_SERVICE_ACCOUNT } else { "$ProjectName-app@$ProjectId.iam.gserviceaccount.com" }

if (-not $ProjectId) {
    Write-Error "❌ GOOGLE_CLOUD_PROJECT is not set in .env file."
}

# Detect repository owner/name from git remote if REPO not explicitly set
$Repo = $env:REPO
if (-not $Repo) {
    $GitRemote = git config --get remote.origin.url
    if ($GitRemote -match "github\.com[:/]([^/]+/[^/.]+)(\.git)?$") {
        $Repo = $Matches[1]
    }
    else {
        Write-Error "❌ Could not auto-detect GitHub repository from git remote. Set REPO=owner/repo environment variable."
    }
}

# Workload Identity Federation pool/provider created by single-project/wif.tf
$WifPoolId = if ($env:WIF_POOL_ID) { $env:WIF_POOL_ID } else { "$ProjectName-pool" }
$WifProviderId = if ($env:WIF_PROVIDER_ID) { $env:WIF_PROVIDER_ID } else { "$ProjectName-oidc" }
$Region = if ($env:REGION) { $env:REGION } else { "us-east1" }
$LogsBucketName = "$ProjectId-$ProjectName-logs"

Write-Host "🔍 Fetching GCP Project Number for '$ProjectId'..."
$ProjectNumber = (gcloud projects describe $ProjectId --format="value(projectNumber)").Trim()

if (-not $ProjectNumber) {
    Write-Error "❌ Could not determine Project Number for project '$ProjectId'."
}

# 4. Set GitHub Secrets
Write-Host "🔑 Setting Secrets..."
gh secret set WIF_POOL_ID                    --repo $Repo --body $WifPoolId
gh secret set WIF_PROVIDER_ID                --repo $Repo --body $WifProviderId
gh secret set GOOGLE_CLOUD_PROJECT           --repo $Repo --body $ProjectId
gh secret set GCP_PROJECT_NUMBER             --repo $Repo --body $ProjectNumber
gh secret set REGION                         --repo $Repo --body $Region
gh secret set APP_SERVICE_ACCOUNT            --repo $Repo --body $AppServiceAccount
gh secret set LOGS_BUCKET_NAME               --repo $Repo --body $LogsBucketName

# 5. Set GitHub Variables (only non-sensitive settings)
Write-Host "📊 Setting Variables..."
$UseEnterprise = if ($env:GOOGLE_GENAI_USE_ENTERPRISE) { $env:GOOGLE_GENAI_USE_ENTERPRISE } else { "true" }
gh variable set GOOGLE_GENAI_USE_ENTERPRISE  --repo $Repo --body $UseEnterprise

Write-Host "--------------------------------------------------------"
Write-Host "✅ All GitHub Secrets and Variables configured successfully for $Repo!"
