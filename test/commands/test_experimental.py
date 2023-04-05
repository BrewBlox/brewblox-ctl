"""
Tests brewblox_ctl.commands.experimental
"""

import pytest

from brewblox_ctl.commands import experimental
from brewblox_ctl.discovery import DiscoveredDevice
from brewblox_ctl.testing import check_sudo, invoke

TESTED = experimental.__name__


@pytest.fixture
def m_utils(mocker):
    m = mocker.patch(TESTED + '.utils', autospec=True)
    m.host_lan_ip.return_value = 'external-host'
    m.optsudo.return_value = 'SUDO '
    m.random_string.return_value = 'password_string'
    return m


@pytest.fixture
def m_sh(mocker):
    m = mocker.patch(TESTED + '.sh', autospec=True)
    m.side_effect = check_sudo
    return m


@pytest.fixture
def m_choose(mocker):
    m = mocker.patch(TESTED + '.choose_device', autospec=True)
    m.side_effect = lambda _1, _2: DiscoveredDevice(
        discovery='mDNS',
        model='Spark 4',
        device_id='c4dd5766bb18',
        device_host='192.168.0.55'
    )
    return m


@pytest.fixture
def m_find(mocker):
    m = mocker.patch(TESTED + '.find_device_by_host', autospec=True)
    m.side_effect = lambda host: DiscoveredDevice(
        discovery='mDNS',
        model='Spark 4',
        device_id='c4dd5766bb18',
        device_host=host,
    )
    return m


def test_enable_spark_mqtt_empty(m_sh, m_utils, m_choose):
    m_choose.side_effect = lambda _1, _2: None
    invoke(experimental.enable_spark_mqtt)
    assert m_sh.call_count == 0


def test_enable_spark_mqtt(m_sh, m_utils, m_choose, m_find):
    invoke(experimental.enable_spark_mqtt)
    invoke(experimental.enable_spark_mqtt, '--system-host=192.168.0.1 --system-port=8888')
    invoke(experimental.enable_spark_mqtt, '--device-host=192.168.0.1')
    assert m_choose.call_count == 2
    assert m_find.call_count == 1
