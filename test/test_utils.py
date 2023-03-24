"""
Tests brewblox_ctl.utils
"""

import json
from subprocess import DEVNULL, PIPE, STDOUT, CalledProcessError
from unittest.mock import call

import click
import pytest

from brewblox_ctl import const, utils

TESTED = utils.__name__


@pytest.fixture
def m_getenv(mocker):
    return mocker.patch(TESTED + '.getenv', autospec=True)


@pytest.fixture
def m_sh(mocker):
    return mocker.patch(TESTED + '.sh', autospec=True)


@pytest.fixture
def mocked_ext(mocker):
    mocked = [
        'input',
        'shutil.which',
        'platform.machine',
        'platform.version',
        'run',
        'dotenv.set_key',
        'dotenv.unset_key',
        'dotenv_values',
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


def test_path_exists(mocker):
    m_path = mocker.patch(TESTED + '.Path').return_value
    m_path.exists.side_effect = [
        True,
        False,
    ]
    assert utils.path_exists('p1')
    assert not utils.path_exists('p2')


def test_command_exists(mocked_ext):
    m = mocked_ext['shutil.which']
    m.return_value = ''
    assert not utils.command_exists('wobberjacky')

    m.return_value = '/bin/promised-land'
    assert utils.command_exists('pizza')


@pytest.mark.parametrize('combo', [
    ('armv7hf', False),
    ('armv6hf', True),
    ('amd64', False),
    ('x86-64', False),
])
def test_is_armv6(combo, mocked_ext):
    machine, result = combo
    mocked_ext['platform.machine'].return_value = machine
    assert utils.is_armv6() is result


@pytest.mark.parametrize('combo', [
    ('Linux version 5.4.0-88-generic', False),
    ('Linux version 5.4.0-88-Microsoft', True),
])
def test_is_wsl(combo, mocked_ext):
    version, result = combo
    mocked_ext['platform.version'].return_value = version
    assert utils.is_wsl() is result


def test_docker_tag(mocker):
    mocker.patch(TESTED + '.getenv').return_value = 'value'

    assert utils.docker_tag() == 'value'
    assert utils.docker_tag('release') == 'release'


def test_docker_tag_err(mocker):
    mocker.patch(TESTED + '.getenv').return_value = None

    assert utils.docker_tag('release') == 'release'
    with pytest.raises(KeyError):
        utils.docker_tag()


def test_check_config(mocker, mocked_ext):
    m_is_brewblox_dir = mocker.patch(TESTED + '.is_brewblox_dir')
    m_is_brewblox_dir.side_effect = [
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


def test_sh_stream(mocker):
    m_opts = mocker.patch(TESTED + '.ctx_opts').return_value
    m_opts.verbose = False
    m_popen = mocker.patch(TESTED + '.Popen')
    m_popen.return_value.stdout.readline.side_effect = [
        'line 1',
        '',
        'line 2',
        'line 3',
        ''
    ]
    m_popen.return_value.poll.side_effect = [
        None,
        0,
    ]
    assert list(utils.sh_stream('cmd')) == [
        'line 1',
        '',
        'line 2',
        'line 3',
    ]


def test_sh_stream_empty(mocker):
    m_opts = mocker.patch(TESTED + '.ctx_opts').return_value
    m_opts.verbose = True
    m_popen = mocker.patch(TESTED + '.Popen')
    m_popen.return_value.stdout.readline.side_effect = ['']
    m_popen.return_value.poll.side_effect = [0]
    assert list(utils.sh_stream('cmd')) == []


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


def test_pip_install(mocker, m_sh):
    utils.pip_install('lib', 'lib2')
    m_sh.assert_called_with('python3 -m pip install --upgrade --no-cache-dir --prefer-binary lib lib2')


def test_esptool(mocked_ext, m_sh):
    m_which = mocked_ext['shutil.which']
    m_which.return_value = ''

    utils.esptool('--chip esp32', 'read_flash', 'coredump.bin')
    m_sh.assert_called_with('sudo -E env "PATH=$PATH" esptool.py --chip esp32 read_flash coredump.bin')
    assert m_sh.call_count == 2

    m_sh.reset_mock()
    m_which.return_value = 'esptool.py'
    utils.esptool()
    m_sh.assert_called_with('sudo -E env "PATH=$PATH" esptool.py ')
    assert m_sh.call_count == 1


def test_show_data(mocker):
    m_opts = mocker.patch(TESTED + '.ctx_opts').return_value
    m_secho = mocker.patch(TESTED + '.click.secho')

    utils.show_data('desc', 'text')
    utils.show_data('desc', {'obj': True})
    assert m_secho.call_count == 4
    m_secho.assert_called_with(json.dumps({'obj': True}, indent=2), fg='blue', color=m_opts.color)

    m_secho.reset_mock()
    m_opts.dry_run = False
    m_opts.verbose = False

    utils.show_data('desc', 'text')
    assert m_secho.call_count == 0


def test_get_urls(m_getenv):
    m_getenv.side_effect = [
        '1234',
        '4321',
    ]
    assert utils.history_url() == f'{const.HOST}:1234/history/history'
    assert utils.datastore_url() == f'{const.HOST}:4321/history/datastore'

    assert m_getenv.call_args_list == [
        call(const.ENV_KEY_PORT_HTTPS, '443'),
        call(const.ENV_KEY_PORT_HTTPS, '443'),
    ]


def test_host_ip(m_getenv):
    m_getenv.side_effect = [
        '192.168.0.100 54321 192.168.0.69 22',
        '',
    ]
    assert utils.host_ip() == '192.168.0.69'
    assert utils.host_ip() == '127.0.0.1'


def test_list_services():
    services = utils.list_services(
        'ghcr.io/brewblox/brewblox-history',
        'brewblox_ctl/deployed/config/docker-compose.shared.yml')
    assert services == ['history']


def test_read_shared_compose():
    cfg = utils.read_shared_compose(
        'brewblox_ctl/deployed/config/docker-compose.shared.yml')
    assert 'history' in cfg['services']


@pytest.mark.parametrize('name', [
    'spark-one',
    'sparkey',
    'spark_three',
    'spark4',
])
def test_check_service_name(name):
    assert utils.check_service_name(None, 'name', name) == name


@pytest.mark.parametrize('name', [
    '',
    'spark one',
    'Sparkey',
    'spark#',
    's/park',
])
def test_check_service_name_err(name):
    with pytest.raises(click.BadParameter):
        utils.check_service_name(None, 'name', name)
