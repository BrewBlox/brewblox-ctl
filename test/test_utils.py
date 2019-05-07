"""
Tests brewblox_ctl.utils
"""

from subprocess import CalledProcessError
from unittest.mock import call

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
        'check_call',
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


@pytest.mark.parametrize('combo', [
    ('armv7hf', True),
    ('armv6hf', True),
    ('amd64', False),
    ('x86-64', False)
])
def test_is_pi(combo, mocked_ext):
    machine, result = combo
    mocked_ext['machine'].return_value = machine
    assert utils.is_pi() is result


@pytest.mark.parametrize('combo', [
    ('armv7hf', False),
    ('armv6hf', True),
    ('amd64', False),
    ('x86-64', False)
])
def test_is_v6(combo, mocked_ext):
    machine, result = combo
    mocked_ext['machine'].return_value = machine
    assert utils.is_v6() is result


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


@pytest.mark.parametrize('combo', [
    ('True', True),
    ('False', False),
    ('false', False),
    ('1', True),
    ('0', False)
])
def test_skipping_confirm(combo, mocked_ext):
    mocked_ext['getenv_'].return_value = combo[0]
    assert utils.skipping_confirm() == combo[1]


def test_optsudo(mocker):
    m = mocker.patch(TESTED + '.is_docker_user')
    m.side_effect = [
        True,
        False,
    ]
    assert utils.optsudo() == ''
    assert utils.optsudo() == 'sudo '


@pytest.mark.parametrize('combo', [
    ('armv6', 'rpi-'),
    ('armv7hf', 'rpi-'),
    ('amd64', ''),
    ('deep-thought', ''),
])
def test_tag_prefix(combo, mocked_ext):
    machine, result = combo
    mocked_ext['machine'].return_value = machine
    assert utils.tag_prefix() == result


def test_docker_tag(mocker):
    mocker.patch(TESTED + '.tag_prefix').return_value = 'prefix'
    mocker.patch(TESTED + '.getenv').return_value = 'value'

    assert utils.docker_tag() == 'prefixvalue'
    assert utils.docker_tag('release') == 'prefixrelease'


@pytest.mark.parametrize('combo', [
    (['armv7hf'], ['', 'edge'], 'rpi-edge'),
    (['amd64'], ['stable'], 'stable'),
    (['deep-thought'], ['stable'], 'stable'),
])
def test_ctl_lib_tag(combo, mocked_ext):
    machine, env, result = combo

    mocked_ext['machine'].side_effect = machine
    mocked_ext['getenv_'].side_effect = env
    assert utils.ctl_lib_tag() == result


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


def test_prompt_usb(mocked_ext):
    utils.prompt_usb()
    assert mocked_ext['input'].call_count == 1


def test_announce(mocked_ext):
    utils.announce(['cmd1', 'cmd2'])
    assert mocked_ext['input'].call_count == 1


def test_run(mocked_ext):
    utils.run('cmd')
    mocked_ext['check_call'].assert_called_once_with('cmd', shell=True, stderr=utils.STDOUT)


def test_run_all(mocked_ext, mocker):
    s_m = mocker.patch(TESTED + '.skipping_confirm')
    a_m = mocker.patch(TESTED + '.announce')
    r_m = mocker.patch(TESTED + '.run')

    s_m.side_effect = [
        True,
        False,
    ]

    utils.run_all(['cmd1', 'cmd2'], False)
    utils.run_all(['cmd3', 'cmd4'])
    utils.run_all(['cmd5', 'cmd6'])

    assert s_m.call_count == 2

    assert r_m.call_args_list == [
        call('cmd1'),
        call('cmd2'),
        call('cmd3'),
        call('cmd4'),
        call('cmd5'),
        call('cmd6'),
    ]

    assert a_m.call_args_list == [
        call(['cmd5', 'cmd6'])
    ]


def test_lib_loading_command(mocker):
    ctl_lib_tag = mocker.patch(TESTED + '.ctl_lib_tag')
    optsudo = mocker.patch(TESTED + '.optsudo')

    ctl_lib_tag.side_effect = [
        'edge',
        'rpi-stable'
    ]

    optsudo.side_effect = [
        '',
        'sudo ',
    ]

    cmds = utils.lib_loading_commands()
    assert len(cmds) == 6  # no chown
    assert 'sudo' not in ' '.join(cmds)

    cmds = utils.lib_loading_commands()
    assert len(cmds) == 7  # sudo requires a chown
    assert 'sudo' in ' '.join(cmds)
