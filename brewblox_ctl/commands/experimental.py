"""
Commands for experimental features
"""

import json
from pathlib import Path

import click

from brewblox_ctl import click_helpers, const, sh, utils
from brewblox_ctl.discovery import (DiscoveredDevice, DiscoveryType,
                                    choose_device, find_device_by_host)


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Top-level commands"""


@cli.group()
def experimental():
    """Experimental features."""


@experimental.command()
@click.option('--system-host',
              default=None,
              help='External hostname for the Brewblox system. '
              'This value defaults to the server LAN IP address.')
@click.option('--system-port',
              type=int,
              default=None,
              help='External MQTTS port for the Brewblox system. '
              'This value defaults to the current BREWBLOX_PORT_MQTTS value.')
@click.option('--device-host',
              help='Static controller URL. This will only be used for the initial credential exchange.')
@click.option('--device-id',
              help='Manually set the device ID. '
              'brewblox-ctl will not attempt to communicate, and print a cURL command instead. '
              'If --device-host is set, it will be included in the printed command.')
@click.option('--release', default=None, help='Brewblox release track')
def enable_spark_mqtt(system_host, system_port, device_host, device_id, release):
    """
    Enable MQTT for a Spark 4 controller.

    The Spark will connect to the password-protected MQTTS (MQTT + TLS) port.
    This command will automatically generate a random password for this particular device,
    and send the address and password to the Spark.
    """
    utils.check_config()
    utils.confirm_mode()

    opts = utils.ctx_opts()
    sudo = utils.optsudo()
    tag = utils.docker_tag(release)
    config = utils.read_compose()

    # Users can manually set the device ID if the controller is remote
    # In this case we don't send credentials, but print a command instead
    send_credentials = not device_id

    if system_host is None:
        system_host = utils.host_lan_ip()

    if system_port is None:
        system_port = int(utils.getenv(const.ENV_KEY_PORT_MQTTS, const.DEFAULT_PORT_MQTTS))

    # If this is a dry run, we'll massage the settings a bit
    # The command shouldn't fail if no controller is present
    if opts.dry_run:
        device_id = device_id or '123456'
        device_host = device_host or 'dummy.home'
        utils.warn("This is a dry run. We'll use dummy settings where needed.")
        utils.warn(f'Device ID = {device_id}')
        utils.warn(f'Device hostname = {device_host}')
        utils.warn(f'System hostname = {system_host}')

    if device_id:
        dev = DiscoveredDevice(
            discovery='TCP',
            device_id=device_id,
            model='Spark 4',
            device_host=device_host or '{DEVICE_HOST}'
        )
    elif device_host:
        dev = find_device_by_host(device_host)
    else:
        dev = choose_device(DiscoveryType.mqtt, config)

    if not dev:
        return

    device_id = dev.device_id
    device_host = dev.device_host
    password = utils.random_string(20)
    mosquitto_path = Path('./mosquitto').resolve()

    credentials = {
        'hostname': system_host,
        'port': system_port,
        'password': password,
    }

    # Set username/password for device
    utils.info('Adding user to MQTT eventbus...')
    sh(f'{sudo}docker run' +
       ' -it --rm' +
       f' -v {mosquitto_path}:/mosquitto/include' +
       ' --entrypoint mosquitto_passwd' +
       f' ghcr.io/brewblox/mosquitto:{tag}' +
       ' -b /mosquitto/include/externals.passwd' +
       f' {device_id} {password}')

    # Reload eventbus configuration
    sh(f'{sudo}docker compose kill -s SIGHUP eventbus', silent=True)

    # Send credentials to controller
    # Use cURL to make the command reproducible on different machines
    send_credentials_cmd = ' '.join([
        'curl -sS -X POST',
        f"-d '{json.dumps(credentials)}'",
        f'http://{device_host}/mqtt_credentials',
    ])

    if send_credentials:
        utils.info('Sending MQTT credentials to controller...')
        sh(send_credentials_cmd)
    else:
        utils.warn('Device ID was set manually.')
        utils.warn('To set MQTT credentials on your Spark, run:')
        utils.warn('')
        utils.warn('    ' + send_credentials_cmd)
        utils.warn('')
