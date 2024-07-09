"""
Commands for experimental features
"""

import json
from pathlib import Path
from typing import Optional

import click

from brewblox_ctl import click_helpers, utils
from brewblox_ctl.discovery import (DiscoveredDevice, DiscoveryType,
                                    choose_device, find_device_by_host)


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Top-level commands"""


@cli.group()
def experimental():
    """Experimental features."""


@experimental.command()
@click.option('--server-host',
              default=None,
              help='External hostname for the Brewblox system. '
              'This value defaults to "$HOSTNAME.local".')
@click.option('--server-port',
              type=int,
              default=None,
              help='External MQTTS port for the Brewblox system. '
              'This value defaults to the current BREWBLOX_PORT_MQTTS value.')
@click.option('--device-host',
              help='Static controller URL. This will only be used for the initial credential exchange.')
@click.option('--cert-file',
              type=click.Path(exists=True, resolve_path=True, path_type=Path),
              default='./traefik/minica.pem',
              help='Path to broker certificate.')
@click.option('--device-id',
              help='Manually set the device ID. '
              'brewblox-ctl will not attempt to communicate, and print a cURL command instead. '
              'If --device-host is set, it will be included in the printed command.')
@click.option('--release', default=None, help='Brewblox release track.')
def enable_spark_mqtt(server_host: Optional[str],
                      server_port: Optional[int],
                      device_host: Optional[str],
                      cert_file: Path,
                      device_id: Optional[str],
                      release: Optional[str],
                      ):
    """
    Enables secured MQTT communication between a Spark 4 and Brewblox.

    The server exposes a TLS+password protected MQTT port.
    For MQTT login, the controller ID is always used as username.
    To provide compatibility with self-signed server SSL certificates,
    the Spark must be sent the certificate itself.

    \b
    Steps:
        - Determine device ID. Discover Spark if --device-id not set.
        - Generate new password.
        - Add new MQTT user, with username = device ID. Overwrite if exists.
        - Reload broker to apply configuration change.
        - If controller is in local network:
            - Send MQTT credentials to controller.
            - Send server certificate to controller.
        - Else:
            - Print curl command for user to manually send MQTT credentials.
            - Print curl command for user to manually send server certificate.
    """
    utils.check_config()
    utils.confirm_mode()

    opts = utils.get_opts()
    config = utils.get_config()
    sudo = utils.optsudo()
    tag = utils.docker_tag(release)
    compose = utils.read_compose()

    # Users can manually set the device ID if the controller is remote
    # In this case we don't send configuration, but print a command instead
    send_config = not device_id

    if server_host is None:
        server_host = f'{utils.hostname()}.local'

    if server_port is None:
        server_port = config.ports.mqtts

    cert = cert_file.read_text()

    # If this is a dry run, we'll massage the settings a bit
    # The command shouldn't fail if no controller is present
    if opts.dry_run:
        device_id = device_id or '123456'
        device_host = device_host or 'dummy.home'
        utils.warn("This is a dry run. We'll use dummy settings where needed.")
        utils.warn(f'Device ID = {device_id}')
        utils.warn(f'Device hostname = {device_host}')
        utils.warn(f'System hostname = {server_host}')

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
        dev = choose_device(DiscoveryType.mqtt, compose)

    if not dev:
        return

    device_id = dev.device_id
    device_host = dev.device_host
    password = utils.random_string(20)
    mosquitto_path = Path('./mosquitto').resolve()

    credentials = {
        'hostname': server_host,
        'port': server_port,
        'password': password,
    }

    # Set username/password for device
    utils.info('Adding user to MQTT eventbus ...')
    utils.sh(f'{sudo}docker run' +
             ' -it --rm' +
             f' -v {mosquitto_path}:/mosquitto/include' +
             ' --entrypoint mosquitto_passwd' +
             f' ghcr.io/brewblox/mosquitto:{tag}' +
             ' -b /mosquitto/include/externals.passwd' +
             f' {device_id} {password}')

    # Reload eventbus configuration
    utils.sh(f'{sudo}docker compose kill -s SIGHUP eventbus', silent=True)

    # Send credentials to controller
    # Use cURL to make the command reproducible on different machines
    send_credentials_cmd = ' '.join([
        'curl -sS -X POST',
        f'http://{device_host}/mqtt_credentials',
        f"-d '{json.dumps(credentials)}'",
    ])

    send_cert_cmd = ' '.join([
        'curl -sS -X POST',
        f'http://{device_host}/ca_certificate',
        f"-d '{cert}'"
    ])

    if send_config:
        utils.info('Sending MQTT configuration to controller ...')
        utils.sh(send_credentials_cmd)
        utils.sh(send_cert_cmd)
    else:
        utils.warn('====================================================')
        utils.warn('IMPORTANT: CONFIGURATION MUST BE APPLIED MANUALLY.')
        utils.warn('This happens when the --device-id argument is used.')
        utils.warn('To apply MQTT configuration, run the commands below.')
        utils.warn('====================================================')
        click.echo('')
        click.echo(send_credentials_cmd)
        click.echo('')
        click.echo(send_cert_cmd)
        click.echo('')
        utils.warn('====================================================')
        utils.warn('IMPORTANT: CONFIGURATION MUST BE APPLIED MANUALLY.')
        utils.warn('This happens when the --device-id argument is used.')
        utils.warn('To apply MQTT configuration, run the commands above.')
        utils.warn('====================================================')
