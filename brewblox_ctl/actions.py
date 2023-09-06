"""
Shared functionality
"""

import json
import re
from copy import deepcopy
from pathlib import Path
from tempfile import NamedTemporaryFile

import psutil
from configobj import ConfigObj

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
        f' ghcr.io/brewblox/omgwtfssl:{tag}')
    sh(f'sudo chmod 644 "{absdir}/brewblox.crt"')
    sh(f'sudo chmod 600 "{absdir}/brewblox.key"')


def update_system_packages():
    if utils.command_exists('apt-get'):
        utils.info('Updating apt packages...')
        sh('sudo apt-get update && sudo apt-get upgrade -y')


def add_particle_udev_rules():
    rules_dir = '/etc/udev/rules.d'
    target = f'{rules_dir}/50-particle.rules'
    if not utils.path_exists(target) and utils.command_exists('udevadm'):
        utils.info('Adding udev rules for Particle devices...')
        sh(f'sudo mkdir -p {rules_dir}')
        sh(f'sudo cp {const.DIR_DEPLOYED_CONFIG}/50-particle.rules {target}')
        sh('sudo udevadm control --reload-rules && sudo udevadm trigger')


def install_ctl_package(download: str = 'always'):  # always | missing | never
    exists = utils.path_exists('./brewblox-ctl.tar.gz')
    release = utils.getenv(const.ENV_KEY_CTL_RELEASE) or utils.getenv(const.ENV_KEY_RELEASE)
    if download == 'always' or download == 'missing' and not exists:
        sh(f'wget -q -O ./brewblox-ctl.tar.gz https://brewblox.blob.core.windows.net/ctl/{release}/brewblox-ctl.tar.gz')
    sh('python3 -m pip install --prefer-binary ./brewblox-ctl.tar.gz')


def uninstall_old_ctl_package():
    sh('rm -rf ./brewblox_ctl_lib/', check=False)
    sh('rm -rf $(python3 -m site --user-site)/brewblox_ctl*', check=False)


def deploy_ctl_wrapper():
    sh(f'chmod +x "{const.DIR_DEPLOYED_SCRIPTS}/brewblox-ctl"')
    if utils.user_home_exists():
        sh(f'mkdir -p "$HOME/.local/bin" && cp "{const.DIR_DEPLOYED_SCRIPTS}/brewblox-ctl" "$HOME/.local/bin/"')
    else:
        sh(f'sudo cp "{const.DIR_DEPLOYED_SCRIPTS}/brewblox-ctl" /usr/local/bin/')


def check_compose_plugin():
    if utils.check_ok(f'{utils.optsudo()}docker compose version'):
        return
    if utils.command_exists('apt-get'):
        utils.info('Installing Docker Compose plugin...')
        sh('sudo apt-get update && sudo apt-get install -y docker-compose-plugin')
    else:
        utils.warn('The Docker Compose plugin is not installed, and apt is not available.')
        utils.warn('You need to install the Docker Compose plugin manually.')
        utils.warn('')
        utils.warn('    https://docs.docker.com/compose/install/linux/')
        utils.warn('')
        raise SystemExit(1)


def check_ports():
    if utils.path_exists('./docker-compose.yml'):
        utils.info('Stopping services...')
        sh(f'{utils.optsudo()}docker compose down')

    ports = [
        int(utils.getenv(const.ENV_KEY_PORT_HTTP, const.DEFAULT_PORT_HTTP)),
        int(utils.getenv(const.ENV_KEY_PORT_HTTPS, const.DEFAULT_PORT_HTTPS)),
        int(utils.getenv(const.ENV_KEY_PORT_MQTT, const.DEFAULT_PORT_MQTT)),
        int(utils.getenv(const.ENV_KEY_PORT_MQTTS, const.DEFAULT_PORT_MQTTS)),
        int(utils.getenv(const.ENV_KEY_PORT_ADMIN, const.DEFAULT_PORT_ADMIN)),
    ]

    try:
        port_connnections = [
            conn
            for conn in psutil.net_connections()
            if conn.laddr.ip in ['::', '0.0.0.0']
            and conn.laddr.port in ports
        ]
    except psutil.AccessDenied:
        utils.warn('Unable to read network connections. You need to run `netstat` or `lsof` manually.')
        port_connnections = []

    if port_connnections:
        port_str = ', '.join(set(str(conn.laddr.port) for conn in port_connnections))
        utils.warn(f'Port(s) {port_str} already in use.')
        utils.warn('Run `brewblox-ctl service ports` to configure Brewblox ports.')
        if not utils.confirm('Do you want to continue?'):
            raise SystemExit(1)


def fix_ipv6(config_file=None, restart=True):
    utils.info('Fixing Docker IPv6 settings...')

    if utils.is_wsl():
        utils.info('WSL environment detected. Skipping IPv6 config changes.')
        return

    # Config is either provided, or parsed from active daemon process
    if not config_file:
        default_config_file = '/etc/docker/daemon.json'
        dockerd_proc = sh('ps aux | grep dockerd', capture=True)
        proc_match = re.match(r'.*--config-file[\s=](?P<file>.*\.json).*', dockerd_proc, flags=re.MULTILINE)
        config_file = proc_match and proc_match.group('file') or default_config_file

    config_file = Path(config_file)
    utils.info(f'Using Docker config file {config_file}')

    # Read config. Create file if not exists
    sh(f"sudo mkdir -p '{config_file.parent}'")
    sh(f"sudo touch '{config_file}'")
    config = sh(f"sudo cat '{config_file}'", capture=True)

    if 'fixed-cidr-v6' in config:
        utils.info('IPv6 settings are already present. Making no changes.')
        return

    # Edit and write. Do not overwrite existing values
    config = json.loads(config or '{}')
    config.setdefault('ipv6', False)
    config.setdefault('fixed-cidr-v6', '2001:db8:1::/64')
    config_str = json.dumps(config, indent=2)
    sh(f"echo '{config_str}' | sudo tee '{config_file}' > /dev/null")

    # Restart daemon
    if restart:
        if utils.command_exists('service'):
            utils.info('Restarting Docker service...')
            sh('sudo service docker restart')
        else:
            utils.warn('"service" command not found. Please restart your machine to apply config changes.')


def edit_avahi_config():
    conf = Path('/etc/avahi/avahi-daemon.conf')

    if not conf.exists():
        return

    config = ConfigObj(str(conf), file_error=True)
    copy = deepcopy(config)
    config.setdefault('server', {}).setdefault('use-ipv6', 'no')
    config.setdefault('publish', {}).setdefault('publish-aaaa-on-ipv4', 'no')
    config.setdefault('reflector', {}).setdefault('enable-reflector', 'yes')

    if config == copy:
        return

    utils.show_data(conf, config.dict())

    with NamedTemporaryFile('w') as tmp:
        config.filename = None
        lines = config.write()
        # avahi-daemon.conf requires a 'key=value' syntax
        tmp.write('\n'.join(lines).replace(' = ', '=') + '\n')
        tmp.flush()
        sh(f'sudo chmod --reference={conf} {tmp.name}')
        sh(f'sudo cp -fp {tmp.name} {conf}')

    if utils.command_exists('systemctl'):
        utils.info('Restarting avahi-daemon service...')
        sh('sudo systemctl restart avahi-daemon')
    else:
        utils.warn('"systemctl" command not found. Please restart your machine to enable Wifi discovery.')


def disable_ssh_accept_env():
    """Disable the 'AcceptEnv LANG LC_*' setting in sshd_config

    This setting is default on the Raspberry Pi,
    but leads to locale errors when an unsupported LANG is sent.

    Given that the Pi by default only includes the en_GB locale,
    the chances of being sent a unsupported locale are very real.
    """
    file = Path('/etc/ssh/sshd_config')
    if not file.exists():
        return

    content = file.read_text()
    updated = re.sub(r'^AcceptEnv LANG LC',
                     '#AcceptEnv LANG LC',
                     content,
                     flags=re.MULTILINE)

    if content == updated:
        return

    with NamedTemporaryFile('w') as tmp:
        tmp.write(updated)
        tmp.flush()
        utils.info('Updating SSHD config to disable AcceptEnv...')
        utils.show_data('/etc/ssh/sshd_config', updated)
        sh(f'sudo chmod --reference={file} {tmp.name}')
        sh(f'sudo cp -fp {tmp.name} {file}')

    if utils.command_exists('systemctl'):
        utils.info('Restarting SSH service...')
        sh('sudo systemctl restart ssh')
