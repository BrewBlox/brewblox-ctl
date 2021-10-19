"""
Tests brewblox_ctl.discovery
"""

from socket import inet_aton
from unittest.mock import Mock

import pytest
from brewblox_ctl import const, discovery
from brewblox_ctl.testing import check_sudo
from zeroconf import ServiceInfo, ServiceStateChange

TESTED = discovery.__name__


class ServiceBrowserMock():

    def __init__(self, conf, service_type, handlers):
        self.conf = conf
        self.service_type = service_type
        self.handlers = handlers

        for name in ['id0', 'id1', 'id2']:
            for handler in self.handlers:
                handler(zeroconf=conf,
                        service_type=service_type,
                        name=name,
                        state_change=ServiceStateChange.Added)
                handler(zeroconf=conf,
                        service_type=service_type,
                        name=name,
                        state_change=ServiceStateChange.Removed)


@pytest.fixture
def m_conf(mocker):

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


@pytest.fixture
def m_browser(mocker):
    mocker.patch(TESTED + '.DISCOVER_TIMEOUT_S', 0.01)
    return mocker.patch(TESTED + '.ServiceBrowser', ServiceBrowserMock)


@pytest.fixture
def m_usb(mocker):
    m_dev = Mock()
    m_dev.idProduct = const.PID_P1

    m = mocker.patch(TESTED + '.usb', autospec=True)
    m.core.find.return_value = [m_dev]
    m.util.get_string.return_value = '4f0052000551353432383931'
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


def test_discover_usb(m_usb):
    expected = {
        'id': '4F0052000551353432383931',
        'desc': 'USB Spark 3 4F0052000551353432383931',
        'hw': 'Spark 3',
    }

    gen = discovery.discover_usb()
    assert next(gen, None) == expected
    assert next(gen, None) == expected
    assert next(gen, None) is None


def test_discover_wifi(m_browser, m_conf):
    gen = discovery.discover_wifi()
    assert next(gen, None) == {
        'id': 'id1',
        'desc': 'LAN Spark 3 id1                      1.2.3.4',
        'hw': 'Spark 3',
        'host': '1.2.3.4',
        'port': 1234,
    }
    assert next(gen, None) == {
        'id': 'id2',
        'desc': 'LAN Spark 4 id2                      4.3.2.1',
        'hw': 'Spark 4',
        'host': '4.3.2.1',
        'port': 4321,
    }
    assert next(gen, None) is None


def test_discover_device(m_utils, m_browser, m_conf, m_usb):
    usb_devs = [v for v in discovery.discover_device('usb')]
    assert len(usb_devs) == 2
    assert usb_devs[0]['id'] == '4F0052000551353432383931'

    wifi_devs = [v for v in discovery.discover_device('wifi')]
    assert len(wifi_devs) == 2
    assert wifi_devs[0]['id'] == 'id1'

    all_devs = [v for v in discovery.discover_device('all')]
    assert all_devs == usb_devs + wifi_devs


def test_find_device(m_utils, m_browser, m_conf, m_usb, mocker):
    m_prompt = mocker.patch(TESTED + '.click.prompt')
    m_prompt.return_value = 1

    assert discovery.find_device('all')['id'] == '4F0052000551353432383931'
    assert discovery.find_device('wifi')['id'] == 'id1'
    assert discovery.find_device('all', 'Valhalla') is None
    assert discovery.find_device('usb', '4.3.2.1') is None
    assert discovery.find_device('wifi', '4.3.2.1')['id'] == 'id2'
