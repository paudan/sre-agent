#!/usr/bin/env bash
# Script to initialize GitHub Secrets and Variables by reading settings from .env file

set -euo pipefail
env_file=".env"

# 1. Verify Prerequisites
if ! command -v gh &> /dev/null; then
    echo "❌ Error: GitHub CLI ('gh') is not installed. Please install it from https://cli.github.com/"
    exit 1
fi

if ! command -v gcloud &> /dev/null; then
    echo "❌ Error: Google Cloud SDK ('gcloud') is not installed."
    exit 1
fi

# 2. Load .env File
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"
ENV_FILE="${PROJECT_ROOT}/${env_file}"

if [ -f "${ENV_FILE}" ]; then
    echo "📄 Loading environment variables from .env file..."
    set -o allexport
    # shellcheck disable=SC1090
    source <(grep -v '^#' "${ENV_FILE}" | grep -v '^[[:space:]]*$')
    set +o allexport
else
    echo "❌ Error: .env file not found at ${ENV_FILE}"
    exit 1
fi

# 3. Read & Validate Required Variables from .env
PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-}"
PROJECT_NAME="${PROJECT_NAME:-sre-agent}"
# Service account created by deployment/terraform/single-project (also used by GitHub Actions)
APP_SERVICE_ACCOUNT="${APP_SERVICE_ACCOUNT:-${PROJECT_NAME}-app@${PROJECT_ID}.iam.gserviceaccount.com}"

if [ -z "${PROJECT_ID}" ]; then
    echo "❌ Error: GOOGLE_CLOUD_PROJECT is not set in .env file."
    exit 1
fi

# Detect repository owner/name from git remote if REPO not explicitly set
if [ -z "${REPO:-}" ]; then
    GIT_REMOTE_URL=$(git config --get remote.origin.url || true)
    if [[ "${GIT_REMOTE_URL}" =~ github\.com[:/]([^/]+/[^/.]+)(\.git)?$ ]]; then
        REPO="${BASH_REMATCH[1]}"
    else
        echo "❌ Error: Could not auto-detect GitHub repository from git remote. Set REPO=owner/repo environment variable."
        exit 1
    fi
fi

# Workload Identity Federation pool/provider created by single-project/wif.tf
WIF_POOL_ID="${WIF_POOL_ID:-${PROJECT_NAME}-pool}"
WIF_PROVIDER_ID="${WIF_PROVIDER_ID:-${PROJECT_NAME}-oidc}"
REGION="${REGION:-us-east1}"
LOGS_BUCKET_NAME="${PROJECT_ID}-${PROJECT_NAME}-logs"

echo "🔍 Fetching GCP Project Number for '${PROJECT_ID}'..."
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format="value(projectNumber)")

if [ -z "${PROJECT_NUMBER}" ]; then
    echo "❌ Error: Could not determine Project Number for project '${PROJECT_ID}'."
    exit 1
fi

# 4. Set GitHub Secrets (everything but the non-sensitive model switch, since this is a public demo)
echo "🔑 Setting Secrets..."
gh secret set WIF_POOL_ID                    --repo "${REPO}" --body "${WIF_POOL_ID}"
gh secret set WIF_PROVIDER_ID                --repo "${REPO}" --body "${WIF_PROVIDER_ID}"
gh secret set GOOGLE_CLOUD_PROJECT           --repo "${REPO}" --body "${PROJECT_ID}"
gh secret set GCP_PROJECT_NUMBER             --repo "${REPO}" --body "${PROJECT_NUMBER}"
gh secret set REGION                         --repo "${REPO}" --body "${REGION}"
gh secret set APP_SERVICE_ACCOUNT            --repo "${REPO}" --body "${APP_SERVICE_ACCOUNT}"
gh secret set LOGS_BUCKET_NAME               --repo "${REPO}" --body "${LOGS_BUCKET_NAME}"

# 5. Set GitHub Variables (only non-sensitive settings)
echo "📊 Setting Variables..."
gh variable set GOOGLE_GENAI_USE_ENTERPRISE  --repo "${REPO}" --body "${GOOGLE_GENAI_USE_ENTERPRISE:-true}"

echo "--------------------------------------------------------"
echo "✅ All GitHub Secrets and Variables configured successfully for ${REPO}!"
