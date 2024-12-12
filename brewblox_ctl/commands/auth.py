"""
Manage users for the auth service
"""

from typing import Optional

import click

from brewblox_ctl import auth_users, click_helpers


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Command collector"""


@cli.group(cls=click_helpers.OrderedGroup)
def auth():
    """Configure password authentication for the web UI."""


@auth.command()
@click.option('-u', '--username', help='Name for the new web UI user')
@click.option('-p', '--password', help='Password for the new web UI user')
def add(username: Optional[str], password: Optional[str]):
    """
    Add or update a user.

    If the user already exists, they will be replaced.
    """
    auth_users.add_user(username, password)


@auth.command()
@click.option('-u', '--username', prompt=True, help='User name')
def remove(username: str):
    """
    Remove a user.
    """
    auth_users.remove_user(username)
