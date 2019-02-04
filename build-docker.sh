#! /usr/bin/env bash
set -e

cp -rf ./brewblox_ctl_lib ./docker

# recursively clean all pycache/pyc files
find ./docker/brewblox_ctl_lib | grep -E "(__pycache__|\.pyc|\.pyo$)" | xargs rm -rf

docker build --no-cache -f docker/amd/Dockerfile -t brewblox/brewblox-ctl-lib:local docker
docker build --no-cache -f docker/arm/Dockerfile -t brewblox/brewblox-ctl-lib:rpi-local docker
