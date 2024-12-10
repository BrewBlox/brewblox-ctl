#!/usr/bin/env bash
set -euo pipefail

# tput is used to color shell messages
# Not all systems have it, and if they don't, we can safely noop it
type tput >/dev/null 2>&1 || alias tput=:

log_info() {
    echo "$(tput setaf 6)INFO       $1 $(tput sgr0)"
}

log_warn() {
    echo "$(tput setaf 3)WARN       $1 $(tput sgr0)"
}

log_error() {
    echo "$(tput setaf 1)ERROR      $1 $(tput sgr0)"
}

flush_stdin() {
    while read -ret 0.1; do :; done
}

# Args:
# - checked command
command_exists() {
    command -v "$@" >/dev/null 2>&1
}

# Args:
# - target directory
is_brewblox_dir() {
    [[ -f "$1/.env" ]] && grep -q "BREWBLOX_RELEASE" "$1/.env"
    return
}

install() {
    # We should not be creating config files with root permissions
    if [[ $EUID -eq 0 ]]; then
        log_error "This script must not be run as root, or using sudo."
        exit 1
    fi

    # Use BREWBLOX_DIR from env if set, otherwise find out
    if [ -z "${BREWBLOX_DIR:-}" ]; then
        if is_brewblox_dir "${PWD}"; then
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
    if [ -z "${BREWBLOX_RELEASE:-}" ]; then
        if is_brewblox_dir "${BREWBLOX_DIR}"; then
            BREWBLOX_RELEASE=$(grep BREWBLOX_RELEASE "${BREWBLOX_DIR}/.env" | cut -d '=' -f2)
        else
            BREWBLOX_RELEASE="edge"
        fi
    fi

    # Install system packages

    log_info "Installing uv"
    wget -qO- https://astral.sh/uv/install.sh | sh

    log_info "Brewblox dir is \"${BREWBLOX_DIR}\""
    log_info "Brewblox release is \"${BREWBLOX_RELEASE}\""

    # Check if dir exists, but is not a brewblox dir, and is not empty
    if [[ -d "${BREWBLOX_DIR}" ]] &&
        ! is_brewblox_dir "${BREWBLOX_DIR}" &&
        [ -n "$(ls -A "${BREWBLOX_DIR:?}")" ]; then
        log_warn "${BREWBLOX_DIR} already exists, but is not a Brewblox directory."
        flush_stdin
        read -rp "Remove all files in this directory and continue? (y/N)" response
        if [[ "$response" =~ ^y(es)? ]]; then
            rm -rf "${BREWBLOX_DIR:?}/*"
        else
            exit 1
        fi
    fi

    # Ensure that the Brewblox dir is cwd
    if [[ ${BREWBLOX_DIR} != "${PWD}" ]]; then
        mkdir -p "${BREWBLOX_DIR}"
        pushd "${BREWBLOX_DIR}" >/dev/null
    fi

    log_info "Creating Python virtual env..."
    uv venv

    # Install packages into the virtual env
    log_info "Installing Python packages..."
    uv pip install "git+https://github.com/brewblox/brewblox-ctl@${BREWBLOX_RELEASE}"

    # Init the config file
    echo "release: ${BREWBLOX_RELEASE}" >./brewblox.yml

    exec python3 -m brewblox_ctl install
}

# Protect against incomplete file downloads
install
