"""
Brewblox-ctl docker commands
"""


import click
from brewblox_ctl import click_helpers, utils
from brewblox_ctl.utils import sh


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Command collector"""


@cli.command(context_settings=dict(
    ignore_unknown_options=True,
))
@click.argument('compose_args', nargs=-1, type=click.UNPROCESSED)
def up(compose_args):
    """Start all services.

    This wraps `docker-compose up -d`
    """
    utils.check_config()
    utils.confirm_mode()
    sudo = utils.optsudo()
    sh(f'{sudo}docker-compose up -d ' + ' '.join(list(compose_args)))


@cli.command(context_settings=dict(
    ignore_unknown_options=True,
))
@click.argument('compose_args', nargs=-1, type=click.UNPROCESSED)
def down(compose_args):
    """Stop all services.

    This wraps `docker-compose down`
    """
    utils.check_config()
    utils.confirm_mode()
    sudo = utils.optsudo()
    sh(f'{sudo}docker-compose down ' + ' '.join(list(compose_args)))


@cli.command(context_settings=dict(
    ignore_unknown_options=True,
))
@click.argument('compose_args', nargs=-1, type=click.UNPROCESSED)
def restart(compose_args):
    """Recreates all services.

    This wraps `docker-compose up -d --force-recreate`

    Note: `docker-compose restart` also exists -
    it restarts containers without recreating them.
    """
    utils.check_config()
    utils.confirm_mode()
    sudo = utils.optsudo()
    sh(f'{sudo}docker-compose up -d --force-recreate ' + ' '.join(list(compose_args)))


@cli.command()
@click.argument('services', nargs=-1, required=False)
def follow(services):
    """Show logs for one or more services.

    This will start watching the logs for specified services.
    Call without arguments to show logs for all running services.

    Once started, press ctrl+C to stop.

    Service name will be equal to those specified in docker-compose.log,
    not the container name.

    To follow logs for service 'spark-one':

    \b
        GOOD: `brewblox-ctl follow spark-one`
         BAD: `brewblox-ctl follow brewblox_spark-one_1`
    """
    utils.check_config()
    sudo = utils.optsudo()
    sh(f'{sudo}docker-compose logs --follow ' + ' '.join(services))


@cli.command()
def kill():
    """Stop and remove all containers on this computer.

    This includes those not from Brewblox.
    """
    utils.confirm_mode()
    sudo = utils.optsudo()
    sh(f'{sudo}docker rm --force $({sudo}docker ps -aq)', check=False)
