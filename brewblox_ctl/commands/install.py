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
              default=None,
              help='Use default settings for installation.')
@click.option('--dir',
              help='Install directory.')
@click.option('--release',
              default='edge',
              help='Brewblox release track.')
def install(use_defaults, dir, release):
    """Create Brewblox directory; install system dependencies; reboot.

    Brewblox can be installed multiple times on the same computer.
    Settings and databases are stored in a Brewblox directory (default: ./brewblox).

    This command also installs system-wide dependencies (docker, docker-compose).
    After `brewblox-ctl install`, run `brewblox-ctl setup` in the created Brewblox directory.

    A reboot is required after installing docker, or adding the user to the 'docker' group.

    By default, `brewblox-ctl install` attempts to download packages using the apt package manager.
    If you are using a system without apt (eg. Synology NAS), this step will be skipped.
    You will need to manually install any missing libraries.

    \b
    Steps:
        - Install apt packages.
        - Install docker.
        - Install docker-compose.
        - Add user to 'docker' group.
        - Create Brewblox directory (default ./brewblox).
        - Set variables in .env file.
        - Reboot.
    """
    utils.confirm_mode()

    if use_defaults is None:
        use_defaults = utils.confirm('Do you want to install with default settings?')

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

    # Install docker
    if utils.command_exists('docker'):
        utils.info('Docker is already installed, skipping...')
    elif use_defaults or utils.confirm('Do you want to install docker?'):
        utils.info('Installing docker...')
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
        utils.info('{} already belongs to the docker group, skipping...'.format(user))
    elif use_defaults or utils.confirm('Do you want to run docker commands without sudo?'):
        utils.info('Adding {} to \'docker\' group...'.format(user))
        sh('sudo usermod -aG docker $USER')

    # Determine install directory
    default_dir = path.abspath('./brewblox')
    if not dir \
        and not use_defaults \
            and not utils.confirm('Using Brewblox directory \'{}\'. Do you want to continue?'.format(default_dir)):
        return

    dir = dir or default_dir

    # Create install directory
    if utils.path_exists(dir):
        if not utils.confirm('{} already exists. Do you want to continue?'.format(dir)):
            return
    else:
        utils.info('Creating Brewblox directory ({})...'.format(dir))
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

    After the first install, firmware updates can also be installed using the UI.

    \b
    Steps:
        - Stop running services.
        - Pull flasher image.
        - Run flash command.
    """
    utils.confirm_mode()
    utils.confirm_usb()
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
    utils.confirm_usb()
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
    utils.confirm_usb()
    prepare_flasher(release, pull)

    utils.info('Configuring wifi...')
    run_flasher(release, 'wifi')
