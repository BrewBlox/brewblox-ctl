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
@click.option('--apt-install/--no-apt-install',
              default=None,
              help='Update and install apt dependencies. Overrides --use-defaults if set.')
@click.option('--docker-install/--no-docker-install',
              default=None,
              help='Install docker. Overrides --use-defaults if set.')
@click.option('--docker-user/--no-docker-user',
              default=None,
              help='Add user to docker group. Overrides --use-defaults if set.')
@click.option('--dir',
              help='Install directory.')
@click.option('--no-reboot',
              is_flag=True,
              help='Do not reboot after install is done.')
@click.option('--release',
              default='edge',
              help='Brewblox release track.')
def install(use_defaults,
            apt_install,
            docker_install,
            docker_user,
            no_reboot,
            dir,
            release):
    """Create Brewblox directory; install system dependencies; reboot.

    Brewblox can be installed multiple times on the same computer.
    Settings and databases are stored in a Brewblox directory (default: ./brewblox).

    This command also installs system-wide dependencies (docker).
    After `brewblox-ctl install`, run `brewblox-ctl setup` in the created Brewblox directory.

    A reboot is required after installing docker, or adding the user to the 'docker' group.

    By default, `brewblox-ctl install` attempts to download packages using the apt package manager.
    If you are using a system without apt (eg. Synology NAS), this step will be skipped.
    You will need to manually install any missing libraries.

    \b
    Steps:
        - Install apt packages.
        - Install docker.
        - Add user to 'docker' group.
        - Create Brewblox directory (default ./brewblox).
        - Set variables in .env file.
        - Reboot.
    """
    utils.confirm_mode()

    apt_deps = 'curl net-tools libssl-dev libffi-dev'
    user = utils.getenv('USER')
    default_dir = path.abspath('./brewblox')
    prompt_reboot = True

    if use_defaults is None:
        use_defaults = utils.confirm('Do you want to install with default settings?')

    # Check if packages should be installed
    if not utils.command_exists('apt'):
        utils.info('Apt is not available. You may need to find another way to install dependencies.')
        utils.info('Apt packages: "{}"'.format(apt_deps))
        apt_install = False

    if apt_install is None:
        if use_defaults:
            apt_install = True
        else:
            apt_install = utils.confirm('Do you want to install apt packages "{}"?'.format(apt_deps))

    # Check if docker should be installed
    if utils.command_exists('docker'):
        utils.info('Docker is already installed.')
        docker_install = False

    if docker_install is None:
        if use_defaults:
            docker_install = True
        else:
            docker_install = utils.confirm('Do you want to install docker?')

    # Check if user should be added to docker group
    if utils.is_docker_user():
        utils.info('{} already belongs to the docker group.'.format(user))
        docker_user = False

    if docker_user is None:
        if use_defaults:
            docker_user = True
        else:
            docker_user = utils.confirm('Do you want to run docker commands without sudo?')

    # Check used directory
    if dir is None:
        if use_defaults or utils.confirm("The default directory is '{}'. Do you want to continue?".format(default_dir)):
            dir = default_dir
        else:
            return

    if utils.path_exists(dir):
        if not utils.confirm('{} already exists. Do you want to continue?'.format(dir)):
            return

    if not no_reboot:
        prompt_reboot = utils.confirm('A reboot is required after installation. ' +
                                      'Do you want to be prompted before that happens?')

    # Install Apt packages
    if apt_install:
        utils.info('Installing apt packages...')
        sh([
            'sudo apt update',
            'sudo apt upgrade -y',
            'sudo apt install -y {}'.format(apt_deps),
        ])
    else:
        utils.info('Skipped: apt install.')

    # Install docker
    if docker_install:
        utils.info('Installing docker...')
        sh('curl -sL get.docker.com | sh')
    else:
        utils.info('Skipped: docker install.')

    # Add user to 'docker' group
    if docker_user:
        utils.info("Adding {} to 'docker' group...".format(user))
        sh('sudo usermod -aG docker $USER')
    else:
        utils.info("Skipped: adding {} to 'docker' group.".format(user))

    # Create install directory
    utils.info('Creating Brewblox directory ({})...'.format(dir))
    sh('mkdir -p {}'.format(dir))

    # Set variables in .env file
    utils.info('Setting variables in .env file...')
    dotenv_path = path.abspath('{}/.env'.format(dir))
    sh('touch {}'.format(dotenv_path))
    utils.setenv(const.RELEASE_KEY, release, dotenv_path)
    utils.setenv(const.CFG_VERSION_KEY, '0.0.0', dotenv_path)
    utils.setenv(const.SKIP_CONFIRM_KEY, str(use_defaults), dotenv_path)

    utils.info('Done!')

    # Reboot
    if not no_reboot:
        if prompt_reboot:
            utils.info('Press ENTER to reboot.')
            input()
        else:
            utils.info('Rebooting in 10 seconds...')
            sleep(10)
        sh('sudo reboot')
    else:
        utils.info('Skipped: reboot.')


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
    opts = '-it --rm --privileged -v /dev:/dev'
    sh('{}docker run {} brewblox/firmware-flasher:{} {}'.format(sudo, opts, tag, args))


@cli.command()
@click.option('--release', default=None, help='Brewblox release track')
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
    run_flasher(release, 'flash')


@cli.command()
@click.option('--release', default=None, help='Brewblox release track')
@click.option('--pull/--no-pull', default=True)
def wifi(release, pull):
    """DISABLED: Configure Spark Wifi settings.

    This requires the Spark to be connected over USB.

    \b
    Steps:
        - Stop running services.
        - Pull flasher image.
        - Run wifi command.
    """
    utils.info('This command is temporarily disabled')
    utils.info('To set up Wifi, connect to the Spark over USB')
    utils.info('On the Spark service page (actions, top right), you can configure Wifi settings')
    # utils.confirm_mode()
    # utils.confirm_usb()
    # prepare_flasher(release, pull)

    # utils.info('Configuring wifi...')
    # run_flasher(release, 'wifi')


@cli.command()
@click.option('--release', default=None, help='Brewblox release track')
@click.option('--pull/--no-pull', default=True)
@click.option('-c', '--command', default='')
def particle(release, pull, command):
    """Start a Docker container with access to the Particle CLI.

    This requires the Spark to be connected over USB.

    \b
    Steps:
        - Stop running services.
        - Pull flasher image.
        - Start flasher image.
    """
    utils.confirm_mode()
    utils.confirm_usb()
    prepare_flasher(release, pull)

    utils.info('Starting Particle image...')
    utils.info("Type 'exit' and press enter to exit the shell")
    run_flasher(release, command)


@cli.command()
def disable_ipv6():
    """Disable IPv6 support on the host machine.

    Reason: https://github.com/docker/for-linux/issues/914
    Should only be used if your services are having stability issues
    """
    utils.confirm_mode()
    is_disabled = sh('cat /proc/sys/net/ipv6/conf/all/disable_ipv6', capture=True).strip()
    if is_disabled == '1':
        utils.info('IPv6 is already disabled')
    elif is_disabled == '0' or utils.ctx_opts().dry_run:
        utils.info('Disabling IPv6...')
        sh('echo "net.ipv6.conf.all.disable_ipv6 = 1" | sudo tee -a /etc/sysctl.conf')
        sh('echo "net.ipv6.conf.default.disable_ipv6 = 1" | sudo tee -a /etc/sysctl.conf')
        sh('echo "net.ipv6.conf.lo.disable_ipv6 = 1" | sudo tee -a /etc/sysctl.conf')
        sh('sudo sysctl -p')
    else:
        utils.info('Invalid result when checking IPv6 status: ' + is_disabled)
