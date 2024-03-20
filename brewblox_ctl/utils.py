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
from typing import Generator, List, Union

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
    if const.CONFIG_FILE.exists():
        config = CtlConfig.model_validate(yaml.load(const.CONFIG_FILE))
    else:
        config = CtlConfig()
    return config


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


def confirm_mode():  # pragma: no cover
    config = get_config()
    opts = get_opts()
    if config.skip_confirm or opts.yes or opts.dry_run or opts.verbose:
        return

    ctx = click.get_current_context()
    short_help = click.style(ctx.command.get_short_help_str(100), fg='cyan')
    click.echo(f'Command is about to: {short_help}', color=opts.color)

    y, n, v, d = [click.style(v, underline=True) for v in 'ynvd']
    suffix = f" ({y}es, {n}o, {v}erbose, {d}ry-run) [press ENTER for default value 'yes']"

    retv: str = click.prompt('Do you want to continue?',
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
        opts.yes = True


def getenv(key, default=None):  # pragma: no cover
    return os.getenv(key, default)


def setenv(key, value, dotenv_path=None):  # pragma: no cover
    if dotenv_path is None:
        dotenv_path = Path('.env').resolve()
    opts = get_opts()
    if opts.dry_run or opts.verbose:
        click.secho(f'{const.LOG_ENV} {key}={value}', fg='magenta', color=opts.color)
    if not opts.dry_run:
        dotenv.set_key(dotenv_path, key, str(value), quote_mode='never')


def clearenv(key, dotenv_path=None):  # pragma: no cover
    if dotenv_path is None:
        dotenv_path = Path('.env').resolve()
    opts = get_opts()
    if opts.dry_run or opts.verbose:
        click.secho(f'{const.LOG_ENV} unset {key}', fg='magenta', color=opts.color)
    if not opts.dry_run:
        dotenv.unset_key(dotenv_path, key, quote_mode='never')


def start_dotenv(*args):
    return sh(' '.join(['dotenv', '--quote=never', *args]))


def file_exists(path: PathLike_):  # pragma: no cover
    return Path(path).exists()


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
    return (Path(dir) / 'brewblox.yml').exists() or \
        (const.ENV_KEY_CFG_VERSION in dotenv_values(f'{dir}/.env'))


def is_empty_dir(dir):  # pragma: no cover
    path = Path(dir)
    return path.is_dir() and not next(path.iterdir(), None)


def user_home_exists() -> bool:  # pragma: no cover
    home = Path.home()
    return home.name != 'root' and home.exists()


def is_compose_up():  # pragma: no cover
    sudo = optsudo()
    return Path('docker-compose.yml').exists() and \
        sh(f'{sudo}docker compose ps -q', capture=True).strip() != ''


@contextmanager
def downed_services():
    """
    Ensures services are down during context, and in the previous state afterwards.
    """
    sudo = optsudo()
    running = is_compose_up()

    if running:
        sh(f'{sudo}docker compose --log-level CRITICAL down')
        yield
        sh(f'{sudo}docker compose up -d')
    else:
        yield


def cache_sudo():  # pragma: no cover
    """Elevated privileges are cached for default 15m"""
    sh('sudo true', silent=True)


def optsudo():  # pragma: no cover
    return '' if has_docker_rights() else 'sudo -E env "PATH=$PATH" '


def docker_tag(release=None):
    release = release or get_config().release
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


def sh(cmd: str, check=True, capture=False, silent=False) -> str:
    opts = get_opts()
    if opts.verbose or opts.dry_run:
        click.secho(f'{const.LOG_SHELL} {cmd}', fg='magenta', color=opts.color)
    if opts.dry_run:
        return ''

    stderr = STDOUT if check and not silent else DEVNULL
    stdout = PIPE if capture or silent else None

    result = run(cmd,
                 shell=True,
                 check=check,
                 universal_newlines=capture,
                 stdout=stdout,
                 stderr=stderr)

    return result.stdout or ''


def sh_stream(cmd: str) -> Generator[str, None, None]:
    opts = get_opts()
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


def check_ok(cmd: str) -> bool:
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
        click.secho(data, fg='blue', color=opts.color)


def host_url() -> str:
    return f'http://localhost:{get_config().ports.admin}'


def history_url() -> str:
    return f'{host_url()}/history/history'


def datastore_url() -> str:
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


def host_ip_addresses() -> List[str]:
    addresses = []
    for if_name, snics in psutil.net_if_addrs().items():
        if re.fullmatch(r'(lo|veth[0-9a-f]+)', if_name):
            continue
        addresses += [snic.address
                      for snic in snics
                      if snic.family in [socket.AF_INET, socket.AF_INET6]
                      and not snic.address.startswith('fe80::')]
    return addresses


def read_file(infile: PathLike_) -> str:  # pragma: no cover
    return Path(infile).read_text()


def read_file_sudo(infile: PathLike_) -> str:  # pragma: no cover
    return sh(f'sudo cat "{infile}"', capture=True)


def write_file(outfile: PathLike_, content: str):  # pragma: no cover
    show_data(str(outfile), content)
    if not get_opts().dry_run:
        Path(outfile).write_text(content)


def write_file_sudo(outfile: PathLike_, content: str):  # pragma: no cover
    show_data(str(outfile), content)
    if not get_opts().dry_run:
        with NamedTemporaryFile('w') as tmp:
            tmp.write(content)
            tmp.flush()
            sh(f'sudo chmod --reference="{outfile}" "{tmp.name}"', check=False)
            sh(f'sudo cp -fp "{tmp.name}" "{outfile}"')


def read_yaml(infile: PathLike_) -> CommentedMap:  # pragma: no cover
    return yaml.load(Path(infile))


def write_yaml(outfile: PathLike_, data: Union[dict, CommentedMap]):  # pragma: no cover
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


def write_compose(data: Union[dict, CommentedMap]):  # pragma: no cover
    write_yaml(const.COMPOSE_FILE, data)


def read_shared_compose() -> CommentedMap:
    return read_yaml(const.COMPOSE_SHARED_FILE)


def write_shared_compose(data: Union[dict, CommentedMap]):  # pragma: no cover
    write_yaml(const.COMPOSE_SHARED_FILE, data)


def save_config(config: CtlConfig):
    data = config.model_dump(mode='json', exclude_defaults=True)
    write_yaml(const.CONFIG_FILE, data)
    get_config.cache_clear()


def list_services(image=None) -> List[str]:
    config = read_compose()
    return [
        k for k, v in config['services'].items()
        if image is None or v.get('image', '').startswith(image)
    ]


def check_service_name(ctx, param, value):
    if not re.match(r'^[a-z0-9-_]+$', value):
        raise click.BadParameter('Names can only contain lowercase letters, numbers, - or _')
    return value
