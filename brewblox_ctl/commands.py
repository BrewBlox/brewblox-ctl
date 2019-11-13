"""
Brewblox-ctl command definitions
"""

import click

from brewblox_ctl import click_helpers, utils
from brewblox_ctl.const import (CFG_VERSION_KEY, PY, RELEASE_KEY,
                                SKIP_CONFIRM_KEY)


def release_tag(release):
    if not release and not utils.is_brewblox_cwd():
        print('Please run this command in a BrewBlox directory, or use the --release argument')
        raise SystemExit(1)

    return utils.docker_tag(release)


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Command collector"""


@cli.command()
def down():
    """Stop running services"""
    utils.check_config()
    shell_commands = [
        '{}docker-compose down --remove-orphans'.format(utils.optsudo()),
    ]
    utils.run_all(shell_commands)


@cli.command()
def up():
    """Start all services if not running"""
    utils.check_config()
    shell_commands = [
        '{}docker-compose up -d --remove-orphans'.format(utils.optsudo()),
    ]
    utils.run_all(shell_commands)


@cli.command()
def restart():
    """(re)start all services"""
    utils.check_config()
    sudo = utils.optsudo()
    shell_commands = [
        '{}docker-compose down --remove-orphans'.format(sudo),
        '{}docker-compose up -d'.format(sudo),
    ]
    utils.run_all(shell_commands)


@cli.command()
def install():
    """Install a new BrewBlox system"""
    shell_commands = []

    use_defaults = utils.confirm('Do you want to install with default settings?')

    if utils.command_exists('apt') \
            and (use_defaults or utils.confirm('Do you want to install apt dependency packages?')):
        shell_commands += [
            'sudo apt update',
            'sudo apt upgrade -y',
            'sudo apt install -y libssl-dev libffi-dev',
        ]

    if utils.command_exists('docker'):
        print('Docker is already installed, skipping...')
    elif use_defaults or utils.confirm('Do you want to install Docker?'):
        shell_commands += [
            "curl -sL get.docker.com | sh",
        ]

    if utils.is_docker_user():
        print('{} already belongs to the Docker group, skipping...'.format(utils.getenv('USER')))
    elif use_defaults or utils.confirm('Do you want to run Docker commands without sudo?'):
        shell_commands += [
            'sudo usermod -aG docker $USER'
        ]

    if utils.command_exists('docker-compose'):
        print('docker-compose is already installed, skipping...')
    elif use_defaults or utils.confirm('Do you want to install docker-compose (from pip)?'):
        shell_commands += [
            'sudo {} -m pip install -U docker-compose'.format(PY)
        ]

    if use_defaults:
        target_dir = './brewblox'
    else:
        target_dir = utils.select(
            'In which directory do you want to install the BrewBlox configuration?',
            './brewblox'
        ).rstrip('/')

    if utils.path_exists(target_dir):
        if not utils.confirm('{} already exists. Do you want to continue?'.format(target_dir)):
            return

    # TODO(Bob) Wait until stable is actually stable before offering new users a choice
    release = 'edge'
    # if utils.confirm('Do you want to wait for stable releases?'):
    #     release = 'stable'
    # else:
    #     release = 'edge'

    set_env_command = '{} -m dotenv.cli --quote never -f {}/.env set'.format(PY, target_dir)

    shell_commands += [
        'mkdir -p {}'.format(target_dir),
        'touch {}/.env'.format(target_dir),
        '{} {} {}'.format(set_env_command, RELEASE_KEY, release),
        '{} {} 0.0.0'.format(set_env_command, CFG_VERSION_KEY),
        '{} {} {}'.format(set_env_command, SKIP_CONFIRM_KEY, str(use_defaults)),
    ]

    if use_defaults or utils.confirm('A reboot is recommended. Do you want to do so?'):
        shell_commands.append('sudo reboot')

    utils.run_all(shell_commands, not use_defaults)


@cli.command()
def kill():
    """Stop and remove all containers on this machine"""
    if not utils.confirm('This will stop and remove ALL docker containers on your system. ' +
                         'This includes those not from BrewBlox. ' +
                         'Do you want to continue?'):
        return

    sudo = utils.optsudo()
    shell_commands = [
        '{}docker rm --force $({}docker ps -aq) 2> /dev/null '.format(sudo, sudo) +
        '|| echo "No containers found"',
    ]

    utils.run_all(shell_commands)


@cli.command()
@click.option('--release', default=None, help='BrewBlox release track')
@click.option('--pull/--no-pull', default=True)
def flash(release, pull):
    """Flash firmware on Spark"""
    tag = release_tag(release)
    sudo = utils.optsudo()
    shell_commands = []

    if utils.path_exists('./docker-compose.yml'):
        shell_commands += [
            '{}docker-compose down'.format(sudo),
        ]

    if pull:
        shell_commands += [
            '{}docker pull brewblox/firmware-flasher:{}'.format(sudo, tag),
        ]

    shell_commands += [
        '{}docker run -it --rm --privileged brewblox/firmware-flasher:{} trigger-dfu'.format(sudo, tag),
        '{}docker run -it --rm --privileged brewblox/firmware-flasher:{} flash'.format(sudo, tag),
    ]

    utils.prompt_usb()
    utils.run_all(shell_commands)


@cli.command()
@click.option('--release', default=None, help='BrewBlox release track')
@click.option('--force', is_flag=True, help='Force flashing the bootloader')
def bootloader(release, force):
    """Flash bootloader on Spark"""
    tag = release_tag(release)
    sudo = utils.optsudo()
    shell_commands = []

    if utils.path_exists('./docker-compose.yml'):
        shell_commands += [
            '{}docker-compose down'.format(sudo),
        ]

    shell_commands += [
        '{}docker pull brewblox/firmware-flasher:{}'.format(sudo, tag),
        '{}docker run -it --rm --privileged brewblox/firmware-flasher:{} flash-bootloader{}'.format(
            sudo, tag, ' --force' if force else ''),
    ]

    utils.prompt_usb()
    utils.run_all(shell_commands)


@cli.command()
@click.option('--release', default=None, help='BrewBlox release track')
def wifi(release):
    """Connect Spark to Wifi"""
    tag = release_tag(release)
    sudo = utils.optsudo()
    shell_commands = []

    if utils.path_exists('./docker-compose.yml'):
        shell_commands += [
            '{}docker-compose down'.format(sudo),
        ]

    shell_commands += [
        '{}docker pull brewblox/firmware-flasher:{}'.format(sudo, tag),
        '{}docker run -it --rm --privileged brewblox/firmware-flasher:{} wifi'.format(sudo, tag),
    ]

    utils.prompt_usb()
    utils.run_all(shell_commands)


@cli.command()
def settings():
    """brewblox-ctl settings"""
    utils.check_config()
    current_skip_setting = utils.skipping_confirm()
    new_skip_setting = utils.confirm(
        'Do you want to skip confirmation prompts when running commands? (is {})'.format(current_skip_setting),
        current_skip_setting)

    shell_commands = [
        '{} -m dotenv.cli --quote never -f .env set {} {}'.format(
            PY, SKIP_CONFIRM_KEY, str(new_skip_setting)),
    ]

    utils.run_all(shell_commands, not new_skip_setting)
