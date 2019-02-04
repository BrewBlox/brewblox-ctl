"""
Migration scripts
"""

from distutils.version import StrictVersion
from os import getenv

from brewblox_ctl.commands import Command
from brewblox_ctl.utils import check_config

CURRENT_VERSION = '0.1.0'


class MigrateCommand(Command):
    def __init__(self):
        super().__init__('Run migration scripts against current configuration', 'migrate')

    def action(self):
        check_config()
        prev_version = StrictVersion(getenv('BREWBLOX_CFG_VERSION', '0.0.0'))
        major, minor, patch = prev_version.version

        if (major, minor, patch) == (0, 0, 0):
            print('This configuration was never set up. Please run brewblox-ctl setup first')
            raise SystemExit(1)

        shell_commands = [
            '{}docker-compose down'.format(self.optsudo),
        ]

        shell_commands += [
            'dotenv --quote never set BREWBLOX_CFG_VERSION {}'.format(CURRENT_VERSION),
        ]

        self.run_all(shell_commands)
