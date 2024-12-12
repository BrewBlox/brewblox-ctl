"""
Database manipulation commands
"""

import click

from brewblox_ctl import click_helpers, migration, utils


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Command collector"""


@cli.group()
def database():
    """Database migration commands."""


@database.command()
@click.option(
    '--target', default='victoria', help='Where to store exported data', type=click.Choice(['victoria', 'file'])
)
@click.option(
    '--duration',
    default='',
    prompt='From how far back do you want to migrate data? (eg. 1d, 30d, 1y). ' 'Leave empty to migrate everything.',
    help='Period of exported data. Example: 30d',
)
@click.option(
    '--offset',
    multiple=True,
    nargs=2,
    type=click.Tuple([str, int]),
    default=[],
    help='Start given service(s) with an offset. Useful for resuming exports. '
    'Example: [--offset spark-one 10000 --offset spark-two 5000]',
)
@click.argument('services', nargs=-1)
def from_influxdb(target, duration, offset, services):
    """Migrate history data from InfluxDB to Victoria Metrics or file.

    In config version 0.7.0 Victoria Metrics replaced InfluxDB as history database.

    This command exports the history data from InfluxDB,
    and then either immediately imports it to Victoria Metrics, or saves it to file.

    By default, all services are migrated.
    You can override this by listing the services you want to migrate.

    When writing data to file, files are stored in the ./influxdb-export/ directory.

    \b
    Steps:
        - Create InfluxDB container.
        - Get list of services from InfluxDB. (Optional)
        - Read data from InfluxDB.
        - Write data to Victoria Metrics.     (Optional)
        - OR: write data to file.             (Optional)
    """
    utils.check_config()
    utils.confirm_mode()
    migration.migrate_influxdb(target, duration, list(services), list(offset))
