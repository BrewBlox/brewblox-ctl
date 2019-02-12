"""
Utility functions
"""

from distutils.util import strtobool
from os import getcwd
from os import getenv as getenv_
from os import path
from platform import machine
from shutil import which
from subprocess import STDOUT, CalledProcessError, check_output

from brewblox_ctl.const import CFG_VERSION_KEY, LIB_RELEASE_KEY, RELEASE_KEY


def confirm(question):
    print('{} [Y/n]'.format(question))
    while True:
        try:
            return bool(strtobool(input().lower() or 'y'))
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


def is_root():
    return check_ok('ls /root')


def is_docker_user():
    return check_ok('id -nG $USER | grep -qw "docker"')


def is_brewblox_cwd():
    return bool(getenv(CFG_VERSION_KEY))


def docker_tag():
    return '{}{}'.format(
        'rpi-' if is_pi() else '',
        getenv(RELEASE_KEY, 'stable')
    )


def ctl_lib_tag():
    release = getenv(LIB_RELEASE_KEY) or getenv(RELEASE_KEY, 'stable')
    return '{}{}'.format('rpi-' if is_pi() else '', release)


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
