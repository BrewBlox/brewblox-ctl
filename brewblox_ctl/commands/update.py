"""
Migration scripts
"""

from distutils.version import StrictVersion

import click
from brewblox_ctl import click_helpers, sh
from brewblox_ctl import const, migration, utils


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Global command group"""


def check_version(prev_version: StrictVersion):
    """Verify that the previous version is sane and sensible"""
    if prev_version.version == (0, 0, 0):
        utils.error('This configuration was never set up. Please run brewblox-ctl setup first')
        raise SystemExit(1)

    if prev_version > StrictVersion(const.CURRENT_VERSION):
        utils.error('Your system is running a version newer than the selected release. ' +
                    'This may be due to switching release tracks.' +
                    'You can use the --from-version flag if you know what you are doing.')
        raise SystemExit(1)


def check_sudo_install():
    """
    Early versions were installed using 'sudo pip install brewblox-ctl'.
    This should be fixed to avoid duplicate installs.
    """
    if utils.user_home_exists() and utils.path_exists('/usr/local/bin/brewblox-ctl'):  # pragma: no cover
        utils.warn('brewblox-ctl appears to have been installed using sudo.')
        if utils.confirm('Do you want to fix this now?'):
            sh(f'sudo {const.PY} -m pip uninstall -y brewblox-ctl docker-compose', check=False)
            utils.pip_install('brewblox-ctl')  # docker-compose is a dependency
            raise SystemExit(1)


def check_path():
    """
    Verify that ~/.local/bin is in $PATH.
    This was not the default for Debian Stretch, and is always good to check.
    """
    if utils.user_home_exists() and '.local/bin' not in utils.getenv('PATH'):
        sh('echo \'export PATH="$HOME/.local/bin:$PATH"\' >> ~/.bashrc')
        utils.info('Added the ~/.local/bin directory to $PATH')
        utils.warn('Please run "exec $SHELL --login" to apply the changes to $PATH')
        raise SystemExit(1)


def apply_config_files():
    """Apply system-defined configuration from config dir"""
    utils.info('Updating configuration files...')
    sh(f'cp -f {const.CONFIG_DIR}/traefik-cert.yaml ./traefik/')
    sh(f'cp -f {const.CONFIG_DIR}/docker-compose.shared.yml ./')
    shared_cfg = utils.read_shared_compose()
    usr_cfg = utils.read_compose()

    usr_cfg['version'] = shared_cfg['version']
    utils.write_compose(usr_cfg)


def check_automation_ui():
    # The automation service is deprecated, and its editor is removed from the UI.
    # The service was always optional - only add the automation-ui service if automation is present.
    config = utils.read_compose()
    services = config['services']
    if 'automation' in services and 'automation-ui' not in services:
        utils.info('Adding automation-ui service...')
        services['automation-ui'] = {
            'image': 'brewblox/brewblox-automation-ui:${BREWBLOX_RELEASE}',
            'restart': 'unless-stopped',
        }
        utils.write_compose(config)


def check_env_vars():
    utils.info('Checking .env variables...')
    for (key, default_value) in const.ENV_DEFAULTS.items():
        current_value = utils.getenv(key)
        if current_value is None:
            utils.setenv(key, default_value)


def check_dirs():
    utils.info('Checking data directories...')
    sh('mkdir -p ./traefik/ ./redis/ ./victoria/')


def downed_migrate(prev_version):
    """Migration commands to be executed without any running services"""
    # Always apply shared config files
    apply_config_files()
    utils.update_avahi_config()
    utils.add_particle_udev_rules()

    if prev_version < StrictVersion('0.3.0'):
        migration.migrate_compose_split()

    if prev_version < StrictVersion('0.6.0'):
        migration.migrate_compose_datastore()

    if prev_version < StrictVersion('0.6.1'):
        migration.migrate_ipv6_fix()

    # Not related to a specific release
    check_automation_ui()
    check_env_vars()
    check_dirs()


def upped_migrate(prev_version):
    """Migration commands to be executed after the services have been started"""
    if prev_version < StrictVersion('0.6.0'):
        utils.warn('')
        utils.warn('Brewblox now uses a new configuration database.')
        utils.warn('To migrate your data, run:')
        utils.warn('')
        utils.warn('    brewblox-ctl database from-couchdb')
        utils.warn('')

    if prev_version < StrictVersion('0.7.0'):
        utils.warn('')
        utils.warn('Brewblox now uses a new history database.')
        utils.warn('To migrate your data, run:')
        utils.warn('')
        utils.warn('    brewblox-ctl database from-influxdb')
        utils.warn('')


@cli.command()
def libs():
    """Reinstall local libs."""
    utils.confirm_mode()
    utils.load_ctl_lib()


@cli.command()
@click.option('--update-ctl/--no-update-ctl',
              default=True,
              help='Update brewblox-ctl.')
@click.option('--update-ctl-done',
              is_flag=True,
              hidden=True)
@click.option('--pull/--no-pull',
              default=True,
              help='Update docker service images.')
@click.option('--update-system/--no-update-system',
              default=True,
              help='Update Apt system packages. Skipped for systems without Apt.')
@click.option('--migrate/--no-migrate',
              default=True,
              help='Migrate Brewblox configuration and service settings.')
@click.option('--prune/--no-prune',
              default=True,
              help='Remove unused docker images.')
@click.option('--from-version',
              default='0.0.0',
              envvar=const.CFG_VERSION_KEY,
              help='[ADVANCED] Override current version number.')
def update(update_ctl, update_ctl_done, pull, update_system, migrate, prune, from_version):
    """Download and apply updates.

    This is the one-stop-shop for updating your Brewblox install.
    You can use any of the options to fine-tune the update by enabling or disabling subroutines.

    By default, all options are enabled.

    --update-ctl/--no-update-ctl: Whether to download and install new versions of
    of brewblox-ctl and brewblox-ctl lib. If this flag is set, update will download the new version
    and then restart itself. This way, the migrate is done with the latest version of brewblox-ctl.

    If you're using dry run mode, you'll notice the hidden option --update-ctl-done.
    You can use it to watch the rest of the update: it\'s a flag to avoid endless loops.

    --pull/--no-pull. Whether to pull docker images.
    This is useful if any of your services is using a local image (not from Docker Hub).

    --update-system/--no-update-system determines whether

    --migrate/--no-migrate. Updates regularly require changes to configuration.
    Required changes are applied here.

    --prune/--no-prune. Updates to docker images can leave unused old versions
    on your system. These can be pruned to free up disk space.
    This includes all images and volumes on your system, and not just those created by Brewblox.

    \b
    Steps:
        - Check whether any system fixes must be applied.
        - Update brewblox-ctl and brewblox-ctl libs.
        - Stop services.
        - Update Avahi config.
        - Update system packages.
        - Migrate configuration files.
        - Pull Docker images.
        - Prune unused Docker images and volumes.
        - Start services.
        - Migrate service configuration.
        - Write version number to .env file.
    """
    utils.check_config()
    utils.confirm_mode()
    sudo = utils.optsudo()

    prev_version = StrictVersion(from_version)

    check_version(prev_version)
    check_sudo_install()
    check_path()

    if update_ctl and not update_ctl_done:
        utils.info('Updating brewblox-ctl...')
        utils.pip_install('brewblox-ctl')
        utils.info('Updating brewblox-ctl lib...')
        utils.load_ctl_lib()
        # Restart ctl - we just replaced the source code
        sh(' '.join([const.PY, *const.ARGS, '--update-ctl-done']))
        return

    utils.info('Stopping services...')
    sh(f'{sudo}docker-compose down')

    if update_system:
        utils.update_system_packages()

    if migrate:
        downed_migrate(prev_version)

    if pull:
        utils.info('Pulling docker images...')
        sh(f'{sudo}docker-compose pull')

    if prune:
        utils.info('Pruning unused images...')
        sh(f'{sudo}docker image prune -f > /dev/null')
        utils.info('Pruning unused volumes...')
        sh(f'{sudo}docker volume prune -f > /dev/null')

    utils.info('Starting services...')
    sh(f'{sudo}docker-compose up -d')

    if migrate:
        upped_migrate(prev_version)
        utils.info(f'Configuration version: {prev_version} -> {const.CURRENT_VERSION}')
        utils.setenv(const.CFG_VERSION_KEY, const.CURRENT_VERSION)
