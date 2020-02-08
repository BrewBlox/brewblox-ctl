"""
Testing utils
"""

import re
from types import GeneratorType
from unittest.mock import DEFAULT

import click
from click.testing import CliRunner


def invoke(*args, _err=None, **kwargs):
    """
    Reduces boilerplate when invoking the click test runner.
    """
    result = CliRunner().invoke(*args, **kwargs)
    if (_err is None) != (result.exception is None):
        click.echo(result.stdout)
        click.echo(result)
        raise result.exception or AssertionError('expected {}, got {}'.format(_err, type(result.exception)))
    return result


class matching:
    """Assert that a given string meets some expectations."""

    def __init__(self, pattern, flags=0):
        self._regex = re.compile(pattern, flags)

    def __eq__(self, actual):
        return bool(self._regex.match(actual))

    def __repr__(self):
        return self._regex.pattern


def check_sudo(shell_cmd, *args, **kwargs):
    """
    Utility function for checking whether there are any instances of un-sudo'd docker calls.
    Typically, utils.optsudo() is used, and mocked to return 'SUDO'.

    This function checks whether an sh call was made that forgot to prefix docker/docker-compose with optsudo.

    To use, mock utils.sh, and set this function as side effect.
    """
    if isinstance(shell_cmd, (GeneratorType, list, tuple)):
        return [check_sudo(cmd) for cmd in shell_cmd]
    elif re.match(r'(^|.*[;&\|])\s*docker', shell_cmd):
        raise AssertionError('Found docker call without sudo: "{}"'.format(shell_cmd))
    else:
        return DEFAULT
