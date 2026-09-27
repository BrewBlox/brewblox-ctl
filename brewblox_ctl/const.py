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
CFG_VERSION = '0.12.0'

# Docker before 20.10.10 blocks the clone3 system call instead of reporting it as unsupported.
# The glibc in Brewblox images uses clone3 to start threads, so services fail on older versions.
MIN_DOCKER_VERSION = '20.10.10'

# The configuration version that splits history into a long-term and a dense database
HISTORY_DENSE_VERSION = '0.12.0'

# History database images. The legacy database stays on the version that wrote it:
# from v1.133 on, Victoria Metrics migrates the index of older data, which older versions cannot read.
VICTORIA_IMAGE = 'victoriametrics/victoria-metrics:v1.152.0'
VICTORIA_LEGACY_IMAGE = 'victoriametrics/victoria-metrics:v1.129.1'

# History database directories
VICTORIA_DIR = './victoria'
VICTORIA_DENSE_DIR = './victoria-dense'
# The database from before configuration version 0.12.0, kept apart until its history is migrated
VICTORIA_LEGACY_DIR = './victoria-legacy'
# The legacy database as the history service reaches it on the Docker network
VICTORIA_LEGACY_URL = 'http://victoria-legacy:8428/victoria-legacy'
# The history migration's state in the datastore
MIGRATION_NAMESPACE = 'brewblox-history'
MIGRATION_ID = 'migration'

# Keys to used environment variables
ENV_KEY_CFG_VERSION = 'BREWBLOX_CFG_VERSION'

# Prefixes for log messages
LOG_SHELL = 'SHELL'.ljust(10)
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
    'python3-dev',
    'avahi-daemon',
    'git',
]

# USB Vendor / Product IDs
VID_PARTICLE = 0x2B04
PID_PHOTON = 0xC006
PID_PHOTON_DFU = 0xD006
PID_P1 = 0xC008
PID_P1_DFU = 0xD008
VID_ESPRESSIF = 0x10C4
PID_ESP32 = 0xEA60
VID_ESPRESSIF_NATIVE = 0x303A
PID_ESP32_S3 = 0x1001
