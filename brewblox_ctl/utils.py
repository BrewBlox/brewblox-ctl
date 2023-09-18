"""
Utility functions
"""

import grp
import json
import os
import platform
import random
import re
import shlex
import shutil
import socket
import string
from contextlib import closing
from getpass import getpass
from pathlib import Path
from subprocess import DEVNULL, PIPE, STDOUT, CalledProcessError, Popen, run
from tempfile import NamedTemporaryFile
from types import GeneratorType
from typing import Generator, Tuple, Union

import click
import dotenv
from dotenv.main import dotenv_values
from passlib.hash import pbkdf2_sha512
from ruamel.yaml import YAML
from ruamel.yaml.compat import StringIO

from brewblox_ctl import const

yaml = YAML()


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


def strtobool(val: str) -> bool:
    """Convert a string representation of truth to true (1) or false (0).
    True values are 'y', 'yes', 't', 'true', 'on', and '1'; false values
    are 'n', 'no', 'f', 'false', 'off', and '0'.  Raises ValueError if
    'val' is anything else.
    """
    val = val.lower()
    if val in ('y', 'yes', 't', 'true', 'on', '1'):
        return True
    elif val in ('n', 'no', 'f', 'false', 'off', '0'):
        return False
    else:
        raise ValueError(f'invalid truth value {val}')


def random_string(size: int) -> str:
    opts = string.ascii_letters + string.digits
    return ''.join(random.choice(opts) for _ in range(size))


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


def read_users() -> dict:
    content = ''

    if const.PASSWD_FILE.exists():  # pragma: no cover
        content = sh(f'sudo cat "{const.PASSWD_FILE}"', capture=True) or ''

    return {
        name: hashed
        for (name, hashed)
        in [line.strip().split(':', 1)
            for line in content.split('\n')
            if ':' in line]
    }


def write_users(users: dict):
    with NamedTemporaryFile('w') as tempf:
        for k, v in users.items():
            tempf.write(f'{k}:{v}\n')
        tempf.flush()
        sh(f'sudo cp "{tempf.name}" "{const.PASSWD_FILE}"')
        sh(f'sudo chown root:root "{const.PASSWD_FILE}"')


def prompt_user_info() -> Tuple[str, str]:
    username = click.prompt('Name')
    while not re.fullmatch(r'\w+', username):
        warn('Names can only contain letters, numbers, - or _')
        username = click.prompt('Name')
    password = getpass()
    return (username, password)


def add_user(username: str, password: str):
    users = read_users()
    users[username] = pbkdf2_sha512.hash(password)
    write_users(users)


def remove_user(username):
    users = read_users()
    try:
        del users[username]
        write_users(users)
    except KeyError:
        pass


def getenv(key, default=None):  # pragma: no cover
    return os.getenv(key, default)


def setenv(key, value, dotenv_path=None):  # pragma: no cover
    if dotenv_path is None:
        dotenv_path = Path('.env').resolve()
    opts = ctx_opts()
    if opts.dry_run or opts.verbose:
        click.secho(f'{const.LOG_ENV} {key}={value}', fg='magenta', color=opts.color)
    if not opts.dry_run:
        dotenv.set_key(dotenv_path, key, value, quote_mode='never')


def clearenv(key, dotenv_path=None):  # pragma: no cover
    if dotenv_path is None:
        dotenv_path = Path('.env').resolve()
    opts = ctx_opts()
    if opts.dry_run or opts.verbose:
        click.secho(f'{const.LOG_ENV} unset {key}', fg='magenta', color=opts.color)
    if not opts.dry_run:
        dotenv.unset_key(dotenv_path, key, quote_mode='never')


def defaultenv():  # pragma: no cover
    for key, default_val in const.ENV_FILE_DEFAULTS.items():
        existing = getenv(key)
        if existing is None:
            setenv(key, default_val)


def start_dotenv(*args):
    return sh(' '.join(['dotenv', '--quote=never', *args]))


def path_exists(path_name):  # pragma: no cover
    return Path(path_name).exists()


def command_exists(cmd):  # pragma: no cover
    return bool(shutil.which(cmd))


def is_armv6() -> bool:
    return platform.machine().startswith('armv6')


def is_wsl() -> bool:
    return bool(re.match(r'.*(Microsoft|WSL)',
                         platform.version(),
                         flags=re.IGNORECASE))


def is_root() -> bool:  # pragma: no cover
    return os.geteuid() == 0


def is_docker_user() -> bool:  # pragma: no cover
    return 'docker' in [grp.getgrgid(g).gr_name for g in os.getgroups()]


def has_docker_rights():  # pragma: no cover
    # Can current user run docker commands without sudo?
    # The shell must be reloaded after adding a user to the 'docker' group,
    # so a strict group membership check is not sufficient
    return 'permission denied' not in sh('docker version 2>&1', capture=True, check=False)


def is_brewblox_dir(dir: str) -> bool:  # pragma: no cover
    return const.ENV_KEY_CFG_VERSION in dotenv_values(f'{dir}/.env')


def is_empty_dir(dir):  # pragma: no cover
    path = Path(dir)
    return path.is_dir() and not next(path.iterdir(), None)


def user_home_exists() -> bool:  # pragma: no cover
    home = Path.home()
    return home.name != 'root' and home.exists()


def cache_sudo():  # pragma: no cover
    """Elevated privileges are cached for default 15m"""
    sh('sudo true', silent=True)


def optsudo():  # pragma: no cover
    return '' if has_docker_rights() else 'sudo -E env "PATH=$PATH" '


def docker_tag(release=None):
    release = release or getenv(const.ENV_KEY_RELEASE)
    if not release:
        raise KeyError('No Brewblox release specified. Please run this command in a Brewblox directory.')
    return release


def check_config(required=True):
    if is_brewblox_dir('.'):
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


def sh_stream(cmd: str) -> Generator[str, None, None]:
    opts = ctx_opts()
    if opts.verbose:
        click.secho(f'{const.LOG_SHELL} {cmd}', fg='magenta', color=opts.color)

    process = Popen(
        shlex.split(cmd),
        stdout=PIPE,
        universal_newlines=True,
    )

    while True:
        output = process.stdout.readline()
        if not output and process.poll() is not None:
            break
        else:
            yield output


def check_ok(cmd):
    try:
        run(cmd, shell=True, stderr=DEVNULL, check=True)
        return True
    except CalledProcessError:
        return False


def pip_install(*libs):
    return sh('python3 -m pip install '
              + '--upgrade --no-cache-dir --prefer-binary '
              + ' '.join(libs))


def start_esptool(*args):
    if not command_exists('esptool.py'):
        pip_install('esptool')
    return sh('sudo -E env "PATH=$PATH" esptool.py ' + ' '.join(args))


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


def show_data(desc: str, data):
    opts = ctx_opts()
    if opts.dry_run or opts.verbose:
        if not isinstance(data, str):
            data = json.dumps(data, indent=2)
        click.secho(f'{const.LOG_CONFIG} {desc}', fg='magenta', color=opts.color)
        click.secho(data, fg='blue', color=opts.color)


def host_url():
    port = getenv(const.ENV_KEY_PORT_ADMIN, str(const.DEFAULT_PORT_ADMIN))
    return f'http://localhost:{port}'


def history_url():
    return f'{host_url()}/history/history'


def datastore_url():
    return f'{host_url()}/history/datastore'


def hostname() -> str:  # pragma: no cover
    return socket.gethostname()


def host_lan_ip() -> str:  # pragma: no cover
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0)
    try:
        # We don't expect this to be reachable
        s.connect(('10.254.254.254', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP


def host_ip():
    try:
        # remote IP / port, local IP / port
        return getenv('SSH_CONNECTION', '').split()[2]
    except IndexError:
        return '127.0.0.1'


def read_file(fname):  # pragma: no cover
    with open(fname) as f:
        return '\n'.join(f.readlines())


def read_compose(fname='docker-compose.yml'):
    config: dict = yaml.load(Path(fname))
    config.setdefault('services', {})
    return config


def write_compose(config, fname='docker-compose.yml'):  # pragma: no cover
    opts = ctx_opts()
    if opts.dry_run or opts.verbose:
        stream = StringIO()
        yaml.dump(config, stream)
        show_data(fname, stream.getvalue())
    if not opts.dry_run:
        yaml.dump(config, Path(fname))


def read_shared_compose(fname='docker-compose.shared.yml'):
    return read_compose(fname)


def write_shared_compose(config, fname='docker-compose.shared.yml'):  # pragma: no cover
    write_compose(config, fname)


def list_services(image=None, fname='docker-compose.yml'):
    config = read_compose(fname)
    return [
        k for k, v in config['services'].items()
        if image is None or v.get('image', '').startswith(image)
    ]


def check_service_name(ctx, param, value):
    if not re.match(r'^[a-z0-9-_]+$', value):
        raise click.BadParameter('Names can only contain lowercase letters, numbers, - or _')
    return value


def file_netcat(host: str,
                port: int,
                path: Union[str, Path]) -> bytes:  # pragma: no cover
    """Uploads given file to host/url.

    Not all supported systems (looking at you, Synology) come with `nc` pre-installed.
    This provides a naive netcat alternative in pure python.
    """
    info(f'Uploading {path} to {host}:{port}...')

    if ctx_opts().dry_run:
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
