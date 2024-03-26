"""
Shortcuts to external tools stored in virtualenv
"""

import click

from brewblox_ctl import actions, click_helpers


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Command collector"""


@cli.command(
    context_settings={
        'help_option_names': ['--click-help'],
        'ignore_unknown_options': True,
    }
)
@click.argument('cmd', nargs=-1, type=click.UNPROCESSED)
def esptool(cmd):
    """Run the esptool.py tool for Spark 4 management.

    This requires the Spark to be connected over USB.
    """
    actions.start_esptool(*cmd)


@cli.command(
    context_settings={
        'help_option_names': ['--click-help'],
        'ignore_unknown_options': True,
    }
)
@click.argument('cmd', nargs=-1, type=click.UNPROCESSED)
def dotenv(cmd):
    """Run the dotenv tool.

    This is a command-line shortcut for manually editing
    the .env file.
    """
    actions.start_dotenv(*cmd)
