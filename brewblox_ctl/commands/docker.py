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
    """Start all services"""
    utils.check_config()
    utils.confirm_mode()
    sudo = utils.optsudo()
    sh('{}docker-compose up -d --remove-orphans'.format(sudo))


@cli.command()
def down():
    """Stop all services"""
    utils.check_config()
    sudo = utils.optsudo()
    sh('{}docker-compose down --remove-orphans'.format(sudo))


@cli.command()
def restart():
    """Stop and start all services"""
    utils.check_config()
    utils.confirm_mode()
    sudo = utils.optsudo()
    sh('{}docker-compose down --remove-orphans'.format(sudo))
    sh('{}docker-compose up -d'.format(sudo))


@cli.command()
@click.argument('services', nargs=-1, required=False)
def follow(services):
    utils.check_config()
    sudo = utils.optsudo()
    sh('{}docker-compose logs --follow {}'.format(sudo, ' '.join(services)))


@cli.command()
def kill():
    """Stop and remove all containers on this machine.

    This includes those not from Brewblox.
    """
    utils.confirm_mode()
    sudo = utils.optsudo()
    sh('{}docker rm --force $({}docker ps -aq)'.format(sudo, sudo), check=False)
