import json
import re
from tempfile import NamedTemporaryFile

from configobj import ConfigObj

from brewblox_ctl import const, sh, utils


def fix_ipv6(config_file=None, restart=True):
    utils.info('Fixing Docker IPv6 settings...')

    os_version = sh('cat /proc/version', capture=True) or ''
    if re.match(r'.*(Microsoft|WSL)', os_version, flags=re.IGNORECASE):
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


def fix_pip_install():
    """
    Brewblox-ctl is no longer installed using pip.
    Fix this by uninstalling it there.
    """
    pip = f'{const.PY} -m pip'
    if not utils.user_home_exists():
        pip = f'sudo {pip}'
    if 'brewblox-ctl' in sh(f'{pip} list', capture=True):
        sh(f'{pip} uninstall brewblox-ctl')
