"""
Tests brewblox_ctl.click_helpers
"""

import click

from brewblox_ctl import click_helpers

TESTED = click_helpers.__name__


@click.group(cls=click_helpers.OrderedGroup)
def cli_one():
    pass


@click.group(cls=click_helpers.OrderedGroup)
def cli_two():
    pass


@cli_one.command()
def z_cmd_one_one():
    """Starts with Z to check list order"""


@cli_one.command()
def cmd_one_two():
    pass


@cli_two.command()
def cmd_two_one():
    pass


@cli_two.command()
def _cmd_two_two():
    """Starts with _ to check list order"""


def test_ordered_commands():
    cli = click_helpers.OrderedCommandCollection(
        sources=[
            cli_one,
            cli_two,
        ])

    assert cli.list_commands(None) == [
        'z-cmd-one-one',
        'cmd-one-two',
        'cmd-two-one',
        '-cmd-two-two',
    ]
