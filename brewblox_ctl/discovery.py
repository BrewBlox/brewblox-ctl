"""
Device discovery
"""

from queue import Empty, Queue
from socket import inet_ntoa

import click
import usb
from zeroconf import ServiceBrowser, ServiceInfo, ServiceStateChange, Zeroconf

from brewblox_ctl import const, utils

BREWBLOX_DNS_TYPE = '_brewblox._tcp.local.'
DISCOVER_TIMEOUT_S = 5
MAX_ID_LEN = 24  # Spark 4 IDs are shorter


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
        desc = f'USB {hw} {id}'
        yield {
            'id': id,
            'desc': desc,
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
            port = info.port
            desc = f'LAN {hw} {id.ljust(MAX_ID_LEN)} {host}'
            yield {
                'id': id,
                'desc': desc,
                'hw': hw,
                'host': host,
                'port': port,
            }
    except Empty:
        pass
    finally:
        conf.close()


def discover_device(discovery_type):
    utils.info('Discovering devices...')
    if discovery_type in ['all', 'usb']:
        yield from discover_usb()
    if discovery_type in ['all', 'wifi', 'lan']:
        yield from discover_wifi()


def find_device(discovery_type, device_host=None):
    devs = []

    for i, dev in enumerate(discover_device(discovery_type)):
        desc = dev['desc']

        if not device_host:
            devs.append(dev)
            click.echo(f'device {i+1} :: {desc}')

        # Don't echo discarded devices
        if device_host and dev.get('host') == device_host:
            click.echo(f'{desc} matches --device-host {device_host}')
            return dev

    if device_host or not devs:
        click.echo('No devices discovered')
        return None

    idx = click.prompt('Which device do you want to use?',
                       type=click.IntRange(1, len(devs)),
                       default=1)

    return devs[idx-1]
