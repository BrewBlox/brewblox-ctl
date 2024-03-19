"""
Manage users for the auth service
"""

from typing import Optional

import click

from brewblox_ctl import auth_users, click_helpers, utils


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
    config = utils.get_config()
    if not config.auth.enabled:
        config.auth.enabled = True
        utils.save_config(config)

    if utils.confirm('Do you want to add a new user?'):
        auth_users.add_user(None, None)


@auth.command()
def disable():
    """
    Disable password authentication.

    This will not remove existing users.
    """
    config = utils.get_config()
    if config.auth.enabled:
        config.auth.enabled = False
        utils.save_config(config)


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
    auth_users.add_user(username, password)


@auth.command()
@click.option('-u', '--username',
              prompt=True,
              help='User name')
def remove(username: str):
    """
    Removes a user.
    """
    auth_users.remove_user(username)
