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
    '--dense-days',
    type=click.IntRange(min=0),
    default=None,
    help='Days of raw history to copy into the dense database. [default: 30]',
)
@click.option('--status', 'show_status', is_flag=True, help='Show the status of the migration, and exit.')
@click.option('--discard', is_flag=True, help='Stop the migration, and discard it: a new one starts over.')
def migrate_history(dense_days, show_status, discard):
    """Migrate the legacy history in ./victoria-legacy.

    Since configuration version 0.12.0, history is kept in two databases.
    By default, the dense database keeps raw history for 30 days,
    and the long-term database keeps averages of every 60 seconds.
    The update to 0.12.0 moved the older history database to ./victoria-legacy.

    This command starts the migration of that history.
    It runs in the background, inside the history service, and continues after restarts.
    Graphs fill in backwards from the update: first the last days of raw history (see --dense-days),
    then averages of older history.

    When the migration is done, check your graphs, and remove ./victoria-legacy
    with `brewblox-ctl database remove-legacy-history`.

    A migration that stopped with an error does not continue.
    Discard it with --discard, and run this command again: the new migration starts from the beginning.
    --discard is also the only way to start again with another --dense-days.

    \b
    Steps:
        - Show the status if the migration runs, is done, or stopped with an error.
        - Check the free memory and disk space.
        - Find the earliest history in ./victoria-legacy.
        - Start the migration in the background, or resume it.
    """
    utils.check_config()

    if show_status and discard:
        raise click.UsageError('--status and --discard cannot be combined.')

    if show_status:
        migration.show_migration_status()
        return

    utils.confirm_mode()

    if discard:
        migration.discard_migration_confirmed()
    else:
        migration.migrate_history(dense_days)


@database.command()
@click.option('--force', is_flag=True, help='Remove the legacy history, also if the migration is not done.')
def remove_legacy_history(force):
    """Remove the legacy history in ./victoria-legacy.

    Once `brewblox-ctl database migrate-history` is done, the legacy history in ./victoria-legacy can be removed.
    The migrated history is then kept as averages in the long-term database.

    This cannot be undone.
    You can copy ./victoria-legacy to another disk first.

    \b
    Steps:
        - Check that the migration is done, unless --force is used.
        - Show the periods and fields that were not migrated.
        - Copy ./victoria-legacy to another disk (optional).
        - Discard an unfinished migration (with --force).
        - Stop services.
        - Generate the configuration without the legacy database.
        - Remove ./victoria-legacy.
        - Start services.
    """
    utils.check_config()
    utils.confirm_mode()
    migration.remove_legacy_history(force)
