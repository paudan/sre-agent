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
SERVICE_ACCOUNT="${GCP_SERVICE_ACCOUNT:-}"

if [ -z "${PROJECT_ID}" ]; then
    echo "❌ Error: GOOGLE_CLOUD_PROJECT is not set in .env file."
    exit 1
fi

if [ -z "${SERVICE_ACCOUNT}" ]; then
    echo "❌ Error: GCP_SERVICE_ACCOUNT is not set in .env file."
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

WIF_POOL_ID="${WIF_POOL_ID:-github-actions-pool}"
WIF_PROVIDER_ID="${WIF_PROVIDER_ID:-github-provider}"
REGION="${REGION:-us-east1}"
PROJECT_NAME="${PROJECT_NAME:-sre-agent}"
LOGS_BUCKET_NAME="${PROJECT_ID}-${PROJECT_NAME}-logs"

echo "🔍 Fetching GCP Project Number for '${PROJECT_ID}'..."
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format="value(projectNumber)")

if [ -z "${PROJECT_NUMBER}" ]; then
    echo "❌ Error: Could not determine Project Number for project '${PROJECT_ID}'."
    exit 1
fi

WIF_PROVIDER_RESOURCE="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${WIF_POOL_ID}/providers/${WIF_PROVIDER_ID}"

# 4. Set GitHub Secrets
echo "🔑 Setting Secrets..."
gh secret set GCP_WORKLOAD_IDENTITY_PROVIDER --repo "${REPO}" --body "${WIF_PROVIDER_RESOURCE}"
gh secret set WORKLOAD_IDENTITY_PROVIDER     --repo "${REPO}" --body "${WIF_PROVIDER_RESOURCE}"
gh secret set WIF_POOL_ID                    --repo "${REPO}" --body "${WIF_POOL_ID}"
gh secret set WIF_PROVIDER_ID                --repo "${REPO}" --body "${WIF_PROVIDER_ID}"
gh secret set GCP_SERVICE_ACCOUNT            --repo "${REPO}" --body "${SERVICE_ACCOUNT}"

# 5. Set GitHub Variables
echo "📊 Setting Variables..."
gh variable set GOOGLE_CLOUD_PROJECT         --repo "${REPO}" --body "${PROJECT_ID}"
gh variable set STAGING_PROJECT_ID           --repo "${REPO}" --body "${PROJECT_ID}"
gh variable set GCP_PROJECT_NUMBER           --repo "${REPO}" --body "${PROJECT_NUMBER}"
gh variable set REGION                       --repo "${REPO}" --body "${REGION}"
gh variable set APP_SERVICE_ACCOUNT_STAGING  --repo "${REPO}" --body "${SERVICE_ACCOUNT}"
gh variable set LOGS_BUCKET_NAME_STAGING     --repo "${REPO}" --body "${LOGS_BUCKET_NAME}"
gh variable set LOGS_BUCKET_NAME             --repo "${REPO}" --body "${LOGS_BUCKET_NAME}"

echo "--------------------------------------------------------"
echo "✅ All GitHub Secrets and Variables configured successfully for ${REPO}!"
