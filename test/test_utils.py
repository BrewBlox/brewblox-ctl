"""
Tests brewblox_ctl.utils
"""

from subprocess import CalledProcessError

import pytest
from brewblox_ctl import utils

TESTED = utils.__name__


@pytest.fixture
def mocked_ext(mocker):
    mocked = [
        'input',
        'getcwd',
        'getenv_',
        'path',
        'which',
        'machine',
        'check_output',
    ]
    return {k: mocker.patch(TESTED + '.' + k) for k in mocked}


def test_confirm(mocked_ext):
    mocked_ext['input'].side_effect = [
        '',
        'flapjacks',
        'NNNNO',
        'YES',
    ]
    assert utils.confirm('what?')  # default empty
    assert utils.confirm('why?')  # yes
    assert mocked_ext['input'].call_count == 4


def test_select(mocked_ext):
    m = mocked_ext['input']
    m.return_value = 'answer'
    assert utils.select('question?') == 'answer'
    assert m.call_count == 1

    m.clear_mock()
    m.return_value = ''
    assert utils.select('other question?', 'three') == 'three'
    assert m.call_count == 2


def test_check_ok(mocked_ext):
    m = mocked_ext['check_output']
    assert utils.check_ok('whatever')
    m.side_effect = CalledProcessError(1, '')
    assert not utils.check_ok('really?')

    m.side_effect = RuntimeError()
    with pytest.raises(RuntimeError):
        utils.check_ok('truly?')


def test_path_exists(mocked_ext):
    mocked_ext['path'].exists.side_effect = [
        True,
        False,
    ]
    assert utils.path_exists('p1')
    assert not utils.path_exists('p2')


def test_command_exists(mocked_ext):
    m = mocked_ext['which']
    m.return_value = ''
    assert not utils.command_exists('wobberjacky')

    m.return_value = '/bin/promised-land'
    assert utils.command_exists('pizza')


def test_is_pi(mocked_ext):
    mocked_ext['machine'].side_effect = [
        'armv7hf',
        'armv6hf',
        'amd64',
        'x86-64',
    ]

    assert utils.is_pi()
    assert utils.is_pi()
    assert not utils.is_pi()
    assert not utils.is_pi()


def test_is_root(mocked_ext):
    assert utils.is_root()

    mocked_ext['check_output'].side_effect = CalledProcessError(1, 'permission denied')
    assert not utils.is_root()


def test_is_docker_user(mocked_ext):
    assert utils.is_docker_user()

    mocked_ext['check_output'].side_effect = CalledProcessError(1, 'not found')
    assert not utils.is_docker_user()


def test_is_brewblox_cwd(mocked_ext):
    mocked_ext['getenv_'].side_effect = [
        '',
        '1.2.3',
    ]
    assert not utils.is_brewblox_cwd()
    assert utils.is_brewblox_cwd()


def test_docker_tag(mocked_ext):
    mocked_ext['machine'].side_effect = [
        'armv7hf',
        'amd64',
        'deep-thought',
    ]
    mocked_ext['getenv_'].side_effect = [
        'edge',
        'stable',
        'stable'
    ]
    assert utils.docker_tag() == 'rpi-edge'
    assert utils.docker_tag() == 'stable'
    assert utils.docker_tag() == 'stable'


def test_ctl_lib_tag(mocked_ext):
    mocked_ext['machine'].side_effect = [
        'armv7hf',
        'amd64',
        'deep-thought',
    ]
    mocked_ext['getenv_'].side_effect = [
        '',
        'edge',
        'stable',
        'stable'
    ]
    assert utils.ctl_lib_tag() == 'rpi-edge'
    assert utils.ctl_lib_tag() == 'stable'
    assert utils.ctl_lib_tag() == 'stable'


def test_check_config(mocked_ext):
    mocked_ext['getenv_'].side_effect = [
        '1.2.3',
        '',
        '',
        '',
        '',
    ]
    mocked_ext['input'].side_effect = [
        '',
        'no',
    ]
    # version ok
    assert utils.check_config()
    # version nok, user ok
    assert not utils.check_config(required=False)
    # required version nok
    with pytest.raises(SystemExit):
        utils.check_config()
    # version nok, user nok
    with pytest.raises(SystemExit):
        utils.check_config(required=False)
