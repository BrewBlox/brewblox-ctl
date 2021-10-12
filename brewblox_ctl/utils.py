"""
Utility functions
"""

import json
import os
import re
import shlex
import subprocess
from pathlib import Path
from platform import machine
from shutil import which
from subprocess import DEVNULL, PIPE, STDOUT, CalledProcessError, run
from types import GeneratorType
from typing import Generator

import click
import yaml
from dotenv import set_key, unset_key
from dotenv.main import dotenv_values

from brewblox_ctl import const

# Matches API of distutils.util.strtobool
# https://docs.python.org/3/distutils/apiref.html#distutils.util.strtobool
TRUE_PATTERN = re.compile('^(y|yes|t|true|on|1)$', re.IGNORECASE)
FALSE_PATTERN = re.compile('^(n|no|f|false|off|0)$', re.IGNORECASE)


class ContextOpts:

    def __init__(self,
                 dry_run=False,
                 quiet=False,
                 verbose=False,
                 skip_confirm=False,
                 color=None):  # None -> let click decide
        self.dry_run = dry_run
        self.quiet = quiet
        self.verbose = verbose
        self.skip_confirm = skip_confirm
        self.color = color


def ctx_opts():
    return click.get_current_context().find_object(ContextOpts)


def strtobool(val):
    if re.match(TRUE_PATTERN, val):
        return True
    if re.match(FALSE_PATTERN, val):
        return False
    raise ValueError()


def confirm(question, default=True):
    default_val = 'yes' if default else 'no'
    click.echo(f"{question} [Press ENTER for default value '{default_val}']")
    while True:
        try:
            return strtobool(input() or default_val)
        except ValueError:
            click.echo("Please type 'y(es)' or 'n(o)' and press ENTER.")


def select(question, default=''):
    default_prompt = f"[press ENTER for default value '{default}']" if default else ''
    answer = input(f'{question} {default_prompt}')
    return answer or default


def confirm_usb():
    input('Please connect a single Spark over USB, and press ENTER')


def confirm_mode():  # pragma: no cover
    opts = ctx_opts()
    if opts.skip_confirm or opts.dry_run or opts.verbose:
        return

    ctx = click.get_current_context()
    short_help = click.style(ctx.command.get_short_help_str(100), fg='cyan')
    click.echo(f'Command is about to: {short_help}', color=opts.color)

    y, n, v, d = [click.style(v, underline=True) for v in 'ynvd']
    suffix = f" ({y}es, {n}o, {v}erbose, {d}ry-run) [press ENTER for default value 'yes']"

    retv = click.prompt('Do you want to continue?',
                        type=click.Choice([
                            'y',
                            'yes',
                            'n',
                            'no',
                            'v',
                            'verbose',
                            'd',
                            'dry-run',
                        ], case_sensitive=False),
                        default='yes',
                        show_default=False,
                        show_choices=False,
                        prompt_suffix=suffix)

    v = retv.lower()
    if v in ('n', 'no'):
        ctx.abort()
    elif v in ('d', 'dry-run'):
        opts.dry_run = True
    elif v in ('v', 'verbose'):
        opts.verbose = True
    else:
        # Don't require additional confirmation for subcommands
        opts.skip_confirm = True


def getenv(key, default=None):
    return os.getenv(key, default)


def setenv(key, value, dotenv_path=Path('.env').absolute()):
    opts = ctx_opts()
    if opts.dry_run or opts.verbose:
        click.secho(f'{const.LOG_ENV} {key}={value}', fg='magenta', color=opts.color)
    if not opts.dry_run:
        set_key(dotenv_path, key, value, quote_mode='never')


def clearenv(key, dotenv_path=Path('.env').absolute()):
    opts = ctx_opts()
    if opts.dry_run or opts.verbose:
        click.secho(f'{const.LOG_ENV} unset {key}', fg='magenta', color=opts.color)
    if not opts.dry_run:
        unset_key(dotenv_path, key, quote_mode='never')


def path_exists(path_name):
    return Path(path_name).exists()


def command_exists(cmd):
    return bool(which(cmd))


def is_pi():
    return machine().startswith('arm')


def is_v6():
    return machine().startswith('armv6')


def is_root():
    return check_ok('ls /root')


def is_docker_user():
    return 'docker' in sh('id -nG $USER', capture=True)


def has_docker_rights():
    # Can current user run docker commands without sudo?
    # The shell must be reloaded after adding a user to the 'docker' group,
    # so a strict group membership check is not sufficient
    return 'permission denied' not in sh('docker version 2>&1', capture=True, check=False)


def is_brewblox_cwd():
    return bool(getenv(const.CFG_VERSION_KEY))


def is_brewblox_dir(dir):
    env_path = dir + '/.env'
    if not Path(env_path).is_file():
        return False
    return const.CFG_VERSION_KEY in dotenv_values(env_path)


def is_empty_dir(dir):
    path = Path(dir)
    return path.is_dir() and not list(path.iterdir())


def optsudo():
    return '' if has_docker_rights() else 'sudo -E env "PATH=$PATH" '


def docker_tag(release=None):
    release = release or getenv(const.RELEASE_KEY)
    if not release:
        raise KeyError('No Brewblox release specified. Please run this command in a Brewblox directory.')
    return release


def check_config(required=True):
    if is_brewblox_cwd():
        return True
    elif required:
        click.echo('Please run brewblox-ctl in a Brewblox directory.')
        raise SystemExit(1)
    elif confirm(
            f'No Brewblox configuration found in current directory ({Path.cwd()}).' +
            ' Are you sure you want to continue?'):
        return False
    else:
        raise SystemExit(0)


def sh(shell_cmd, opts=None, check=True, capture=False, silent=False):
    if isinstance(shell_cmd, (GeneratorType, list, tuple)):
        return [sh(cmd, opts, check, capture, silent) for cmd in shell_cmd]
    else:
        opts = opts or ctx_opts()
        if opts.verbose or opts.dry_run:
            click.secho(f'{const.LOG_SHELL} {shell_cmd}', fg='magenta', color=opts.color)
        if not opts.dry_run:
            stderr = STDOUT if check and not silent else DEVNULL
            stdout = PIPE if capture or silent else None

            result = run(shell_cmd,
                         shell=True,
                         check=check,
                         universal_newlines=capture,
                         stdout=stdout,
                         stderr=stderr)
            if capture:
                return result.stdout
        return ''


def check_ok(cmd):
    try:
        run(cmd, shell=True, stderr=DEVNULL, check=True)
        return True
    except CalledProcessError:
        return False


def pip_install(*libs):
    args = '--upgrade --no-cache-dir ' + ' '.join(libs)
    return sh(f'{const.PY} -m pip install {args}')


def info(msg):
    opts = ctx_opts()
    if not opts.quiet:
        click.secho(f'{const.LOG_INFO} {msg}', fg='cyan', color=opts.color)


def warn(msg):
    opts = ctx_opts()
    click.secho(f'{const.LOG_WARN} {msg}', fg='yellow', color=opts.color)


def error(msg):
    opts = ctx_opts()
    click.secho(f'{const.LOG_ERR} {msg}', fg='red', color=opts.color)


def show_data(data):
    opts = ctx_opts()
    if opts.dry_run or opts.verbose:
        if not isinstance(data, str):
            data = json.dumps(data)
        click.secho(data, fg='blue', color=opts.color)


def host_url():
    port = getenv(const.HTTPS_PORT_KEY, '443')
    return f'{const.HOST}:{port}'


def history_url():
    return f'{host_url()}/history/history'


def datastore_url():
    return f'{host_url()}/history/datastore'


def host_ip():
    try:
        # remote IP / port, local IP / port
        return getenv('SSH_CONNECTION', '').split()[2]
    except IndexError:
        return '127.0.0.1'


def user_home_exists() -> bool:
    home = Path.home()
    return home.name != 'root' and home.exists()


def read_file(fname):  # pragma: no cover
    with open(fname) as f:
        return '\n'.join(f.readlines())


def read_compose(fname='docker-compose.yml'):
    with open(fname) as f:
        return yaml.safe_load(f)


def write_compose(config, fname='docker-compose.yml'):  # pragma: no cover
    opts = ctx_opts()
    if opts.dry_run or opts.verbose:
        click.secho(f'{const.LOG_COMPOSE} {fname}', fg='magenta', color=opts.color)
        show_data(yaml.safe_dump(config))
    if not opts.dry_run:
        with open(fname, 'w') as f:
            yaml.safe_dump(config, f)


def read_shared_compose(fname='docker-compose.shared.yml'):
    return read_compose(fname)


def write_shared_compose(config, fname='docker-compose.shared.yml'):  # pragma: no cover
    write_compose(config, fname)


def list_services(image=None, fname=None):
    config = read_compose(fname) if fname else read_compose()

    return [
        k for k, v in config['services'].items()
        if image is None or v.get('image', '').startswith(image)
    ]


def check_service_name(ctx, param, value):
    if not re.match(r'^[a-z0-9-_]+$', value):
        raise click.BadParameter('Names can only contain lowercase letters, numbers, - or _')
    return value


def sh_stream(cmd: str) -> Generator[str, None, None]:
    opts = ctx_opts()
    if opts.verbose:
        click.secho(f'{const.LOG_SHELL} {cmd}', fg='magenta', color=opts.color)

    process = subprocess.Popen(
        shlex.split(cmd),
        stdout=subprocess.PIPE,
        universal_newlines=True,
    )

    while True:
        output = process.stdout.readline()
        if not output and process.poll() is not None:
            break
        else:
            yield output


def makecert(dir, release: str = None):
    absdir = Path(dir).absolute()
    sudo = optsudo()
    tag = docker_tag(release)
    sh(f'mkdir -p "{absdir}"')
    sh(f'{sudo}docker run' +
        ' --rm --privileged' +
        ' --pull always' +
        f' -v "{absdir}":/certs/' +
        f' brewblox/omgwtfssl:{tag}')
    sh(f'sudo chmod 644 "{absdir}/brewblox.crt"')
    sh(f'sudo chmod 600 "{absdir}/brewblox.key"')


def update_system_packages():
    if command_exists('apt'):
        info('Updating apt packages...')
        sh('sudo apt -qq update && sudo apt -qq upgrade -y')


def add_particle_udev_rules():
    rules_dir = '/etc/udev/rules.d'
    target = f'{rules_dir}/50-particle.rules'
    if not path_exists(target) and command_exists('udevadm'):
        info('Adding udev rules for Particle devices...')
        sh(f'sudo mkdir -p {rules_dir}')
        sh(f'sudo cp {const.CONFIG_DIR}/50-particle.rules {target}')
        sh('sudo udevadm control --reload-rules && sudo udevadm trigger')


def download_ctl():
    release = getenv(const.CTL_RELEASE_KEY) or getenv(const.RELEASE_KEY)
    sh(f'wget -q -O ./brewblox-ctl.tar.gz https://brewblox.blob.core.windows.net/ctl/{release}/brewblox-ctl.tar.gz')
    sh(f'{const.PY} -m pip install --quiet --upgrade --upgrade-strategy eager --target ./lib ./brewblox-ctl.tar.gz')
    if user_home_exists():
        sh('mkdir -p $HOME/.local/bin')
        sh(f'cp {const.SCRIPT_DIR}/brewblox-ctl $HOME/.local/bin/')
        sh('chmod +x $HOME/.local/bin/brewblox-ctl')
    else:
        sh(f'sudo cp {const.SCRIPT_DIR}/brewblox-ctl /usr/local/bin/')
        sh('sudo chmod 777 /usr/local/bin/brewblox-ctl')


def check_ports():
    if path_exists('./docker-compose.yml'):
        info('Stopping services...')
        sh(f'{optsudo()}docker-compose down')

    ports = [
        getenv(key, const.ENV_DEFAULTS[key]) for key in [
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
        warn(f'Port(s) {port_str} already in use.')
        warn('Run `brewblox-ctl service ports` to configure Brewblox ports.')
        for line in used_lines:
            warn(line)
        if not confirm('Do you want to continue?'):
            raise SystemExit(1)
