"""
Commands for experimental features
"""

import json
from pathlib import Path

import click

from brewblox_ctl import click_helpers, const, sh, utils
from brewblox_ctl.discovery import (DiscoveryType, choose_device,
                                    find_device_by_host)


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
@click.option('--release', default=None, help='Brewblox release track')
def enable_spark_mqtt(system_host, system_port, device_host, release):
    """
    Enable MQTT for a Spark 4 controller.

    The Spark will connect to the password-protected MQTTS (MQTT + TLS) port.
    This command will automatically generate a random password for this particular device,
    and send the address and password to the Spark.
    """
    utils.check_config()
    utils.confirm_mode()

    sudo = utils.optsudo()
    tag = utils.docker_tag(release)
    config = utils.read_compose()

    if system_host is None:
        system_host = utils.host_lan_ip()

    if system_port is None:
        system_port = int(utils.getenv(const.ENV_KEY_PORT_MQTTS))

    if device_host:
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
    sh(f'{sudo}docker run'
       ' -it --rm'
       f' -v {mosquitto_path}:/mosquitto/include'
       ' --entrypoint mosquitto_passwd'
       f' ghcr.io/brewblox/mosquitto:{tag}'
       f' -b /mosquitto/include/externals.passwd'
       f' {device_id} {password}')

    # Reload eventbus configuration
    sh(f'{sudo}docker compose kill -s SIGHUP eventbus', silent=True)

    # Send credentials to controller
    utils.info('Sending MQTT credentials to controller...')
    sh(f'{const.CLI} http post'
       f' http://{device_host}/mqtt_credentials'
       ' --quiet'
       f" -d '{json.dumps(credentials)}'")
