"""
Shared functionality
"""

import json
import re
from pathlib import Path
from tempfile import NamedTemporaryFile

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
        f' brewblox/omgwtfssl:{tag}')
    sh(f'sudo chmod 644 "{absdir}/brewblox.crt"')
    sh(f'sudo chmod 600 "{absdir}/brewblox.key"')


def update_system_packages():
    if utils.command_exists('apt'):
        utils.info('Updating apt packages...')
        sh('sudo apt update && sudo apt upgrade -y')


def add_particle_udev_rules():
    rules_dir = '/etc/udev/rules.d'
    target = f'{rules_dir}/50-particle.rules'
    if not utils.path_exists(target) and utils.command_exists('udevadm'):
        utils.info('Adding udev rules for Particle devices...')
        sh(f'sudo mkdir -p {rules_dir}')
        sh(f'sudo cp {const.CONFIG_DIR}/50-particle.rules {target}')
        sh('sudo udevadm control --reload-rules && sudo udevadm trigger')


def install_ctl_package(download: str = 'always'):  # always | missing | never
    exists = utils.path_exists('./brewblox-ctl.tar.gz')
    release = utils.getenv(const.CTL_RELEASE_KEY) or utils.getenv(const.RELEASE_KEY)
    if download == 'always' or download == 'missing' and not exists:
        sh(f'wget -q -O ./brewblox-ctl.tar.gz https://brewblox.blob.core.windows.net/ctl/{release}/brewblox-ctl.tar.gz')
    sh(f'{const.PY} -m pip install --quiet ./brewblox-ctl.tar.gz')


def uninstall_old_ctl_package():
    sh('rm -rf ./brewblox_ctl_lib/', check=False)
    sh('rm -rf $(python3 -m site --user-site)/brewblox_ctl*', check=False)


def deploy_ctl_wrapper():
    sh(f'chmod +x {const.SCRIPT_DIR}/brewblox-ctl')
    if utils.user_home_exists():
        sh(f'mkdir -p $HOME/.local/bin && cp {const.SCRIPT_DIR}/brewblox-ctl $HOME/.local/bin/')
    else:
        sh(f'sudo cp {const.SCRIPT_DIR}/brewblox-ctl /usr/local/bin/')


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

    utils.info(f'Using Docker config file {config_file}')

    # Read config. Create file if not exists
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


def unset_avahi_reflection():
    conf = const.AVAHI_CONF

    try:
        config = ConfigObj(conf, file_error=True)
    except OSError:
        utils.warn(f'Avahi config file not found: {conf}')
        return

    try:
        del config['reflector']['enable-reflector']
        utils.show_data(config.dict())
    except KeyError:
        return  # nothing to change

    with NamedTemporaryFile('w') as tmp:
        config.filename = None
        lines = config.write()
        # avahi-daemon.conf requires a 'key=value' syntax
        tmp.write('\n'.join(lines).replace(' = ', '=') + '\n')
        tmp.flush()
        sh(f'sudo chmod --reference={conf} {tmp.name}')
        sh(f'sudo cp -fp {tmp.name} {conf}')

    if utils.command_exists('service'):
        utils.info('Restarting avahi-daemon service...')
        sh('sudo service avahi-daemon restart')
    else:
        utils.warn('"service" command not found. Please restart your machine to enable Wifi discovery.')
