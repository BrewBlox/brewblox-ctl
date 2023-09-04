"""
Entrypoint for the Brewblox commands menu
"""

import sys
from pathlib import Path

import click
from click.exceptions import ClickException
from dotenv import load_dotenv

from brewblox_ctl import click_helpers, const, utils
from brewblox_ctl.commands import (add_service, backup, database, diagnostic,
                                   docker, env, experimental, fix, flash, http,
                                   install, service, snapshot, update, user)

SUPPORTED_PYTHON_MINOR = 7


def escalate(ex):
    if utils.getenv(const.ENV_KEY_DEBUG):
        raise ex
    else:
        raise SystemExit(1)


def ensure_tty():  # pragma: no cover
    # There is no valid use case where we want to use a stdin pipe
    # We do expect to do multiple input() calls
    if not sys.stdin.isatty():  # pragma: no cover
        try:
            sys.stdin = open('/dev/tty')
        except (IOError, OSError):
            click.secho('Failed to open TTY input. Confirm prompts will fail.')


def main(args=sys.argv[1:]):
    try:
        ensure_tty()
        load_dotenv(Path('.env').resolve())

        if utils.is_root():
            click.secho('brewblox-ctl should not be run as root.', fg='red')
            raise SystemExit(1)

        if utils.is_armv6() \
                and not utils.getenv(const.ENV_KEY_ALLOW_ARMV6):
            click.secho('ARMv6 detected. The Raspberry Pi Zero and 1 are not supported.', fg='red')
            raise SystemExit(1)

        if sys.version_info[1] < SUPPORTED_PYTHON_MINOR:
            major = sys.version_info[0]
            minor = sys.version_info[1]
            click.echo(f'WARNING: You are using Python {major}.{minor}, which is no longer maintained.')
            click.echo('We recommend upgrading your system.')
            click.echo('For more information, please visit https://brewblox.netlify.app/user/system_upgrades.html')
            click.echo('')

        @click.group(
            cls=click_helpers.OrderedCommandCollection,
            sources=[
                docker.cli,
                install.cli,
                user.cli,
                env.cli,
                update.cli,
                http.cli,
                add_service.cli,
                service.cli,
                flash.cli,
                diagnostic.cli,
                fix.cli,
                database.cli,
                backup.cli,
                snapshot.cli,
                experimental.cli,
            ])
        @click.option('-y', '--yes',
                      is_flag=True,
                      envvar=const.ENV_KEY_SKIP_CONFIRM,
                      help='Do not prompt to confirm commands.')
        @click.option('-d', '--dry', '--dry-run',
                      is_flag=True,
                      help='Dry run mode: echo commands instead of running them.')
        @click.option('-q', '--quiet',
                      is_flag=True,
                      help='Show less detailed output.')
        @click.option('-v', '--verbose',
                      is_flag=True,
                      help='Show more detailed output.')
        @click.option('--color/--no-color',
                      default=None,
                      help='Format messages with unicode color codes.')
        @click.pass_context
        def cli(ctx, yes, dry, quiet, verbose, color):
            """
            The Brewblox management tool.

            Example calls:

            \b
                brewblox-ctl install
                brewblox-ctl --quiet down
                brewblox-ctl --verbose up
            """
            opts = ctx.ensure_object(utils.ContextOpts)
            opts.dry_run = dry
            opts.skip_confirm = yes
            opts.quiet = quiet
            opts.verbose = verbose
            opts.color = color

        cli(args=args, standalone_mode=False)

    except ClickException as ex:  # pragma: no cover
        ex.show()
        escalate(ex)

    except Exception as ex:  # pragma: no cover
        click.echo(str(ex), err=True)
        escalate(ex)


if __name__ == '__main__':
    main()
