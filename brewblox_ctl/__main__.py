"""
Entrypoint for the BrewBlox commands menu
"""

import sys
from subprocess import CalledProcessError

from dotenv import find_dotenv, load_dotenv

from brewblox_ctl.commands import ALL_COMMANDS, is_root

MENU = """
index - name         description
----------------------------------------------------------
{}
----------------------------------------------------------

Press Ctrl+C to exit.
"""


def main(args=...):
    load_dotenv(find_dotenv(usecwd=True))
    command_descriptions = [
        '{} - {}'.format(str(idx+1).rjust(2), cmd)
        for idx, cmd in enumerate(ALL_COMMANDS)
    ]

    if is_root():
        print('The BrewBlox menu should not be run as root.')
        raise SystemExit(1)

    if args is ...:
        args = sys.argv[1:]
    print('Welcome to the BrewBlox menu!')
    has_args = bool(args)
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
                (cmd for idx, cmd in enumerate(ALL_COMMANDS) if arg in [cmd.keyword, str(idx+1)]),
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


if __name__ == '__main__':
    main()
