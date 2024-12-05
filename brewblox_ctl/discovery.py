"""
Device discovery
"""

import enum
import re
from dataclasses import asdict, dataclass
from glob import glob
from pathlib import Path
from queue import Empty, Queue
from socket import inet_ntoa
from typing import Dict, Generator, List, Optional

import click
import requests
import usb
from zeroconf import ServiceBrowser, ServiceInfo, ServiceStateChange, Zeroconf

from brewblox_ctl import const, tabular, utils

BREWBLOX_DNS_TYPE = '_brewblox._tcp.local.'
DISCOVER_TIMEOUT_S = 5
DISCOVERY_LEN = 4  # USB / TCP / mDNS
MODEL_LEN = 7  # 'Spark 2' / 'Spark 3' / 'Spark 4'
MAX_ID_LEN = 24  # Spark 4 IDs are shorter
HOST_LEN = 4 * 3 + 3


class DiscoveryType(enum.Enum):
    all = 1
    usb = 2
    mdns = 3
    mqtt = 4

    # aliases
    wifi = 3
    lan = 3

    def __str__(self):
        return self.name

    @staticmethod
    def choices():
        return list(str(v) for v in DiscoveryType.__members__)


@dataclass
class DiscoveredDevice:
    discovery: str
    model: str
    device_id: str
    device_host: str = ''

    def __post_init__(self):
        self.device_id = self.device_id.lower()


@dataclass
class HandshakeMessage:
    brewblox: str
    firmware_version: str
    proto_version: str
    firmware_date: str
    proto_date: str
    system_version: str
    platform: str
    reset_reason_hex: str
    reset_data_hex: str
    device_id: str
    model: str = ''

    def __post_init__(self):
        self.device_id = self.device_id.lower()

        if self.platform == 'photon':
            self.model = 'Spark 2'
        elif self.platform == 'p1':
            self.model = 'Spark 3'
        elif self.platform == 'esp32':
            self.model = 'Spark 4'
        else:
            self.model = self.platform


def match_id_services(config: Optional[dict]) -> Dict[str, str]:  # [ID, service_name]
    """Gets the --device-id value for all Spark services in config.

    Because IDs are yielded during discovery,
    values are returned with the ID as key,
    and a comma-separated string of services as value
    """
    if not config:
        return {}

    output: Dict[str, List[str]] = {}
    for name, service in config.get('services', {}).items():
        if not service.get('image', '').startswith('ghcr.io/brewblox/brewblox-devcon-spark'):
            continue
        match = re.match(r'.*\-\-device\-id(\w|=)(?P<id>\w+)', service.get('command', ''))
        if match:
            id = match.group('id').lower()
            output.setdefault(id, []).append(name)

    return {id: ', '.join(services) for id, services in output.items()}


def find_device_by_host(device_host: str) -> Optional[DiscoveredDevice]:
    utils.info(f'Querying device with address {device_host} ...')
    try:
        resp = requests.get(f'http://{device_host}', timeout=5)
        resp.raise_for_status()

        content = resp.text
        if not content.startswith('!BREWBLOX'):
            raise RuntimeError('Host did not respond with a Brewblox handshake')

        handshake = HandshakeMessage(*content.split(','))
        utils.info(f'Found a {handshake.model} with ID {handshake.device_id}')
        return DiscoveredDevice(
            discovery='TCP',
            device_id=handshake.device_id,
            model=handshake.model,
            device_host=device_host,
        )

    except Exception as ex:
        utils.warn(f'Failed to fetch device info: {ex!s}')
        return None


def discover_usb() -> Generator[DiscoveredDevice, None, None]:
    devices = [
        *usb.core.find(find_all=True, idVendor=const.VID_PARTICLE, idProduct=const.PID_PHOTON),
        *usb.core.find(find_all=True, idVendor=const.VID_PARTICLE, idProduct=const.PID_P1),
        # Spark 4 does not support USB control, and is not listed
    ]
    for dev in devices:
        dev: usb.core.Device
        id = usb.util.get_string(dev, dev.iSerialNumber).lower()
        model = {const.PID_PHOTON: 'Spark 2', const.PID_P1: 'Spark 3'}[dev.idProduct]
        yield DiscoveredDevice(discovery='USB', model=model, device_id=id)


def discover_particle_spark_tty(device_id: Optional[str] = None) -> Generator[str, None, None]:  # pragma: no cover
    for tty in glob('/sys/class/tty/ttyACM*'):
        tty = Path(tty)

        if (tty / 'device' / 'subsystem').resolve() != Path('/sys/bus/usb'):
            continue

        dev_root = (tty / 'device').resolve() / '..'
        usb_vid = (dev_root / 'idVendor').read_text().strip()
        usb_pid = (dev_root / 'idProduct').read_text().strip()
        usb_device_id = (dev_root / 'serial').read_text().strip()

        if all(
            [
                int(usb_vid, 16) == const.VID_PARTICLE,
                int(usb_pid, 16) in (const.PID_PHOTON, const.PID_P1),
                device_id is None or usb_device_id == device_id,
            ]
        ):
            yield f'/dev/{tty.name}'


def discover_esp_spark_tty() -> Generator[str, None, None]:  # pragma: no cover
    for tty in glob('/sys/class/tty/ttyUSB*'):
        tty = Path(tty)

        if (tty / 'device' / 'subsystem').resolve() != Path('/sys/bus/usb-serial'):
            continue

        dev_root = (tty / 'device').resolve() / '..' / '..'
        usb_vid = (dev_root / 'idVendor').read_text().strip()
        usb_pid = (dev_root / 'idProduct').read_text().strip()

        if all(
            [
                int(usb_vid, 16) == const.VID_ESPRESSIF,
                int(usb_pid, 16) == const.PID_ESP32,
            ]
        ):
            yield f'/dev/{tty.name}'


def discover_mdns() -> Generator[DiscoveredDevice, None, None]:
    queue: Queue[ServiceInfo] = Queue()
    conf = Zeroconf()

    def on_service_state_change(zeroconf: Zeroconf, service_type, name, state_change):
        if state_change == ServiceStateChange.Added:
            info = zeroconf.get_service_info(service_type, name)
            queue.put(info)

    try:
        ServiceBrowser(conf, BREWBLOX_DNS_TYPE, handlers=[on_service_state_change])
        while True:
            info = queue.get(timeout=DISCOVER_TIMEOUT_S)
            if not info or not info.addresses or info.addresses == [b'\x00\x00\x00\x00']:
                continue  # discard simulators
            id = info.properties[b'ID'].decode()
            model = info.properties[b'HW'].decode()
            host = inet_ntoa(info.addresses[0])
            yield DiscoveredDevice(discovery='mDNS', model=model, device_id=id, device_host=host)
    except Empty:
        pass
    finally:
        conf.close()


def discover_device(discovery_type: DiscoveryType) -> Generator[DiscoveredDevice, None, None]:
    if discovery_type in [DiscoveryType.all, DiscoveryType.usb]:
        yield from discover_usb()
    if discovery_type in [DiscoveryType.all, DiscoveryType.mdns, DiscoveryType.mqtt]:
        yield from discover_mdns()


def list_devices(discovery_type: DiscoveryType, compose_config: Optional[dict]):
    id_services = match_id_services(compose_config)
    table = tabular.Table(
        keys=['discovery', 'model', 'device_id', 'device_host', 'service'],
        headers={
            'discovery': 'Discovery'.ljust(DISCOVERY_LEN),
            'model': 'Model'.ljust(MODEL_LEN),
            'device_id': 'Device ID'.ljust(MAX_ID_LEN),
            'device_host': 'Device host'.ljust(HOST_LEN),
            'service': 'Service',
        },
    )

    utils.info('Discovering devices ...')
    table.print_headers()
    for dev in discover_device(discovery_type):
        table.print_row(
            {
                **asdict(dev),
                'service': id_services.get(dev.device_id, ''),
            }
        )


def choose_device(
    discovery_type: DiscoveryType,
    compose_config: Optional[dict],
) -> Optional[DiscoveredDevice]:
    id_services = match_id_services(compose_config)
    table = tabular.Table(
        keys=['index', 'discovery', 'model', 'device_id', 'device_host', 'service'],
        headers={
            'index': 'Index',
            'discovery': 'Discovery'.ljust(DISCOVERY_LEN),
            'model': 'Model'.ljust(MODEL_LEN),
            'device_id': 'Device ID'.ljust(MAX_ID_LEN),
            'device_host': 'Device host'.ljust(HOST_LEN),
            'service': 'Service',
        },
    )
    devs = []

    utils.info('Discovering devices ...')
    table.print_headers()
    for dev in discover_device(discovery_type):
        # TODO(Bob) less hacky check
        if discovery_type == DiscoveryType.mqtt and dev.model != 'Spark 4':
            continue
        devs.append(dev)
        table.print_row(
            {
                **asdict(dev),
                'index': len(devs),
                'service': id_services.get(dev.device_id, ''),
            }
        )

    if not devs:
        click.echo('No devices discovered')
        return None

    idx = click.prompt('Which device do you want to use?', type=click.IntRange(1, len(devs)), default=1)

    return devs[idx - 1]
