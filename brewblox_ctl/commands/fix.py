"""
Host configuration fixes.
"""

import click

from brewblox_ctl import actions, click_helpers, utils


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Command collector"""


@cli.group()
def fix():
    """Fix configuration on the host system."""


@fix.command()
@click.option('--config-file', help='Path to Docker daemon config. Defaults to /etc/docker/daemon.json.')
def ipv6(config_file):
    """Fix IPv6 support on the host machine.

    Reason: https://github.com/docker/for-linux/issues/914
    Unlike globally disabling IPv6 support on the host,
    this has no impact outside the Docker environment.

    Some hosts (Synology) may be using a custom location for the daemon config file.
    If the --config-file argument is not set, the --config-file argument for the active docker daemon is used.
    If that is not set, the default /etc/docker/daemon.json is used.
    """
    utils.confirm_mode()
    actions.fix_ipv6(config_file)


@fix.command()
def avahi():
    """Edit avahi-daemon configuration on the host machine.

    This includes disabling IPv6 mDNS support, and enabling mDNS reflection.
    """
    utils.confirm_mode()
    actions.edit_avahi_config()
