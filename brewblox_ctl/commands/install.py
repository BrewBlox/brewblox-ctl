"""
Brewblox-ctl installation commands
"""

from time import sleep

import click

from .. import actions, click_helpers, const, utils
from . import snapshot


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Command collector"""


class InstallOptions:
    def __init__(self) -> None:
        self.use_defaults: bool = False
        self.skip_confirm: bool = True

        self.apt_install: bool = True

        self.docker_install: bool = True
        self.docker_group_add: bool = True
        self.docker_pull: bool = True

        self.reboot_needed: bool = False
        self.prompt_reboot: bool = True

        self.init_compose: bool = True
        self.init_auth: bool = True
        self.init_datastore: bool = True
        self.init_history: bool = True
        self.init_gateway: bool = True
        self.init_eventbus: bool = True

    def check_compatibility(self):
        if utils.is_armv6() and not utils.confirm(
            'ARMv6 detected. The Raspberry Pi Zero and 1 are not supported. ' + 'Do you want to continue?',
            default=False,
        ):
            raise SystemExit(0)

    def check_confirm_opts(self):
        self.use_defaults = False
        self.skip_confirm = True

        self.use_defaults = utils.confirm('Do you want to install with default settings?')

        if not self.use_defaults:
            self.skip_confirm = utils.confirm(
                'Do you want to disable the confirmation prompt for brewblox-ctl commands?'
            )

    def check_system_opts(self):
        self.apt_install = True

        apt_deps = ' '.join(const.APT_DEPENDENCIES)
        if not utils.command_exists('apt-get'):
            utils.info('`apt-get` is not available. You may need to find another way to install dependencies.')
            utils.info(f'Apt packages: "{apt_deps}"')
            self.apt_install = False
        elif not self.use_defaults:
            self.apt_install = utils.confirm(
                'Do you want brewblox-ctl to install and update system (apt) packages? '
                + f'Installed packages: `{apt_deps}`.'
            )

    def check_docker_opts(self):
        self.docker_install = True
        self.docker_group_add = True
        self.docker_pull = True

        if utils.command_exists('docker'):
            utils.info('Docker is already installed.')
            self.docker_install = False
        elif not self.use_defaults:
            self.docker_install = utils.confirm('Do you want to install docker?')

        if utils.is_docker_user():
            user = utils.getenv('USER')
            utils.info(f'{user} already belongs to the docker group.')
            self.docker_group_add = False
        elif not self.use_defaults:
            self.docker_group_add = utils.confirm('Do you want to run docker commands without sudo?')

        if not self.use_defaults:
            self.docker_pull = utils.confirm('Do you want to pull the docker images for your services?')

    def check_reboot_opts(self):
        self.reboot_needed = False
        self.prompt_reboot = True

        if self.docker_install or self.docker_group_add or (utils.is_docker_user() and not utils.has_docker_rights()):
            self.reboot_needed = True
            self.prompt_reboot = utils.confirm(
                'A reboot is required after installation. ' + 'Do you want to be prompted before that happens?'
            )

    def check_init_opts(self):
        self.init_compose = True
        self.init_auth = True
        self.init_datastore = True
        self.init_history = True
        self.init_gateway = True
        self.init_eventbus = True
        self.init_spark_backup = True

        if utils.file_exists('./docker-compose.yml'):
            self.init_compose = not utils.confirm(
                'This directory already contains a docker-compose.yml file. ' + 'Do you want to keep it?'
            )

        if utils.file_exists('./auth/'):
            self.init_auth = not utils.confirm(
                'This directory already contains user authentication files. ' 'Do you want to keep them?'
            )

        if utils.file_exists('./redis/'):
            self.init_datastore = not utils.confirm(
                'This directory already contains Redis datastore files. ' + 'Do you want to keep them?'
            )

        if utils.file_exists('./victoria/'):
            self.init_history = not utils.confirm(
                'This directory already contains Victoria history files. ' + 'Do you want to keep them?'
            )

        if utils.file_exists('./traefik/'):
            self.init_gateway = not utils.confirm(
                'This directory already contains Traefik gateway files. ' + 'Do you want to keep them?'
            )

        if utils.file_exists('./mosquitto/'):
            self.init_eventbus = not utils.confirm(
                'This directory already contains Mosquitto config files. ' + 'Do you want to keep them?'
            )

        if utils.file_exists('./spark/backup/'):
            self.init_spark_backup = not utils.confirm(
                'This directory already contains Spark backup files. ' + 'Do you want to keep them?'
            )


@cli.command()
@click.pass_context
@click.option('--snapshot', 'snapshot_file', help='Load system snapshot generated by `brewblox-ctl snapshot save`.')
def install(ctx: click.Context, snapshot_file):
    """Install Brewblox and its dependencies.

    Brewblox can be installed multiple times on the same computer.
    Settings and databases are stored in a Brewblox directory.

    This command also installs system-wide dependencies.
    A reboot is required after installing docker, or adding the user to the 'docker' group.

    By default, `brewblox-ctl install` attempts to download packages using the apt package manager.
    If you are using a system without apt (eg. Synology NAS), this step will be skipped.
    You will need to manually install any missing libraries.

    When using the `--snapshot ARCHIVE` option, no dir is created.
    Instead, the directory in the snapshot is extracted.
    It will be renamed to the desired name of the Brewblox directory.

    \b
    Steps:
        - Ask confirmation for installation steps.
        - Install apt packages.
        - Install docker.
        - Add user to 'docker' group.
        - Fix host IPv6 settings.
        - Disable host-wide mDNS reflection.
        - Set variables in .env file.
        - If snapshot provided:
            - Load configuration from snapshot.
        - Else:
            - Check for port conflicts.
            - Create docker compose configuration files.
            - Create datastore (Redis) directory.
            - Create history (Victoria) directory.
            - Create gateway (Traefik) directory.
            - Create SSL certificates.
            - Create eventbus (Mosquitto) directory.
            - Set version number in .env file.
        - Pull docker images.
        - Reboot if needed.
    """
    utils.confirm_mode()
    config = utils.get_config()
    user = utils.getenv('USER')
    opts = InstallOptions()

    opts.check_compatibility()
    opts.check_confirm_opts()
    opts.check_system_opts()
    opts.check_docker_opts()
    opts.check_reboot_opts()

    if not snapshot_file:
        opts.check_init_opts()

    # Save preferences to brewblox.yml
    utils.info('Generating brewblox.yml ...')
    config.skip_confirm = opts.skip_confirm
    config.system.apt_upgrade = opts.apt_install
    actions.make_brewblox_config(config)

    # Install Apt packages
    if opts.apt_install:
        utils.info('Installing apt packages ...')
        apt_deps = ' '.join(const.APT_DEPENDENCIES)
        utils.sh('sudo apt-get update')
        utils.sh('sudo apt-get upgrade -y')
        utils.sh(f'sudo apt-get install -y {apt_deps}')
    else:
        utils.info('Skipped: apt-get install.')

    # Install docker
    if opts.docker_install:
        utils.info('Installing docker ...')
        utils.sh('curl -sL get.docker.com | sh', check=False)
    else:
        utils.info('Skipped: docker install.')

    # Add user to 'docker' group
    if opts.docker_group_add:
        utils.info(f"Adding {user} to 'docker' group ...")
        utils.sh('sudo usermod -aG docker $USER')
    else:
        utils.info(f"Skipped: adding {user} to 'docker' group.")

    # Always apply these actions
    actions.install_compose_plugin()
    actions.edit_sshd_config()
    actions.fix_ipv6(None, False)
    actions.make_udev_rules()
    actions.make_ctl_entrypoint()

    # Install process splits here
    # Either load all config files from snapshot or run init
    sudo = utils.optsudo()
    if snapshot_file:
        ctx.invoke(snapshot.load, file=snapshot_file)
    else:
        utils.info('Checking for port conflicts ...')
        actions.check_ports()

        if opts.init_compose:
            utils.sh('rm -f ./docker-compose.yml')

        actions.make_dotenv('0.0.0')
        actions.make_shared_compose()
        actions.make_compose()

        # Stop after we're sure we have a compose file
        if utils.is_compose_up():
            utils.info('Stopping services ...')
            utils.sh(f'{sudo}docker compose down --remove-orphans')

        if opts.init_datastore:
            utils.info('Creating datastore directory ...')
            utils.sh('sudo rm -rf ./redis/; mkdir ./redis/')

        if opts.init_auth:
            utils.info('Creating auth directory ...')
            utils.sh('sudo rm -rf ./auth/; mkdir ./auth/')

        if opts.init_history:
            utils.info('Creating history directory ...')
            utils.sh('sudo rm -rf ./victoria/; mkdir ./victoria/')

        if opts.init_gateway:
            utils.info('Creating gateway directory ...')
            utils.sh('sudo rm -rf ./traefik/; mkdir ./traefik/ ./traefik/dynamic')

            utils.info('Creating SSL certificate ...')
            actions.make_tls_certificates(always=True)
            actions.make_traefik_config()

        if opts.init_eventbus:
            utils.info('Creating mosquitto config directory ...')
            utils.sh('sudo rm -rf ./mosquitto/; mkdir ./mosquitto/')

        if opts.init_spark_backup:
            utils.info('Creating Spark backup directory ...')
            utils.sh('sudo rm -rf ./spark/backup/; mkdir -p ./spark/backup/')

        # Init done - now set CFG version
        utils.setenv(const.ENV_KEY_CFG_VERSION, const.CFG_VERSION)

    # This depends on loaded settings
    actions.edit_avahi_config()

    if opts.docker_pull:
        utils.info('Pulling docker images ...')
        utils.sh(f'{sudo}docker compose pull')

    utils.info('All done!')

    # Reboot
    if opts.reboot_needed:
        if opts.prompt_reboot:
            utils.info('Press ENTER to reboot.')
            input()
        else:
            utils.info('Rebooting in 10 seconds ...')
            sleep(10)
        utils.sh('sudo reboot')


@cli.command()
@click.option(
    '--domain',
    multiple=True,
    help='Additional alternative domain name for the generated cert. ' + 'This option can be used multiple times.',
)
@click.option('--release', default=None, help='Brewblox release track for the minica Docker image.')
def makecert(domain, release):
    """Generate SSL CA and certificate.

    These are locally signed certificates, and will generate browser warnings
    unless installed in a trust store.

    By default, the generated cert covers all known LAN IP addresses for this machine,
    along with {hostname}, {hostname}.local, and {hostname}.home.

    \b
    Steps:
        - Create directory if it does not exist.
        - Create CA files: traefik/minica.pem and traefik/minica-key.pem.
        - Create cert files: traefik/brew.blox/cert.pem and traefik/brew.blox/key.pem
    """
    utils.confirm_mode()
    actions.make_tls_certificates(True, domain, release)
