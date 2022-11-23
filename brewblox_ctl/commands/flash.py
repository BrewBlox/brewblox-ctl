"""
Flash device settings
"""

from pathlib import Path
from time import sleep

import click
import usb
from brewblox_ctl import click_helpers, const, sh, utils

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


def find_usb_spark() -> usb.core.Device:
    while True:
        devices = [
            *usb.core.find(find_all=True,
                           idVendor=const.VID_PARTICLE,
                           idProduct=const.PID_PHOTON),
            *usb.core.find(find_all=True,
                           idVendor=const.VID_PARTICLE,
                           idProduct=const.PID_P1),
            *usb.core.find(find_all=True,
                           idVendor=const.VID_ESPRESSIF,
                           idProduct=const.PID_ESP32),
        ]
        num_devices = len(devices)
        if num_devices == 0:
            utils.warn('No USB-connected Spark detected')
            utils.confirm_usb()
        elif num_devices == 1:
            return devices[0]
        else:
            utils.warn(f'{len(devices)} USB-connected Sparks detected.')
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
    dev = find_usb_spark()

    if dev.idProduct == const.PID_PHOTON:
        utils.info('Flashing Spark 2...')
        run_particle_flasher(release, pull, 'flash')
    elif dev.idProduct == const.PID_P1:
        utils.info('Flashing Spark 3...')
        run_particle_flasher(release, pull, 'flash')
    elif dev.idProduct == const.PID_ESP32:
        utils.info('Flashing Spark 4...')
        run_esp_flasher(release, pull)
    else:
        raise ValueError('Unknown USB device')


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

    serial = usb.util.get_string(dev, dev.iSerialNumber)
    path = next(Path('/dev/serial/by-id').glob(f'*{serial}*'),
                Path('/dev/ttyACM0'))

    utils.info('Press w to start Wifi configuration.')
    utils.info('Press Ctrl + ] to cancel.')
    utils.info('The Spark must be restarted after canceling.')
    sh(f'pyserial-miniterm -q {path.resolve()} 2>/dev/null')


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
        particle_dev = usb.core.find(idVendor=const.VID_PARTICLE)
        if particle_dev:
            particle_wifi(particle_dev)
            break

        esp_dev = usb.core.find(idVendor=const.VID_ESPRESSIF, idProduct=const.PID_ESP32)
        if esp_dev:
            esp_wifi()
            break

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

    utils.info('Starting Particle image...')
    utils.info("Type 'exit' and press enter to exit the shell")
    run_particle_flasher(release, pull, command)


@cli.command()
@click.argument('cmd', nargs=-1, type=click.UNPROCESSED)
def esptool(cmd):
    """Run the esptool.py tool for Spark 4 management.

    This requires the Spark to be connected over USB.
    """
    utils.esptool(*cmd)
