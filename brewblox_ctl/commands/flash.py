"""
Flash device settings
"""

import re
from glob import glob
from time import sleep
from typing import List

import click
import usb.core
from brewblox_ctl import click_helpers, sh, utils

LISTEN_MODE_WAIT_S = 1


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Command collector"""


def run_particle_flasher(release: str, pull: bool, cmd: str):
    tag = utils.docker_tag(release)
    sudo = utils.optsudo()

    opts = ' '.join([
        '-it',
        '--rm',
        '--privileged',
        '-v /dev:/dev',
        '--pull ' + ('always' if pull else 'missing'),
    ])

    sh(f'{sudo}docker-compose --log-level CRITICAL down', check=False)
    sh(f'{sudo}docker run {opts} brewblox/firmware-flasher:{tag} {cmd}')


def run_esp_flasher(release: str, pull: bool):
    tag = utils.docker_tag(release)
    sudo = utils.optsudo()

    opts = ' '.join([
        '-it',
        '--rm',
        '--privileged',
        '-v /dev:/dev',
        '-w /app/firmware',
        '--entrypoint bash',
        '--pull ' + ('always' if pull else 'missing'),
    ])

    sh(f'{sudo}docker-compose --log-level CRITICAL down', check=False)
    sh(f'{sudo}docker run {opts} brewblox/brewblox-devcon-spark:{tag} flash')


def discover_usb_sparks() -> List[str]:
    devices = sh('lsusb', capture=True)
    output = []
    for match in re.finditer(r'ID (?P<id>\w{4}:\w{4})',
                             devices,
                             re.MULTILINE):
        id = match.group('id').lower()
        if id in ['2b04:c006', '2b04:d006']:  # photon, photon DFU
            output.append('Spark v2')
        if id in ['2b04:c008', '2b04:d008']:  # p1, p1 DFU
            output.append('Spark v3')
        if id in ['10c4:ea60']:  # ESP32
            output.append('Spark v4')

    return output


def prompt_usb_spark() -> str:
    while True:
        devices = discover_usb_sparks()
        num_devices = len(devices)
        if num_devices == 0:
            utils.warn('No USB-connected Spark detected')
            utils.confirm_usb()
        elif num_devices == 1:
            return devices[0]
        else:
            utils.warn(f'Multiple USB-connected Sparks detected: {", ".join(devices)}')
            utils.confirm_usb()


@cli.command()
@click.option('--release', default=None, help='Brewblox release track')
@click.option('--pull/--no-pull', default=True)
def flash(release, pull):
    """Flash Spark firmware over USB.

    This requires the Spark to be connected over USB.

    After the first install, firmware updates can also be installed using the UI.

    \b
    Steps:
        - Stop running services.
        - Pull flasher image.
        - Run flash command.
    """
    utils.confirm_mode()
    spark = prompt_usb_spark()

    utils.info(f'Flashing {spark}...')

    if spark in ['Spark v2', 'Spark v3']:
        run_particle_flasher(release, pull, 'flash')
    elif spark in ['Spark v4']:
        run_esp_flasher(release, pull)
    else:
        raise ValueError(f'Unknown device "{spark}"')


def particle_wifi(dev: usb.core.Device):

    if utils.ctx_opts().dry_run:
        utils.info('Dry run: skipping activation of Spark listening mode')
    else:
        dev.reset()

        # Magic numbers for the USB control call
        HOST_TO_DEVICE = 0x40  # bmRequestType
        REQUEST_INIT = 1  # bRequest
        REQUEST_SEND = 3  # bRequest
        PARTICLE_LISTEN_INDEX = 70  # wIndex
        PARTICLE_LISTEN_VALUE = 0  # wValue
        PARTICLE_BUF_SIZE = 64  # wLength

        dev.ctrl_transfer(
            HOST_TO_DEVICE,
            REQUEST_INIT,
            PARTICLE_LISTEN_VALUE,
            PARTICLE_LISTEN_INDEX,
            PARTICLE_BUF_SIZE
        )

        dev.ctrl_transfer(
            HOST_TO_DEVICE,
            REQUEST_SEND,
            PARTICLE_LISTEN_VALUE,
            PARTICLE_LISTEN_INDEX,
            PARTICLE_BUF_SIZE
        )

    sleep(LISTEN_MODE_WAIT_S)

    try:
        path = glob('/dev/serial/by-id/usb-Particle_*').pop()
    except IndexError:
        path = '/dev/ttyACM0'

    utils.info('Press w to start Wifi configuration.')
    utils.info('Press Ctrl + ] to cancel.')
    utils.info('The Spark must be restarted after canceling.')
    sh(f'miniterm.py -q {path} 2>/dev/null')


def esp_wifi():
    utils.info('Spark 4 Wifi credentials are set over Bluetooth, using the ESP BLE Provisioning app.')
    utils.info('')
    utils.info('To set Wifi credentials:')
    utils.info('- Press the (R)ESET button on your Spark.')
    utils.info('- While the Spark restarts, press and hold the OK button for five seconds.')
    utils.info('- The Spark is ready for provisioning if its buttons are blinking blue.')
    utils.info('- Download the ESP BLE Provisioning app.')
    utils.info('- Enable Bluetooth in your phone settings.')
    utils.info('- Open the app.')
    utils.info('- Click Provision New Device.')
    utils.info("- Click I don't have a QR code.")
    utils.info('- Select the PROV_BREWBLOX_ device.')
    utils.info('- Select your Wifi network, and enter your credentials.')
    utils.info('')
    utils.info('The app will set the Wifi credentials for your Spark.')
    utils.info('An additional IP address will be shown in the top left corner of the Spark display.')


@cli.command()
def wifi():
    """Configure Spark Wifi settings.

    This requires the Spark to be connected over USB.

    \b
    Steps:
        - Stop running services.
        - Look for valid USB device.
        - Spark 2 / Spark 3:
            - Trigger listening mode.
            - Connect to device serial to set up Wifi.
        - Spark 4:
            - Print provisioning instructions.
    """
    utils.confirm_mode()

    while True:
        particle_dev = usb.core.find(idVendor=0x2b04)
        esp_dev = usb.core.find(idVendor=0x10c4, idProduct=0xea60)

        if particle_dev:
            particle_wifi(particle_dev)
            return
        elif esp_dev:
            esp_wifi()
            return
        else:
            utils.confirm_usb()


@cli.command()
@click.option('--release', default=None, help='Brewblox release track')
@click.option('--pull/--no-pull', default=True)
@click.option('-c', '--command', default='')
def particle(release, pull, command):
    """Start a Docker container with access to the Particle CLI.

    This requires the Spark to be connected over USB.

    \b
    Steps:
        - Stop running services.
        - Pull flasher image.
        - Start flasher image.
    """
    utils.confirm_mode()
    utils.confirm_usb()

    utils.info('Starting Particle image...')
    utils.info("Type 'exit' and press enter to exit the shell")
    run_particle_flasher(release, pull, command)
