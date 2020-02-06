"""
Brewblox-ctl installation commands
"""

from os import path
from time import sleep

import click

from brewblox_ctl import click_helpers, const, utils
from brewblox_ctl.utils import sh


def release_tag(release):
    if not release and not utils.is_brewblox_cwd():
        print('Please run this command in a BrewBlox directory, or use the --release argument')
        raise SystemExit(1)

    return utils.docker_tag(release)


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Command collector"""


@cli.command()
@click.option('--express',
              is_flag=True,
              default=True,
              prompt='Do you want to install with default settings?',
              help='Use default settings for installation')
def install(express):
    """Install a new Brewblox system

    \f
    \b
    Steps:
        - Install apt packages.
        - Install Docker.
        - Add user to 'docker' group.
        - Install docker-compose.
        - Create install directory.
        - Set variables in .env file.
        - Reboot.
    """
    utils.confirm_mode()

    if utils.command_exists('apt') \
            and (express or utils.confirm('Do you want to install apt packages?')):
        utils.info('Installing apt packages...')
        sh([
            'sudo apt update',
            'sudo apt upgrade -y',
            'sudo apt install -y libssl-dev libffi-dev',
        ])

    if utils.command_exists('docker'):
        utils.info('Docker is already installed, skipping...')
    elif express or utils.confirm('Do you want to install Docker?'):
        utils.info('Installing Docker...')
        sh('curl -sL get.docker.com | sh')

    if utils.is_docker_user():
        print('{} already belongs to the Docker group, skipping...'.format(utils.getenv('USER')))
    elif express or utils.confirm('Do you want to run Docker commands without sudo?'):
        utils.info('Adding user to \'docker\' group...')
        sh('sudo usermod -aG docker $USER')

    if utils.command_exists('docker-compose'):
        print('docker-compose is already installed, skipping...')
    elif express or utils.confirm('Do you want to install docker-compose (from pip)?'):
        utils.info('Installing docker-compose...')
        sh('sudo {} -m pip install -U docker-compose'.format(const.PY))

    if express:
        target_dir = './brewblox'
    else:
        target_dir = utils.select(
            'In which directory do you want to install the BrewBlox configuration?',
            './brewblox'
        ).rstrip('/ \t\n')

    if utils.path_exists(target_dir):
        if not utils.confirm('{} already exists. Do you want to continue?'.format(target_dir)):
            return

    # TODO(Bob) Wait until stable is actually stable before offering new users a choice
    release = 'edge'
    # if utils.confirm('Do you want to wait for stable releases?'):
    #     release = 'stable'
    # else:
    #     release = 'edge'

    dotenv_path = path.abspath('{}/.env'.format(target_dir))

    utils.info('Creating install directory ({})...'.format(target_dir))
    sh('mkdir -p {}'.format(target_dir))

    utils.info('Setting variables in .env file...')
    sh('touch {}'.format(dotenv_path))
    utils.setenv(const.RELEASE_KEY, release, dotenv_path)
    utils.setenv(const.CFG_VERSION_KEY, '0.0.0', dotenv_path)
    utils.setenv(const.SKIP_CONFIRM_KEY, str(express), dotenv_path)

    if express or utils.confirm('A reboot is recommended. Do you want to do so?'):
        utils.info('Rebooting in 10 seconds...')
        sleep(10)
        sh('sudo reboot')


def prepare_flasher(release, pull):
    tag = release_tag(release)
    sudo = utils.optsudo()

    if utils.path_exists('./docker-compose.yml'):
        utils.info('Stopping services...')
        sh('{}docker-compose down'.format(sudo))

    if pull:
        utils.info('Pulling flasher image...')
        sh('{}docker pull brewblox/firmware-flasher:{}'.format(sudo, tag))


def run_flasher(release, args):
    tag = release_tag(release)
    sudo = utils.optsudo()
    sh('{}docker run -it --rm --privileged brewblox/firmware-flasher:{} {}'.format(sudo, tag, args))


@cli.command()
@click.option('--release', default=None, help='BrewBlox release track')
@click.option('--pull/--no-pull', default=True)
def flash(release, pull):
    """Flash firmware on Spark

    \f
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
    """Flash bootloader on Spark

    \f
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
    """Connect Spark to Wifi

    \f
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
