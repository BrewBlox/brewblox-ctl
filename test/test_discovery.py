"""
Tests brewblox_ctl.discovery
"""

from socket import inet_aton
from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture
from zeroconf import ServiceInfo, ServiceStateChange

from brewblox_ctl import const, discovery
from brewblox_ctl.discovery import DiscoveredDevice, DiscoveryType
from brewblox_ctl.testing import matching

TESTED = discovery.__name__


class ServiceBrowserMock:
    def __init__(self, conf, service_type, handlers):
        self.conf = conf
        self.service_type = service_type
        self.handlers = handlers

        for name in ['id0', 'id1', 'id2']:
            for handler in self.handlers:
                handler(zeroconf=conf, service_type=service_type, name=name, state_change=ServiceStateChange.Added)
                handler(zeroconf=conf, service_type=service_type, name=name, state_change=ServiceStateChange.Removed)


@pytest.fixture(autouse=True)
def m_conf(mocker: MockerFixture):
    def get_service_info(service_type, name):
        dns_type = discovery.BREWBLOX_DNS_TYPE
        service_name = f'{name}.{dns_type}'
        if name == 'id0':
            return ServiceInfo(
                service_type,
                service_name,
                addresses=[inet_aton('0.0.0.0')],
                properties={
                    b'ID': b'id0',
                    b'HW': b'Spark 3',
                },
            )
        if name == 'id1':
            return ServiceInfo(
                service_type,
                service_name,
                server=f'{name}.local.',
                addresses=[inet_aton('1.2.3.4')],
                port=1234,
                properties={
                    b'ID': b'id1',
                    b'HW': b'Spark 3',
                },
            )
        if name == 'id2':
            return ServiceInfo(
                service_type,
                service_name,
                server=f'{name}.local.',
                addresses=[inet_aton('4.3.2.1')],
                port=4321,
                properties={
                    b'ID': b'id2',
                    b'HW': b'Spark 4',
                },
            )

    def close():
        pass

    m = mocker.patch(TESTED + '.Zeroconf')
    m.return_value.get_service_info = get_service_info
    m.return_value.close = close
    return m


@pytest.fixture(autouse=True)
def m_browser(mocker: MockerFixture):
    mocker.patch(TESTED + '.DISCOVER_TIMEOUT_S', 0.01)
    return mocker.patch(TESTED + '.ServiceBrowser', ServiceBrowserMock)


@pytest.fixture(autouse=True)
def m_usb(mocker: MockerFixture):
    m_dev = Mock()
    m_dev.idProduct = const.PID_P1

    m = mocker.patch(TESTED + '.usb', autospec=True)
    m.core.find.return_value = [m_dev]
    m.util.get_string.return_value = '4F0052000551353432383931'
    return m


def test_handshake_message():
    msg = discovery.HandshakeMessage('', '', '', '', '', '', 'photon', '', '', 'UPPERCASE')
    assert msg.model == 'Spark 2'
    assert msg.device_id == 'uppercase'

    msg = discovery.HandshakeMessage('', '', '', '', '', '', 'p1', '', '', '')
    assert msg.model == 'Spark 3'

    msg = discovery.HandshakeMessage('', '', '', '', '', '', 'esp32', '', '', '')
    assert msg.model == 'Spark 4'

    msg = discovery.HandshakeMessage('', '', '', '', '', '', 'sim', '', '', '')
    assert msg.model == 'sim'


def test_match_id_services():
    config = {
        'services': {
            'spark1': {
                'image': 'ghcr.io/brewblox/brewblox-devcon-spark:${BREWBLOX_RELEASE}',
                'command': '--discovery=all --device-id=C4DD5766BB18',
            },
            'spark2': {
                'image': 'ghcr.io/brewblox/brewblox-devcon-spark:${BREWBLOX_RELEASE}',
                'command': '--discovery=all --device-id=C4DD5766BB18',
            },
            'spark3': {
                'image': 'ghcr.io/brewblox/brewblox-devcon-spark:${BREWBLOX_RELEASE}',
                'command': '--discovery=all --device-id=30003D001947383434353030',
            },
            'spark-none': {
                'image': 'ghcr.io/brewblox/brewblox-devcon-spark:${BREWBLOX_RELEASE}',
            },
            'service-other': {
                'image': 'brewblox/brewblox-tilt:${BREWBLOX_RELEASE}',
                'command': '--device-id=C4DD5766BB18',
            },
            'service-override': {
                'ports': ['80:80'],
            },
        },
    }
    assert discovery.match_id_services(config) == {
        'c4dd5766bb18': 'spark1, spark2',
        '30003d001947383434353030': 'spark3',
    }


def test_discover_usb():
    expected = DiscoveredDevice(discovery='USB', model='Spark 3', device_id='4f0052000551353432383931')

    gen = discovery.discover_usb()
    assert next(gen, None) == expected
    assert next(gen, None) == expected
    assert next(gen, None) is None


def test_discover_mdns():
    gen = discovery.discover_mdns()
    assert next(gen, None) == DiscoveredDevice(
        discovery='mDNS', model='Spark 3', device_id='id1', device_host='1.2.3.4'
    )
    assert next(gen, None) == DiscoveredDevice(
        discovery='mDNS', model='Spark 4', device_id='id2', device_host='4.3.2.1'
    )
    assert next(gen, None) is None


def test_discover_device():
    usb_devs = [v for v in discovery.discover_device(DiscoveryType.usb)]
    assert len(usb_devs) == 2
    assert usb_devs[0].device_id == '4f0052000551353432383931'

    wifi_devs = [v for v in discovery.discover_device(DiscoveryType.mdns)]
    assert len(wifi_devs) == 2
    assert wifi_devs[0].device_id == 'id1'

    all_devs = [v for v in discovery.discover_device(DiscoveryType.all)]
    assert all_devs == usb_devs + wifi_devs


def test_list_devices(mocker: MockerFixture):
    m_echo = mocker.patch(discovery.tabular.__name__ + '.click.echo')
    discovery.list_devices(DiscoveryType.all, None)
    assert m_echo.call_count == 6  # headers, spacers, 2 lan, 2 usb
    m_echo.assert_called_with(matching(r'mDNS\s+Spark 4\s+id2\s+'))


def test_choose_device(m_usb: Mock, mocker: MockerFixture):
    m_prompt = mocker.patch(TESTED + '.click.prompt')
    m_prompt.return_value = 1

    assert discovery.choose_device(DiscoveryType.all, None).device_id == '4f0052000551353432383931'
    assert discovery.choose_device(DiscoveryType.mdns, None).device_id == 'id1'

    m_usb.core.find.return_value = []
    assert discovery.choose_device(DiscoveryType.usb, None) is None

    assert discovery.choose_device(DiscoveryType.mqtt, None).device_id == 'id2'


def test_find_device_by_host(mocker: MockerFixture):
    m_get = mocker.patch(TESTED + '.requests.get', autospec=True)

    m_get.return_value.text = '!BREWBLOX,fw_version,proto_version,fw_date,proto_date,sys_version,esp32,00,00,id2'
    assert discovery.find_device_by_host('4.3.2.1').device_id == 'id2'

    m_get.return_value.text = 'Hello, this is dog!'
    assert discovery.find_device_by_host('4f0052000551353432383931') is None
