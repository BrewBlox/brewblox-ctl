"""
Tests brewblox_ctl.commands.add_service
"""

from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from brewblox_ctl.commands import add_service
from brewblox_ctl.discovery import DiscoveredDevice, DiscoveryType
from brewblox_ctl.testing import invoke

TESTED = add_service.__name__


@pytest.fixture(autouse=True)
def m_list_devices(mocker: MockerFixture) -> Mock:
    m = mocker.patch(TESTED + '.list_devices', autospec=True)
    return m


@pytest.fixture(autouse=True)
def m_choose(mocker: MockerFixture):
    m = mocker.patch(TESTED + '.choose_device', autospec=True)
    m.side_effect = lambda _1, _2: DiscoveredDevice(
        discovery='mDNS', model='Spark 4', device_id='280038000847343337373738', device_host='192.168.0.55'
    )
    return m


@pytest.fixture(autouse=True)
def m_find_by_host(mocker: MockerFixture):
    m = mocker.patch(TESTED + '.find_device_by_host', autospec=True)
    m.side_effect = lambda _1: DiscoveredDevice(
        discovery='mDNS', model='Spark 4', device_id='280038000847343337373738', device_host='192.168.0.55'
    )
    return m


def test_discover_spark(m_read_compose: Mock, m_list_devices: Mock):
    m_read_compose.return_value = {'services': {}}
    invoke(add_service.discover_spark)
    m_list_devices.assert_called_with(DiscoveryType.all, {'services': {}})

    m_read_compose.side_effect = FileNotFoundError
    invoke(add_service.discover_spark)
    m_list_devices.assert_called_with(DiscoveryType.all, None)


def test_add_spark(m_choose: Mock, m_read_compose: Mock, m_confirm: Mock):
    m_read_compose.side_effect = lambda: {'services': {}}
    m_confirm.return_value = True

    invoke(add_service.add_spark, '--name testey --discover-now --discovery mdns')
    invoke(add_service.add_spark, input='testey\n')

    invoke(add_service.add_spark, '-n testey')

    m_choose.side_effect = lambda _1, _2=None: None
    invoke(add_service.add_spark, '--name testey --discovery mdns', _err=True)
    invoke(add_service.add_spark, '--name testey --device-host 1234')
    invoke(add_service.add_spark, '--name testey --device-id 12345 --simulation')
    invoke(add_service.add_spark, '--name testey --simulation')


def test_add_spark_yes(m_read_compose: Mock, m_confirm: Mock):
    m_confirm.return_value = False

    m_read_compose.side_effect = lambda: {'services': {}}
    invoke(add_service.add_spark, '--name testey', _err=True)
    invoke(add_service.add_spark, '--name testey --yes')

    m_read_compose.side_effect = lambda: {'services': {'testey': {}}}
    invoke(add_service.add_spark, '--name testey', _err=True)
    invoke(add_service.add_spark, '--name testey --yes')


def test_spark_overwrite(m_read_compose: Mock):
    m_read_compose.side_effect = lambda: {
        'services': {'testey': {'image': 'ghcr.io/brewblox/brewblox-devcon-spark:develop'}}
    }

    invoke(add_service.add_spark, '--name testey --yes')
    invoke(add_service.add_spark, '--name new-testey')


def test_add_tilt(m_sh: Mock, m_read_compose: Mock, m_confirm: Mock):
    m_read_compose.side_effect = lambda: {'services': {}}
    m_confirm.return_value = True
    invoke(add_service.add_tilt)
    assert m_sh.call_count == 2

    m_sh.reset_mock()
    m_confirm.return_value = False
    invoke(add_service.add_tilt, _err=True)
    assert m_sh.call_count == 0

    m_sh.reset_mock()
    m_read_compose.side_effect = lambda: {'services': {'tilt': {}}}
    invoke(add_service.add_tilt, _err=True)
    assert m_sh.call_count == 0


def test_add_tilt_yes(m_read_compose: Mock, m_confirm: Mock):
    m_confirm.return_value = False
    m_read_compose.side_effect = lambda: {'services': {'tilt': {}}}

    invoke(add_service.add_tilt, _err=True)
    invoke(add_service.add_tilt, '--yes')


def test_add_plaato(m_sh: Mock, m_read_compose: Mock, m_confirm: Mock):
    m_read_compose.side_effect = lambda: {'services': {}}

    invoke(add_service.add_plaato, '--name testey --token x')
    invoke(add_service.add_plaato, input='testey\ntoken\n')
    assert m_sh.call_count == 2

    m_sh.reset_mock()
    m_confirm.return_value = False
    invoke(add_service.add_plaato, '-n testey --token x', _err=True)
    assert m_sh.call_count == 0


def test_add_plaato_yes(m_read_compose: Mock, m_confirm: Mock):
    m_confirm.return_value = False
    m_read_compose.side_effect = lambda: {'services': {'testey': {}}}

    invoke(add_service.add_plaato, '--name testey --token x', _err=True)
    invoke(add_service.add_plaato, '--name testey --token x --yes')
