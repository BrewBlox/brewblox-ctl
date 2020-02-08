"""
Brewblox-ctl docker commands
"""


import click

from brewblox_ctl import click_helpers, utils
from brewblox_ctl.utils import sh


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Command collector"""


@cli.command()
def up():
    """Start all services.

    This wraps `docker-compose up -d --remove-orphans`
    """
    utils.check_config()
    utils.confirm_mode()
    sudo = utils.optsudo()
    sh('{}docker-compose up -d --remove-orphans'.format(sudo))


@cli.command()
def down():
    """Stop all services.

    This wraps `docker-compose down --remove-orphans`
    """
    utils.check_config()
    utils.confirm_mode()
    sudo = utils.optsudo()
    sh('{}docker-compose down --remove-orphans'.format(sudo))


@cli.command()
def restart():
    """Stop and start all services.

    This wraps `docker-compose down --remove-orphans; docker-compose up -d`

    Note: `docker-compose restart` also exists -
    it restarts containers without recreating them.
    """
    utils.check_config()
    utils.confirm_mode()
    sudo = utils.optsudo()
    sh('{}docker-compose down --remove-orphans'.format(sudo))
    sh('{}docker-compose up -d'.format(sudo))


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
    sh('{}docker-compose logs --follow {}'.format(sudo, ' '.join(services)))


@cli.command()
def kill():
    """Stop and remove all containers on this computer.

    This includes those not from Brewblox.
    """
    utils.confirm_mode()
    sudo = utils.optsudo()
    sh('{}docker rm --force $({}docker ps -aq)'.format(sudo, sudo), check=False)
