"""
Manage users for the auth service
"""

from typing import Optional

import click

from brewblox_ctl import click_helpers, const, utils


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Command collector"""


@cli.group(cls=click_helpers.OrderedGroup)
def auth():
    """Configure password authentication for the web UI."""


@auth.command()
def enable():
    """
    Enable password authentication.
    """
    utils.setenv(const.ENV_KEY_AUTH_ENABLED, str(True))

    if utils.confirm('Do you want to add a new user?'):
        utils.add_user(None, None)


@auth.command()
def disable():
    """
    Disable password authentication.

    This will not remove existing users.
    """
    utils.setenv(const.ENV_KEY_AUTH_ENABLED, str(False))


@auth.command()
@click.option('-u', '--username',
              help='Name for the new web UI user')
@click.option('-p', '--password',
              help='Password for the new web UI user')
def add(username: Optional[str], password: Optional[str]):
    """
    Adds or updates a user.

    If the user already exists, it will be replaced.
    """
    utils.add_user(username, password)


@auth.command()
@click.option('-u', '--username',
              prompt=True,
              help='User name')
def remove(username: str):
    """
    Removes a user.
    """
    utils.remove_user(username)
