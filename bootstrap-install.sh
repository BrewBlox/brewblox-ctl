#!/usr/bin/env bash
set -euo pipefail

if [[ $EUID -eq 0 ]]; then
   echo "ERROR: This script must not be run as root, or using sudo."
   exit 1
fi

# Args:
# - checked command
command_exists() {
    command -v "$@" > /dev/null 2>&1
}

# Args:
# - target directory
is_brewblox_dir() {
    [[ -f "$1/.env" ]] && grep -q "BREWBLOX_RELEASE" "$1/.env"
    return
}

check_ssh_config() {
    # Check if we have to fix accepted LC/Lang settings.
    # If we don't do this, the system will complain if it's being sent a non-supported locale
    if [ -f /etc/ssh/sshd_config ] && grep -q '^AcceptEnv LANG LC' /etc/ssh/sshd_config
    then
        sudo sed -i 's/^AcceptEnv LANG LC/# AcceptEnv LANG LC/g' /etc/ssh/sshd_config
        sudo systemctl restart ssh
    fi
}

install() {
    # Use BREWBLOX_DIR from env if set, otherwise find out
    if [ -z "${BREWBLOX_DIR:-}" ]
    then
        if is_brewblox_dir "${PWD}"
        then
            BREWBLOX_DIR="${PWD}"
        else
            BREWBLOX_DIR="${PWD}/brewblox"
        fi
    fi

    # Determine BREWBLOX_RELEASE
    # Priority is given to:
    # - Environment variable
    # - Value for previous install
    # - Default
    if [ -z "${BREWBLOX_RELEASE:-}" ]
    then
        if is_brewblox_dir "${BREWBLOX_DIR}"
        then
            BREWBLOX_RELEASE=$(read_var BREWBLOX_RELEASE "${BREWBLOX_DIR}/.env")
        else
            BREWBLOX_RELEASE="edge"
        fi
    fi

    # Install system packages
    if command_exists "apt"
    then
        echo "INFO: Installing Apt packages..."
        sudo apt update
        sudo apt upgrade -y
        sudo apt install -y python3-pip python3-venv
    fi

    if ! command_exists python3
    then
        echo "ERROR: Python3 not found."
        echo "ERROR: You will need to install Python >=3.6 manually."
        exit 1
    fi

    echo "INFO: Brewblox dir is \"${BREWBLOX_DIR}\""
    echo "INFO: Brewblox release is \"${BREWBLOX_RELEASE}\""

    # Check if dir exists, but is not a brewblox dir, and is not empty
    if [[ -d "${BREWBLOX_DIR}" ]] \
        && ! is_brewblox_dir "${BREWBLOX_DIR}" \
        && [ -n "$(ls -A "${BREWBLOX_DIR:?}")" ]
    then
        echo "WARN: ${BREWBLOX_DIR} already exists, but is not a Brewblox directory."
        read -rp "Remove all files in this directory and continue? (y/N)" response
        if [[ "$response" =~ ^y(es)? ]]
        then
            rm -rf "${BREWBLOX_DIR:?}/*"
        else
            exit 1
        fi
    fi

    # Ensure that the Brewblox dir is cwd
    if [[ ${BREWBLOX_DIR} != "${PWD}" ]]
    then
        mkdir -p "${BREWBLOX_DIR}"
        pushd "${BREWBLOX_DIR}" > /dev/null
    fi

    # Create virtual env
    echo "INFO: Creating Python virtual env..."
    python3 -m venv .venv

    # Download the sdist tarball
    echo "INFO: Downloading brewblox-ctl..."
    wget -q \
        -O ./brewblox-ctl.tar.gz \
        "https://brewblox.blob.core.windows.net/ctl/${BREWBLOX_RELEASE}/brewblox-ctl.tar.gz"

    # Activate virtual env
    # shellcheck source=/dev/null
    source .venv/bin/activate

    # Install packages into the virtual env
    echo "INFO: Installing Python packages..."
    python3 -m pip install pip setuptools wheel
    python3 -m pip install ./brewblox-ctl.tar.gz

    # Init the .env file
    echo "BREWBLOX_RELEASE=${BREWBLOX_RELEASE}" > .env

    python3 -m brewblox_ctl install
}

# Protect against incomplete file downloads
install
