"""
Shared functionality
"""

import json
import os
import re
import socket
from contextlib import closing, suppress
from copy import deepcopy
from pathlib import Path
from typing import Iterable

import jinja2
import psutil
from configobj import ConfigObj

from . import const, utils
from .models import CtlConfig

JINJA_ENV = jinja2.Environment(loader=jinja2.PackageLoader('brewblox_ctl'),
                               autoescape=jinja2.select_autoescape())


def make_dotenv(version: str):
    config = utils.get_config()

    utils.info('Generating .env file ...')
    template = JINJA_ENV.get_template('env.j2')
    content = template.render(config=config, version=version)
    utils.write_file('.env', content)


def make_config_dirs():
    utils.info('Checking data directories ...')
    dirs = [
        './traefik',
        './traefik/dynamic',
        './auth',
        './redis',
        './victoria',
        './mosquitto',
        './spark/backup',
    ]
    utils.sh('mkdir -p ' + ' '.join(dirs))


def make_tls_certificates(always: bool = False,
                          custom_domains: Iterable[str] = None,
                          release: str = None):
    absdir = Path('./traefik').resolve()
    sudo = utils.optsudo()
    tag = utils.docker_tag(release)
    hostname = utils.hostname()
    addresses = utils.host_ip_addresses()
    domains = [
        'brew.blox',  # dummy to have predictable output between installs
        hostname,
        hostname + '.local',
        hostname + '.home',
        *(custom_domains or []),
    ]

    create_cert = always or not utils.file_exists(absdir / 'brew.blox/cert.pem')
    create_der = create_cert or not utils.file_exists(absdir / 'minica.der')

    if create_cert:
        utils.info(f'Generating new certificates in {absdir} ...')
        utils.sh(f'mkdir -p "{absdir}"')
        utils.sh(f'sudo rm -rf "{absdir}/brew.blox"')
        utils.sh(' '.join([
            f'{sudo}docker',
            'run',
            '--rm',
            '--pull=always',
            f'--user={os.geteuid()}:{os.getgid()}',
            f'--volume="{absdir}":/cert',
            f'ghcr.io/brewblox/minica:{tag}',
            f'--domains="{",".join(domains)}"',
            f'--ip-addresses={",".join(addresses)}',
        ]))

    if create_der:
        utils.sh(' '.join([
            f'{sudo}docker',
            'run',
            '--rm',
            f'--user={os.geteuid()}:{os.getgid()}',
            f'--volume="{absdir}":/cert',
            'alpine/openssl',
            'x509',
            '-in /cert/minica.pem',
            '-inform PEM',
            '-out /cert/minica.der',
            '-outform DER',
        ]))

    utils.sh(f'chmod +r {absdir}/minica.pem')


def make_traefik_config():
    config = utils.get_config()

    utils.info('Generating static traefik config ...')
    template = JINJA_ENV.get_template('traefik-static.yml.j2')
    content = template.render(config=config)
    utils.write_file('./traefik/traefik.yml', content)

    utils.info('Generating dynamic traefik config ...')
    template = JINJA_ENV.get_template('traefik-dynamic.yml.j2')
    content = template.render(config=config)
    utils.write_file('./traefik/dynamic/brewblox-provider.yml', content)


def make_shared_compose():
    config = utils.get_config()

    utils.info('Generating docker-compose.shared.yml ...')
    template = JINJA_ENV.get_template('docker-compose.shared.yml.j2')
    content = template.render(config=config)
    utils.write_file('./docker-compose.shared.yml', content)


def make_compose():
    utils.info('Generating docker-compose.yml ...')
    try:
        compose = utils.read_compose()
        compose.setdefault('services', {})
    except FileNotFoundError:
        compose = {'services': {}}

    with suppress(KeyError):
        del compose['version']

    utils.write_compose(compose)


def make_udev_rules():
    rules_dir = '/etc/udev/rules.d'
    target = f'{rules_dir}/50-particle.rules'
    if not utils.file_exists(target) and utils.command_exists('udevadm'):
        utils.info('Adding udev rules for Particle devices ...')
        utils.sh(f'sudo mkdir -p {rules_dir}')
        utils.sh(f'sudo cp "{const.DIR_DEPLOYED}/50-particle.rules" {target}')
        utils.sh('sudo udevadm control --reload-rules && sudo udevadm trigger', check=False)


def make_ctl_entrypoint():
    fpath = const.DIR_DEPLOYED / 'brewblox-ctl'
    utils.sh(f'chmod +x "{fpath}"')
    if utils.user_home_exists():
        utils.sh(f'mkdir -p "$HOME/.local/bin" && cp "{fpath}" "$HOME/.local/bin/"')
    else:
        utils.sh(f'sudo cp "{fpath}" /usr/local/bin/')


def make_brewblox_config(config: CtlConfig):
    """
    First-time generation of brewblox.yml.

    This should only be used to create a new file.
    Any roundtrips afterwards will reset user comments.
    """
    data = config.model_dump(mode='json', exclude_defaults=True)
    config_str = utils.dump_yaml(data)

    utils.info('Generating brewblox.yml ...')
    template = JINJA_ENV.get_template('brewblox.yml.j2')
    content = template.render(config_str=config_str)
    utils.write_file(const.CONFIG_FILE, content)

    # Reload local config
    utils.get_config.cache_clear()


def apt_upgrade():
    if utils.command_exists('apt-get'):
        utils.info('Updating apt packages ...')
        utils.sh('sudo apt-get update && sudo apt-get upgrade -y')


def install_ctl_package(download: str = 'always'):  # always | missing | never
    config = utils.get_config()
    exists = utils.file_exists('./brewblox-ctl.tar.gz')
    release = config.ctl_release or config.release
    if download == 'always' or download == 'missing' and not exists:
        url = f'https://brewblox.blob.core.windows.net/ctl/{release}/brewblox-ctl.tar.gz'
        utils.sh(f'wget -q -O ./brewblox-ctl.tar.gz {url}')
    utils.sh('python3 -m pip install --prefer-binary ./brewblox-ctl.tar.gz')


def uninstall_old_ctl_package():
    utils.sh('rm -rf ./brewblox_ctl_lib/', check=False)
    utils.sh('rm -rf $(python3 -m site --user-site)/brewblox_ctl*', check=False)


def install_compose_plugin():
    if utils.check_ok(f'{utils.optsudo()}docker compose version'):
        return
    if utils.command_exists('apt-get'):
        utils.info('Installing Docker Compose plugin ...')
        utils.sh('sudo apt-get update && sudo apt-get install -y docker-compose-plugin')
    else:
        utils.warn('The Docker Compose plugin is not installed, and apt is not available.')
        utils.warn('You need to install the Docker Compose plugin manually.')
        utils.warn('')
        utils.warn('    https://docs.docker.com/compose/install/linux/')
        utils.warn('')
        raise SystemExit(1)


def edit_avahi_config():
    config = utils.get_config()
    fpath = Path('/etc/avahi/avahi-daemon.conf')

    if not config.avahi.managed or not utils.file_exists(fpath):
        return

    content = utils.read_file_sudo(fpath)
    # `infile` is treated as file.readlines() output if it is a list[str]
    avahi_config = ConfigObj(infile=content.split('\n'))
    copy = deepcopy(avahi_config)
    avahi_config.setdefault('server', {}).setdefault('use-ipv6', 'no')
    avahi_config.setdefault('publish', {}).setdefault('publish-aaaa-on-ipv4', 'no')
    avahi_config.setdefault('reflector', {}).setdefault('enable-reflector', 'yes')

    if avahi_config == copy:
        return

    # avahi-daemon.conf requires a 'key=value' syntax
    content = '\n'.join(avahi_config.write()).replace(' = ', '=') + '\n'
    utils.write_file_sudo(fpath, content)

    if utils.command_exists('systemctl'):
        utils.info('Restarting avahi-daemon service ...')
        utils.sh('sudo systemctl restart avahi-daemon')
    else:
        utils.warn('"systemctl" command not found. Please restart your machine to enable Wifi discovery.')


def edit_sshd_config():
    """Disable the 'AcceptEnv LANG LC_*' setting in sshd_config

    This setting is default on the Raspberry Pi,
    but leads to locale errors when an unsupported LANG is sent.

    Given that the Pi by default only includes the en_GB locale,
    the chances of being sent a unsupported locale are very real.
    """
    fpath = Path('/etc/ssh/sshd_config')
    if not utils.file_exists(fpath):
        return

    content = utils.read_file_sudo(fpath)
    updated = re.sub(r'^AcceptEnv LANG LC',
                     '#AcceptEnv LANG LC',
                     content,
                     flags=re.MULTILINE)

    if content == updated:
        return

    utils.info('Updating SSHD config to disable AcceptEnv ...')
    utils.write_file_sudo(fpath, updated)

    if utils.command_exists('systemctl'):
        utils.info('Restarting SSH service ...')
        utils.sh('sudo systemctl restart ssh')


def check_ports():
    if utils.is_compose_up():
        utils.info('Stopping services ...')
        utils.sh(f'{utils.optsudo()}docker compose down')

    config = utils.get_config()
    ports = config.ports.model_dump().values()

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
        utils.warn('You can change the ports used by Brewblox in `brewblox.yml`')
        if not utils.confirm('Do you want to continue?'):
            raise SystemExit(1)


def fix_ipv6(config_file=None, restart=True):
    utils.info('Fixing Docker IPv6 settings ...')

    if utils.is_wsl():
        utils.info('WSL environment detected. Skipping IPv6 config changes.')
        return

    # Config is either provided, or parsed from active daemon process
    if not config_file:
        default_config_file = '/etc/docker/daemon.json'
        dockerd_proc = utils.sh('ps aux | grep dockerd', capture=True)
        proc_match = re.match(r'.*--config-file[\s=](?P<file>.*\.json).*', dockerd_proc, flags=re.MULTILINE)
        config_file = proc_match and proc_match.group('file') or default_config_file

    config_file = Path(config_file)
    utils.info(f'Using Docker config file {config_file}')

    # Read config. Create file if not exists
    utils.sh(f"sudo mkdir -p '{config_file.parent}'")
    utils.sh(f"sudo touch '{config_file}'")
    config = utils.read_file_sudo(config_file)

    if 'fixed-cidr-v6' in config:
        utils.info('IPv6 settings are already present. Making no changes.')
        return

    # Edit and write. Do not overwrite existing values
    config = json.loads(config or '{}')
    config.setdefault('ipv6', False)
    config.setdefault('fixed-cidr-v6', '2001:db8:1::/64')
    utils.write_file_sudo(config_file, json.dumps(config, indent=2))

    # Restart daemon
    if restart:
        if utils.command_exists('service'):
            utils.info('Restarting Docker service ...')
            utils.sh('sudo service docker restart')
        else:
            utils.warn('"service" command not found. Please restart your machine to apply config changes.')


def file_netcat(host: str,
                port: int,
                path: utils.PathLike_) -> bytes:  # pragma: no cover
    """Uploads given file to host/url.

    Not all supported systems (looking at you, Synology) come with `nc` pre-installed.
    This provides a naive netcat alternative in pure python.
    """
    utils.info(f'Uploading {path} to {host}:{port} ...')

    if utils.get_opts().dry_run:
        return ''

    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        # Connect
        s.connect((host, int(port)))

        # Transmit
        with open(path, 'rb') as f:
            while True:
                out_bytes = f.read(4096)
                if not out_bytes:
                    break
                s.sendall(out_bytes)

        # Shutdown
        s.shutdown(socket.SHUT_WR)

        # Get result
        while True:
            data = s.recv(4096)
            if not data:
                break
            return data


def start_dotenv(*args):
    return utils.sh(' '.join(['dotenv', '--quote=never', *args]))


def start_esptool(*args):
    if not utils.command_exists('esptool.py'):
        utils.pip_install('esptool')
    return utils.sh('sudo -E env "PATH=$PATH" esptool.py ' + ' '.join(args))
