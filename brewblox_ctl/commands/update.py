"""
Migration scripts
"""

from subprocess import CalledProcessError
import click
from packaging.version import Version

from brewblox_ctl import actions, click_helpers, const, migration, utils


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Global command group"""


def check_version(prev_version: Version):
    """Verify that the previous version is sane and sensible"""
    if prev_version == Version('0.0.0'):
        utils.error('This configuration was never set up. Please run brewblox-ctl install first')
        raise SystemExit(1)

    if prev_version > Version(const.CFG_VERSION):
        utils.error(
            'Your system is running a version newer than the selected release. '
            + 'This may be due to switching release tracks.'
            + 'You can use the --from-version flag if you know what you are doing.'
        )
        raise SystemExit(1)


def bind_localtime():
    shared_compose = utils.read_shared_compose()
    compose = utils.read_compose()

    changed = False
    localtime_volume_str = '/etc/localtime:/etc/localtime:ro'
    localtime_volume = {
        'type': 'bind',
        'source': '/etc/localtime',
        'target': '/etc/localtime',
        'read_only': True,
    }

    for name, service in compose['services'].items():
        name: str
        service: dict

        if name in shared_compose['services']:
            continue

        volumes = service.get('volumes', [])
        if localtime_volume in volumes:
            continue
        if localtime_volume_str in volumes:
            continue

        changed = True
        utils.info(f'Mounting localtime in `{name}` service ...')
        volumes.append(localtime_volume.copy())
        service['volumes'] = volumes

    if changed:
        utils.write_compose(compose)


def bind_spark_backup():
    compose = utils.read_compose()

    changed = False
    backup_volume = {
        'type': 'bind',
        'source': './spark/backup',
        'target': '/app/backup',
    }

    for name, service in compose['services'].items():
        name: str
        service: dict

        if not service.get('image', '').startswith('ghcr.io/brewblox/brewblox-devcon-spark'):
            continue

        volumes = service.get('volumes', [])
        present = False
        for volume in volumes:
            if (isinstance(volume, str) and volume.endswith(':/app/backup')) or (
                isinstance(volume, dict) and volume.get('target') == '/app/backup'
            ):
                present = True
                break

        if present:
            continue

        changed = True
        utils.info(f'Mounting backup volume in `{name}` service ...')
        volumes.append(backup_volume.copy())
        service['volumes'] = volumes

    if changed:
        utils.write_compose(compose)


def downed_migrate(prev_version):
    """Migration commands to be executed without any running services"""
    actions.make_dotenv(version=prev_version)
    actions.make_config_dirs()
    actions.make_tls_certificates()
    actions.make_traefik_config()
    actions.make_shared_compose()
    actions.make_compose()
    actions.make_udev_rules()
    actions.edit_avahi_config()

    if prev_version < Version('0.8.0'):
        migration.migrate_ghcr_images()

    if prev_version < Version('0.9.0'):
        migration.migrate_tilt_images()

    if prev_version < Version('0.11.0'):
        utils.sh('rm -f ./traefik/traefik-cert.yaml')

    # Not related to a specific release
    bind_localtime()
    bind_spark_backup()


def upped_migrate(prev_version):
    """Migration commands to be executed after the services have been started"""
    if prev_version < Version('0.7.0'):
        utils.warn('')
        utils.warn('Brewblox now uses a new history database.')
        utils.warn('To migrate your data, run:')
        utils.warn('')
        utils.warn('    brewblox-ctl database from-influxdb')
        utils.warn('')


@cli.command()
@click.option('--update-ctl/--no-update-ctl', default=True, help='Update brewblox-ctl.')
@click.option('--update-ctl-done', is_flag=True, hidden=True)
@click.option('--pull/--no-pull', default=True, help='Update docker service images.')
@click.option('--migrate/--no-migrate', default=True, help='Migrate Brewblox configuration and service settings.')
@click.option('--prune/--no-prune', default=True, help='Remove unused docker images.')
@click.option(
    '--from-version',
    default='0.0.0',
    envvar=const.ENV_KEY_CFG_VERSION,
    help='[ADVANCED] Override version number of active configuration.',
)
def update(update_ctl, update_ctl_done, pull, migrate, prune, from_version):
    r"""Download and apply updates.

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
    utils.cache_sudo()

    if not utils.file_exists(const.CONFIG_FILE):
        migration.migrate_env_config()

    sudo = utils.optsudo()
    config = utils.get_config()

    prev_version = Version(from_version)
    shipped_version = Version(const.CFG_VERSION)
    check_version(prev_version)

    if not update_ctl_done:
        utils.info(f'Starting update for brewblox {config.release} ...')

    if update_ctl and not update_ctl_done:
        utils.info('Updating brewblox-ctl ...')
        actions.install_ctl_package()
        # Restart update - we just replaced the source code
        utils.sh(' '.join(['exec', const.CLI, *const.ARGS[1:], '--update-ctl-done']))
        return

    if update_ctl:
        actions.make_ctl_entrypoint()

    actions.install_compose_plugin()

    utils.info('Stopping services ...')
    utils.docker_down()

    if config.system.apt_upgrade:
        actions.apt_upgrade()

    if migrate:
        downed_migrate(prev_version)

    if pull:
        utils.info('Pulling docker images ...')
        utils.sh(f'{sudo}docker compose pull')

    if prune:
        utils.info('Pruning unused images ...')
        utils.sh(f'{sudo}docker image prune -f > /dev/null')
        utils.info('Pruning unused volumes ...')
        utils.sh(f'{sudo}docker volume prune -f > /dev/null')

    utils.info('Starting services ...')
    utils.docker_up()

    if migrate:
        upped_migrate(prev_version)
        utils.info(f'Configuration version: {prev_version} -> {shipped_version}')
        utils.setenv(const.ENV_KEY_CFG_VERSION, const.CFG_VERSION)


@cli.command()
def update_ctl():
    """Download and update brewblox-ctl itself."""
    utils.confirm_mode()
    actions.install_ctl_package()
    actions.make_ctl_entrypoint()
