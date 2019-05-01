"""
Entrypoint for the BrewBlox commands menu
"""

import sys
from os import getcwd
from subprocess import CalledProcessError

import click
from dotenv import find_dotenv, load_dotenv

from brewblox_ctl import commands, utils


def check_lib():
    if utils.is_brewblox_cwd() \
        and not utils.path_exists('./brewblox_ctl_lib/__init__.py') \
            and utils.confirm(
                'brewblox-ctl scripts are not yet installed in this directory. Do you want to do so now?'):
        utils.run_all(utils.lib_commands())


def local_commands():  # pragma: no cover
    if not utils.is_brewblox_cwd():
        return []

    try:
        check_lib()
        sys.path.append(getcwd())
        from brewblox_ctl_lib import config_commands
        return [config_commands.cli]

    except ImportError:
        print('No BrewBlox scripts found in current directory')
        return []

    except KeyboardInterrupt:
        raise SystemExit(0)

    except CalledProcessError as ex:
        print('\n' + 'Error:', str(ex))
        raise SystemExit(1)


def main(args=...):
    load_dotenv(find_dotenv(usecwd=True))

    if utils.is_root():
        print('brewblox-ctl should not be run as root.')
        raise SystemExit(1)

    cli = click.CommandCollection(
        sources=[
            commands.cli,
            *local_commands(),
        ])

    cli()


if __name__ == '__main__':
    main()
