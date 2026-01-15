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
    m_dev_p1 = Mock()
    m_dev_p1.idVendor = const.VID_PARTICLE
    m_dev_p1.idProduct = const.PID_P1

    m_dev_esp32 = Mock()
    m_dev_esp32.idVendor = const.VID_ESPRESSIF
    m_dev_esp32.idProduct = const.PID_ESP32

    m_dev_esp32_s3 = Mock()
    m_dev_esp32_s3.idVendor = const.VID_ESPRESSIF_NATIVE
    m_dev_esp32_s3.idProduct = const.PID_ESP32_S3

    m = mocker.patch(TESTED + '.usb', autospec=True)

    def find_devices(find_all, idVendor, idProduct):
        if idVendor == const.VID_PARTICLE and idProduct == const.PID_P1:
            return [m_dev_p1]
        if idVendor == const.VID_ESPRESSIF and idProduct == const.PID_ESP32:
            return [m_dev_esp32]
        if idVendor == const.VID_ESPRESSIF_NATIVE and idProduct == const.PID_ESP32_S3:
            return [m_dev_esp32_s3]
        return []

    def get_string(dev, idx):
        if dev == m_dev_esp32_s3:
            return '48:CA:43:59:12:34'  # MAC address with colons
        return '4F0052000551353432383931'

    m.core.find.side_effect = find_devices
    m.util.get_string.side_effect = get_string
    return m


@pytest.fixture
def m_esp32_serial(mocker: MockerFixture):
    """Mock ESP32 serial discovery and reading."""
    mocker.patch(TESTED + '.discover_esp_spark_tty', return_value=['/dev/ttyUSB0'])
    mocker.patch(TESTED + '.read_esp32_device_id', return_value='c4dd57670670')


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
            # Legacy command format
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
            # New environment list format - both IDs
            'spark4': {
                'image': 'ghcr.io/brewblox/brewblox-devcon-spark:${BREWBLOX_RELEASE}',
                'environment': [
                    'BREWBLOX_SPARK_DEVICE_ID=AABBCCDD',
                    'BREWBLOX_SPARK_USB_DEVICE_ID=USB12345',
                ],
            },
            # Environment list format - only device ID
            'spark4a': {
                'image': 'ghcr.io/brewblox/brewblox-devcon-spark:${BREWBLOX_RELEASE}',
                'environment': [
                    'BREWBLOX_SPARK_DEVICE_ID=LISTDEVONLY',
                ],
            },
            # Environment list format - only USB device ID
            'spark4b': {
                'image': 'ghcr.io/brewblox/brewblox-devcon-spark:${BREWBLOX_RELEASE}',
                'environment': [
                    'BREWBLOX_SPARK_USB_DEVICE_ID=LISTUSBONLY',
                ],
            },
            # Environment list format with other env vars (not device IDs)
            'spark4c': {
                'image': 'ghcr.io/brewblox/brewblox-devcon-spark:${BREWBLOX_RELEASE}',
                'environment': [
                    'BREWBLOX_SPARK_DEVICE_ID=LISTMIXED',
                    'SOME_OTHER_VAR=ignored',
                    'ANOTHER_VAR=also_ignored',
                ],
            },
            # Environment list format with only other env vars (no device IDs)
            'spark4d': {
                'image': 'ghcr.io/brewblox/brewblox-devcon-spark:${BREWBLOX_RELEASE}',
                'environment': [
                    'SOME_VAR=ignored',
                ],
            },
            # Empty environment list (for coverage of empty iteration)
            'spark4e': {
                'image': 'ghcr.io/brewblox/brewblox-devcon-spark:${BREWBLOX_RELEASE}',
                'environment': [],
            },
            # Environment with unexpected type (neither list nor dict)
            'spark4f': {
                'image': 'ghcr.io/brewblox/brewblox-devcon-spark:${BREWBLOX_RELEASE}',
                'environment': 'not-a-list-or-dict',
            },
            # Environment dict format - both IDs
            'spark5': {
                'image': 'ghcr.io/brewblox/brewblox-devcon-spark:${BREWBLOX_RELEASE}',
                'environment': {
                    'BREWBLOX_SPARK_DEVICE_ID': 'DDEEFF00',
                    'BREWBLOX_SPARK_USB_DEVICE_ID': 'USB67890',
                },
            },
            # Environment dict format - only device ID
            'spark5a': {
                'image': 'ghcr.io/brewblox/brewblox-devcon-spark:${BREWBLOX_RELEASE}',
                'environment': {
                    'BREWBLOX_SPARK_DEVICE_ID': 'DICTDEVONLY',
                },
            },
            # Environment dict format - only USB device ID
            'spark5b': {
                'image': 'ghcr.io/brewblox/brewblox-devcon-spark:${BREWBLOX_RELEASE}',
                'environment': {
                    'BREWBLOX_SPARK_USB_DEVICE_ID': 'DICTUSBONLY',
                },
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
    result = discovery.match_id_services(config)
    assert result == {
        'c4dd5766bb18': 'spark1, spark2',
        '30003d001947383434353030': 'spark3',
        'aabbccdd': 'spark4',
        'usb12345': 'spark4',
        'listdevonly': 'spark4a',
        'listusbonly': 'spark4b',
        'listmixed': 'spark4c',
        'ddeeff00': 'spark5',
        'dictdevonly': 'spark5a',
        'dictusbonly': 'spark5b',
        'usb67890': 'spark5',
    }


def test_discover_usb(m_esp32_serial):
    gen = discovery.discover_usb()
    # Particle device: device_id is the USB serial
    assert next(gen, None) == DiscoveredDevice(discovery='USB', model='Spark 3', device_id='4f0052000551353432383931')
    # ESP32 device: device_id read from serial, usb_device_id is the USB serial
    assert next(gen, None) == DiscoveredDevice(
        discovery='USB', model='Spark 4', device_id='c4dd57670670', usb_device_id='4f0052000551353432383931'
    )
    # ESP32-S3 device: MAC address is used as device_id (same for USB and network)
    assert next(gen, None) == DiscoveredDevice(discovery='USB', model='Spark 5', device_id='48ca43591234')
    assert next(gen, None) is None


def test_discover_usb_permission_error(m_esp32_serial, m_usb: Mock, mocker: MockerFixture):
    m_warn = mocker.patch(TESTED + '.utils.warn')
    m_usb.util.get_string.side_effect = ValueError('no langid')
    devs = list(discovery.discover_usb())
    assert devs == []
    assert m_warn.call_count == 3  # Called for P1, ESP32, and ESP32-S3 devices


def test_discover_usb_esp32_no_tty(m_usb: Mock, mocker: MockerFixture):
    """Test ESP32 discovery when no TTY is found."""
    mocker.patch(TESTED + '.discover_esp_spark_tty', return_value=[])
    devs = list(discovery.discover_usb())
    # Should still return the device, but with empty device_id
    esp32_dev = [d for d in devs if d.model == 'Spark 4'][0]
    assert esp32_dev.device_id == ''
    assert esp32_dev.usb_device_id == '4f0052000551353432383931'


def test_discover_usb_esp32_multiple_tty(m_usb: Mock, mocker: MockerFixture):
    """Test ESP32 discovery when first TTY fails but second succeeds."""
    mocker.patch(TESTED + '.discover_esp_spark_tty', return_value=['/dev/ttyUSB0', '/dev/ttyUSB1'])
    # First call returns None, second returns device_id
    mocker.patch(TESTED + '.read_esp32_device_id', side_effect=[None, 'c4dd57670670'])
    devs = list(discovery.discover_usb())
    esp32_dev = [d for d in devs if d.model == 'Spark 4'][0]
    assert esp32_dev.device_id == 'c4dd57670670'


def test_read_esp32_device_id(mocker: MockerFixture):
    # Mock serial.Serial as a context manager
    m_serial = mocker.patch(TESTED + '.serial.Serial')
    m_serial_instance = Mock()
    m_serial.return_value.__enter__ = Mock(return_value=m_serial_instance)
    m_serial.return_value.__exit__ = Mock(return_value=False)

    # Test successful read - sends empty line to request handshake
    m_serial_instance.readline.side_effect = [
        b'Some boot message\n',
        b'<!BREWBLOX,248f4910,0ed3826e,2026-01-14,2025-11-24,5.5.0,esp32,00,00,c4dd57670670><I (1338) wifi:>\n',
    ]
    result = discovery.read_esp32_device_id('/dev/ttyUSB0')
    assert result == 'c4dd57670670'
    # Verify we sent empty line to request handshake
    m_serial_instance.write.assert_called_once_with(b'\n')


def test_read_esp32_device_id_no_handshake(mocker: MockerFixture):
    m_serial = mocker.patch(TESTED + '.serial.Serial')
    m_serial_instance = Mock()
    m_serial.return_value.__enter__ = Mock(return_value=m_serial_instance)
    m_serial.return_value.__exit__ = Mock(return_value=False)

    # Test no handshake found - empty line causes early break
    m_serial_instance.readline.side_effect = [b'some output\n', b'']
    result = discovery.read_esp32_device_id('/dev/ttyUSB0')
    assert result is None
    assert m_serial_instance.readline.call_count == 2  # Stopped after empty line


def test_read_esp32_device_id_max_lines(mocker: MockerFixture):
    m_serial = mocker.patch(TESTED + '.serial.Serial')
    m_serial_instance = Mock()
    m_serial.return_value.__enter__ = Mock(return_value=m_serial_instance)
    m_serial.return_value.__exit__ = Mock(return_value=False)

    # Test no handshake found - max lines reached without empty line
    m_serial_instance.readline.side_effect = [b'no handshake\n'] * 100
    result = discovery.read_esp32_device_id('/dev/ttyUSB0')
    assert result is None
    assert m_serial_instance.readline.call_count == 100  # Read all 100 lines


def test_read_esp32_device_id_error(mocker: MockerFixture):
    import serial as pyserial

    m_warn = mocker.patch(TESTED + '.utils.warn')
    mocker.patch(TESTED + '.serial.Serial', side_effect=pyserial.SerialException('Port not found'))
    result = discovery.read_esp32_device_id('/dev/ttyUSB0')
    assert result is None
    assert m_warn.call_count == 1


def test_discover_mdns():
    gen = discovery.discover_mdns()
    assert next(gen, None) == DiscoveredDevice(
        discovery='mDNS', model='Spark 3', device_id='id1', device_host='1.2.3.4'
    )
    assert next(gen, None) == DiscoveredDevice(
        discovery='mDNS', model='Spark 4', device_id='id2', device_host='4.3.2.1'
    )
    assert next(gen, None) is None


def test_discover_device(m_esp32_serial):
    usb_devs = [v for v in discovery.discover_device(DiscoveryType.usb)]
    assert len(usb_devs) == 3
    assert usb_devs[0].device_id == '4f0052000551353432383931'

    wifi_devs = [v for v in discovery.discover_device(DiscoveryType.mdns)]
    assert len(wifi_devs) == 2
    assert wifi_devs[0].device_id == 'id1'

    all_devs = [v for v in discovery.discover_device(DiscoveryType.all)]
    assert all_devs == usb_devs + wifi_devs


def test_list_devices(m_esp32_serial, mocker: MockerFixture):
    m_echo = mocker.patch(discovery.tabular.__name__ + '.click.echo')
    discovery.list_devices(DiscoveryType.all, None)
    assert m_echo.call_count == 7  # headers, spacers, 2 lan, 3 usb
    m_echo.assert_called_with(matching(r'mDNS\s+Spark 4\s+id2\s+'))


def test_choose_device(m_esp32_serial, m_usb: Mock, mocker: MockerFixture):
    m_prompt = mocker.patch(TESTED + '.click.prompt')
    m_prompt.return_value = 1

    assert discovery.choose_device(DiscoveryType.all, None).device_id == '4f0052000551353432383931'
    assert discovery.choose_device(DiscoveryType.mdns, None).device_id == 'id1'

    m_usb.core.find.side_effect = lambda **kwargs: []
    assert discovery.choose_device(DiscoveryType.usb, None) is None

    assert discovery.choose_device(DiscoveryType.mqtt, None).device_id == 'id2'


def test_find_device_by_host(mocker: MockerFixture):
    m_get = mocker.patch(TESTED + '.requests.get', autospec=True)

    m_get.return_value.text = '!BREWBLOX,fw_version,proto_version,fw_date,proto_date,sys_version,esp32,00,00,id2'
    assert discovery.find_device_by_host('4.3.2.1').device_id == 'id2'

    m_get.return_value.text = 'Hello, this is dog!'
    assert discovery.find_device_by_host('4f0052000551353432383931') is None
