"""
Shared functionality
"""

import re
from pathlib import Path

from brewblox_ctl import const, sh, utils


def makecert(dir, release: str = None):
    absdir = Path(dir).resolve()
    sudo = utils.optsudo()
    tag = utils.docker_tag(release)
    sh(f'mkdir -p "{absdir}"')
    sh(f'{sudo}docker run' +
        ' --rm --privileged' +
        ' --pull always' +
        f' -v "{absdir}":/certs/' +
        f' brewblox/omgwtfssl:{tag}')
    sh(f'sudo chmod 644 "{absdir}/brewblox.crt"')
    sh(f'sudo chmod 600 "{absdir}/brewblox.key"')


def update_system_packages():
    if utils.command_exists('apt'):
        utils.info('Updating apt packages...')
        sh('sudo apt -qq update && sudo apt -qq upgrade -y')


def add_particle_udev_rules():
    rules_dir = '/etc/udev/rules.d'
    target = f'{rules_dir}/50-particle.rules'
    if not utils.path_exists(target) and utils.command_exists('udevadm'):
        utils.info('Adding udev rules for Particle devices...')
        sh(f'sudo mkdir -p {rules_dir}')
        sh(f'sudo cp {const.CONFIG_DIR}/50-particle.rules {target}')
        sh('sudo udevadm control --reload-rules && sudo udevadm trigger')


def download_ctl():
    release = utils.getenv(const.CTL_RELEASE_KEY) or utils.getenv(const.RELEASE_KEY)
    sh(f'wget -q -O ./brewblox-ctl.tar.gz https://brewblox.blob.core.windows.net/ctl/{release}/brewblox-ctl.tar.gz')
    sh(f'{const.PY} -m pip install --quiet --upgrade --upgrade-strategy eager --target ./lib ./brewblox-ctl.tar.gz')
    if utils.user_home_exists():
        sh('mkdir -p $HOME/.local/bin')
        sh(f'cp {const.SCRIPT_DIR}/brewblox-ctl $HOME/.local/bin/')
        sh('chmod +x $HOME/.local/bin/brewblox-ctl')
    else:
        sh(f'sudo cp {const.SCRIPT_DIR}/brewblox-ctl /usr/local/bin/')
        sh('sudo chmod 777 /usr/local/bin/brewblox-ctl')


def check_ports():
    if utils.path_exists('./docker-compose.yml'):
        utils.info('Stopping services...')
        sh(f'{utils.optsudo()}docker-compose down')

    ports = [
        utils.getenv(key, const.ENV_DEFAULTS[key]) for key in [
            const.HTTP_PORT_KEY,
            const.HTTPS_PORT_KEY,
            const.MQTT_PORT_KEY,
        ]]

    retv = sh('sudo netstat -tulpn', capture=True)
    lines = retv.split('\n')

    used_ports = []
    used_lines = []
    for port in ports:
        for line in lines:
            if re.match(r'.*(:::|0.0.0.0:){}\s.*'.format(port), line):
                used_ports.append(port)
                used_lines.append(line)
                break

    if used_ports:
        port_str = ', '.join(used_ports)
        utils.warn(f'Port(s) {port_str} already in use.')
        utils.warn('Run `brewblox-ctl service ports` to configure Brewblox ports.')
        for line in used_lines:
            utils.warn(line)
        if not utils.confirm('Do you want to continue?'):
            raise SystemExit(1)
