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
    """List, get, or set env values.

    Brewblox stores system settings in the brewblox/.env file.
    These settings are used in docker-compose.yml files, and in brewblox-ctl commands.

    You can add your own, and use them in docker-compose.yml with the `${VAR_NAME}` syntax.
    """


@env.command()
@click.argument('value',
                type=click.Choice(['true', 'false'], case_sensitive=False),
                default='true')
def skip_confirm(value):
    """Auto-answer 'yes' when prompted to confirm commands.

    This sets the 'BREWBLOX_SKIP_CONFIRM' variable in .env.
    You can still use the `brewblox-ctl [--dry-run|--verbose] COMMAND` arguments.
    """
    utils.check_config()
    utils.confirm_mode()
    utils.setenv(const.SKIP_CONFIRM_KEY, value.lower())


@env.command(name='list')
def list_env():
    """List all .env variables

    This does not include other variables set in the current shell.
    """
    utils.check_config()
    for k, v in dotenv.dotenv_values('.env').items():
        click.echo('{} = {}'.format(k, v))


@env.command(name='get')
@click.argument('key')
@click.argument('default', default='')
def get_env(key, default):
    """Read a single env variable.

    This includes values from .env, but also other shell values.
    """
    click.echo(utils.getenv(key, default))


@env.command(name='set')
@click.argument('key')
@click.argument('value')
def set_env(key, value):
    """Set a .env variable.

    The value will be added to the .env file. You can set new variables with this.
    """
    utils.check_config()
    utils.confirm_mode()
    utils.setenv(key, value)
