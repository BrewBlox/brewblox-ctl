"""
User service management
"""

import click

from .. import click_helpers, utils
from .docker import up


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
@click.option('--image', help='Image type filter. Leave blank to show all images.')
def show(image):
    """Show all services of a specific type.

    Use the --image flag to filter.
    """
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


@service.command()
@click.argument('services', type=str, nargs=-1)
@click.pass_context
def pull(ctx, services):
    """Pull one or more services without doing a full update."""
    sudo = utils.optsudo()
    utils.sh(f'{sudo}docker compose pull ' + ' '.join(services))
    restart_services(ctx)
