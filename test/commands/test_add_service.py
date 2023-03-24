"""
Tests brewblox_ctl.commands.add_service
"""

import pytest

from brewblox_ctl.commands import add_service
from brewblox_ctl.testing import check_sudo, invoke

TESTED = add_service.__name__


@pytest.fixture(autouse=True)
def m_getgid(mocker):
    m = mocker.patch(TESTED + '.getgid')
    m.return_value = 1000
    return m


@pytest.fixture(autouse=True)
def m_getuid(mocker):
    m = mocker.patch(TESTED + '.getuid')
    m.return_value = 1000
    return m


@pytest.fixture
def m_utils(mocker):
    m = mocker.patch(TESTED + '.utils', autospec=True)
    m.optsudo.return_value = 'SUDO '
    return m


@pytest.fixture
def m_sh(mocker):
    m = mocker.patch(TESTED + '.sh', autospec=True)
    m.side_effect = check_sudo
    return m


@pytest.fixture
def m_choose(mocker):
    m = mocker.patch(TESTED + '.choose_device')
    m.side_effect = lambda _1, _2: {
        'id': '280038000847343337373738',
        'host': '192.168.0.55',
    }
    return m


@pytest.fixture
def m_find_by_host(mocker):
    m = mocker.patch(TESTED + '.find_device_by_host')
    m.side_effect = lambda _1: {
        'id': '280038000847343337373738',
        'host': '192.168.0.55',
    }
    return m


def test_discover_spark(m_utils, mocker):
    m_discover = mocker.patch(TESTED + '.list_devices', autospec=True)

    m_utils.read_compose.return_value = {'services': {}}
    invoke(add_service.discover_spark)
    m_discover.assert_called_with('all', {'services': {}})

    m_utils.read_compose.side_effect = FileNotFoundError
    invoke(add_service.discover_spark)
    m_discover.assert_called_with('all', {})


def test_add_spark(m_utils, m_sh, mocker, m_choose, m_find_by_host):
    m_utils.read_compose.side_effect = lambda: {'services': {}}
    m_utils.confirm.return_value = True

    invoke(add_service.add_spark, '--name testey --discover-now --discovery wifi --command "--do-stuff"')
    invoke(add_service.add_spark, input='testey\n')

    invoke(add_service.add_spark, '-n testey')

    m_choose.side_effect = lambda _1, _2=None: None
    invoke(add_service.add_spark, '--name testey --discovery wifi', _err=True)
    invoke(add_service.add_spark, '--name testey --device-host 1234')
    invoke(add_service.add_spark, '--name testey --device-id 12345 --simulation')
    invoke(add_service.add_spark, '--name testey --simulation')


def test_add_spark_yes(m_utils, m_sh, mocker, m_choose):
    m_utils.confirm.return_value = False

    m_utils.read_compose.side_effect = lambda: {'services': {}}
    invoke(add_service.add_spark, '--name testey', _err=True)
    invoke(add_service.add_spark, '--name testey --yes')

    m_utils.read_compose.side_effect = lambda: {'services': {'testey': {}}}
    invoke(add_service.add_spark, '--name testey', _err=True)
    invoke(add_service.add_spark, '--name testey --yes')


def test_spark_overwrite(m_utils, m_sh, m_choose, mocker):
    m_utils.read_compose.side_effect = lambda: {
        'services': {
            'testey': {
                'image': 'ghcr.io/brewblox/brewblox-devcon-spark:develop'
            }}}

    invoke(add_service.add_spark, '--name testey --yes')
    assert m_utils.warn.call_count == 0

    invoke(add_service.add_spark, '--name new-testey')
    assert m_utils.warn.call_count > 0


def test_add_tilt(m_utils, m_sh, mocker):
    m_utils.read_compose.side_effect = lambda: {'services': {}}
    m_utils.confirm.return_value = True
    invoke(add_service.add_tilt)
    assert m_sh.call_count == 2

    m_sh.reset_mock()
    m_utils.confirm.return_value = False
    invoke(add_service.add_tilt, _err=True)
    assert m_sh.call_count == 0

    m_sh.reset_mock()
    m_utils.read_compose.side_effect = lambda: {'services': {'tilt': {}}}
    invoke(add_service.add_tilt, _err=True)
    assert m_sh.call_count == 0


def test_add_tilt_yes(m_utils, m_sh, mocker, m_choose):
    m_utils.confirm.return_value = False
    m_utils.read_compose.side_effect = lambda: {'services': {'tilt': {}}}

    invoke(add_service.add_tilt, _err=True)
    invoke(add_service.add_tilt, '--yes')


def test_add_plaato(m_utils, m_sh, mocker):
    m_utils.read_compose.side_effect = lambda: {'services': {}}

    invoke(add_service.add_plaato, '--name testey --token x')
    invoke(add_service.add_plaato, input='testey\ntoken\n')
    assert m_sh.call_count == 2

    m_sh.reset_mock()
    m_utils.confirm.return_value = False
    invoke(add_service.add_plaato, '-n testey --token x', _err=True)
    assert m_sh.call_count == 0


def test_add_plaato_yes(m_utils, m_sh, mocker, m_choose):
    m_utils.confirm.return_value = False
    m_utils.read_compose.side_effect = lambda: {'services': {'testey': {}}}

    invoke(add_service.add_plaato, '--name testey --token x', _err=True)
    invoke(add_service.add_plaato, '--name testey --token x --yes')


def test_add_node_red(m_utils, m_sh, mocker):
    m_utils.read_compose.side_effect = lambda: {'services': {}}
    m_utils.confirm.return_value = True
    invoke(add_service.add_node_red)
    assert m_sh.call_count == 2

    m_sh.reset_mock()
    m_utils.confirm.return_value = False
    invoke(add_service.add_node_red, _err=True)
    assert m_sh.call_count == 0


def test_add_node_red_other_uid(m_utils, m_sh, mocker, m_getuid):
    m_getuid.return_value = 1001
    m_utils.confirm.return_value = True
    m_utils.read_compose.side_effect = lambda: {'services': {}}
    invoke(add_service.add_node_red)
    assert m_sh.call_count == 3


def test_add_node_red_yes(m_utils, m_sh, mocker, m_choose):
    m_utils.confirm.return_value = False
    m_utils.read_compose.side_effect = lambda: {'services': {'node-red': {}}}
    invoke(add_service.add_node_red, _err=True)
    invoke(add_service.add_node_red, '--yes')
