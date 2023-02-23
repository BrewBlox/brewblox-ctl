"""
User service management
"""

import re

import click

from brewblox_ctl import click_helpers, const, sh, utils
from brewblox_ctl.commands.docker import up


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Command collector"""


@cli.group()
def service():
    """Edit or remove services in docker-compose.yml."""


def restart_services(ctx: click.Context, **kwargs):
    if utils.confirm('Do you want to restart your Brewblox services?'):
        ctx.invoke(up, **kwargs)


@service.command()
@click.option('--image',
              help='Image type filter. Leave blank to show all images.')
@click.option('--file',
              default='docker-compose.yml',
              help='docker compose configuration file.')
def show(image, file):
    """Show all services of a specific type.

    Use the --image flag to filter."""
    utils.check_config()
    services = utils.list_services(image, file)
    click.echo('\n'.join(services), nl=bool(services))


@service.command()
@click.argument('services', type=str, nargs=-1)
@click.pass_context
def remove(ctx, services):
    """Remove a service."""
    utils.check_config()
    utils.confirm_mode()

    config = utils.read_compose()
    for name in services:
        try:
            del config['services'][name]
            utils.info(f"Removed service '{name}'")
        except KeyError:
            utils.warn(f"Service '{name}' not found")

    if services:
        utils.write_compose(config)
        restart_services(ctx, compose_args=['--remove-orphans'])


@service.command()
@click.option('--http',
              envvar=const.ENV_KEY_PORT_HTTP,
              help='Port used for HTTP connections.')
@click.option('--https',
              envvar=const.ENV_KEY_PORT_HTTPS,
              help='Port used for HTTPS connections.')
@click.option('--mqtt',
              envvar=const.ENV_KEY_PORT_MQTT,
              help='Port used for MQTT connections.')
def ports(http, https, mqtt):
    """Update used ports"""
    utils.check_config()
    utils.confirm_mode()

    cfg = {
        const.ENV_KEY_PORT_HTTP: http,
        const.ENV_KEY_PORT_HTTPS: https,
        const.ENV_KEY_PORT_MQTT: mqtt,
    }

    utils.info('Writing port settings to .env...')
    for key, val in cfg.items():
        utils.setenv(key, val)


def nested_setdefault(parent, lookups):
    obj = parent
    for (key, default) in lookups:
        obj.setdefault(key, default)
        obj = obj[key]
    return obj


def clean_empty(d):
    if isinstance(d, list):
        return [v for v in (clean_empty(v) for v in d) if v]
    if isinstance(d, dict):
        return {k: v for k, v in ((k, clean_empty(v)) for k, v in d.items()) if v}
    return d


def check_port_value(ctx, param, value):
    if not re.match(r'^(\d+:\d+|\d+)$', value):
        raise click.BadParameter('Port value must either be an integer, or formatted as int:int')
    return value


@service.command()
@click.option('-d', '--delete', is_flag=True,
              help='Remove exposed port from configuration.')
@click.argument('service', type=str, callback=utils.check_service_name)
@click.argument('value', type=str, callback=check_port_value)
@click.pass_context
def expose(ctx, delete, service, value):
    """Add exposed port to docker-compose.yml for backend service"""
    config = utils.read_compose()

    ports = nested_setdefault(config, [
        ('services', {}),
        (service, {}),
        ('ports', [])
    ])

    if (value in ports) ^ delete:
        return  # already in desired state

    if delete:
        ports.remove(value)
    else:
        ports.append(value)

    config['services'] = clean_empty(config['services'])
    utils.write_compose(config)
    restart_services(ctx)


@service.command()
@click.argument('services', type=str, nargs=-1)
@click.pass_context
def pull(ctx, services):
    """Pull one or more services without doing a full update."""
    sudo = utils.optsudo()
    sh(f'{sudo}docker compose pull ' + ' '.join(services))
    restart_services(ctx)
