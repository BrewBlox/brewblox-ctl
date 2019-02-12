"""
Entrypoint for the BrewBlox commands menu
"""

import sys
from os import getcwd
from subprocess import CalledProcessError

from brewblox_ctl import commands
from brewblox_ctl.utils import confirm, is_brewblox_cwd, is_root, path_exists
from dotenv import find_dotenv, load_dotenv

MENU = """
index - name         description
----------------------------------------------------------
{}
----------------------------------------------------------

Press Ctrl+C to exit.
"""


class CheckLibCommand(commands.Command):
    def __init__(self):
        super().__init__('Check for brewblox_ctl_lib', 'lib')

    def action(self):
        if is_brewblox_cwd() \
            and not path_exists('./brewblox_ctl_lib/__init__.py') \
                and confirm('brewblox-ctl scripts are not yet installed in this directory. Do you want to do so now?'):
            self.run_all(self.lib_commands())


class ExitCommand(commands.Command):
    def __init__(self):
        super().__init__('Exit this menu', 'exit')

    def action(self):
        raise SystemExit()


def local_commands():  # pragma: no cover
    if is_brewblox_cwd():
        try:
            CheckLibCommand().action()
            sys.path.append(getcwd())
            from brewblox_ctl_lib import config_commands
            return config_commands.ALL_COMMANDS
        except ImportError:
            print('No BrewBlox scripts found in current directory')
        except KeyboardInterrupt:
            raise SystemExit(0)
        except CalledProcessError as ex:
            print('\n' + 'Error:', str(ex))
            raise SystemExit(1)

    return []


def run_commands(args, all_commands):
    has_args = bool(args)

    command_descriptions = [
        '{} - {}'.format(str(idx+1).rjust(2), cmd)
        for idx, cmd in enumerate(all_commands)
    ]

    if has_args:
        print('Running commands: {}'.format(', '.join(args)))

    try:
        while True:
            if not has_args:
                print(MENU.format('\n'.join(command_descriptions)))

            try:
                arg = args.pop(0)
            except IndexError:
                arg = input('Please type a command name or index, and press ENTER. ')

            command = next(
                (cmd for idx, cmd in enumerate(all_commands) if arg in [cmd.keyword, str(idx+1)]),
                None,
            )

            if command:
                command.action()

                if not args:
                    break

    except CalledProcessError as ex:
        print('\n' + 'Error:', str(ex))

    except KeyboardInterrupt:
        pass


def main(args=...):
    load_dotenv(find_dotenv(usecwd=True))

    if is_root():
        print('The BrewBlox menu should not be run as root.')
        raise SystemExit(1)

    print('Welcome to the BrewBlox menu!')

    args = sys.argv[1:] if args is ... else args

    all_commands = [
        *commands.ALL_COMMANDS,
        *local_commands(),
        ExitCommand(),
    ]

    run_commands(args, all_commands)


if __name__ == '__main__':
    main()
