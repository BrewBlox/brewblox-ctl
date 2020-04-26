"""
Utility functions
"""

from distutils.util import strtobool
from os import getcwd
from os import getenv as getenv_
from os import path
from pathlib import Path
from platform import machine
from shutil import which
from subprocess import DEVNULL, PIPE, STDOUT, CalledProcessError, run
from types import GeneratorType

import click
from dotenv import set_key

from brewblox_ctl import const


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


def confirm(question, default=True):
    default_val = 'Yes' if default else 'No'
    prompt = "{} [Press ENTER for default value '{}']".format('{}', default_val)
    click.echo(prompt.format(question))
    while True:
        try:
            return bool(strtobool(input().lower() or str(default)))
        except ValueError:
            click.echo("Please type 'y(es)' or 'n(o)' and press ENTER.")


def select(question, default=''):
    answer = input('{} {}'.format(
        question,
        "[press ENTER for default value '{}']".format(default) if default else ''))
    return answer or default


def confirm_usb():
    input('Please press ENTER when your Spark is connected over USB')


def confirm_mode():  # pragma: no cover
    opts = ctx_opts()
    if opts.skip_confirm or opts.dry_run or opts.verbose:
        return

    ctx = click.get_current_context()
    short_help = click.style(ctx.command.get_short_help_str(100), fg='cyan')
    click.echo('Command is about to: {}'.format(short_help), color=opts.color)

    suffix = " ({}es, {}o, {}erbose, {}ry-run) [press ENTER for default value 'yes']".format(
        *[click.style(v, underline=True) for v in 'ynvd']
    )

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


def getenv(key, default=None):
    return getenv_(key, default)


def setenv(key, value, dotenv_path=path.abspath('.env')):
    opts = ctx_opts()
    if opts.dry_run or opts.verbose:
        click.secho('{} {}={}'.format(const.LOG_ENV, key, value), fg='magenta', color=opts.color)
    if not opts.dry_run:
        set_key(dotenv_path, key, value, quote_mode='never')


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
        'No Brewblox configuration found in current directory ({}). '.format(getcwd()) +
            'Are you sure you want to continue?'):
        return False
    else:
        raise SystemExit(0)


def sh(shell_cmd, opts=None, check=True, capture=False, silent=False):
    if isinstance(shell_cmd, (GeneratorType, list, tuple)):
        return [sh(cmd, opts, check, capture, silent) for cmd in shell_cmd]
    else:
        opts = opts or ctx_opts()
        if opts.verbose or opts.dry_run:
            click.secho('{} {}'.format(const.LOG_SHELL, shell_cmd), fg='magenta', color=opts.color)
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
    if user and Path('/home/{}'.format(user)).is_dir():
        return sh('{} -m pip install --user {}'.format(const.PY, args))
    else:
        return sh('sudo {} -m pip install {}'.format(const.PY, args))


def info(msg):
    opts = ctx_opts()
    if not opts.quiet:
        click.secho('{} {}'.format(const.LOG_INFO, msg), fg='cyan', color=opts.color)


def warn(msg):
    opts = ctx_opts()
    click.secho('{} {}'.format(const.LOG_WARN, msg), fg='yellow', color=opts.color)


def error(msg):
    opts = ctx_opts()
    click.secho('{} {}'.format(const.LOG_ERR, msg), fg='red', color=opts.color)


def load_ctl_lib(opts=None):
    sudo = optsudo()
    release = getenv(const.LIB_RELEASE_KEY) or getenv(const.RELEASE_KEY)
    if not release:
        raise KeyError('Failed to identify Brewblox release.')

    sh('{}docker rm ctl-lib'.format(sudo), opts, check=False)
    sh('{}docker pull brewblox/brewblox-ctl-lib:{}'.format(sudo, release), opts)
    sh('{}docker create --name ctl-lib brewblox/brewblox-ctl-lib:{}'.format(sudo, release), opts)
    sh('rm -rf ./brewblox_ctl_lib', opts, check=False)
    sh('{}docker cp ctl-lib:/brewblox_ctl_lib ./'.format(sudo), opts)
    sh('{}docker rm ctl-lib'.format(sudo), opts)

    if sudo:
        sh('sudo chown -R $USER ./brewblox_ctl_lib/', opts)
