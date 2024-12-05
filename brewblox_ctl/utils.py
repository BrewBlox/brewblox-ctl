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
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from subprocess import DEVNULL, PIPE, STDOUT, CalledProcessError, Popen, run
from tempfile import NamedTemporaryFile
from typing import Dict, Generator, List, Union

import click
import dotenv
import psutil
from dotenv.main import dotenv_values
from ruamel.yaml import YAML, CommentedMap
from ruamel.yaml.compat import StringIO

from . import const
from .models import CtlConfig, CtlOpts

PathLike_ = Union[str, os.PathLike]

yaml = YAML()


@lru_cache
def get_opts() -> CtlOpts:
    return CtlOpts()


@lru_cache
def get_config() -> CtlConfig:
    if not const.CONFIG_FILE.exists():
        return CtlConfig()

    try:
        return CtlConfig.model_validate(yaml.load(const.CONFIG_FILE))
    except Exception as ex:
        click.secho(f'Loading `{const.CONFIG_FILE}` failed with a {strex(ex)}', err=True)
        raise SystemExit(1)


def strtobool(val: str) -> bool:
    """Convert a string representation of truth to true (1) or false (0).
    True values are 'y', 'yes', 't', 'true', 'on', and '1'; false values
    are 'n', 'no', 'f', 'false', 'off', and '0'.  Raises ValueError if
    'val' is anything else.
    """
    val = val.lower()
    if val in ('y', 'yes', 't', 'true', 'on', '1'):
        return True
    if val in ('n', 'no', 'f', 'false', 'off', '0'):
        return False
    raise ValueError(f'invalid truth value {val}')


def strex(ex: Exception) -> str:
    """
    Formats exception as `Exception(message)`
    """
    msg = str(ex)
    if '\n' in msg:
        return f'{type(ex).__name__}:\n{msg}'
    return f'{type(ex).__name__}({msg})'


def random_string(size: int) -> str:
    opts = string.ascii_letters + string.digits
    return ''.join(random.choice(opts) for _ in range(size))


def confirm(question, default=True) -> bool:
    default_val = 'yes' if default else 'no'
    click.echo(f"{question} [Press ENTER for default value '{default_val}']")
    while True:
        try:
            return strtobool(input() or default_val)
        except ValueError:
            click.echo("Please type 'y(es)' or 'n(o)' and press ENTER.")


def select(question, default='') -> str:
    default_prompt = f"[press ENTER for default value '{default}']" if default else ''
    answer = input(f'{question} {default_prompt}')
    return answer or default


def confirm_usb():
    input('Please connect a single Spark over USB, and press ENTER')


def confirm_mode():
    config = get_config()
    opts = get_opts()
    if config.skip_confirm or opts.yes or opts.dry_run or opts.verbose:
        return

    ctx = click.get_current_context()
    short_help = click.style(ctx.command.get_short_help_str(100), fg='cyan')
    click.echo(f'Command is about to: {short_help}', color=opts.color)

    y, n, v, d = [click.style(v, underline=True) for v in 'ynvd']
    suffix = f" ({y}es, {n}o, {v}erbose, {d}ry-run) [press ENTER for default value 'yes']"

    retv: str = click.prompt(
        'Do you want to continue?',
        type=click.Choice(
            [
                'y',
                'yes',
                'n',
                'no',
                'v',
                'verbose',
                'd',
                'dry-run',
            ],
            case_sensitive=False,
        ),
        default='yes',
        show_default=False,
        show_choices=False,
        prompt_suffix=suffix,
    )

    v = retv.lower()
    if v in ('n', 'no'):
        ctx.abort()
    elif v in ('d', 'dry-run'):
        opts.dry_run = True
    elif v in ('v', 'verbose'):
        opts.verbose = True
    else:
        # Don't require additional confirmation for subcommands
        opts.yes = True


def getenv(key, default=None):
    return os.getenv(key, default)


def envdict(dotenv_path=None) -> Dict[str, Union[str, None]]:
    return dotenv.dotenv_values(dotenv_path=dotenv_path)


def setenv(key, value, dotenv_path=None):
    if dotenv_path is None:
        dotenv_path = Path('.env').resolve()
    opts = get_opts()
    if opts.dry_run or opts.verbose:
        click.secho(f'{const.LOG_ENV} {key}={value}', fg='magenta', color=opts.color)
    if not opts.dry_run:
        dotenv.set_key(dotenv_path, key, str(value), quote_mode='never')


def clearenv(key, dotenv_path=None):
    if dotenv_path is None:
        dotenv_path = Path('.env').resolve()
    opts = get_opts()
    if opts.dry_run or opts.verbose:
        click.secho(f'{const.LOG_ENV} unset {key}', fg='magenta', color=opts.color)
    if not opts.dry_run:
        dotenv.unset_key(dotenv_path, key, quote_mode='never')


def file_exists(path: PathLike_):
    return Path(path).exists()


def command_exists(cmd):
    return bool(shutil.which(cmd))


def is_armv6() -> bool:
    return platform.machine().startswith('armv6')


def is_wsl() -> bool:
    return bool(re.match(r'.*(Microsoft|WSL)', platform.version(), flags=re.IGNORECASE))


def is_root() -> bool:
    return os.geteuid() == 0


def is_docker_user() -> bool:
    return 'docker' in [grp.getgrgid(g).gr_name for g in os.getgroups()]


def has_docker_rights():
    # Can current user run docker commands without sudo?
    # The shell must be reloaded after adding a user to the 'docker' group,
    # so a strict group membership check is not sufficient
    return 'permission denied' not in sh('docker version 2>&1', capture=True, check=False)


def is_brewblox_dir(dir: str) -> bool:
    return (Path(dir) / 'brewblox.yml').exists() or (const.ENV_KEY_CFG_VERSION in dotenv_values(f'{dir}/.env'))


def is_empty_dir(dir):
    path = Path(dir)
    return path.is_dir() and not next(path.iterdir(), None)


def user_home_exists() -> bool:
    home = Path.home()
    return home.name != 'root' and home.exists()


def is_compose_up():
    sudo = optsudo()
    return Path('docker-compose.yml').exists() and sh(f'{sudo}docker compose ps -q', capture=True).strip() != ''


@contextmanager
def downed_services():
    """
    Ensures services are down during context, and in the previous state afterwards.
    """
    sudo = optsudo()

    try:
        running = is_compose_up()
    except CalledProcessError as ex:
        warn('Failed to check service state. Services will not be stopped.')
        warn(strex(ex))
        warn(ex.stdout)
        running = False

    if running:
        sh(f'{sudo}docker compose down')
        yield
        sh(f'{sudo}docker compose up -d')
    else:
        yield


def cache_sudo():
    """Elevated privileges are cached for default 15m"""
    sh('sudo true', silent=True)


def optsudo():
    return '' if has_docker_rights() else 'sudo -E env "PATH=$PATH" '


def docker_tag(release=None):
    return release or get_config().release


def check_config(required=True):
    if is_brewblox_dir('.'):
        return True
    if required:
        click.echo('Please run brewblox-ctl in a Brewblox directory.')
        raise SystemExit(1)
    if confirm(
        f'No Brewblox configuration found in current directory ({Path.cwd()}).' + ' Are you sure you want to continue?'
    ):
        return False
    raise SystemExit(0)


def sh(cmd: str, check=True, capture=False, silent=False) -> str:
    opts = get_opts()
    if opts.verbose or opts.dry_run:
        click.secho(f'{const.LOG_SHELL} {cmd}', fg='magenta', color=opts.color)
    if opts.dry_run:
        return ''

    stderr = STDOUT if check and not silent else DEVNULL
    stdout = PIPE if capture or silent else None

    result = run(cmd, shell=True, check=check, text=capture, stdout=stdout, stderr=stderr)

    return result.stdout or ''


def sh_stream(cmd: str) -> Generator[str, None, None]:
    opts = get_opts()
    if opts.verbose or opts.dry_run:
        click.secho(f'{const.LOG_SHELL} {cmd}', fg='magenta', color=opts.color)
    if opts.dry_run:
        return

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


def check_ok(cmd: str) -> bool:
    try:
        run(cmd, shell=True, stderr=DEVNULL, check=True)
        return True
    except CalledProcessError:
        return False


def pip_install(*libs):
    return sh('uv pip install ' + '--upgrade --no-cache' + ' '.join(libs))


def info(msg: str):
    opts = get_opts()
    if not opts.quiet:
        click.secho(f'{const.LOG_INFO} {msg}', fg='cyan', color=opts.color)


def warn(msg: str):
    opts = get_opts()
    click.secho(f'{const.LOG_WARN} {msg}', fg='yellow', color=opts.color)


def error(msg: str):
    opts = get_opts()
    click.secho(f'{const.LOG_ERR} {msg}', fg='red', color=opts.color)


def show_data(desc: str, data):
    opts = get_opts()
    if opts.dry_run or opts.verbose:
        if not isinstance(data, str):
            data = json.dumps(data, indent=2)
        click.secho(f'{const.LOG_CONFIG} {desc}', fg='magenta', color=opts.color)
        click.secho(data)


def host_url() -> str:
    return f'http://localhost:{get_config().ports.admin}'


def history_url() -> str:
    return f'{host_url()}/history/history'


def datastore_url() -> str:
    return f'{host_url()}/history/datastore'


def hostname() -> str:
    return socket.gethostname()


def host_lan_ip() -> str:
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


def host_ip_addresses() -> List[str]:
    addresses = []
    for if_name, snics in psutil.net_if_addrs().items():
        if re.fullmatch(r'(lo|veth[0-9a-f]+)', if_name):
            continue
        addresses += [
            snic.address
            for snic in snics
            if snic.family in [socket.AF_INET, socket.AF_INET6] and not snic.address.startswith('fe80::')
        ]
    return addresses


def read_file(infile: PathLike_) -> str:
    return Path(infile).read_text()


def read_file_sudo(infile: PathLike_) -> str:
    return sh(f'sudo cat "{infile}"', capture=True)


def write_file(outfile: PathLike_, content: str, secret=False):
    show_data(str(outfile), '***' if secret else content)
    if not get_opts().dry_run:
        Path(outfile).write_text(content)


def write_file_sudo(outfile: PathLike_, content: str, secret=False):
    show_data(str(outfile), '***' if secret else content)
    if not get_opts().dry_run:
        with NamedTemporaryFile('w') as tmp:
            tmp.write(content)
            tmp.flush()
            sh(f'sudo chmod --reference="{outfile}" "{tmp.name}"', check=False)
            sh(f'sudo cp -fp "{tmp.name}" "{outfile}"')


def read_yaml(infile: PathLike_) -> CommentedMap:
    return yaml.load(Path(infile))


def write_yaml(outfile: PathLike_, data: Union[dict, CommentedMap]):
    opts = get_opts()
    if opts.dry_run or opts.verbose:
        stream = StringIO()
        yaml.dump(data, stream)
        show_data(str(outfile), stream.getvalue())
    if not opts.dry_run:
        yaml.dump(data, Path(outfile))


def dump_yaml(data: Union[dict, CommentedMap]) -> str:
    stream = StringIO()
    yaml.dump(data, stream)
    return stream.getvalue()


def read_compose() -> CommentedMap:
    data = read_yaml(const.COMPOSE_FILE)
    return data


def write_compose(data: Union[dict, CommentedMap]):
    write_yaml(const.COMPOSE_FILE, data)


def read_shared_compose() -> CommentedMap:
    return read_yaml(const.COMPOSE_SHARED_FILE)


def write_shared_compose(data: Union[dict, CommentedMap]):
    write_yaml(const.COMPOSE_SHARED_FILE, data)


def list_services(image=None) -> List[str]:
    config = read_compose()
    return [k for k, v in config['services'].items() if image is None or v.get('image', '').startswith(image)]


def check_service_name(ctx, param, value):
    if not re.match(r'^[a-z0-9-_]+$', value):
        raise click.BadParameter('Names can only contain lowercase letters, numbers, - or _')
    return value
