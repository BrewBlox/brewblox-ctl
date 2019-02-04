"""
Migration scripts
"""

from distutils.version import StrictVersion
from os import getenv

from brewblox_ctl.commands import Command
from brewblox_ctl.utils import check_config, confirm
from brewblox_ctl_lib.const import CURRENT_VERSION, HISTORY


class MigrateCommand(Command):
    def __init__(self):
        super().__init__('Run migration scripts against current configuration', 'migrate')
        self.prev_version = None

    def downed_commands(self):
        """Migration commands to be executed while the services are down"""
        shell_commands = []

        if self.prev_version < StrictVersion('0.2.0'):
            # Breaking changes: Influx downsampling model overhaul
            # Old data is completely incompatible
            if confirm('Upgrading to version >=0.2.0 requires a complete reset of your history data. ' +
                       'Do you want to copy the data to a different directory (./influxdb-old) first?'):
                shell_commands += ['sudo cp -rf ./influxdb ./influxdb-old']
            shell_commands += ['sudo rm -rf ./influxdb']

        return shell_commands

    def upped_commands(self):
        """Migration commands to be executed after the services have been started"""
        shell_commands = []

        if self.prev_version < StrictVersion('0.2.0'):
            # Breaking changes: Influx downsampling model overhaul
            # Old data is completely incompatible
            shell_commands += [
                'curl -Sk -X GET --retry 60 --retry-delay 10 {}/_service/status > /dev/null'.format(HISTORY),
                'curl -Sk -X POST {}/query/configure'.format(HISTORY),
            ]

        return shell_commands

    def action(self):
        check_config()
        self.prev_version = StrictVersion(getenv('BREWBLOX_CFG_VERSION', '0.0.0'))

        if self.prev_version.version == (0, 0, 0):
            print('This configuration was never set up. Please run brewblox-ctl setup first')
            raise SystemExit(1)

        shell_commands = [
            '{}docker-compose down'.format(self.optsudo),
        ]

        shell_commands += self.downed_commands()

        shell_commands += [
            '{}docker-compose up -d'.format(self.optsudo),
            'sleep 10',
        ]

        shell_commands += self.upped_commands()

        shell_commands += [
            'dotenv --quote never set BREWBLOX_CFG_VERSION {}'.format(CURRENT_VERSION),
        ]

        self.run_all(shell_commands)
