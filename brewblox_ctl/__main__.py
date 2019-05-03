"""
Entrypoint for the BrewBlox commands menu
"""

import sys
from os import getcwd
from subprocess import CalledProcessError

from dotenv import find_dotenv, load_dotenv

from brewblox_ctl import click_helpers, commands, http, utils

HELPTEXT = """
The BrewBlox management tool.

It can be used to create and control BrewBlox configurations.
When used from a BrewBlox installation directory, it will automatically load additional commands.

If the command you're looking for was not found, please check if your current directory
is a BrewBlox installation directory.

By default, BrewBlox is installed to ~/brewblox.

Example use:

    brewblox-ctl install
"""


def check_lib():
    if utils.is_brewblox_cwd() \
        and not utils.path_exists('./brewblox_ctl_lib/__init__.py') \
            and utils.confirm(
                'brewblox-ctl requires extensions that match your BrewBlox release. ' +
                'Do you want to download them now?'):
        utils.run_all(utils.lib_loading_commands())


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


def main():
    load_dotenv(find_dotenv(usecwd=True))

    if utils.is_root():
        print('brewblox-ctl should not be run as root.')
        raise SystemExit(1)

    if utils.is_v6() \
        and not utils.confirm(
            'Raspberry Pi models 1 and 0 are not supported. Do you want to continue?', False):
        raise SystemExit(0)

    cli = click_helpers.OrderedCommandCollection(
        help=HELPTEXT,
        sources=[
            commands.cli,
            http.cli,
            *local_commands(),
        ])

    cli()


if __name__ == '__main__':
    main()
