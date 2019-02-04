"""
Brewblox-ctl command definitions
"""

from abc import ABC, abstractmethod
from os import getenv
from subprocess import STDOUT, check_call

from brewblox_ctl.utils import (check_config, command_exists, confirm,
                                ctl_lib_tag, docker_tag, is_docker_user,
                                path_exists, select)


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

    def lib_commands(self):
        tag = ctl_lib_tag()
        return [
            '{}docker rm ctl-lib || true'.format(self.optsudo),
            '{}docker pull brewblox/brewblox-ctl-lib:{} || true'.format(self.optsudo, tag),
            '{}docker create --name ctl-lib brewblox/brewblox-ctl-lib:{}'.format(self.optsudo, tag),
            'rm -rf ./brewblox_ctl_lib; {}docker cp ctl-lib:/brewblox_ctl_lib ./'.format(self.optsudo),
            '{}docker rm ctl-lib'.format(self.optsudo),
        ]

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

        target_dir = select(
            'In which directory do you want to install the BrewBlox configuration?',
            './brewblox'
        ).rstrip('/')

        if path_exists(target_dir):
            if not confirm('{} already exists. Do you want to continue?'.format(target_dir)):
                return

        if confirm('Do you want to wait for stable releases?'):
            release = 'stable'
        else:
            release = 'edge'

        shell_commands += [
            'mkdir -p {}'.format(target_dir),
            'touch {}/.env'.format(target_dir),
            'dotenv -f {}/.env set BREWBLOX_RELEASE {}'.format(target_dir, release),
            'dotenv -f {}/.env set BREWBLOX_CFG_VERSION 0.0.0'.format(target_dir),
            'cd {} && brewblox-ctl setup'.format(target_dir),
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


ALL_COMMANDS = [
    ComposeUpCommand(),
    ComposeDownCommand(),
    InstallCommand(),
    FirmwareFlashCommand(),
    BootloaderCommand(),
    WiFiCommand(),
]
