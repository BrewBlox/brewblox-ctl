"""
Const values
"""
import sys

PY = sys.executable
ARGS = sys.argv
CLI = f'{PY} -m brewblox_ctl'
HOST = 'https://localhost'

CFG_VERSION_KEY = 'BREWBLOX_CFG_VERSION'
LIB_RELEASE_KEY = 'BREWBLOX_CTL_LIB_RELEASE'
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
LOG_COMPOSE = 'COMPOSE'.ljust(10)
LOG_INFO = 'INFO'.ljust(10)
LOG_WARN = 'WARN'.ljust(10)
LOG_ERR = 'ERROR'.ljust(10)

DATA_DIR = './brewblox_ctl_lib/data'
CONFIG_DIR = f'{DATA_DIR}/config'
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
