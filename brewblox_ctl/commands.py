"""
Brewblox-ctl command definitions
"""

from abc import ABC, abstractmethod
from subprocess import STDOUT, check_call

from brewblox_ctl.const import CFG_VERSION_KEY, PY, RELEASE_KEY
from brewblox_ctl.utils import (check_config, command_exists, confirm,
                                ctl_lib_tag, docker_tag, getenv,
                                is_docker_user, path_exists, select)


class Command(ABC):
    def __init__(self, description, keyword):
        self.description = description
        self.keyword = keyword
        self.optsudo = 'sudo ' if not is_docker_user() else ''

    def __str__(self):
        return '{} {}'.format(self.keyword.ljust(15), self.description)

    def prompt_usb(self):
        input('Please press ENTER when your Spark is connected over USB')

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
        shell_commands = [
            '{}docker rm ctl-lib || echo "you can ignore this error"'.format(self.optsudo),
            '{}docker pull brewblox/brewblox-ctl-lib:{} || true'.format(self.optsudo, tag),
            '{}docker create --name ctl-lib brewblox/brewblox-ctl-lib:{}'.format(self.optsudo, tag),
            'rm -rf ./brewblox_ctl_lib || echo "you can ignore this error"',
            '{}docker cp ctl-lib:/brewblox_ctl_lib ./'.format(self.optsudo),
            '{}docker rm ctl-lib'.format(self.optsudo),
        ]

        if self.optsudo:
            shell_commands += [
                'sudo chown -R $USER ./brewblox_ctl_lib/',
            ]

        return shell_commands

    @abstractmethod
    def action(self):
        """To be implemented by subclasses"""


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
        shell_commands = []

        if command_exists('apt') and confirm('Do you want to upgrade apt packages?'):
            shell_commands += [
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
                'sudo {} -m pip install -U docker-compose'.format(PY)
            ]

        target_dir = select(
            'In which directory do you want to install the BrewBlox configuration?',
            './brewblox'
        ).rstrip('/')

        if path_exists(target_dir):
            if not confirm('{} already exists. Do you want to continue?'.format(target_dir)):
                return

        # TODO(Bob) Wait until stable is actually stable before offering new users a choice
        release = 'edge'
        # if confirm('Do you want to wait for stable releases?'):
        #     release = 'stable'
        # else:
        #     release = 'edge'

        shell_commands += [
            'mkdir -p {}'.format(target_dir),
            'touch {}/.env'.format(target_dir),
            '{} -m dotenv.cli --quote never -f {}/.env set {} {}'.format(PY, target_dir, RELEASE_KEY, release),
            '{} -m dotenv.cli --quote never -f {}/.env set {} 0.0.0'.format(PY, target_dir, CFG_VERSION_KEY),
        ]

        if reboot_required and confirm('A reboot will be required, do you want to do so?'):
            shell_commands.append('sudo reboot')

        self.run_all(shell_commands)


class KillCommand(Command):
    def __init__(self):
        super().__init__('Stop and remove all containers on this machine', 'kill')

    def action(self):
        if not confirm('This will stop and remove ALL docker containers on your system. ' +
                       'This includes those not from BrewBlox. ' +
                       'Do you want to continue?'):
            return

        shell_commands = [
            '{}docker rm --force $({}docker ps -aq) 2> /dev/null '.format(self.optsudo, self.optsudo) +
            '|| echo "No containers found"',
        ]

        self.run_all(shell_commands)


class FirmwareFlashCommand(Command):
    def __init__(self):
        super().__init__('Flash firmware on Spark', 'flash')

    def action(self):
        tag = docker_tag()
        shell_commands = []

        if path_exists('./docker-compose.yml'):
            shell_commands += [
                '{}docker-compose down'.format(self.optsudo),
            ]

        shell_commands += [
            '{}docker pull brewblox/firmware-flasher:{}'.format(self.optsudo, tag),
            '{}docker run -it --rm --privileged brewblox/firmware-flasher:{} trigger-dfu'.format(self.optsudo, tag),
            '{}docker run -it --rm --privileged brewblox/firmware-flasher:{} flash'.format(self.optsudo, tag),
        ]

        self.prompt_usb()
        self.run_all(shell_commands)


class BootloaderCommand(Command):
    def __init__(self):
        super().__init__('Flash bootloader on Spark', 'bootloader')

    def action(self):
        tag = docker_tag()
        shell_commands = []

        if path_exists('./docker-compose.yml'):
            shell_commands += [
                '{}docker-compose down'.format(self.optsudo),
            ]

        shell_commands += [
            '{}docker pull brewblox/firmware-flasher:{}'.format(self.optsudo, tag),
            '{}docker run -it --rm --privileged brewblox/firmware-flasher:{} flash-bootloader'.format(
                self.optsudo, tag),
        ]

        self.prompt_usb()
        self.run_all(shell_commands)


class WiFiCommand(Command):
    def __init__(self):
        super().__init__('Connect Spark to WiFi', 'wifi')

    def action(self):
        tag = docker_tag()
        shell_commands = []

        if path_exists('./docker-compose.yml'):
            shell_commands += [
                '{}docker-compose down'.format(self.optsudo),
            ]

        shell_commands += [
            '{}docker pull brewblox/firmware-flasher:{}'.format(self.optsudo, tag),
            '{}docker run -it --rm --privileged brewblox/firmware-flasher:{} wifi'.format(self.optsudo, tag),
        ]

        self.prompt_usb()
        self.run_all(shell_commands)


ALL_COMMANDS = [
    ComposeUpCommand(),
    ComposeDownCommand(),
    InstallCommand(),
    KillCommand(),
    FirmwareFlashCommand(),
    BootloaderCommand(),
    WiFiCommand(),
]
