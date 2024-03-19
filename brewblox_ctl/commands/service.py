"""
User service management
"""

import re

import click

from brewblox_ctl import click_helpers, sh, utils
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
def show(image):
    """Show all services of a specific type.

    Use the --image flag to filter."""
    utils.check_config()
    services = utils.list_services(image)
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
@click.argument('services', type=str, nargs=-1)
@click.pass_context
def pull(ctx, services):
    """Pull one or more services without doing a full update."""
    sudo = utils.optsudo()
    sh(f'{sudo}docker compose pull ' + ' '.join(services))
    restart_services(ctx)
