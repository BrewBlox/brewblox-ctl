"""
Utility functions
"""

from distutils.util import strtobool
from os import getcwd
from os import getenv as getenv_
from os import path
from platform import machine
from shutil import which
from subprocess import DEVNULL, STDOUT, CalledProcessError, check_output, run
from types import GeneratorType

import click
import dotenv

from brewblox_ctl.const import CFG_VERSION_KEY, LIB_RELEASE_KEY, RELEASE_KEY


def confirm(question, default=True):
    default_val = 'Yes' if default else 'No'
    prompt = '{} [Press ENTER for default value \'{}\']'.format('{}', default_val)
    print(prompt.format(question))
    while True:
        try:
            return bool(strtobool(input().lower() or str(default)))
        except ValueError:
            print('Please type \'y(es)\' or \'n(o)\' and press ENTER.')


def select(question, default=''):
    answer = input('{} {}'.format(
        question,
        '[press ENTER for default value \'{}\']'.format(default) if default else ''))
    return answer or default


def prompt_usb():
    input('Please press ENTER when your Spark is connected over USB')


def check_ok(cmd):
    try:
        check_output(cmd, shell=True, stderr=STDOUT)
        return True
    except CalledProcessError:
        return False


def ctx_obj():
    return click.get_current_context().ensure_object(dict)


def dry():
    return ctx_obj().get('dry_run', False)


def quiet():
    return ctx_obj().get('quiet', False)


def verbose():
    return ctx_obj().get('verbose', False)


def getenv(key, default=None):
    return getenv_(key, default)


def setenv(key, value, dotenv_path=path.abspath('.env')):
    if dry() or verbose():
        click.echo('[ENV] {}={}'.format(key, value))
    if not dry():
        dotenv.set_key(dotenv_path, key, value, quote_mode='never')


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
    return bool(getenv(CFG_VERSION_KEY))


def optsudo():
    return 'sudo ' if not is_docker_user() else ''


def tag_prefix():
    return 'rpi-' if is_pi() else ''


def docker_tag(release=None):
    return '{}{}'.format(
        tag_prefix(),
        release or getenv(RELEASE_KEY, 'stable')
    )


def ctl_lib_tag():
    release = getenv(LIB_RELEASE_KEY) or getenv(RELEASE_KEY, 'stable')
    return '{}{}'.format(tag_prefix(), release)


def check_config(required=True):
    if is_brewblox_cwd():
        return True
    elif required:
        print('Please run brewblox-ctl in the same directory as your docker-compose.yml file.')
        raise SystemExit(1)
    elif confirm(
        'No BrewBlox configuration found in current directory ({}). '.format(getcwd()) +
            'Are you sure you want to continue?'):
        return False
    else:
        raise SystemExit(0)


def confirm_mode():
    obj = ctx_obj()
    if obj['skip_confirm'] or obj['dry_run']:
        return

    # Print help text for current command (without options)
    ctx = click.get_current_context()
    fmt = ctx.make_formatter()
    cmd = ctx.command
    cmd.format_usage(ctx, fmt)
    cmd.format_help_text(ctx, fmt)
    click.echo(fmt.getvalue().rstrip('\n'))

    retv = click.prompt('\nDo you want to continue?',
                        type=click.Choice([
                            'Yes',
                            'No',
                            'dry-run',
                        ], case_sensitive=False),
                        default='Yes',
                        show_default=False,
                        prompt_suffix=' [press ENTER for default value \'Yes\']')

    if retv.lower() == 'no':
        ctx.abort()
    elif retv.lower() == 'dry-run':
        obj['dry_run'] = True


def sh(shell_cmd, opts=None, check=True):
    if isinstance(shell_cmd, (GeneratorType, list, tuple)):
        for cmd in shell_cmd:
            sh(cmd)
    else:
        obj = opts or ctx_obj()
        if obj['verbose'] or obj['dry_run']:
            click.echo('[SHELL] {}'.format(shell_cmd))
        if not obj['dry_run']:
            stderr = STDOUT if check else DEVNULL
            run(shell_cmd, shell=True, stderr=stderr, check=check)


def info(msg):
    if not quiet():
        click.echo(msg)


def load_ctl_lib(opts=None):
    tag = ctl_lib_tag()
    sudo = optsudo()

    sh([
        '{}docker rm ctl-lib 2> /dev/null || true'.format(sudo),
        '{}docker pull brewblox/brewblox-ctl-lib:{} || true'.format(sudo, tag),
        '{}docker create --name ctl-lib brewblox/brewblox-ctl-lib:{}'.format(sudo, tag),
        'rm -rf ./brewblox_ctl_lib 2> /dev/null || true ',
        '{}docker cp ctl-lib:/brewblox_ctl_lib ./'.format(sudo),
        '{}docker rm ctl-lib'.format(sudo),
    ], opts)

    if sudo:
        sh('sudo chown -R $USER ./brewblox_ctl_lib/', opts)
