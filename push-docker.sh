#! /usr/bin/env bash
set -e

# The build script generated :local and :rpi-local tags of images
# This script retags and pushes those images
#
# Argument is the tag name they should be pushed as
# Leave this blank to set it to the git branch name

CLEAN_BRANCH_NAME=$(echo "$(git rev-parse --abbrev-ref HEAD)" | tr '/' '-' | tr '[:upper:]' '[:lower:]');
REPO=brewblox/brewblox-ctl-lib
TAG=${1:-${CLEAN_BRANCH_NAME}}

docker tag ${REPO}:local ${REPO}:${TAG}
docker tag ${REPO}:rpi-local ${REPO}:rpi-${TAG}

docker push ${REPO}:${TAG}
docker push ${REPO}:rpi-${TAG}
