"""
Entrypoint for the Brewblox commands menu
"""

import sys
from os import getcwd, path
from subprocess import CalledProcessError

import click
from click.exceptions import UsageError
from dotenv import load_dotenv

from brewblox_ctl import click_helpers, const, utils
from brewblox_ctl.commands import docker, env, http, install


def check_lib():
    if utils.is_brewblox_cwd() \
        and not utils.path_exists('./brewblox_ctl_lib/__init__.py') \
            and utils.confirm(
                'brewblox-ctl requires extensions that match your Brewblox release. ' +
                'Do you want to download them now?'):
        utils.load_ctl_lib({'dry_run': False, 'verbose': True})


def local_commands():  # pragma: no cover
    if not utils.is_brewblox_cwd():
        return []

    try:
        check_lib()
        sys.path.append(getcwd())
        from brewblox_ctl_lib import loader
        return loader.cli_sources()

    except ImportError:
        print('No brewblox-ctl extensions found in current directory')
        return []

    except KeyboardInterrupt:
        raise SystemExit(0)

    except CalledProcessError as ex:
        print('\n' + 'Error:', str(ex))
        raise SystemExit(1)


def usage_hint(message):
    if 'No such command' in message and not utils.is_brewblox_cwd():
        default_dir = '/home/{}/brewblox'.format(utils.getenv('USER'))
        prompt = [
            '',
            'Many commands only work if your current directory is a Brewblox directory.',
        ]

        if utils.path_exists('{}/docker-compose.yml'.format(default_dir)):
            prompt += [
                'It looks like you installed Brewblox in the default location.',
                'To navigate there, run:',
                '',
                '    cd {}'.format(default_dir),
                ''
            ]

        print('\n'.join(prompt))


def main():
    try:
        load_dotenv(path.abspath('.env'))

        if utils.is_root():
            print('brewblox-ctl should not be run as root.')
            raise SystemExit(1)

        if utils.is_v6() \
            and not utils.confirm(
                'Raspberry Pi models 0 and 1 are not supported. Do you want to continue?', False):
            raise SystemExit(0)

        @click.group(
            cls=click_helpers.OrderedCommandCollection,
            sources=[
                docker.cli,
                install.cli,
                env.cli,
                http.cli,
                *local_commands(),
            ])
        @click.option('-y', '--yes',
                      is_flag=True,
                      envvar=const.SKIP_CONFIRM_KEY,
                      help='Do not prompt to confirm commands.')
        @click.option('--dry-run',
                      is_flag=True,
                      help='Dry run mode: echo commands to output instead of running them.')
        @click.option('-q', '--quiet',
                      is_flag=True,
                      help='Show less detailed command output.')
        @click.option('-v', '--verbose',
                      is_flag=True,
                      help='Show more detailed command output.')
        @click.pass_context
        def cli(ctx, yes, dry_run, quiet, verbose):
            """
            The Brewblox management tool.

            It can be used to create and control Brewblox configurations.
            When used from a Brewblox installation directory, it will automatically load additional commands.

            If the command you're looking for was not found, please check if your current directory
            is a Brewblox installation directory.

            By default, Brewblox is installed to ~/brewblox.

            Example calls:

            \b
                brewblox-ctl install
                brewblox-ctl --quiet down
                brewblox-ctl --verbose up
            """
            obj = ctx.ensure_object(dict)
            obj.update({
                'skip_confirm': yes,
                'dry_run': dry_run,
                'quiet': quiet,
                'verbose': verbose
            })

        cli(standalone_mode=False)

    except UsageError as ex:
        print(str(ex), file=sys.stderr)
        usage_hint(str(ex))
        raise SystemExit(1)

    except Exception as ex:
        print(str(ex), file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
