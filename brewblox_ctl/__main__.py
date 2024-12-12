"""
Entrypoint for the Brewblox commands menu
"""

import sys
from pathlib import Path
from subprocess import CalledProcessError
from typing import Optional

import click
from click.exceptions import ClickException
from dotenv import load_dotenv

from brewblox_ctl import click_helpers, utils
from brewblox_ctl.commands import (
    add_service,
    auth,
    backup,
    configuration,
    database,
    diagnostic,
    docker,
    experimental,
    fix,
    flash,
    install,
    service,
    snapshot,
    tools,
    update,
)


def escalate(ex):
    if utils.get_config().debug:
        raise ex
    raise SystemExit(1)


def ensure_tty():  # pragma: no cover
    # There is no valid use case where we want to use a stdin pipe
    # We do expect to do multiple input() calls
    if not sys.stdin.isatty():  # pragma: no cover
        try:
            sys.stdin = open('/dev/tty')
        except OSError:
            click.secho('Failed to open TTY input. Confirm prompts will fail.')


def main(args=sys.argv[1:]):
    try:
        config = utils.get_config()

        ensure_tty()
        load_dotenv(Path('.env').resolve())

        if utils.is_root():
            click.secho('brewblox-ctl should not be run as root.', fg='red')
            raise SystemExit(1)

        @click.group(
            cls=click_helpers.OrderedCommandCollection,
            sources=[
                docker.cli,
                install.cli,
                configuration.cli,
                auth.cli,
                update.cli,
                add_service.cli,
                service.cli,
                flash.cli,
                tools.cli,
                diagnostic.cli,
                fix.cli,
                database.cli,
                backup.cli,
                snapshot.cli,
                experimental.cli,
            ],
        )
        @click.option('-y', '--yes', is_flag=True, help='Do not prompt to confirm commands.')
        @click.option(
            '-d', '--dry', '--dry-run', is_flag=True, help='Dry run mode: echo commands instead of running them.'
        )
        @click.option('-q', '--quiet', is_flag=True, help='Show less detailed output.')
        @click.option('-v', '--verbose', is_flag=True, help='Show more detailed output.')
        @click.option('--color/--no-color', default=None, help='Format messages with unicode color codes.')
        def cli(yes: bool, dry: bool, quiet: bool, verbose: bool, color: Optional[bool]):
            r"""
            The Brewblox management tool.

            Example calls:

            \b
                brewblox-ctl install
                brewblox-ctl --quiet down
                brewblox-ctl --verbose up
            """
            opts = utils.get_opts()
            opts.dry_run = dry
            opts.yes = yes
            opts.quiet = quiet
            opts.verbose = verbose or config.debug
            opts.color = color

        cli(args=args, standalone_mode=False)

    except ClickException as ex:  # pragma: no cover
        ex.show()
        escalate(ex)

    except CalledProcessError as ex:  # pragma: no cover
        utils.error(utils.strex(ex))
        utils.error(ex.stdout or '')
        escalate(ex)

    except Exception as ex:  # pragma: no cover
        utils.error(utils.strex(ex))
        escalate(ex)


if __name__ == '__main__':
    main()
