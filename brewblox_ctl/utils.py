"""
Utility functions
"""

import platform
import shutil
from distutils.util import strtobool
from os import getcwd, getenv, path
from subprocess import STDOUT, CalledProcessError, check_output


def is_pi():
    return platform.machine().startswith('arm')


def is_root():
    return check_ok('ls /root')


def is_docker_user():
    return check_ok('id -nG $USER | grep -qw "docker"')


def base_dir():
    return path.dirname(__file__)


def is_brewblox_cwd():
    return bool(getenv('BREWBLOX_CFG_VERSION'))


def docker_tag():
    return '{}{}'.format(
        'rpi-' if is_pi() else '',
        getenv('BREWBLOX_RELEASE', 'stable')
    )


def ctl_lib_tag():
    release = getenv('BREWBLOX_CTL_LIB_RELEASE') or getenv('BREWBLOX_RELEASE', 'stable')
    return '{}{}'.format('rpi-' if is_pi() else '', release)


def command_exists(cmd):
    return bool(shutil.which(cmd))


def path_exists(path_name):
    return path.exists(path_name)


def check_ok(cmd):
    try:
        check_output(cmd, shell=True, stderr=STDOUT)
        return True
    except CalledProcessError:
        return False


def confirm(question):
    print('{} [Y/n]'.format(question))
    while True:
        try:
            return strtobool(input().lower() or 'y')
        except ValueError:
            print('Please respond with \'y(es)\' or \'n(o)\'.')


def select(question, default=''):
    answer = input('{} {}'.format(question, '[{}]'.format(default) if default else ''))
    return answer or default


def choose(question, choices, default=''):
    display_choices = ' / '.join(['[{}]'.format(c) if c == default else c for c in choices])
    print(question, display_choices)
    valid_answers = [c.lower() for c in choices]
    while True:
        answer = input().lower() or default.lower()
        if answer in valid_answers:
            return answer
        print('Please choose one:', display_choices)


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
