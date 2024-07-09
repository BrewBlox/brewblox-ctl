"""
Add and configure optional services
"""

from typing import Optional

import click

from brewblox_ctl import click_helpers, utils
from brewblox_ctl.discovery import (DiscoveryType, choose_device,
                                    find_device_by_host, list_devices)


def localtime_volume() -> dict:
    return {
        'type': 'bind',
        'source': '/etc/localtime',
        'target': '/etc/localtime',
        'read_only': True,
    }


def check_create_overwrite(config: dict, name: str):
    if name in config['services']:
        prompt = f'Service `{name}` already exists. Do you want to overwrite it?'
    else:
        prompt = f'Service `{name}` does not yet exist. Do you want to create it?'

    if not utils.confirm(prompt):
        raise SystemExit(1)


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Command collector"""


@cli.command()
@click.option('--discovery', 'discovery_type',
              type=click.Choice(DiscoveryType.choices()),
              default='all',
              help='Discovery setting. Use "all" to check both mDNS and USB')
def discover_spark(discovery_type):
    """
    Discover available Spark controllers.

    This prints device ID for all devices, and IP address for wifi/ethernet devices.
    If a device is connected over USB, and has wifi active, it may show up twice.

    Whether Multicast DNS (mDNS) discovery works
    is dependent on the configuration of your router and avahi-daemon.
    """
    try:
        compose = utils.read_compose()
    except FileNotFoundError:
        compose = None

    list_devices(DiscoveryType[discovery_type], compose)


@cli.command()
@click.option('-n', '--name',
              prompt='How do you want to call this service? The name must be unique',
              callback=utils.check_service_name,
              help='Service name')
@click.option('--discover-now/--no-discover-now',
              default=True,
              help='Select from discovered devices if --device-id is not set')
@click.option('--device-id',
              help='Checked device ID')
@click.option('--discovery', 'discovery_type',
              type=click.Choice(DiscoveryType.choices()),
              default='all',
              help='Methods for discovering devices. This will become part of the service configuration.')
@click.option('--device-host',
              help='Static controller URL')
@click.option('-y', '--yes',
              is_flag=True,
              help='Do not prompt for confirmation')
@click.option('--release',
              default='${BREWBLOX_RELEASE}',
              help='Brewblox release track used by the Spark service.')
@click.option('--simulation',
              is_flag=True,
              help='Add a simulation service. This will override discovery and connection settings.')
def add_spark(name: str,
              discover_now: bool,
              device_id: Optional[str],
              discovery_type: str,
              device_host: Optional[str],
              yes: bool,
              release: str,
              simulation: bool):
    """
    Create or update a Spark service.

    If you run brewblox-ctl add-spark without any arguments,
    it will prompt you for required info, and then create a sensibly configured service.

    If you want to fine-tune your service configuration, multiple arguments are available.

    For a detailed explanation: https://www.brewblox.com/user/services/spark.html#spark-connection-settings
    """
    utils.check_config()
    utils.confirm_mode()

    sudo = utils.optsudo()
    compose: dict = utils.read_compose()
    discovery_type: DiscoveryType = DiscoveryType[discovery_type]

    if not yes:
        check_create_overwrite(compose, name)

    if discover_now and not simulation and not device_id:
        if device_host:
            dev = find_device_by_host(device_host)
        else:
            dev = choose_device(discovery_type, compose)

        if dev:
            device_id = dev.device_id
        else:
            # We have no device ID, and no device host. Avoid a wildcard service
            click.echo('No valid combination of device ID and device host.')
            raise SystemExit(1)

    if discovery_type == DiscoveryType.mqtt:  # pragma: no cover
        utils.warn('Support for MQTT connections is still experimental.')
        utils.warn('To have the controller connect to the eventbus, you also need to run:')
        utils.warn('')
        utils.warn('    brewblox-ctl experimental enable-spark-mqtt')
        utils.warn('')

    environment: list[str] = []

    def push_env(key: str, value):
        if value:
            environment.append(f'BREWBLOX_SPARK_{key.upper()}={value}')

    push_env('discovery', discovery_type)
    push_env('device_id', device_id)
    push_env('device_host', device_host)
    push_env('simulation', simulation)

    compose['services'][name] = {
        'image': f'ghcr.io/brewblox/brewblox-devcon-spark:{utils.docker_tag(release)}',
        'restart': 'unless-stopped',
        'environment': environment,
        'volumes': [
            localtime_volume(),
            {
                'type': 'bind',
                'source': './spark/backup',
                'target': '/app/backup',
            },
        ]
    }

    if simulation:
        mount_dir = f'./simulator__{name}'
        compose['services'][name]['volumes'].append({
            'type': 'bind',
            'source': mount_dir,
            'target': '/app/simulator'
        })
        utils.sh(f'mkdir -m 777 -p {mount_dir}')

    utils.write_compose(compose)
    click.echo(f'Added Spark service `{name}`.')
    click.echo('It will automatically show up in the UI.\n')
    if utils.confirm('Do you want to run `brewblox-ctl up` now?'):
        utils.sh(f'{sudo}docker compose up -d')


@cli.command()
@click.option('-y', '--yes',
              is_flag=True,
              help='Do not prompt for confirmation')
def add_tilt(yes):
    """
    Create a service for the Tilt hydrometer.

    The service listens for Bluetooth status updates from the Tilt,
    and requires the host to have a Bluetooth receiver.

    The empty ./tilt dir is created to hold calibration files.
    """
    utils.check_config()
    utils.confirm_mode()

    name = 'tilt'
    sudo = utils.optsudo()
    compose = utils.read_compose()

    if not yes:
        check_create_overwrite(compose, name)

    compose['services'][name] = {
        'image': 'ghcr.io/brewblox/brewblox-tilt:${BREWBLOX_RELEASE}',
        'restart': 'unless-stopped',
        'privileged': True,
        'volumes': [
            localtime_volume(),
            {
                'type': 'bind',
                'source': f'./{name}',
                'target': '/share',
            },
            {
                'type': 'bind',
                'source': '/var/run/dbus',
                'target': '/var/run/dbus',
            },
        ],
        'labels': [
            'traefik.enable=false',
        ],
    }

    utils.sh(f'mkdir -p ./{name}')

    utils.write_compose(compose)
    click.echo(f'Added Tilt service `{name}`.')
    click.echo('It will automatically show up in the UI.\n')
    if utils.confirm('Do you want to run `brewblox-ctl up` now?'):
        utils.sh(f'{sudo}docker compose up -d')


@cli.command()
@click.option('-n', '--name',
              prompt='How do you want to call this service? The name must be unique',
              callback=utils.check_service_name,
              default='plaato',
              help='Service name')
@click.option('--token',
              prompt='What is your Plaato auth token? '
              'For more info: https://plaato.io/apps/help-center#!hc-auth-token',
              help='Plaato authentication token.')
@click.option('-y', '--yes',
              is_flag=True,
              help='Do not prompt for confirmation')
def add_plaato(name, token, yes):
    """
    Create a service for the Plaato airlock.

    This will periodically query the Plaato server for current state.
    An authentication token is required.

    See https://plaato.io/apps/help-center#!hc-auth-token on how to get one.
    """
    utils.check_config()
    utils.confirm_mode()

    sudo = utils.optsudo()
    compose = utils.read_compose()

    if not yes:
        check_create_overwrite(compose, name)

    compose['services'][name] = {
        'image': 'ghcr.io/brewblox/brewblox-plaato:${BREWBLOX_RELEASE}',
        'restart': 'unless-stopped',
        'environment': {
            'PLAATO_AUTH': token,
        },
        'command': f'--name={name}',
        'volumes': [localtime_volume()]
    }

    utils.write_compose(compose)
    click.echo(f'Added Plaato service `{name}`.')
    click.echo('This service publishes history data, but does not have a UI component.')
    if utils.confirm('Do you want to run `brewblox-ctl up` now?'):
        utils.sh(f'{sudo}docker compose up -d')
