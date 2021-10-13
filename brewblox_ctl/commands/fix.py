"""
Host configuration fixes.
"""

import click
from brewblox_ctl import click_helpers, fixes, utils


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Command collector"""


@cli.group()
def fix():
    """Host configuration fixes"""


@fix.command()
@click.option('--config-file', help='Path to Docker daemon config. Defaults to /etc/docker/daemon.json.')
def ipv6(config_file):
    """Fix IPv6 support on the host machine.

    Reason: https://github.com/docker/for-linux/issues/914
    Unlike globally disabling IPv6 support on the host,
    this has no impact outside the Docker environment.

    Some hosts (Synology) may be using a custom location for the daemon config file.
    If the --config-file argument is not set, the --config-file argument for the active docker daemon is used.
    If it is not set, the default /etc/docker/daemon.json is used.
    """
    utils.confirm_mode()
    fixes.fix_ipv6(config_file)


@fix.command()
def avahi_reflection():
    """Unset configuration changes for host Avahi daemon.

    Reason: to offer more granular control, and to avoid
    host configuration changes, mDNS reflection was moved
    to its own Brewblox service.
    """
    utils.confirm_mode()
    fixes.unset_avahi_reflection()
