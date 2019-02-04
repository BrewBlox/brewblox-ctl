"""
Config-dependent commands
"""

import sys
from os import path

from brewblox_ctl.commands import Command
from brewblox_ctl.utils import base_dir, check_config, confirm, select

DATASTORE = 'https://localhost/datastore'
HISTORY = 'https://localhost/history'


class SetupCommand(Command):
    def __init__(self):
        super().__init__('Run first-time setup', 'setup')

    def action(self):
        check_config()

        database = 'brewblox-ui-store'
        presets_dir = '{}/presets'.format(base_dir())
        modules = ['services', 'dashboards', 'dashboard-items']

        # Update dependencies
        shell_commands = [
            '{}docker-compose down'.format(self.optsudo),
            '{}docker-compose pull'.format(self.optsudo),
            'sudo pip3 install -U brewblox-ctl',
        ]

        # Generate self-signed SSH certificate
        shell_commands += [
            'sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 ' +
            '-keyout traefik/brewblox.key ' +
            '-out traefik/brewblox.crt',
            'sudo chmod 644 traefik/brewblox.crt',
            'sudo chmod 600 traefik/brewblox.key',
        ]

        # Bring system online. Wait for datastore to be available
        shell_commands += [
            '{}docker-compose up -d datastore influx history traefik'.format(self.optsudo),
            'sleep 30',
            'curl -Sk -X GET --retry 60 --retry-delay 10 {} > /dev/null'.format(DATASTORE),
        ]

        # Basic datastore setup
        shell_commands += [
            'curl -Sk -X PUT {}/_users'.format(DATASTORE),
            'curl -Sk -X PUT {}/{}'.format(DATASTORE, database),
        ]

        # Load presets
        shell_commands += [
            'cat {}/{}.json '.format(presets_dir, mod) +
            '| curl -Sk -X POST ' +
            '--header \'Content-Type: application/json\' ' +
            '--header \'Accept: application/json\' ' +
            '--data "@-" {}/{}/_bulk_docs'.format(DATASTORE, database)
            for mod in modules
        ]

        # Configure history / influx
        shell_commands += [
            'curl -Sk -X POST {}/query/configure',
        ]

        # Shut it down - we're done
        shell_commands += [
            '{}docker-compose down'.format(self.optsudo),
        ]

        self.run_all(shell_commands)


class UpdateCommand(Command):
    def __init__(self):
        super().__init__('Update all services', 'update')

    def action(self):
        check_config()
        shell_commands = [
            '{}docker-compose down'.format(self.optsudo),
            '{}docker-compose pull'.format(self.optsudo),
            'sudo pip3 install -U brewblox-ctl',
            '{} -m brewblox_ctl.migrate'.format(sys.executable),
        ]
        self.run_all(shell_commands)


class ImportCommand(Command):
    def __init__(self):
        super().__init__('Import database files', 'import')

    def action(self):
        check_config()

        while True:
            target_dir = select(
                'In which directory can the exported files be found?',
                './brewblox-export'
            ).rstrip('/')

            couchdb_target = target_dir + '/couchdb-snapshot'
            influxdb_target = target_dir + '/influxdb-snapshot'

            if not path.exists(couchdb_target):
                print('"{}" not found'.format(couchdb_target))
            elif not path.exists(influxdb_target):
                print('"{}" not found'.format(influxdb_target))
            else:
                break

        shell_commands = [
            '{}docker-compose up -d influx datastore traefik'.format(self.optsudo),
            'sleep 10',
            'curl -Sk -X GET --retry 60 --retry-delay 10 {} > /dev/null'.format(DATASTORE),
            '{} -m brewblox_ctl.import_data {}'.format(sys.executable, couchdb_target),
            '{}docker cp {} $({}docker-compose ps -q influx):/tmp/'.format(
                self.optsudo, influxdb_target, self.optsudo),
            '{}docker-compose exec influx influxd restore -portable /tmp/influxdb-snapshot/'.format(self.optsudo),
        ]
        self.run_all(shell_commands)


class ExportCommand(Command):
    def __init__(self):
        super().__init__('Export database files', 'export')

    def action(self):
        check_config()

        target_dir = select(
            'In which directory do you want to place the exported files?',
            './brewblox-export'
        ).rstrip('/')

        couchdb_target = target_dir + '/couchdb-snapshot'
        influxdb_target = target_dir + '/influxdb-snapshot'

        shell_commands = []

        if path.exists(couchdb_target) or path.exists(influxdb_target):
            if confirm('This action will overwrite existing files. Do you want to continue?'):
                shell_commands += [
                    'rm -r {} {}'.format(couchdb_target, influxdb_target)
                ]

        shell_commands += [
            'mkdir -p {}'.format(couchdb_target),
            'mkdir -p {}'.format(influxdb_target),
            '{}docker-compose up -d influx datastore traefik'.format(self.optsudo),
            'sleep 10',
            'curl -Sk -X GET --retry 60 --retry-delay 10 {} > /dev/null'.format(DATASTORE),
            '{} -m brewblox_ctl.export_data {}'.format(sys.executable, couchdb_target),
            '{}docker-compose exec influx rm -r /tmp/influxdb-snapshot/ || true'.format(self.optsudo),
            '{}docker-compose exec influx influxd backup -portable /tmp/influxdb-snapshot/'.format(self.optsudo),
            '{}docker cp $({}docker-compose ps -q influx):/tmp/influxdb-snapshot/ {}/'.format(
                self.optsudo, self.optsudo, target_dir),
        ]
        self.run_all(shell_commands)


class LogFileCommand(Command):
    def __init__(self):
        super().__init__('Generate and share log file for bug reports', 'log')

    def action(self):
        check_config()

        reason = select('Why are you generating this log? (will be included in log)')

        shell_commands = [
            'echo "BREWBLOX DIAGNOSTIC DUMP" > brewblox.log',
            'date >> brewblox.log',
            'echo \'{}\' >> brewblox.log'.format(reason),
        ]

        shell_commands += [
            'echo "==============VARS==============" >> brewblox.log',
            'echo "$(uname -a)" >> brewblox.log',
            'echo "$(docker --version)" >> brewblox.log',
            'echo "$(docker-compose --version)" >> brewblox.log',
            'source .env; echo "BREWBLOX_RELEASE=$BREWBLOX_RELEASE" >> brewblox.log',
            'source .env; echo "BREWBLOX_CFG_VERSION=$BREWBLOX_CFG_VERSION" >> brewblox.log',
        ]

        if confirm('Can we include your docker-compose file? ' +
                   'You should choose "no" if it contains any passwords or other sensitive information'):
            shell_commands += [
                'echo "==============CONFIG==============" >> brewblox.log',
                'cat docker-compose.yml >> brewblox.log',
            ]

        shell_commands += [
            'echo "==============LOGS==============" >> brewblox.log',
            'for svc in $({}docker-compose ps --services | tr "\\n" " "); do '.format(self.optsudo) +
            '{}docker-compose logs --timestamps --no-color --tail 200 ${{svc}} >> brewblox.log; '.format(self.optsudo) +
            'echo \'\\n\' >> brewblox.log; ' +
            'done;',
        ]

        shell_commands += [
            'echo "==============INSPECT==============" >> brewblox.log',
            'for cont in $({}docker-compose ps -q); do '.format(self.optsudo) +
            '{}docker inspect $({}docker inspect --format \'{}\' "$cont") >> brewblox.log; '.format(
                self.optsudo, self.optsudo, '{{ .Image }}') +
            'done;',
        ]

        self.run_all(shell_commands)

        if confirm('Do you want to view your log file at <this computer>:9999/brewblox.log?'):
            try:
                self.run('{} -m http.server 9999'.format(sys.executable))
            except KeyboardInterrupt:
                pass

        if confirm('Do you want to upload your log file - and get a shareable link?'):
            share_commands = [
                'cat brewblox.log | nc termbin.com 9999',
            ]
            self.run_all(share_commands)


ALL_COMMANDS = [
    UpdateCommand(),
    SetupCommand(),
    ImportCommand(),
    ExportCommand(),
    LogFileCommand(),
]
