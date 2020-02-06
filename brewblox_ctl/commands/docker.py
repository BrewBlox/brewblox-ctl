"""
Brewblox-ctl docker commands
"""


import click

from brewblox_ctl import click_helpers, utils
from brewblox_ctl.utils import sh


def release_tag(release):
    if not release and not utils.is_brewblox_cwd():
        print('Please run this command in a BrewBlox directory, or use the --release argument')
        raise SystemExit(1)

    return utils.docker_tag(release)


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Command collector"""


@cli.command()
def down():
    """Stop running services"""
    utils.check_config()
    sh('{}docker-compose down --remove-orphans'.format(utils.optsudo()))


@cli.command()
def up():
    """Start all services if not running"""
    utils.check_config()
    utils.confirm_mode()
    sh('{}docker-compose up -d --remove-orphans'.format(utils.optsudo()))


@cli.command()
def restart():
    """(re)start all services"""
    utils.check_config()
    utils.confirm_mode()
    sudo = utils.optsudo()
    sh('{}docker-compose down --remove-orphans'.format(sudo))
    sh('{}docker-compose up -d'.format(sudo))


@cli.command()
def kill():
    """Stop and remove all containers on this machine.

    This includes those not from Brewblox.
    """
    utils.confirm_mode()
    sudo = utils.optsudo()

    utils.info('Killing containers...')
    sh('{}docker rm --force $({}docker ps -aq)'.format(sudo, sudo), check=False)
