"""
Brewblox-ctl command definitions
"""

import platform
import shutil
import sys
from abc import ABC, abstractmethod
from distutils.util import strtobool
from os import getcwd, getenv, path
from subprocess import STDOUT, CalledProcessError, check_call, check_output

from brewblox_ctl.migrate import CURRENT_VERSION

DATASTORE = 'https://localhost/datastore'


def is_pi():
    return platform.machine().startswith('arm')


def is_root():
    return check_ok('ls /root')


def is_docker_user():
    return check_ok('id -nG $USER | grep -qw "docker"')


def base_dir():
    return path.dirname(__file__)


def docker_tag():
    return '{}{}'.format(
        'rpi-' if is_pi() else '',
        getenv('BREWBLOX_RELEASE', 'latest')
    )


def command_exists(cmd):
    return bool(shutil.which(cmd))


def check_ok(cmd):
    try:
        check_output(cmd, shell=True, stderr=STDOUT)
        return True
    except CalledProcessError:
        return False


def confirm(question, default='y'):
    print('{} [Y/n]'.format(question))
    while True:
        try:
            return strtobool(input().lower() or default)
        except ValueError:
            print('Please respond with \'y(es)\' or \'n(o)\'.')


def select(question, default=''):
    answer = input('{} {}'.format(question, '[{}]'.format(default) if default else ''))
    return answer or default


def choose(question, choices, default=''):
    display_choices = ' / '.join(['[{}]'.format(c) if c == default else c for c in choices])
    print(question, display_choices)
    valid_answers = [c.lower() for c in choices]
    while True:
        answer = input().lower() or default.lower()
        if answer in valid_answers:
            return answer
        print('Please choose one:', display_choices)


class Command(ABC):
    def __init__(self, description, keyword):
        self.description = description
        self.keyword = keyword
        self.optsudo = 'sudo ' if not is_docker_user() else ''

    def __str__(self):
        return '{} {}'.format(self.keyword.ljust(15), self.description)

    def check_required_config(self):
        if not path.exists('./docker-compose.yml'):
            print('Please run brewblox-ctl in the same directory as your docker-compose.yml file.')
            raise SystemExit(1)

    def check_optional_config(self):
        if path.exists('./docker-compose.yml'):
            return True
        elif confirm(
            'No configuration file (docker-compose.yml) found in current directory ({}). '.format(getcwd()) +
                'Are you sure you want to continue?'):
            return False
        else:
            raise SystemExit(0)

    def announce(self, shell_cmds):
        print('The following shell commands will be used: \n')
        for cmd in shell_cmds:
            print('\t', cmd)
        print('')
        input('Press ENTER to continue, Ctrl+C to cancel')

    def run(self, shell_cmd):
        print('\n' + 'Running command: \n\t', shell_cmd, '\n')
        return check_call(shell_cmd, shell=True, stderr=STDOUT)

    def run_all(self, shell_cmds, announce=True):
        if announce:
            self.announce(shell_cmds)
        return [self.run(cmd) for cmd in shell_cmds]

    @abstractmethod
    def action(self):
        pass


class ExitCommand(Command):
    def __init__(self):
        super().__init__('Exit this menu', 'exit')

    def action(self):
        raise SystemExit()


class ComposeDownCommand(Command):
    def __init__(self):
        super().__init__('Stop running services', 'down')

    def action(self):
        self.check_required_config()
        shell_commands = [
            '{}docker-compose down'.format(self.optsudo),
        ]
        self.run_all(shell_commands)


class ComposeUpCommand(Command):
    def __init__(self):
        super().__init__('Start all services if not running', 'up')

    def action(self):
        self.check_required_config()
        shell_commands = [
            '{}docker-compose up -d'.format(self.optsudo),
        ]
        self.run_all(shell_commands)


class UpdateCommand(Command):
    def __init__(self):
        super().__init__('Update all services', 'update')

    def action(self):
        self.check_required_config()
        shell_commands = [
            '{}docker-compose down'.format(self.optsudo),
            '{}docker-compose pull'.format(self.optsudo),
            'sudo pip3 install -U brewblox-ctl',
            '{}docker-compose up -d'.format(self.optsudo),
        ]
        self.run_all(shell_commands)


class InstallCommand(Command):
    def __init__(self):
        super().__init__('Install a new BrewBlox system', 'install')

    def action(self):
        reboot_required = False
        shell_commands = [
            'sudo apt update',
            'sudo apt upgrade -y',
        ]

        if command_exists('docker'):
            print('Docker is already installed, skipping...')
        elif confirm('Do you want to install Docker?'):
            shell_commands.append('curl -sSL https://get.docker.com | sh')
            reboot_required = True

        if is_docker_user():
            print('{} already belongs to the Docker group, skipping...'.format(getenv('USER')))
        elif confirm('Do you want to run Docker commands without sudo?'):
            shell_commands.append('sudo usermod -aG docker $USER')
            reboot_required = True

        if command_exists('docker-compose'):
            print('docker-compose is already installed, skipping...')
        elif confirm('Do you want to install docker-compose (from pip)?'):
            shell_commands.append('sudo pip3 install -U docker-compose')

        source_dir = base_dir() + '/install_files'
        target_dir = select(
            'In which directory do you want to install the BrewBlox configuration?',
            './brewblox'
        ).rstrip('/')
        source_compose = 'docker-compose_{}.yml'.format('armhf' if is_pi() else 'amd64')

        if confirm('Do you want to wait for stable releases?'):
            release = 'stable'
        else:
            release = 'edge'

        if path.exists('{}/docker-compose.yml'.format(target_dir)):
            if not confirm(
                    '{} already contains a BrewBlox installation. Do you want to continue?'.format(target_dir)):
                return

            if confirm('Do you want to keep your existing dashboards?'):
                shell_commands += [
                    'sudo mv {} {}-bak'.format(target_dir, target_dir),
                    'mkdir {}'.format(target_dir),
                    'sudo cp -r {}-bak/couchdb {}/'.format(target_dir, target_dir),
                    'sudo cp -r {}-bak/influxdb {}/'.format(target_dir, target_dir),
                ]

            else:
                shell_commands += [
                    'sudo rm -rf {}/*'.format(target_dir),
                ]

        else:
            shell_commands += [
                'mkdir {}'.format(target_dir),
            ]

        shell_commands += [
            'mkdir -p {}/couchdb'.format(target_dir),
            'mkdir -p {}/influxdb'.format(target_dir),
            'cp {}/{} {}/docker-compose.yml'.format(source_dir, source_compose, target_dir),
            'cp -r {}/traefik {}/'.format(source_dir, target_dir),
            'echo BREWBLOX_RELEASE={} >> {}/.env'.format(release, target_dir),
            'echo BREWBLOX_CFG_VERSION={} >> {}/.env'.format(CURRENT_VERSION, target_dir),
        ]

        if reboot_required and confirm('A reboot will be required, do you want to do so?'):
            shell_commands.append('sudo reboot')

        self.run_all(shell_commands)


class SetupCommand(Command):
    def __init__(self):
        super().__init__('Run first-time setup', 'setup')

    def action(self):
        self.check_required_config()

        database = 'brewblox-ui-store'
        presets_dir = '{}/presets'.format(base_dir())
        modules = ['services', 'dashboards', 'dashboard-items']

        shell_commands = [
            '{}docker-compose down'.format(self.optsudo),
            '{}docker-compose pull'.format(self.optsudo),
            'sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 ' +
            '-keyout traefik/brewblox.key ' +
            '-out traefik/brewblox.crt',
            'sudo chmod 644 traefik/brewblox.crt',
            'sudo chmod 600 traefik/brewblox.key',
            '{}docker-compose up -d datastore traefik'.format(self.optsudo),
            'sleep 30',
            'curl -Sk -X GET --retry 60 --retry-delay 10 {} > /dev/null'.format(DATASTORE),
            'curl -Sk -X PUT {}/_users'.format(DATASTORE),
            'curl -Sk -X PUT {}/{}'.format(DATASTORE, database),
            *[
                'cat {}/{}.json '.format(presets_dir, mod) +
                '| curl -Sk -X POST ' +
                '--header \'Content-Type: application/json\' ' +
                '--header \'Accept: application/json\' ' +
                '--data "@-" {}/{}/_bulk_docs'.format(DATASTORE, database)
                for mod in modules
            ],
            '{}docker-compose down'.format(self.optsudo),
        ]
        self.run_all(shell_commands)


class FirmwareFlashCommand(Command):
    def __init__(self):
        super().__init__('Flash firmware on Spark', 'flash')

    def action(self):
        tag = docker_tag()
        shell_commands = []

        if self.check_optional_config():
            shell_commands += [
                '{}docker-compose down'.format(self.optsudo),
            ]

        shell_commands += [
            'docker pull brewblox/firmware-flasher:{}'.format(tag),
            'docker run -it --rm --privileged brewblox/firmware-flasher:{} trigger-dfu'.format(tag),
            'docker run -it --rm --privileged brewblox/firmware-flasher:{} flash'.format(tag),
        ]

        input('Please press ENTER when your Spark is connected over USB')
        self.run_all(shell_commands)


class BootloaderCommand(Command):
    def __init__(self):
        super().__init__('Flash bootloader on Spark', 'bootloader')

    def action(self):
        tag = docker_tag()
        shell_commands = []

        if self.check_optional_config():
            shell_commands += [
                '{}docker-compose down'.format(self.optsudo),
            ]

        shell_commands += [
            'docker pull brewblox/firmware-flasher:{}'.format(tag),
            'docker run -it --rm --privileged brewblox/firmware-flasher:{} flash-bootloader'.format(tag),
        ]

        input('Please press ENTER when your Spark is connected over USB')
        self.run_all(shell_commands)


class WiFiCommand(Command):
    def __init__(self):
        super().__init__('Connect Spark to WiFi', 'wifi')

    def action(self):
        tag = docker_tag()
        shell_commands = []

        if self.check_optional_config():
            shell_commands += [
                '{}docker-compose down'.format(self.optsudo),
            ]

        shell_commands += [
            'docker pull brewblox/firmware-flasher:{}'.format(tag),
            'docker run -it --rm --privileged brewblox/firmware-flasher:{} wifi'.format(tag),
        ]

        input('Please press ENTER when your Spark is connected over USB')
        self.run_all(shell_commands)


class ImportCommand(Command):
    def __init__(self):
        super().__init__('Import database files', 'import')

    def action(self):
        self.check_required_config()

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
        self.check_required_config()

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


class CheckStatusCommand(Command):
    def __init__(self):
        super().__init__('Check system status', 'status')

    def action(self):
        self.check_required_config()
        shell_commands = [
            '{}docker-compose ps'.format(self.optsudo),
        ]
        self.run_all(shell_commands)


class LogFileCommand(Command):
    def __init__(self):
        super().__init__('Generate and share log file for bug reports', 'log')

    def action(self):
        self.check_required_config()

        reason = select('Why are you generating this log? (will be included in log)')

        shell_commands = [
            'echo "BREWBLOX DIAGNOSTIC DUMP" > brewblox.log',
            'date >> brewblox.log',
            'echo \'{}\' >> brewblox.log'.format(reason),
            'echo "==============VARS==============" >> brewblox.log',
            'echo "$(uname -a)" >> brewblox.log',
            'echo "$(docker --version)" >> brewblox.log',
            'echo "$(docker-compose --version)" >> brewblox.log',
            'source .env; echo "BREWBLOX_RELEASE=$BREWBLOX_RELEASE" >> brewblox.log',
            'source .env; echo "BREWBLOX_CFG_VERSION=$BREWBLOX_CFG_VERSION" >> brewblox.log',
            'echo "==============CONFIG==============" >> brewblox.log',
            'cat docker-compose.yml >> brewblox.log',
            'echo "==============LOGS==============" >> brewblox.log',
            'for svc in $({}docker-compose ps --services | tr "\\n" " "); do '.format(self.optsudo) +
            '{}docker-compose logs --timestamps --no-color --tail 200 ${{svc}} >> brewblox.log; '.format(self.optsudo) +
            'echo \'\\n\' >> brewblox.log; ' +
            'done;',
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
    ComposeUpCommand(),
    ComposeDownCommand(),
    UpdateCommand(),
    InstallCommand(),
    SetupCommand(),
    FirmwareFlashCommand(),
    BootloaderCommand(),
    WiFiCommand(),
    CheckStatusCommand(),
    ImportCommand(),
    ExportCommand(),
    LogFileCommand(),
    ExitCommand(),
]
