#!/usr/bin/env bash
# sync_github_secrets.sh
# Run after terraform apply to push all infra outputs to GitHub secrets.
# Usage: ./sync_github_secrets.sh [github-repo]
# Example: ./sync_github_secrets.sh DVDJNBR/WATT_WATCHER

set -euo pipefail

REPO="${1:-DVDJNBR/WATT_WATCHER}"

echo "Reading Terraform outputs..."
cd "$(dirname "$0")"

FUNC_APP_NAME=$(terraform output -raw function_app_name)
FUNC_APP_URL=$(terraform output -raw function_app_url)
FRONTEND_STORAGE_NAME=$(terraform output -raw frontend_storage_name)
FRONTEND_STORAGE_KEY=$(terraform output -raw frontend_storage_key)
RG=$(terraform output -raw resource_group_name)

echo "Fetching publish profile for $FUNC_APP_NAME..."
PUBLISH_PROFILE=$(az functionapp deployment list-publishing-profiles \
  --name "$FUNC_APP_NAME" \
  --resource-group "$RG" \
  --xml)

echo "Fetching API key from Key Vault..."
KV_NAME=$(terraform output -raw key_vault_name 2>/dev/null || echo "watt-watcher-key-vault")
VITE_API_KEY=$(az keyvault secret show \
  --vault-name "$KV_NAME" \
  --name "API-KEY" \
  --query "value" -o tsv 2>/dev/null || echo "")

echo "Updating GitHub secrets on $REPO..."
gh secret set AZURE_FUNCTIONAPP_NAME    --body "$FUNC_APP_NAME"       --repo "$REPO"
gh secret set AZURE_FUNCTIONS_URL       --body "$FUNC_APP_URL"        --repo "$REPO"
gh secret set AZURE_FRONTEND_STORAGE_NAME --body "$FRONTEND_STORAGE_NAME" --repo "$REPO"
gh secret set AZURE_FRONTEND_STORAGE_KEY  --body "$FRONTEND_STORAGE_KEY"  --repo "$REPO"
gh secret set AZURE_FUNCTIONAPP_PUBLISH_PROFILE --body "$PUBLISH_PROFILE" --repo "$REPO"
if [ -n "$VITE_API_KEY" ]; then
  gh secret set VITE_API_KEY --body "$VITE_API_KEY" --repo "$REPO"
else
  echo "Warning: could not read API-KEY from Key Vault — set VITE_API_KEY manually"
fi

echo ""
echo "Done. Secrets updated:"
echo "  AZURE_FUNCTIONAPP_NAME          = $FUNC_APP_NAME"
echo "  AZURE_FUNCTIONS_URL             = $FUNC_APP_URL"
echo "  AZURE_FRONTEND_STORAGE_NAME     = $FRONTEND_STORAGE_NAME"
echo "  AZURE_FRONTEND_STORAGE_KEY      = (hidden)"
echo "  AZURE_FUNCTIONAPP_PUBLISH_PROFILE = (hidden)"
echo "  VITE_API_KEY                    = (hidden)"
