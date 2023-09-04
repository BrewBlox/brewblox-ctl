"""
Manage users for the auth service
"""

import re

import click

from brewblox_ctl import click_helpers, utils


def check_username(ctx, param, value):
    if not re.fullmatch(r'\w+', value):
        raise click.BadParameter('Names can only contain letters, numbers, - or _')
    return value


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Command collector"""


@cli.group(cls=click_helpers.OrderedGroup)
def user():
    """Add or remove web UI users."""


@user.command()
@click.option('-u', '--username',
              prompt=True,
              callback=check_username,
              help='Name for the new web UI user')
@click.option('-p', '--password',
              prompt=True,
              hide_input=True,
              help='Password for the new web UI user')
def add(username: str, password: str):
    """
    Adds or updates a user.

    If the user already exists, it will be replaced.
    """
    utils.add_user(username, password)


@user.command()
@click.option('-u', '--username',
              prompt=True,
              help='User name')
def remove(username: str):
    """
    Removes a user.
    """
    utils.remove_user(username)
