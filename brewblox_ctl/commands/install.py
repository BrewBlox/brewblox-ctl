"""
Brewblox-ctl installation commands
"""

from os import path
from time import sleep

import click

from brewblox_ctl import click_helpers, const, utils
from brewblox_ctl.utils import sh


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Command collector"""


@cli.command()
@click.option('--use-defaults/--no-use-defaults',
              default=True,
              prompt='Do you want to install with default settings?',
              help='Use default settings for installation')
@click.option('--dir',
              default='./brewblox',
              help='Install directory.')
@click.option('--release',
              default='edge',
              help='Brewblox release track.')
def install(use_defaults, dir, release):
    """Create and prepare brewblox install directory.

    Brewblox can be installed multiple times on the same computer.
    Global dependencies (Docker, docker-compose) are shared, and system-specific
    settings and databases are stored in an installation directory (default: ~/brewblox).

    To get a working system, first run `brewblox-ctl install`,
    then navigate to the installation directory, and run `brewblox-ctl setup`.

    After installing Docker, or adding the user to the 'docker' group, the computer must be rebooted.

    By default, `brewblox-ctl install` attempts to download packages using the Apt package manager.
    If you are using a system without Apt (eg. Synology NAS), this step will be skipped.
    You will need to manually install any missing libraries.

    \b
    Steps:
        - Install Apt packages.
        - Install Docker.
        - Install docker-compose.
        - Add user to 'docker' group.
        - Create install directory.
        - Set variables in .env file.
        - Reboot.
    """
    utils.confirm_mode()

    # Install Apt packages
    apt_deps = 'libssl-dev libffi-dev'
    if not utils.command_exists('apt'):
        utils.info('Apt is not available. You may need to find another way to install dependencies.')
        utils.info('Apt packages: "{}"'.format(apt_deps))
    elif use_defaults or utils.confirm('Do you want to install Apt packages "{}"?'.format(apt_deps)):
        utils.info('Installing Apt packages...')
        sh([
            'sudo apt update',
            'sudo apt upgrade -y',
            'sudo apt install -y {}'.format(apt_deps),
        ])

    # Install Docker
    if utils.command_exists('docker'):
        utils.info('Docker is already installed, skipping...')
    elif use_defaults or utils.confirm('Do you want to install Docker?'):
        utils.info('Installing Docker...')
        sh('curl -sL get.docker.com | sh')

    # Install docker-compose
    if utils.command_exists('docker-compose'):
        utils.info('docker-compose is already installed, skipping...')
    elif use_defaults or utils.confirm('Do you want to install docker-compose (from pip)?'):
        utils.info('Installing docker-compose...')
        sh('sudo {} -m pip install -U docker-compose'.format(const.PY))

    # Add user to 'docker' group
    user = utils.getenv('USER')
    if utils.is_docker_user():
        utils.info('{} already belongs to the Docker group, skipping...'.format(user))
    elif use_defaults or utils.confirm('Do you want to run Docker commands without sudo?'):
        utils.info('Adding {} to \'docker\' group...'.format(user))
        sh('sudo usermod -aG docker $USER')

    # Create install directory
    if utils.path_exists(dir):
        if not utils.confirm('{} already exists. Do you want to continue?'.format(dir)):
            return

    utils.info('Creating install directory ({})...'.format(dir))
    sh('mkdir -p {}'.format(dir))

    # Set variables in .env file
    utils.info('Setting variables in .env file...')
    dotenv_path = path.abspath('{}/.env'.format(dir))
    sh('touch {}'.format(dotenv_path))
    utils.setenv(const.RELEASE_KEY, release, dotenv_path)
    utils.setenv(const.CFG_VERSION_KEY, '0.0.0', dotenv_path)
    utils.setenv(const.SKIP_CONFIRM_KEY, str(use_defaults), dotenv_path)

    # Reboot
    if use_defaults or utils.confirm('Do you want to reboot now?'):
        utils.info('Rebooting in 10 seconds...')
        sleep(10)
        sh('sudo reboot')


def prepare_flasher(release, pull):
    tag = utils.docker_tag(release)
    sudo = utils.optsudo()

    if pull:
        utils.info('Pulling flasher image...')
        sh('{}docker pull brewblox/firmware-flasher:{}'.format(sudo, tag))

    if utils.path_exists('./docker-compose.yml'):
        utils.info('Stopping services...')
        sh('{}docker-compose down'.format(sudo))


def run_flasher(release, args):
    tag = utils.docker_tag(release)
    sudo = utils.optsudo()
    sh('{}docker run -it --rm --privileged brewblox/firmware-flasher:{} {}'.format(sudo, tag, args))


@cli.command()
@click.option('--release', default=None, help='BrewBlox release track')
@click.option('--pull/--no-pull', default=True)
def flash(release, pull):
    """Flash firmware on Spark.

    This requires the Spark to be connected over USB.

    \b
    Steps:
        - Stop running services.
        - Pull flasher image.
        - Run flash command.
    """
    utils.confirm_mode()
    utils.prompt_usb()
    prepare_flasher(release, pull)

    utils.info('Flashing Spark...')
    run_flasher(release, 'trigger-dfu')
    run_flasher(release, 'flash')


@cli.command()
@click.option('--release', default=None, help='BrewBlox release track')
@click.option('--pull/--no-pull', default=True)
@click.option('--force', is_flag=True, help='Force flashing the bootloader')
def bootloader(release, pull, force):
    """Flash bootloader on Spark.

    The bootloader is updated only very rarely.
    You do not have to run this command for every update.

    This requires the Spark to be connected over USB.

    \b
    Steps:
        - Stop running services.
        - Pull flasher image.
        - Run bootloader command.
    """
    utils.confirm_mode()
    utils.prompt_usb()
    prepare_flasher(release, pull)

    utils.info('Flashing bootloader...')
    run_flasher(release, 'flash-bootloader' + ' --force' if force else '')


@cli.command()
@click.option('--release', default=None, help='BrewBlox release track')
@click.option('--pull/--no-pull', default=True)
def wifi(release, pull):
    """Configure Spark Wifi settings.

    This requires the Spark to be connected over USB.

    \b
    Steps:
        - Stop running services.
        - Pull flasher image.
        - Run wifi command.
    """
    utils.confirm_mode()
    utils.prompt_usb()
    prepare_flasher(release, pull)

    utils.info('Configuring wifi...')
    run_flasher(release, 'wifi')
