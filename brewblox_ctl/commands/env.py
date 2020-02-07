"""
Brewblox-ctl .env commands
"""


import click
import dotenv

from brewblox_ctl import click_helpers, const, utils


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Command collector"""


@cli.group(cls=click_helpers.OrderedGroup)
def env():
    """Group: list, get, or set env values"""


@env.command()
@click.argument('value',
                type=click.Choice(['true', 'false'], case_sensitive=False),
                default='true')
def skip_confirm(value):
    """Auto-answer 'yes' when prompted to confirm commands."""
    utils.check_config()
    utils.setenv(const.SKIP_CONFIRM_KEY, value.lower())


@env.command(name='list')
def list_env():
    """List all .env variables"""
    utils.check_config()
    for k, v in dotenv.dotenv_values('.env').items():
        click.echo('{} = {}'.format(k, v))
    else:
        click.echo('.env file not found or empty')


@env.command(name='get')
@click.argument('key')
@click.argument('default', default='')
def get_env(key, default):
    click.echo(utils.getenv(key, default))


@env.command(name='set')
@click.argument('key')
@click.argument('value')
def set_env(key, value):
    """Set a .env variable"""
    utils.check_config()
    utils.setenv(key, value)
