"""
Const values
"""

import sys
from pathlib import Path

ARGS = sys.argv
CLI = 'uv run python3 -m brewblox_ctl'
CURL = "curl -sSk -H 'content-type: application/json'"
CURL_WAIT = f'{CURL} --fail --retry 60 --max-time 5 --retry-all-errors --retry-delay 10 -o /dev/null'

# The configuration version installed by brewblox-ctl
# This is written to .env during updates
CFG_VERSION = '0.11.0'

# Keys to used environment variables
ENV_KEY_CFG_VERSION = 'BREWBLOX_CFG_VERSION'

# Prefixes for log messages
LOG_SHELL = 'SHELL'.ljust(10)
LOG_PYTHON = 'PYTHON'.ljust(10)
LOG_ENV = 'ENV'.ljust(10)
LOG_CONFIG = 'CONFIG'.ljust(10)
LOG_INFO = 'INFO'.ljust(10)
LOG_WARN = 'WARN'.ljust(10)
LOG_ERR = 'ERROR'.ljust(10)

# Static file directories included in the brewblox-ctl package
DIR_CTL_ROOT = Path(__file__).parent.resolve()
DIR_DEPLOYED = DIR_CTL_ROOT / 'deployed'

# File locations
CONFIG_FILE = Path('brewblox.yml').resolve()
PASSWD_FILE = Path('auth/users.passwd').resolve()
COMPOSE_FILE = Path('docker-compose.yml').resolve()
COMPOSE_SHARED_FILE = Path('docker-compose.shared.yml').resolve()

# Apt dependencies required to run brewblox
# This is a duplicate of the list in bootstrap-install.sh
APT_DEPENDENCIES = [
    'curl',
    'libssl-dev',
    'libffi-dev',
    'avahi-daemon',
]

# USB Vendor / Product IDs
VID_PARTICLE = 0x2B04
PID_PHOTON = 0xC006
PID_PHOTON_DFU = 0xD006
PID_P1 = 0xC008
PID_P1_DFU = 0xD008
VID_ESPRESSIF = 0x10C4
PID_ESP32 = 0xEA60
