"""
Brewblox-ctl command definitions
"""

from abc import ABC, abstractmethod
from os import getenv, path
from subprocess import STDOUT, check_call

from brewblox_ctl.migrate import CURRENT_VERSION
from brewblox_ctl.utils import (base_dir, check_config, command_exists,
                                confirm, docker_tag, is_docker_user, is_pi,
                                select)


class Command(ABC):
    def __init__(self, description, keyword):
        self.description = description
        self.keyword = keyword
        self.optsudo = 'sudo ' if not is_docker_user() else ''

    def __str__(self):
        return '{} {}'.format(self.keyword.ljust(15), self.description)

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


class ComposeDownCommand(Command):
    def __init__(self):
        super().__init__('Stop running services', 'down')

    def action(self):
        check_config()
        shell_commands = [
            '{}docker-compose down'.format(self.optsudo),
        ]
        self.run_all(shell_commands)


class ComposeUpCommand(Command):
    def __init__(self):
        super().__init__('Start all services if not running', 'up')

    def action(self):
        check_config()
        shell_commands = [
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
            reboot_required = True
            shell_commands += [
                'curl -sSL https://get.docker.com | sh',
            ]

        if is_docker_user():
            print('{} already belongs to the Docker group, skipping...'.format(getenv('USER')))
        elif confirm('Do you want to run Docker commands without sudo?'):
            reboot_required = True
            shell_commands += [
                'sudo usermod -aG docker $USER'
            ]

        if command_exists('docker-compose'):
            print('docker-compose is already installed, skipping...')
        elif confirm('Do you want to install docker-compose (from pip)?'):
            shell_commands += [
                'sudo pip3 install -U docker-compose'
            ]

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


class FirmwareFlashCommand(Command):
    def __init__(self):
        super().__init__('Flash firmware on Spark', 'flash')

    def action(self):
        tag = docker_tag()
        shell_commands = []

        if check_config(required=False):
            shell_commands += [
                '{}docker-compose down'.format(self.optsudo),
            ]

        shell_commands += [
            '{}docker pull brewblox/firmware-flasher:{}'.format(self.optsudo, tag),
            '{}docker run -it --rm --privileged brewblox/firmware-flasher:{} trigger-dfu'.format(self.optsudo, tag),
            '{}docker run -it --rm --privileged brewblox/firmware-flasher:{} flash'.format(self.optsudo, tag),
        ]

        input('Please press ENTER when your Spark is connected over USB')
        self.run_all(shell_commands)


class BootloaderCommand(Command):
    def __init__(self):
        super().__init__('Flash bootloader on Spark', 'bootloader')

    def action(self):
        tag = docker_tag()
        shell_commands = []

        if check_config(required=False):
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

        if check_config(required=False):
            shell_commands += [
                '{}docker-compose down'.format(self.optsudo),
            ]

        shell_commands += [
            'docker pull brewblox/firmware-flasher:{}'.format(tag),
            'docker run -it --rm --privileged brewblox/firmware-flasher:{} wifi'.format(tag),
        ]

        input('Please press ENTER when your Spark is connected over USB')
        self.run_all(shell_commands)


class CheckStatusCommand(Command):
    def __init__(self):
        super().__init__('Check system status', 'status')

    def action(self):
        check_config()
        shell_commands = [
            '{}docker-compose ps'.format(self.optsudo),
        ]
        self.run_all(shell_commands)


ALL_COMMANDS = [
    ComposeUpCommand(),
    ComposeDownCommand(),
    InstallCommand(),
    FirmwareFlashCommand(),
    BootloaderCommand(),
    WiFiCommand(),
    CheckStatusCommand(),
]
