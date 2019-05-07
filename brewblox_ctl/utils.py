"""
Utility functions
"""

from distutils.util import strtobool
from os import getcwd
from os import getenv as getenv_
from os import path
from platform import machine
from shutil import which
from subprocess import STDOUT, CalledProcessError, check_call, check_output

from brewblox_ctl.const import (CFG_VERSION_KEY, LIB_RELEASE_KEY, RELEASE_KEY,
                                SKIP_CONFIRM_KEY)


def confirm(question, default=True):
    prompt = '{} [Y/n]' if default else '{} [y/N]'
    print(prompt.format(question))
    while True:
        try:
            return bool(strtobool(input().lower() or str(default)))
        except ValueError:
            print('Please respond with \'y(es)\' or \'n(o)\'.')


def select(question, default=''):
    answer = input('{} {}'.format(question, '[{}]'.format(default) if default else ''))
    return answer or default


def check_ok(cmd):
    try:
        check_output(cmd, shell=True, stderr=STDOUT)
        return True
    except CalledProcessError:
        return False


def getenv(env, default=None):
    return getenv_(env, default)


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


def skipping_confirm():
    return bool(strtobool(getenv(SKIP_CONFIRM_KEY, 'false')))


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


def prompt_usb():
    input('Please press ENTER when your Spark is connected over USB')


def announce(shell_cmds):
    print('The following shell commands will be used: \n')
    for cmd in shell_cmds:
        print('\t', cmd)
    print('')
    input('Press ENTER to continue, Ctrl+C to cancel')


def run(shell_cmd):
    print('\n' + 'Running command: \n\t', shell_cmd, '\n')
    return check_call(shell_cmd, shell=True, stderr=STDOUT)


def run_all(shell_cmds, prompt=True):
    if prompt and not skipping_confirm():
        announce(shell_cmds)
    return [run(cmd) for cmd in shell_cmds]


def lib_loading_commands():
    tag = ctl_lib_tag()
    sudo = optsudo()
    shell_commands = [
        '{}docker rm ctl-lib 2> /dev/null || true'.format(sudo),
        '{}docker pull brewblox/brewblox-ctl-lib:{} || true'.format(sudo, tag),
        '{}docker create --name ctl-lib brewblox/brewblox-ctl-lib:{}'.format(sudo, tag),
        'rm -rf ./brewblox_ctl_lib 2> /dev/null || true ',
        '{}docker cp ctl-lib:/brewblox_ctl_lib ./'.format(sudo),
        '{}docker rm ctl-lib'.format(sudo),
    ]

    if sudo:
        shell_commands += [
            'sudo chown -R $USER ./brewblox_ctl_lib/',
        ]

    return shell_commands
