"""
Brewblox-ctl docker commands
"""

import re

import click

from brewblox_ctl import click_helpers, utils


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Command collector"""


@cli.command(
    context_settings=dict(
        ignore_unknown_options=True,
    )
)
@click.option('-d', '--detach', is_flag=True, hidden=True)
@click.argument('compose_args', nargs=-1, type=click.UNPROCESSED)
def up(detach, compose_args):
    """Start all services.

    This wraps `docker compose up -d`
    """
    utils.check_config()
    utils.confirm_mode()
    utils.docker_up(compose_args)


@cli.command(
    context_settings=dict(
        ignore_unknown_options=True,
    )
)
@click.argument('compose_args', nargs=-1, type=click.UNPROCESSED)
def down(compose_args):
    """Stop all services.

    This wraps `docker compose down`
    """
    utils.check_config()
    utils.confirm_mode()
    utils.docker_down(compose_args)


@cli.command(
    context_settings=dict(
        ignore_unknown_options=True,
    )
)
@click.argument('compose_args', nargs=-1, type=click.UNPROCESSED)
def restart(compose_args):
    """Recreates all services.

    This wraps `docker compose up -d --force-recreate`

    Note: `docker compose restart` also exists -
    it restarts containers without recreating them.
    """
    utils.check_config()
    utils.confirm_mode()
    utils.docker_up(['--force-recreate', *list(compose_args)])


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
    utils.sh(f'{sudo}docker compose logs --follow ' + ' '.join(services))


@cli.command()
@click.option('--zombies', is_flag=True, help='Find and kill all zombie processes.')
def kill(zombies):
    """Stop and remove all containers on this host.

    This includes those not from Brewblox.

    If the --zombies flag is set,
    leftover processes that are still claiming a port will be forcibly removed.
    Use this if you get "port is already allocated" errors after your system crashed.
    """
    utils.confirm_mode()
    sudo = utils.optsudo()
    utils.sh(f'{sudo}docker rm --force $({sudo}docker ps -aq)', check=False)

    if zombies:
        # We can't use psutil for this, as we need root rights to get pids
        if not utils.command_exists('netstat'):
            utils.warn('Command `netstat` not found. Please install it by running:')
            utils.warn('')
            utils.warn('    sudo apt-get update && sudo apt-get install net-tools')
            utils.warn('')
            return

        procs = re.findall(r'(\d+)/docker-proxy', utils.sh('sudo netstat -pna', capture=True))

        if procs:
            utils.info(f'Removing {len(procs)} zombies ...')
            utils.sh('sudo service docker stop')
            for proc in procs:
                utils.sh(f'sudo kill -9 {proc}')
            utils.sh('sudo service docker start')
