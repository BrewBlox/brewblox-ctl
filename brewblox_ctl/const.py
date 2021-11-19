"""
Const values
"""
import pathlib
import sys

ARGS = sys.argv
CLI = 'python3 -m brewblox_ctl'
HOST = 'https://localhost'

DOCKER = 'docker'
COMPOSE = '.venv/bin/docker-compose'

CFG_VERSION_KEY = 'BREWBLOX_CFG_VERSION'
CTL_RELEASE_KEY = 'BREWBLOX_CTL_RELEASE'
RELEASE_KEY = 'BREWBLOX_RELEASE'
SKIP_CONFIRM_KEY = 'BREWBLOX_SKIP_CONFIRM'
DEBUG_KEY = 'BREWBLOX_DEBUG'
HTTP_PORT_KEY = 'BREWBLOX_PORT_HTTP'
HTTPS_PORT_KEY = 'BREWBLOX_PORT_HTTPS'
MQTT_PORT_KEY = 'BREWBLOX_PORT_MQTT'
COMPOSE_FILES_KEY = 'COMPOSE_FILE'
COMPOSE_PROJECT_KEY = 'COMPOSE_PROJECT_NAME'

LOG_SHELL = 'SHELL'.ljust(10)
LOG_PYTHON = 'PYTHON'.ljust(10)
LOG_ENV = 'ENV'.ljust(10)
LOG_CONFIG = 'COMPOSE'.ljust(10)
LOG_INFO = 'INFO'.ljust(10)
LOG_WARN = 'WARN'.ljust(10)
LOG_ERR = 'ERROR'.ljust(10)

CTL_DIR = str(pathlib.Path(__file__).parent.resolve())
DEPLOY_DIR = f'{CTL_DIR}/deployed'
CONFIG_DIR = f'{DEPLOY_DIR}/config'
SCRIPT_DIR = f'{DEPLOY_DIR}/scripts'
AVAHI_CONF = '/etc/avahi/avahi-daemon.conf'
UI_DATABASE = 'brewblox-ui-store'

CURRENT_VERSION = '0.7.0'
ENV_DEFAULTS = {
    RELEASE_KEY: 'edge',
    HTTP_PORT_KEY: '80',
    HTTPS_PORT_KEY: '443',
    MQTT_PORT_KEY: '1883',
    COMPOSE_FILES_KEY: 'docker-compose.shared.yml:docker-compose.yml',
    COMPOSE_PROJECT_KEY: 'brewblox',
}
# Also listed in bootstrap-install.sh
APT_DEPENDENCIES = [
    'curl',
    'libssl-dev',
    'libffi-dev',
    'avahi-daemon',
]

VID_PARTICLE = 0x2b04
PID_PHOTON = 0xc006
PID_P1 = 0xc008
VID_ESPRESSIF = 0x10c4
PID_ESP32 = 0xea60
