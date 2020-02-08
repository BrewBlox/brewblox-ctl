"""
Tests brewblox_ctl.utils
"""

from os import path
from subprocess import DEVNULL, PIPE, STDOUT, CalledProcessError

import pytest

from brewblox_ctl import testing, utils

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
        'run',
        'set_key',
    ]
    return {k: mocker.patch(TESTED + '.' + k) for k in mocked}


@pytest.fixture
def mocked_opts(mocker):
    opts = utils.ContextOpts()
    mocker.patch(TESTED + '.ctx_opts').return_value = opts
    return opts


def test_ctx_opts():
    # Will raise an error outside click context
    with pytest.raises(RuntimeError):
        utils.ctx_opts()


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
    m = mocked_ext['run']
    assert utils.check_ok('whatever')
    m.side_effect = CalledProcessError(1, '')
    assert not utils.check_ok('really?')

    m.side_effect = RuntimeError()
    with pytest.raises(RuntimeError):
        utils.check_ok('truly?')


def test_confirm_usb(mocked_ext):
    utils.confirm_usb()
    assert mocked_ext['input'].call_count == 1


def test_setenv(mocked_ext, mocked_opts):
    set_mock = mocked_ext['set_key']

    utils.setenv('key', 'val')
    set_mock.assert_called_with(path.abspath('.env'), 'key', 'val', quote_mode='never')

    utils.setenv('key', 'other', '.other-env')
    set_mock.assert_called_with('.other-env', 'key', 'other', quote_mode='never')

    mocked_opts.dry_run = True
    utils.setenv('key', 'val-dry')
    assert set_mock.call_count == 2


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

    mocked_ext['run'].side_effect = CalledProcessError(1, 'permission denied')
    assert not utils.is_root()


def test_is_docker_user(mocked_ext):
    assert utils.is_docker_user()

    mocked_ext['run'].side_effect = CalledProcessError(1, 'not found')
    assert not utils.is_docker_user()


def test_is_brewblox_cwd(mocked_ext):
    mocked_ext['getenv_'].side_effect = [
        '',
        '1.2.3',
    ]
    assert not utils.is_brewblox_cwd()
    assert utils.is_brewblox_cwd()


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
    mocker.patch(TESTED + '.getenv').return_value = 'value'
    mocker.patch(TESTED + '.tag_prefix').return_value = 'prefix-'

    assert utils.docker_tag() == 'prefix-value'
    assert utils.docker_tag('release') == 'prefix-release'


def test_docker_tag_err(mocker):
    mocker.patch(TESTED + '.getenv').return_value = None
    mocker.patch(TESTED + '.tag_prefix').return_value = 'prefix-'

    assert utils.docker_tag('release') == 'prefix-release'
    with pytest.raises(KeyError):
        utils.docker_tag()


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


def test_sh(mocker):
    m_run = mocker.patch(TESTED + '.run')
    m_secho = mocker.patch(TESTED + '.click.secho')
    m_opts = mocker.patch(TESTED + '.ctx_opts').return_value

    m_opts.dry_run = False
    m_opts.verbose = False

    # Single call
    utils.sh('do things')
    assert m_secho.call_count == 0
    assert m_run.call_count == 1
    m_run.assert_called_with('do things',
                             shell=True,
                             check=True,
                             universal_newlines=False,
                             stdout=None,
                             stderr=STDOUT)

    m_run.reset_mock()
    m_secho.reset_mock()

    # Unchecked call
    utils.sh('do naughty things', check=False)
    assert m_secho.call_count == 0
    assert m_run.call_count == 1
    m_run.assert_called_with('do naughty things',
                             shell=True,
                             check=False,
                             universal_newlines=False,
                             stdout=None,
                             stderr=DEVNULL)

    m_run.reset_mock()
    m_secho.reset_mock()

    # Captured call
    utils.sh('gimme gimme', capture=True)
    assert m_secho.call_count == 0
    assert m_run.call_count == 1
    m_run.assert_called_with('gimme gimme',
                             shell=True,
                             check=True,
                             universal_newlines=True,
                             stdout=PIPE,
                             stderr=STDOUT)

    m_run.reset_mock()
    m_secho.reset_mock()

    # Dry run
    utils.sh('invisible shenannigans', utils.ContextOpts(dry_run=True))
    assert m_secho.call_count == 1
    assert m_run.call_count == 0

    m_run.reset_mock()
    m_secho.reset_mock()

    # List of commands
    utils.sh(['do this', 'and this', 'and that'])
    assert m_secho.call_count == 0
    assert m_run.call_count == 3

    m_run.reset_mock()
    m_secho.reset_mock()

    # Generator
    def generate():
        yield 'first'
        yield 'second'

    m_run.reset_mock()
    utils.sh(generate(), utils.ContextOpts(verbose=True))
    assert m_secho.call_count == 2
    assert m_run.call_count == 2
    m_run.assert_any_call('first',
                          shell=True,
                          check=True,
                          universal_newlines=False,
                          stdout=None,
                          stderr=STDOUT)
    m_run.assert_called_with('second',
                             shell=True,
                             check=True,
                             universal_newlines=False,
                             stdout=None,
                             stderr=STDOUT)


def test_logs(mocker):
    m_opts = mocker.patch(TESTED + '.ctx_opts').return_value
    m_secho = mocker.patch(TESTED + '.click.secho')

    m_opts.quiet = True
    utils.info('test')
    assert m_secho.call_count == 0
    utils.warn('warning')
    assert m_secho.call_count == 1
    utils.error('error')
    assert m_secho.call_count == 2

    m_opts.quiet = False
    utils.info('test')
    assert m_secho.call_count == 3
    utils.warn('warning')
    assert m_secho.call_count == 4
    utils.error('error')
    assert m_secho.call_count == 5


def test_load_ctl_lib(mocker):
    m_sudo = mocker.patch(TESTED + '.optsudo')
    m_sh = mocker.patch(TESTED + '.sh')
    m_getenv = mocker.patch(TESTED + '.getenv')

    m_sudo.return_value = 'SUDO '
    m_sh.side_effect = testing.check_sudo
    m_getenv.return_value = 'release'

    utils.load_ctl_lib()
    assert m_sh.call_count == 7

    m_sh.reset_mock()
    m_sh.side_effect = None  # remove check_sudo
    m_sudo.return_value = ''
    utils.load_ctl_lib()
    assert m_sh.call_count == 6

    m_sh.reset_mock()
    m_getenv.return_value = None
    with pytest.raises(KeyError):
        utils.load_ctl_lib()
    assert m_sh.call_count == 0
