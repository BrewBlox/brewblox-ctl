"""
Tests brewblox_ctl.commands.experimental
"""

from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from brewblox_ctl import utils
from brewblox_ctl.commands import experimental
from brewblox_ctl.discovery import DiscoveredDevice
from brewblox_ctl.testing import invoke

TESTED = experimental.__name__


@pytest.fixture
def m_choose(mocker: MockerFixture):
    m = mocker.patch(TESTED + '.choose_device', autospec=True)
    m.side_effect = lambda _1, _2: DiscoveredDevice(
        discovery='mDNS', model='Spark 4', device_id='c4dd5766bb18', device_host='192.168.0.55'
    )
    return m


@pytest.fixture
def m_find(mocker: MockerFixture):
    m = mocker.patch(TESTED + '.find_device_by_host', autospec=True)
    m.side_effect = lambda host: DiscoveredDevice(
        discovery='mDNS',
        model='Spark 4',
        device_id='c4dd5766bb18',
        device_host=host,
    )
    return m


def test_enable_spark_mqtt_empty(m_choose: Mock, m_sh: Mock):
    m_choose.side_effect = lambda _1, _2: None

    invoke(experimental.enable_spark_mqtt, '--cert-file=README.md')
    assert m_sh.call_count == 0

    utils.get_opts().dry_run = True
    invoke(experimental.enable_spark_mqtt, '--cert-file=README.md')
    assert m_sh.call_count > 0


def test_enable_spark_mqtt(m_choose: Mock, m_find: Mock, m_sh: Mock):
    invoke(experimental.enable_spark_mqtt, '--cert-file=README.md')
    invoke(experimental.enable_spark_mqtt, '--cert-file=README.md --server-host=192.168.0.1 --server-port=8888')
    invoke(experimental.enable_spark_mqtt, '--cert-file=README.md --device-host=192.168.0.1')
    assert m_choose.call_count == 2
    assert m_find.call_count == 1

    # When device ID is set, credentials are not sent
    invoke(experimental.enable_spark_mqtt, '--cert-file=README.md --device-id=12345678')
    assert ' 12345678 ' in m_sh.call_args_list[-2][0][0]
    assert 'docker compose kill' in m_sh.call_args_list[-1][0][0]
