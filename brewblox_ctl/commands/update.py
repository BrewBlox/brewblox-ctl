"""
Migration scripts
"""

import click
from packaging.version import Version

from brewblox_ctl import actions, click_helpers, const, migration, sh, utils


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Global command group"""


def check_version(prev_version: Version):
    """Verify that the previous version is sane and sensible"""
    if prev_version == Version('0.0.0'):
        utils.error('This configuration was never set up. Please run brewblox-ctl setup first')
        raise SystemExit(1)

    if prev_version > Version(const.CFG_VERSION):
        utils.error('Your system is running a version newer than the selected release. ' +
                    'This may be due to switching release tracks.' +
                    'You can use the --from-version flag if you know what you are doing.')
        raise SystemExit(1)


def check_dirs():
    utils.info('Checking data directories...')
    dirs = [
        './traefik',
        './redis',
        './victoria',
        './mosquitto',
        './spark/backup',
    ]

    sh('mkdir -p ' + ' '.join(dirs))
    sh('sudo chown --reference=./ ' + ' '.join(dirs))


def apply_config_files():
    """Apply system-defined configuration from config dir"""
    utils.info('Updating configuration files...')
    sh('touch ./mosquitto/externals.passwd')  # only make sure it exists
    sh(f'cp -f {const.DIR_DEPLOYED_CONFIG}/traefik-cert.yaml ./traefik/')
    sh(f'cp -f {const.DIR_DEPLOYED_CONFIG}/docker-compose.shared.yml ./')
    shared_cfg = utils.read_shared_compose()
    usr_cfg = utils.read_compose()

    usr_cfg['version'] = shared_cfg['version']
    utils.write_compose(usr_cfg)


def check_env_vars():
    utils.info('Checking .env variables...')
    utils.defaultenv()


def bind_localtime():
    shared_cfg = utils.read_shared_compose()
    usr_cfg = utils.read_compose()

    changed = False
    localtime_volume_str = '/etc/localtime:/etc/localtime:ro'
    localtime_volume = {
        'type': 'bind',
        'source': '/etc/localtime',
        'target': '/etc/localtime',
        'read_only': True,
    }

    for (name, service) in usr_cfg['services'].items():
        name: str
        service: dict

        if name in shared_cfg['services']:
            continue

        volumes = service.get('volumes', [])
        if localtime_volume in volumes:
            continue
        if localtime_volume_str in volumes:
            continue

        changed = True
        utils.info(f'Mounting localtime in `{name}` service...')
        volumes.append(localtime_volume.copy())
        service['volumes'] = volumes

    if changed:
        utils.write_compose(usr_cfg)


def bind_spark_backup():
    usr_cfg = utils.read_compose()

    changed = False
    backup_volume = {
        'type': 'bind',
        'source': './spark/backup',
        'target': '/app/backup',
    }

    for (name, service) in usr_cfg['services'].items():
        name: str
        service: dict

        if not service.get('image', '').startswith('ghcr.io/brewblox/brewblox-devcon-spark'):
            continue

        volumes = service.get('volumes', [])
        present = False
        for volume in volumes:
            if (isinstance(volume, str) and volume.endswith(':/app/backup')) \
                    or (isinstance(volume, dict) and volume.get('target') == '/app/backup'):
                present = True
                break

        if present:
            continue

        changed = True
        utils.info(f'Mounting backup volume in `{name}` service...')
        volumes.append(backup_volume.copy())
        service['volumes'] = volumes

    if changed:
        utils.write_compose(usr_cfg)


def downed_migrate(prev_version):
    """Migration commands to be executed without any running services"""
    check_dirs()
    apply_config_files()
    actions.add_particle_udev_rules()
    actions.edit_avahi_config()

    if prev_version < Version('0.3.0'):
        migration.migrate_compose_split()

    if prev_version < Version('0.6.0'):
        migration.migrate_compose_datastore()

    if prev_version < Version('0.6.1'):
        migration.migrate_ipv6_fix()

    if prev_version < Version('0.8.0'):
        migration.migrate_ghcr_images()

    # Not related to a specific release
    check_env_vars()
    bind_localtime()
    bind_spark_backup()


def upped_migrate(prev_version):
    """Migration commands to be executed after the services have been started"""
    if prev_version < Version('0.6.0'):
        utils.warn('')
        utils.warn('Brewblox now uses a new configuration database.')
        utils.warn('To migrate your data, run:')
        utils.warn('')
        utils.warn('    brewblox-ctl database from-couchdb')
        utils.warn('')

    if prev_version < Version('0.7.0'):
        utils.warn('')
        utils.warn('Brewblox now uses a new history database.')
        utils.warn('To migrate your data, run:')
        utils.warn('')
        utils.warn('    brewblox-ctl database from-influxdb')
        utils.warn('')


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
@click.option('--update-system-packages/--no-update-system-packages',
              default=True,
              envvar=const.ENV_KEY_UPDATE_SYSTEM_PACKAGES,
              help='Update system packages.')
@click.option('--migrate/--no-migrate',
              default=True,
              help='Migrate Brewblox configuration and service settings.')
@click.option('--prune/--no-prune',
              default=True,
              help='Remove unused docker images.')
@click.option('--from-version',
              default='0.0.0',
              envvar=const.ENV_KEY_CFG_VERSION,
              help='[ADVANCED] Override version number of active configuration.')
def update(update_ctl, update_ctl_done, pull, update_system_packages, migrate, prune, from_version):
    """Download and apply updates.

    This is the one-stop-shop for updating your Brewblox install.
    You can use any of the options to fine-tune the update by enabling or disabling subroutines.

    By default, all options are enabled.

    --update-ctl/--no-update-ctl: Whether to download and install new versions of
    of brewblox-ctl. If this flag is set, update will download the new version
    and then restart itself. This way, the migrate is done with the latest version of brewblox-ctl.

    If you're using dry run mode, you'll notice the hidden option --update-ctl-done.
    You can use it to watch the rest of the update: it\'s a flag to avoid endless loops.

    --pull/--no-pull. Whether to pull docker images.
    This is useful if any of your services is using a local image (not from Docker Hub).

    --update-system-packages/--no-update-system-packages determines whether generic system packages
    are updated during the brewblox-ctl update.

    --migrate/--no-migrate. Updates regularly require changes to configuration.
    Required changes are applied here.

    --prune/--no-prune. Updates to docker images can leave unused old versions
    on your system. These can be pruned to free up disk space.
    This includes all images and volumes on your system, and not just those created by Brewblox.

    \b
    Steps:
        - Check whether any system fixes must be applied.
        - Update brewblox-ctl.
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

    prev_version = Version(from_version)
    shipped_version = Version(const.CFG_VERSION)
    check_version(prev_version)

    if not update_ctl_done:
        utils.info(f'Starting update for brewblox {utils.getenv(const.ENV_KEY_RELEASE)}...')

    if update_ctl and not update_ctl_done:
        utils.info('Updating brewblox-ctl...')
        utils.pip_install('pip')
        actions.install_ctl_package()
        # Restart update - we just replaced the source code
        sh(' '.join([const.CLI, *const.ARGS[1:], '--update-ctl-done']))
        return

    if update_ctl:
        actions.uninstall_old_ctl_package()
        actions.deploy_ctl_wrapper()

    actions.check_compose_plugin()

    utils.info('Stopping services...')
    sh(f'{sudo}docker compose down')

    if update_system_packages:
        actions.update_system_packages()

    if migrate:
        downed_migrate(prev_version)

    if pull:
        utils.info('Pulling docker images...')
        sh(f'{sudo}docker compose pull')

    if prune:
        utils.info('Pruning unused images...')
        sh(f'{sudo}docker image prune -f > /dev/null')
        utils.info('Pruning unused volumes...')
        sh(f'{sudo}docker volume prune -f > /dev/null')

    utils.info('Starting services...')
    sh(f'{sudo}docker compose up -d')

    if migrate:
        upped_migrate(prev_version)
        utils.info(f'Configuration version: {prev_version} -> {shipped_version}')
        utils.setenv(const.ENV_KEY_CFG_VERSION, const.CFG_VERSION)


@cli.command()
def update_ctl():
    """Download and update brewblox-ctl itself."""
    utils.confirm_mode()
    actions.install_ctl_package()
    actions.uninstall_old_ctl_package()
    actions.deploy_ctl_wrapper()
