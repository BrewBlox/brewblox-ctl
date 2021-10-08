"""
Tests brewblox_ctl.commands.device
"""

import pytest
from brewblox_ctl.testing import check_sudo, invoke
from brewblox_ctl.commands import add_device

TESTED = add_device.__name__


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
    m = mocker.patch(TESTED + '.utils')
    m.optsudo.return_value = 'SUDO '
    return m


@pytest.fixture
def m_sh(mocker):
    m = mocker.patch(TESTED + '.sh')
    m.side_effect = check_sudo
    return m


@pytest.fixture
def m_find(mocker):
    m = mocker.patch(TESTED + '.find_device')
    m.side_effect = lambda _1, _2: {
        'id': '280038000847343337373738',
        'host': '192.168.0.55',
        'port': 8332
    }
    return m


def test_discover_spark(m_utils, mocker):
    def m_discover_func(discovery_type):
        yield from [{'desc': 'one'}, {'desc': 'two'}]

    m_discover = mocker.patch(TESTED + '.discover_device',
                              side_effect=m_discover_func)

    invoke(add_device.discover_spark)
    assert m_discover.called_with('all')
    assert m_utils.info.call_count == 3

    invoke(add_device.discover_spark, '--discovery=wifi')
    assert m_discover.called_with('wifi')
    assert m_utils.info.call_count == 6


def test_add_spark(m_utils, m_sh, mocker, m_find):
    m_utils.read_compose.side_effect = lambda: {'services': {}}

    invoke(add_device.add_spark, '--name testey --discover-now --discovery wifi --command "--do-stuff"')
    invoke(add_device.add_spark, input='testey\n')

    m_utils.confirm.return_value = False
    invoke(add_device.add_spark, '-n testey')

    m_find.side_effect = lambda _1, _2: None
    invoke(add_device.add_spark, '--name testey --discovery wifi', _err=True)
    invoke(add_device.add_spark, '--name testey --device-host 1234')
    invoke(add_device.add_spark, '--name testey --device-id 12345 --simulation')


def test_add_spark_force(m_utils, m_sh, mocker, m_find):
    m_utils.confirm.return_value = False
    m_utils.read_compose.side_effect = lambda: {'services': {'testey': {}}}

    invoke(add_device.add_spark, '--name testey', _err=True)
    invoke(add_device.add_spark, '--name testey --force')


def test_spark_overwrite(m_utils, m_sh, m_find, mocker):
    m_utils.read_compose.side_effect = lambda: {
        'services': {
            'testey': {
                'image': 'brewblox/brewblox-devcon-spark:develop'
            }}}

    invoke(add_device.add_spark, '--name testey --force')
    assert m_utils.warn.call_count == 0

    invoke(add_device.add_spark, '--name new-testey')
    assert m_utils.warn.call_count > 0


def test_add_tilt(m_utils, m_sh, mocker):
    m_utils.read_compose.side_effect = lambda: {'services': {}}
    invoke(add_device.add_tilt)
    assert m_sh.call_count == 2

    m_sh.reset_mock()
    m_utils.confirm.return_value = False
    invoke(add_device.add_tilt)
    assert m_sh.call_count == 1

    m_sh.reset_mock()
    m_utils.read_compose.side_effect = lambda: {'services': {'tilt': {}}}
    invoke(add_device.add_tilt, _err=True)
    assert m_sh.call_count == 0


def test_add_tilt_force(m_utils, m_sh, mocker, m_find):
    m_utils.confirm.return_value = False
    m_utils.read_compose.side_effect = lambda: {'services': {'tilt': {}}}

    invoke(add_device.add_tilt, _err=True)
    invoke(add_device.add_tilt, '--force')


def test_add_plaato(m_utils, m_sh, mocker):
    m_utils.read_compose.side_effect = lambda: {'services': {}}

    invoke(add_device.add_plaato, '--name testey --token x')
    invoke(add_device.add_plaato, input='testey\ntoken\n')
    assert m_sh.call_count == 2

    m_sh.reset_mock()
    m_utils.confirm.return_value = False
    invoke(add_device.add_plaato, '-n testey --token x')
    assert m_sh.call_count == 0


def test_add_plaato_force(m_utils, m_sh, mocker, m_find):
    m_utils.confirm.return_value = False
    m_utils.read_compose.side_effect = lambda: {'services': {'testey': {}}}

    invoke(add_device.add_plaato, '--name testey --token x', _err=True)
    invoke(add_device.add_plaato, '--name testey --token x --force')


def test_add_node_red(m_utils, m_sh, mocker):
    m_utils.read_compose.side_effect = lambda: {'services': {}}
    invoke(add_device.add_node_red)
    assert m_sh.call_count == 2

    m_sh.reset_mock()
    m_utils.confirm.return_value = False
    invoke(add_device.add_node_red)
    assert m_sh.call_count == 1


def test_add_node_red_other_uid(m_utils, m_sh, mocker, m_getuid):
    m_getuid.return_value = 1001
    m_utils.read_compose.side_effect = lambda: {'services': {}}
    invoke(add_device.add_node_red)
    assert m_sh.call_count == 3


def test_add_node_red_force(m_utils, m_sh, mocker, m_find):
    m_utils.confirm.return_value = False
    m_utils.read_compose.side_effect = lambda: {'services': {'node-red': {}}}
    invoke(add_device.add_node_red, _err=True)
    invoke(add_device.add_node_red, '--force')
