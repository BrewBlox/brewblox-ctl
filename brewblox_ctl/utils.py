"""
Utility functions
"""

import json
import re
from os import getcwd
from os import getenv as getenv_
from os import listdir, path
from pathlib import Path
from platform import machine
from shutil import which
from subprocess import DEVNULL, PIPE, STDOUT, CalledProcessError, run
from types import GeneratorType

import click
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
    input('Please press ENTER when your Spark is connected over USB')


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
    return getenv_(key, default)


def setenv(key, value, dotenv_path=path.abspath('.env')):
    opts = ctx_opts()
    if opts.dry_run or opts.verbose:
        click.secho(f'{const.LOG_ENV} {key}={value}', fg='magenta', color=opts.color)
    if not opts.dry_run:
        set_key(dotenv_path, key, value, quote_mode='never')


def clearenv(key, dotenv_path=path.abspath('.env')):
    opts = ctx_opts()
    if opts.dry_run or opts.verbose:
        click.secho(f'{const.LOG_ENV} unset {key}', fg='magenta', color=opts.color)
    if not opts.dry_run:
        unset_key(dotenv_path, key, quote_mode='never')


def path_exists(path_name):
    return path.exists(path_name)


def command_exists(cmd):
    return bool(which(cmd))


def is_pi():
    return machine().startswith('arm')


def is_v6():
    return machine().startswith('armv6')


def is_root():
    return check_ok('ls /root')


def is_docker_user():
    return check_ok('id -nG $USER | grep -qw "docker"')


def is_brewblox_cwd():
    return bool(getenv(const.CFG_VERSION_KEY))


def is_brewblox_dir(dir):
    env_path = dir + '/.env'
    if not path.isfile(env_path):
        return False
    return const.CFG_VERSION_KEY in dotenv_values(env_path)


def is_empty_dir(dir):
    return path.isdir(dir) and not listdir(dir)


def optsudo():
    return 'sudo ' if not is_docker_user() else ''


def tag_prefix():  # pragma: no cover
    """Present for backwards compatibility with older versions of ctl-lib"""
    return ''


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
            f'No Brewblox configuration found in current directory ({getcwd()}).' +
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
    user = getenv('USER')
    args = '--upgrade --no-cache-dir ' + ' '.join(libs)
    if user and Path(f'/home/{user}').is_dir():
        return sh(f'{const.PY} -m pip install --user {args}')
    else:
        return sh(f'sudo {const.PY} -m pip install {args}')


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


def load_ctl_lib(opts=None):
    sudo = optsudo()
    release = getenv(const.LIB_RELEASE_KEY) or getenv(const.RELEASE_KEY)
    if not release:
        raise KeyError('Failed to identify Brewblox release.')

    sh(f'{sudo}docker rm ctl-lib', opts, check=False)
    sh(f'{sudo}docker pull brewblox/brewblox-ctl-lib:{release}', opts)
    sh(f'{sudo}docker create --name ctl-lib brewblox/brewblox-ctl-lib:{release}', opts)
    sh('rm -rf ./brewblox_ctl_lib', opts, check=False)
    sh(f'{sudo}docker cp ctl-lib:/brewblox_ctl_lib ./', opts)
    sh(f'{sudo}docker rm ctl-lib', opts)

    if sudo:
        sh('sudo chown -R $USER ./brewblox_ctl_lib/', opts)


def enable_ipv6(config_file=None, restart=True):
    info('Enabling IPv6 support in Docker...')

    os_version = sh('cat /proc/version', capture=True) or ''
    if re.match(r'.*(Microsoft|WSL)', os_version, flags=re.IGNORECASE):
        info('WSL environment detected. Skipping IPv6 config changes.')
        return

    # Config is either provided, or parsed from active daemon process
    if not config_file:
        default_config_file = '/etc/docker/daemon.json'
        dockerd_proc = sh('ps aux | grep dockerd', capture=True)
        proc_match = re.match(r'.*--config-file[\s=](?P<file>.*\.json).*', dockerd_proc, flags=re.MULTILINE)
        config_file = proc_match and proc_match.group('file') or default_config_file

    info(f'Using Docker config file {config_file}')

    # Read config. Create file if not exists
    sh(f"sudo touch '{config_file}'")
    config = sh(f"sudo cat '{config_file}'", capture=True)

    # Edit and write. Do not overwrite existing values
    config = json.loads(config or '{}')
    config.setdefault('ipv6', True)
    config.setdefault('fixed-cidr-v6', '2001:db8:1::/64')
    config_str = json.dumps(config, indent=2)
    sh(f"echo '{config_str}' | sudo tee '{config_file}' > /dev/null")

    # Restart daemon
    if restart:
        if command_exists('service'):
            info('Restarting Docker service...')
            sh('sudo service docker restart')
        else:
            warn('"service" command not found. Please restart your machine to apply config changes.')
