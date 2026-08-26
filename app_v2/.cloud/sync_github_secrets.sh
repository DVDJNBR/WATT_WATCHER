#!/usr/bin/env bash
# sync_github_secrets.sh
# Run after terraform apply to push Function App deploy secrets to GitHub.
# Usage: ./sync_github_secrets.sh [github-repo]
# Example: ./sync_github_secrets.sh DVDJNBR/WATT_WATCHER

set -euo pipefail

REPO="${1:-DVDJNBR/WATT_WATCHER}"

echo "Reading Terraform outputs..."
cd "$(dirname "$0")"

FUNC_APP_NAME=$(terraform output -raw function_app_name)
RG=$(terraform output -raw resource_group_name)

echo "Fetching publish profile for $FUNC_APP_NAME..."
PUBLISH_PROFILE=$(az functionapp deployment list-publishing-profiles \
  --name "$FUNC_APP_NAME" \
  --resource-group "$RG" \
  --xml)

echo "Updating GitHub secrets on $REPO..."
gh secret set AZURE_FUNCTIONAPP_NAME            --body "$FUNC_APP_NAME"       --repo "$REPO"
gh secret set AZURE_FUNCTIONAPP_PUBLISH_PROFILE --body "$PUBLISH_PROFILE"     --repo "$REPO"

echo ""
echo "Done. Secrets updated:"
echo "  AZURE_FUNCTIONAPP_NAME            = $FUNC_APP_NAME"
echo "  AZURE_FUNCTIONAPP_PUBLISH_PROFILE = (hidden)"
echo ""
echo "VPS deploy secrets (VPS_HOST, VPS_SSH_KEY, ...) are not managed by Terraform —"
echo "set them manually in GitHub repo settings."
