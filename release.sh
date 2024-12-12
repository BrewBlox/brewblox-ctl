#! /bin/env bash
set -euo pipefail
pushd "$(dirname "$0")" >/dev/null

# This script is for building manual releases
# Automatic releases are done in github actions

# Args
TAG=${1:-"local"}

if ! command -v az &>/dev/null; then
    echo "ERROR: Azure CLI could not be found. To install: https://docs.microsoft.com/en-us/cli/azure/install-azure-cli-linux?pivots=apt"
    exit 1
fi

# Azure SAS token must have been set to upload to Azure
if [[ -z "${AZURE_STORAGE_SAS_TOKEN:-}" ]]; then
    echo "ERROR: AZURE_STORAGE_SAS_TOKEN variable was not set."
    echo "You can generate a SAS token at https://portal.azure.com -> brewblox -> containers -> firmware -> Shared access tokens"
    exit 1
fi

uv build --sdist

az storage blob upload \
    --account-name brewblox \
    --container-name ctl \
    --name "${TAG}/brewblox-ctl.tar.gz" \
    --file "./dist/brewblox_ctl-1.0.0.tar.gz"
