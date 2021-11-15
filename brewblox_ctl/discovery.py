"""
Device discovery
"""

import re
from queue import Empty, Queue
from socket import inet_ntoa
from typing import Dict, List, Optional

import click
import usb
from zeroconf import ServiceBrowser, ServiceInfo, ServiceStateChange, Zeroconf

from brewblox_ctl import const, tabular, utils

BREWBLOX_DNS_TYPE = '_brewblox._tcp.local.'
DISCOVER_TIMEOUT_S = 5
HW_LEN = 7
MAX_ID_LEN = 24  # Spark 4 IDs are shorter
HOST_LEN = 4*3+3


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
        if not service.get('image', '').startswith('brewblox/brewblox-devcon-spark'):
            continue
        match = re.match(
            r'.*\-\-device\-id(\w|=)(?P<id>\w+)',
            service.get('command', ''))
        if match:
            id = match.group('id').upper()
            output.setdefault(id, []).append(name)

    return {
        id: ', '.join(services)
        for id, services
        in output.items()
    }


def discover_usb():
    devices = [
        *usb.core.find(find_all=True,
                       idVendor=const.VID_PARTICLE,
                       idProduct=const.PID_PHOTON),
        *usb.core.find(find_all=True,
                       idVendor=const.VID_PARTICLE,
                       idProduct=const.PID_P1),
        # Spark 4 does not support USB control, and is not listed
    ]
    for dev in devices:
        dev: usb.core.Device
        id = usb.util.get_string(dev, dev.iSerialNumber).upper()
        hw = {const.PID_PHOTON: 'Spark 2', const.PID_P1: 'Spark 3'}[dev.idProduct]
        yield {
            'connect': 'USB',
            'id': id,
            'hw': hw,
        }


def discover_wifi():
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
            hw = info.properties[b'HW'].decode()
            host = inet_ntoa(info.addresses[0])
            yield {
                'connect': 'LAN',
                'id': id,
                'hw': hw,
                'host': host,
            }
    except Empty:
        pass
    finally:
        conf.close()


def discover_device(discovery_type):
    if discovery_type in ['all', 'usb']:
        yield from discover_usb()
    if discovery_type in ['all', 'wifi', 'lan']:
        yield from discover_wifi()


def list_devices(discovery_type: str, compose_config: dict = None):
    id_services = match_id_services(compose_config)
    table = tabular.Table(
        keys=['connect', 'hw', 'id', 'host', 'service'],
        headers={
            'connect': 'Type',
            'hw': 'Model'.ljust(HW_LEN),
            'id': 'Device ID'.ljust(MAX_ID_LEN),
            'host': 'Device host'.ljust(HOST_LEN),
            'service': 'Service',
        }
    )

    utils.info('Discovering devices...')
    table.print_headers()
    for dev in discover_device(discovery_type):
        table.print_row({
            **dev,
            'service': id_services.get(dev['id'], ''),
        })


def choose_device(discovery_type: str, compose_config: dict = None):
    id_services = match_id_services(compose_config)
    table = tabular.Table(
        keys=['index', 'connect', 'hw', 'id', 'host', 'service'],
        headers={
            'index': 'Index',
            'connect': 'Type',
            'hw': 'Model'.ljust(HW_LEN),
            'id': 'Device ID'.ljust(MAX_ID_LEN),
            'host': 'Device host'.ljust(HOST_LEN),
            'service': 'Service',
        }
    )
    devs = []

    utils.info('Discovering devices...')
    table.print_headers()
    for i, dev in enumerate(discover_device(discovery_type)):
        devs.append(dev)
        table.print_row({
            **dev,
            'index': i+1,
            'service': id_services.get(dev['id'], ''),
        })

    if not devs:
        click.echo('No devices discovered')
        return None

    idx = click.prompt('Which device do you want to use?',
                       type=click.IntRange(1, len(devs)),
                       default=1)

    return devs[idx-1]


def find_device_by_host(device_host: str):
    utils.info(f'Discovering device with address {device_host}...')
    match = next((dev
                  for dev in discover_device('lan')
                  if dev.get('host') == device_host
                  ),
                 None)
    if match:
        id = match['id']
        hw = match['hw']
        utils.info(f'Discovered a {hw} with ID {id}')
        return match
    else:
        click.echo('No devices discovered')
        return None
