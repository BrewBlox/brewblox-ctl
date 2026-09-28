"""
Tests brewblox_ctl.commands.update
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from subprocess import CalledProcessError
from typing import List
from unittest.mock import Mock, sentinel

import httpretty
import pytest
from packaging.version import Version
from pytest_mock import MockerFixture

from brewblox_ctl import const, migration, testing, utils
from brewblox_ctl.commands import update
from brewblox_ctl.testing import invoke

TESTED = update.__name__


class DummyError(Exception):
    pass


@pytest.fixture(autouse=True)
def m_actions(mocker: MockerFixture):
    m = mocker.patch(TESTED + '.actions', autospec=True)
    return m


@pytest.fixture(autouse=True)
def m_migration(mocker: MockerFixture):
    m = mocker.patch(TESTED + '.migration', autospec=True)
    return m


@pytest.fixture(autouse=True)
def m_utils(m_read_compose: Mock, m_read_shared_compose: Mock, m_getenv: Mock, m_user_home_exists: Mock):
    m_getenv.return_value = '/usr/local/bin:/home/pi/.local/bin'
    m_user_home_exists.return_value = False  # Tested explicitly
    m_read_compose.side_effect = lambda: {
        'services': {
            'spark-one': {
                'image': 'ghcr.io/brewblox/brewblox-devcon-spark:rpi-edge',
                'depends_on': ['datastore'],
            },
            'plaato': {
                'image': 'brewblox/brewblox-plaato:rpi-edge',
            },
            'mcguffin': {
                'image': 'brewblox/brewblox-mcguffin:${BREWBLOX_RELEASE}',
            },
        }
    }
    m_read_shared_compose.side_effect = lambda: {'services': {}}


def test_update_ctl(m_actions: Mock, m_sh: Mock):
    invoke(update.update_ctl)
    m_actions.install_ctl_package.assert_called_once_with()
    m_actions.make_ctl_entrypoint.assert_called_once_with()
    m_sh.assert_not_called()


def test_update(m_file_exists: Mock, m_getenv: Mock, m_migration: Mock):
    config = utils.get_config()
    m_file_exists.add_existing_files(const.CONFIG_FILE)

    invoke(update.update, '--from-version 0.0.1', input='\n')
    invoke(update.update, f'--from-version {const.CFG_VERSION} --no-update-ctl --prune')
    invoke(update.update, '--from-version 0.0.1 --update-ctl-done --prune')
    invoke(update.update, _err=True)
    invoke(update.update, '--from-version 0.0.0 --prune', _err=True)
    invoke(update.update, '--from-version 9001.0.0 --prune', _err=True)
    invoke(update.update, '--from-version 0.0.1 --no-pull --no-update-ctl' + ' --no-migrate --no-prune')

    m_getenv.return_value = None
    invoke(update.update, f'--from-version {const.CFG_VERSION} --no-update-ctl --prune')

    m_file_exists.clear_existing_files()
    config.system.apt_upgrade = False
    invoke(update.update, '--from-version 0.0.1 --no-update-ctl')
    assert m_migration.migrate_env_config.call_count == 1


def test_update_old_docker(m_file_exists: Mock, m_actions: Mock, m_sh: Mock):
    m_file_exists.add_existing_files(const.CONFIG_FILE)
    m_actions.check_docker_version.return_value = False

    invoke(update.update, f'--from-version {const.CFG_VERSION} --no-update-ctl', _err=True)

    # The services are started again, without migrating or pulling
    cmds = [c.args[0] for c in m_sh.call_args_list]
    assert any('compose up' in cmd for cmd in cmds)
    assert not any('compose pull' in cmd for cmd in cmds)
    m_actions.make_compose.assert_not_called()


def test_update_pull_error(m_file_exists: Mock, m_sh: Mock, m_setenv: Mock):
    m_file_exists.add_existing_files(const.CONFIG_FILE)

    def sh(cmd, *args, **kwargs):
        if 'compose pull' in cmd:
            raise CalledProcessError(1, cmd)
        return testing.check_sudo(cmd, *args, **kwargs)

    m_sh.side_effect = sh
    invoke(update.update, f'--from-version {const.CFG_VERSION} --no-update-ctl --prune', _err=True)

    # The services are started again, and the update stops
    cmds = [c.args[0] for c in m_sh.call_args_list]
    pulled = next(i for i, cmd in enumerate(cmds) if 'compose pull' in cmd)
    assert any('compose up' in cmd for cmd in cmds[pulled:])
    assert not any('prune' in cmd for cmd in cmds)
    assert const.ENV_KEY_CFG_VERSION not in [c.args[0] for c in m_setenv.call_args_list]


def test_update_pull_error_up_fails(m_file_exists: Mock, m_sh: Mock, m_error: Mock):
    # A new image is missing, so the services cannot start either: the update still says it did not finish
    m_file_exists.add_existing_files(const.CONFIG_FILE)

    def sh(cmd, *args, **kwargs):
        if 'compose pull' in cmd or 'compose up' in cmd:
            raise CalledProcessError(1, cmd)
        return testing.check_sudo(cmd, *args, **kwargs)

    m_sh.side_effect = sh
    result = invoke(update.update, f'--from-version {const.CFG_VERSION} --no-update-ctl --prune', _err=True)

    assert result.exit_code == 1
    m_error.assert_called_with('The update did not finish. Fix the problem above, and run brewblox-ctl update again.')


def test_warn_traefik_overrides(
    m_file_exists: Mock,
    m_read_compose: Mock,
    m_read_yaml: Mock,
    m_warn: Mock,
    m_get_config,  # autouse fixture returns config object
):
    # Ensure brewblox.yml exists to skip migrate_env_config
    m_file_exists.add_existing_files(const.CONFIG_FILE, const.COMPOSE_FILE, 'extra-compose.yml')

    # docker-compose.yml with custom traefik image v2
    m_read_compose.side_effect = lambda: {
        'services': {
            'traefik': {'image': 'traefik:2.10'},
        }
    }

    # extra compose file with traefik service too
    def read_yaml_side_effect(path=None):
        if path == 'extra-compose.yml':
            return {'services': {'traefik': {'image': 'traefik:3.5'}}}
        return {}

    m_read_yaml.side_effect = read_yaml_side_effect

    # Non-default static/dynamic paths
    cfg = m_get_config
    cfg.compose.files = ['docker-compose.shared.yml', 'docker-compose.yml', 'extra-compose.yml']
    cfg.traefik.static_config_file = '/config/custom-traefik.yml'
    cfg.traefik.dynamic_config_dir = '/config/custom-dynamic'

    # Run update without side-effects
    invoke(
        update.update,
        f'--from-version {const.CFG_VERSION} --no-update-ctl --no-pull --no-prune --no-migrate',
    )

    # We should have emitted multiple warnings
    warn_msgs = [str(call.args[0]) for call in m_warn.call_args_list]
    assert any('docker-compose.yml overrides the Traefik image' in m for m in warn_msgs)
    assert any('brewblox.yml sets traefik.static_config_file' in m for m in warn_msgs)
    assert any('brewblox.yml sets traefik.dynamic_config_dir' in m for m in warn_msgs)
    assert any('extra-compose.yml overrides the traefik service' in m for m in warn_msgs)


def test_warn_traefik_branches(
    m_file_exists: Mock,
    m_read_compose: Mock,
    m_warn: Mock,
    m_get_config,
):
    # Only default files exist; add a non-existent extra file to trigger file-exists=false branch
    m_file_exists.add_existing_files(const.CONFIG_FILE, const.COMPOSE_FILE)

    # docker-compose.yml with traefik defined but no image -> triggers generic override warning
    m_read_compose.side_effect = lambda: {'services': {'traefik': {}}}

    cfg = m_get_config
    cfg.compose.files = ['docker-compose.shared.yml', 'docker-compose.yml', 'nonexistent.yml']
    cfg.traefik.static_config_file = '/config/traefik.yml'
    cfg.traefik.dynamic_config_dir = '/config/dynamic'

    invoke(
        update.update,
        f'--from-version {const.CFG_VERSION} --no-update-ctl --no-pull --no-prune --no-migrate',
    )

    warn_msgs = [str(call.args[0]) for call in m_warn.call_args_list]
    assert any('docker-compose.yml overrides the traefik service' in m for m in warn_msgs)


def test_warn_traefik_extra_branches(
    m_file_exists: Mock,
    m_read_compose: Mock,
    m_read_yaml: Mock,
    m_get_config,
):
    # Both default files and two extra files exist
    m_file_exists.add_existing_files(
        const.CONFIG_FILE,
        const.COMPOSE_FILE,
        'extra-a.yml',
        'extra-b.yml',
    )

    # docker-compose.yml without traefik service -> cover branch where traefik_svc is None
    m_read_compose.side_effect = lambda: {'services': {'redis': {}}}

    def read_yaml_side_effect(path=None):
        if path == 'extra-a.yml':
            # Exists but no traefik service -> cover false branch at 248
            return {'services': {'other': {}}}
        if path == 'extra-b.yml':
            # Has traefik with v2 image -> cover branch at 251
            return {'services': {'traefik': {'image': 'traefik:2.10'}}}
        return {}

    m_read_yaml.side_effect = read_yaml_side_effect

    cfg = m_get_config
    cfg.compose.files = [
        'docker-compose.shared.yml',
        'docker-compose.yml',
        'extra-a.yml',
        'extra-b.yml',
    ]

    invoke(
        update.update,
        f'--from-version {const.CFG_VERSION} --no-update-ctl --no-pull --no-prune --no-migrate',
    )


def test_check_version(mocker: MockerFixture):
    mocker.patch(TESTED + '.const.CFG_VERSION', '1.2.3')
    mocker.patch(TESTED + '.SystemExit', DummyError)

    update.check_version(Version('1.2.2'))

    with pytest.raises(DummyError):
        update.check_version(Version('0.0.0'))

    with pytest.raises(DummyError):
        update.check_version(Version('1.3.0'))


def test_bind_localtime(m_read_compose: Mock, m_write_compose: Mock):
    m_read_compose.side_effect = lambda: {
        'version': '3.7',
        'services': {
            'spark-one': {
                'image': 'ghcr.io/brewblox/brewblox-devcon-spark:rpi-edge',
            },
            'spark-two': {'image': 'ghcr.io/brewblox/brewblox-devcon-spark:rpi-edge', 'volumes': ['/data:/data']},
            'plaato': {'image': 'brewblox/brewblox-plaato:rpi-edge', 'volumes': ['/etc/localtime:/etc/localtime:ro']},
            'mcguffin': {
                'image': 'brewblox/brewblox-mcguffin:${BREWBLOX_RELEASE}',
                'volumes': [
                    {
                        'type': 'bind',
                        'source': '/etc/localtime',
                        'target': '/etc/localtime',
                        'read_only': True,
                    }
                ],
            },
        },
    }

    update.bind_localtime()
    m_write_compose.assert_called_once_with(
        {
            'version': '3.7',
            'services': {
                'spark-one': {
                    'image': 'ghcr.io/brewblox/brewblox-devcon-spark:rpi-edge',
                    'volumes': [
                        {
                            'type': 'bind',
                            'source': '/etc/localtime',
                            'target': '/etc/localtime',
                            'read_only': True,
                        }
                    ],
                },
                'spark-two': {
                    'image': 'ghcr.io/brewblox/brewblox-devcon-spark:rpi-edge',
                    'volumes': [
                        '/data:/data',
                        {
                            'type': 'bind',
                            'source': '/etc/localtime',
                            'target': '/etc/localtime',
                            'read_only': True,
                        },
                    ],
                },
                'plaato': {
                    'image': 'brewblox/brewblox-plaato:rpi-edge',
                    'volumes': ['/etc/localtime:/etc/localtime:ro'],
                },
                'mcguffin': {
                    'image': 'brewblox/brewblox-mcguffin:${BREWBLOX_RELEASE}',
                    'volumes': [
                        {
                            'type': 'bind',
                            'source': '/etc/localtime',
                            'target': '/etc/localtime',
                            'read_only': True,
                        }
                    ],
                },
            },
        }
    )


def test_bind_spark_backup(m_read_compose: Mock, m_write_compose: Mock):
    m_read_compose.side_effect = lambda: {
        'version': '3.7',
        'services': {
            'spark-one': {
                'image': 'ghcr.io/brewblox/brewblox-devcon-spark:rpi-edge',
            },
            'spark-two': {'image': 'ghcr.io/brewblox/brewblox-devcon-spark:rpi-edge', 'volumes': ['/data:/data']},
            'spark-three': {
                'image': 'ghcr.io/brewblox/brewblox-devcon-spark:rpi-edge',
                'volumes': [
                    {
                        'type': 'bind',
                        'source': './custom/backup/dir',
                        'target': '/app/backup',
                    }
                ],
            },
            'plaato': {'image': 'brewblox/brewblox-plaato:rpi-edge', 'volumes': ['/etc/localtime:/etc/localtime:ro']},
            'mcguffin': {
                'image': 'brewblox/brewblox-mcguffin:${BREWBLOX_RELEASE}',
                'volumes': [
                    {
                        'type': 'bind',
                        'source': '/etc/localtime',
                        'target': '/etc/localtime',
                        'read_only': True,
                    }
                ],
            },
        },
    }

    update.bind_spark_backup()
    m_write_compose.assert_called_once_with(
        {
            'version': '3.7',
            'services': {
                'spark-one': {
                    'image': 'ghcr.io/brewblox/brewblox-devcon-spark:rpi-edge',
                    'volumes': [
                        {
                            'type': 'bind',
                            'source': './spark/backup',
                            'target': '/app/backup',
                        }
                    ],
                },
                'spark-two': {
                    'image': 'ghcr.io/brewblox/brewblox-devcon-spark:rpi-edge',
                    'volumes': [
                        '/data:/data',
                        {
                            'type': 'bind',
                            'source': './spark/backup',
                            'target': '/app/backup',
                        },
                    ],
                },
                'spark-three': {
                    'image': 'ghcr.io/brewblox/brewblox-devcon-spark:rpi-edge',
                    'volumes': [
                        {
                            'type': 'bind',
                            'source': './custom/backup/dir',
                            'target': '/app/backup',
                        }
                    ],
                },
                'plaato': {
                    'image': 'brewblox/brewblox-plaato:rpi-edge',
                    'volumes': ['/etc/localtime:/etc/localtime:ro'],
                },
                'mcguffin': {
                    'image': 'brewblox/brewblox-mcguffin:${BREWBLOX_RELEASE}',
                    'volumes': [
                        {
                            'type': 'bind',
                            'source': '/etc/localtime',
                            'target': '/etc/localtime',
                            'read_only': True,
                        }
                    ],
                },
            },
        }
    )


def test_bind_noop(m_read_shared_compose: Mock, m_read_compose: Mock, m_write_compose: Mock):
    m_read_shared_compose.side_effect = lambda: {
        'version': '3.7',
        'services': {
            'redis': {
                'image': 'redis:6.0',
            },
        },
    }
    m_read_compose.side_effect = lambda: {
        'version': '3.7',
        'services': {
            'redis': {
                'image': 'redis:6.0',
            },
        },
    }

    update.bind_localtime()
    update.bind_spark_backup()
    m_write_compose.assert_not_called()


# History migration (configuration version 0.12.0)

UPDATE_ARGS = '--no-update-ctl --no-pull --no-prune'
MOVE_CMD = 'mv ./victoria ./victoria-legacy'


@pytest.fixture
def update_log(m_sh: Mock, m_actions: Mock, m_migration: Mock, m_setenv: Mock) -> List[str]:
    """
    Records the shell commands, generated files and history steps of the update, in order.
    The history steps return `sentinel.legacy_history` as prepared history.
    """
    log = []

    def sh(cmd, *args, **kwargs):
        log.append(cmd)
        return testing.check_sudo(cmd, *args, **kwargs)

    def record(name, result=None):
        def side_effect(*args, **kwargs):
            log.append(name)
            return result

        return side_effect

    m_sh.side_effect = sh
    for name in ['make_dotenv', 'make_config_dirs', 'make_shared_compose', 'make_compose', 'apt_upgrade']:
        getattr(m_actions, name).side_effect = record(name)
    m_migration.prepare_history_update.side_effect = record('prepare_history_update', sentinel.legacy_history)
    m_migration.migrate_history_after_update.side_effect = record('migrate_history_after_update')
    m_setenv.side_effect = record('setenv')
    return log


@pytest.fixture
def m_real_move(m_migration: Mock) -> Mock:
    """The real predicate and move: the rename depends on the files and configuration"""
    m_migration.history_move_pending.side_effect = migration.history_move_pending
    m_migration.move_legacy_history.side_effect = migration.move_legacy_history
    return m_migration


def index_of(log: List[str], part: str) -> int:
    return next(i for i, entry in enumerate(log) if part in entry)


def test_update_moves_legacy_history(update_log: List[str], m_real_move: Mock, m_file_exists: Mock):
    """The rename comes before the new configuration: it must not open the old history"""
    m_file_exists.add_existing_files(const.CONFIG_FILE, './victoria')

    invoke(update.update, f'--from-version 0.11.0 {UPDATE_ARGS}')

    log = update_log
    assert log.count(MOVE_CMD) == 1
    move = log.index(MOVE_CMD)
    # Services are stopped first
    assert index_of(log, 'compose down') < move
    # The new configuration and the fresh databases come after it
    assert move < log.index('make_dotenv')
    assert move < log.index('make_config_dirs')
    assert move < log.index('make_shared_compose')
    assert move < log.index('make_compose')
    assert move < index_of(log, 'compose up')
    m_real_move.move_legacy_history.assert_called_once_with()


@pytest.mark.parametrize(
    'version, files',
    [
        # Moved by an update that did not finish
        ('0.11.0', ['./victoria', './victoria-legacy']),
        ('0.11.0', ['./victoria', './victoria-dense', './victoria-legacy']),
        # The dense database exists: ./victoria is the long-term database (a restored older .env)
        ('0.11.0', ['./victoria', './victoria-dense']),
        # No history
        ('0.11.0', []),
        ('0.11.0', ['./victoria-dense']),
        # Already at 0.12.0
        ('0.12.0', ['./victoria']),
        (const.CFG_VERSION, ['./victoria']),
    ],
)
def test_update_no_move(
    update_log: List[str],
    m_real_move: Mock,
    m_file_exists: Mock,
    version: str,
    files: List[str],
):
    m_file_exists.add_existing_files(const.CONFIG_FILE, *files)

    invoke(update.update, f'--from-version {version} {UPDATE_ARGS}')

    assert not any(entry.startswith('mv ') for entry in update_log)
    m_real_move.move_legacy_history.assert_not_called()
    # The update itself went on
    assert 'make_shared_compose' in update_log


def test_update_no_migrate_no_move(update_log: List[str], m_real_move: Mock, m_file_exists: Mock):
    m_file_exists.add_existing_files(const.CONFIG_FILE, './victoria')

    invoke(update.update, f'--from-version 0.11.0 {UPDATE_ARGS} --no-migrate')

    assert not any(entry.startswith('mv ') for entry in update_log)
    assert 'make_shared_compose' not in update_log


def test_downed_migrate_order(update_log: List[str], m_real_move: Mock, m_file_exists: Mock):
    m_file_exists.add_existing_files(const.CONFIG_FILE, './victoria')

    update.downed_migrate(Version('0.11.0'))

    assert update_log[0] == MOVE_CMD
    assert update_log.index('make_dotenv') == 1


def test_update_prepares_history(update_log: List[str], m_migration: Mock, m_file_exists: Mock):
    """The history migration is checked before anything changes, and offered once the services run"""
    m_file_exists.add_existing_files(const.CONFIG_FILE)

    invoke(update.update, f'--from-version 0.11.0 {UPDATE_ARGS}')

    log = update_log
    m_migration.prepare_history_update.assert_called_once_with(Version('0.11.0'))
    prepare = log.index('prepare_history_update')
    assert prepare < index_of(log, 'compose down')
    assert prepare < log.index('apt_upgrade')
    assert prepare < log.index('make_dotenv')

    # The prepared history is passed on, after the services started
    m_migration.migrate_history_after_update.assert_called_once_with(sentinel.legacy_history)
    assert index_of(log, 'compose up') < log.index('migrate_history_after_update')


def test_update_prepare_abort(
    update_log: List[str],
    m_actions: Mock,
    m_migration: Mock,
    m_file_exists: Mock,
    m_setenv: Mock,
):
    """Aborting at the free-space question leaves everything as it was"""
    m_file_exists.add_existing_files(const.CONFIG_FILE, './victoria')
    m_migration.prepare_history_update.side_effect = SystemExit(1)

    invoke(update.update, f'--from-version 0.11.0 {UPDATE_ARGS}', _err=SystemExit)

    assert not any('compose' in entry for entry in update_log)
    assert not any(entry.startswith('mv ') for entry in update_log)
    m_migration.move_legacy_history.assert_not_called()
    m_actions.apt_upgrade.assert_not_called()
    m_actions.make_dotenv.assert_not_called()
    m_actions.make_config_dirs.assert_not_called()
    m_actions.make_shared_compose.assert_not_called()
    m_actions.make_compose.assert_not_called()
    m_migration.migrate_history_after_update.assert_not_called()
    m_setenv.assert_not_called()


def test_update_no_legacy_history(update_log: List[str], m_migration: Mock, m_file_exists: Mock):
    m_file_exists.add_existing_files(const.CONFIG_FILE)
    m_migration.prepare_history_update.side_effect = None
    m_migration.prepare_history_update.return_value = None

    invoke(update.update, f'--from-version 0.11.0 {UPDATE_ARGS}')

    m_migration.prepare_history_update.assert_called_once_with(Version('0.11.0'))
    m_migration.migrate_history_after_update.assert_not_called()


def test_update_no_migrate_history(update_log: List[str], m_migration: Mock, m_file_exists: Mock):
    m_file_exists.add_existing_files(const.CONFIG_FILE, './victoria')

    invoke(update.update, f'--from-version 0.11.0 {UPDATE_ARGS} --no-migrate')

    m_migration.prepare_history_update.assert_not_called()
    m_migration.migrate_history_after_update.assert_not_called()


def test_update_ctl_first(update_log: List[str], m_migration: Mock, m_file_exists: Mock):
    """The updated brewblox-ctl prepares the history migration"""
    m_file_exists.add_existing_files(const.CONFIG_FILE, './victoria')

    invoke(update.update, '--from-version 0.11.0 --no-pull --no-prune')

    assert update_log[-1].startswith('exec ')
    assert 'prepare_history_update' not in update_log
    assert not any('compose' in entry for entry in update_log)
    m_migration.prepare_history_update.assert_not_called()


def test_update_pull_error_no_history_offer(update_log: List[str], m_sh: Mock, m_migration: Mock, m_file_exists: Mock):
    """The update did not finish: the migration is not offered"""
    m_file_exists.add_existing_files(const.CONFIG_FILE)
    record = m_sh.side_effect

    def sh(cmd, *args, **kwargs):
        record(cmd, *args, **kwargs)
        if 'compose pull' in cmd:
            raise CalledProcessError(1, cmd)
        return testing.check_sudo(cmd, *args, **kwargs)

    m_sh.side_effect = sh

    invoke(update.update, '--from-version 0.11.0 --no-update-ctl --no-prune', _err=SystemExit)

    m_migration.prepare_history_update.assert_called_once_with(Version('0.11.0'))
    m_migration.migrate_history_after_update.assert_not_called()
    assert 'setenv' not in update_log


def test_update_old_docker_no_history_offer(update_log: List[str], m_actions: Mock, m_migration: Mock, m_file_exists):
    m_file_exists.add_existing_files(const.CONFIG_FILE, './victoria')
    m_actions.check_docker_version.return_value = False

    invoke(update.update, f'--from-version 0.11.0 {UPDATE_ARGS}', _err=SystemExit)

    m_migration.move_legacy_history.assert_not_called()
    m_migration.migrate_history_after_update.assert_not_called()


def test_upped_migrate(m_migration: Mock):
    update.upped_migrate(Version('0.11.0'))
    update.upped_migrate(Version('0.11.0'), None)
    m_migration.migrate_history_after_update.assert_not_called()
    # Without a migration to offer, the update shows how far the migration is
    assert m_migration.remind_legacy_history.call_count == 2

    update.upped_migrate(Version('0.11.0'), sentinel.legacy_history)
    m_migration.migrate_history_after_update.assert_called_once_with(sentinel.legacy_history)
    assert m_migration.remind_legacy_history.call_count == 2


@pytest.mark.parametrize(
    'version, influxdb, warned',
    [
        ('0.6.0', True, True),
        ('0.6.0', False, False),
        ('0.7.0', True, False),
    ],
)
def test_upped_migrate_influxdb(m_migration: Mock, m_file_exists: Mock, m_warn: Mock, version, influxdb, warned):
    # This version no longer migrates InfluxDB history: the docs point to an older brewblox-ctl
    if influxdb:
        m_file_exists.add_existing_files('./influxdb/')
    update.upped_migrate(Version(version))
    assert m_warn.call_count == (1 if warned else 0)
    if warned:
        m_warn.assert_called_once_with(
            f'This brewblox-ctl does not migrate the InfluxDB history in ./influxdb/: see {update.INFLUXDB_DOCS}'
        )


# The update with the real history migration, in a Brewblox directory with history of before 0.12.0

NOW = datetime(2026, 9, 26, 12, tzinfo=timezone.utc)
MIGRATE_URL = 'http://localhost:9600/history/timeseries/migrate'


def make_partitions(legacy_dir: Path, *months: str):
    for month in months:
        partition = legacy_dir / 'data' / 'small' / month
        partition.mkdir(parents=True)
        (partition / 'part').write_bytes(b'x' * 10000)


@pytest.fixture
def real_history(mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """The real migration module, in a temporary Brewblox directory"""
    monkeypatch.chdir(tmp_path)
    mocker.patch(TESTED + '.migration', migration)
    mocker.patch.object(migration, '_now', return_value=NOW)
    mocker.patch.object(migration, 'sleep')
    return tmp_path


def register_migrate(status: int = 200):
    httpretty.register_uri(httpretty.DELETE, MIGRATE_URL, body='null', status=status)
    httpretty.register_uri(
        httpretty.POST,
        MIGRATE_URL,
        body=json.dumps({'phase': 'seed', 'running': True}),
        adding_headers={'Content-Type': 'application/json'},
    )


def migrate_requests():
    return [(r.method, r.path) for r in httpretty.latest_requests() if '/migrate' in r.path]


@httpretty.activate(allow_net_connect=False)
def test_update_history_legacy(
    real_history: Path, update_log: List[str], m_file_exists: Mock, m_confirm: Mock, m_setenv: Mock
):
    make_partitions(real_history / 'victoria', '2024_01', '2024_02')
    m_file_exists.add_existing_files(const.CONFIG_FILE, './victoria')
    m_confirm.return_value = True
    register_migrate()

    invoke(update.update, f'--from-version 0.11.0 {UPDATE_ARGS}')

    log = update_log
    down = index_of(log, 'compose down')
    move = log.index(MOVE_CMD)
    up = index_of(log, 'compose up')
    assert down < move < log.index('make_shared_compose') < up

    # Discard any earlier state, then start from the first partition
    requests = [r for r in httpretty.latest_requests() if '/migrate' in r.path]
    assert [(r.method, r.path) for r in requests] == [
        ('DELETE', '/history/timeseries/migrate?discard=true'),
        ('POST', '/history/timeseries/migrate'),
    ]
    assert json.loads(requests[1].body) == {
        'source_url': 'http://victoria-legacy:8428/victoria-legacy',
        'earliest': '2024-01-01T00:00:00+00:00',
        'dense_days': 30,
    }
    m_setenv.assert_called_once_with(const.ENV_KEY_CFG_VERSION, const.CFG_VERSION)


@httpretty.activate(allow_net_connect=False)
def test_update_history_legacy_declined(
    real_history: Path, update_log: List[str], m_file_exists: Mock, m_confirm: Mock, m_warn: Mock
):
    make_partitions(real_history / 'victoria', '2024_01')
    m_file_exists.add_existing_files(const.CONFIG_FILE, './victoria')
    # Continue with the update, but do not start the migration
    m_confirm.side_effect = lambda question, *args, **kwargs: 'continue' in question
    register_migrate()

    invoke(update.update, f'--from-version 0.11.0 {UPDATE_ARGS}')

    assert MOVE_CMD in update_log
    assert migrate_requests() == [('DELETE', '/history/timeseries/migrate?discard=true')]
    m_warn.assert_any_call(f'    {migration.MIGRATE_CMD}')


@httpretty.activate(allow_net_connect=False)
def test_update_history_discard_fails(
    real_history: Path, update_log: List[str], m_file_exists: Mock, m_confirm: Mock, m_warn: Mock, m_setenv: Mock
):
    """Without the discard, nothing starts. The rest of the update goes on."""
    make_partitions(real_history / 'victoria', '2024_01')
    m_file_exists.add_existing_files(const.CONFIG_FILE, './victoria')
    m_confirm.return_value = True
    register_migrate(status=500)

    invoke(update.update, f'--from-version 0.11.0 {UPDATE_ARGS}')

    assert all(method == 'DELETE' for method, _ in migrate_requests())
    # Only the question before the update: the migration is not offered
    m_confirm.assert_called_once_with('Do you want to continue with the update?')
    m_warn.assert_any_call(f'    {migration.DISCARD_CMD}')
    m_warn.assert_any_call(f'    {migration.MIGRATE_CMD}')
    m_setenv.assert_called_once_with(const.ENV_KEY_CFG_VERSION, const.CFG_VERSION)


@httpretty.activate(allow_net_connect=False)
def test_update_history_after_partial_update(
    real_history: Path, update_log: List[str], m_file_exists: Mock, m_confirm: Mock
):
    """An update that moved the history, but did not finish: no second move, and the migration is offered"""
    make_partitions(real_history / 'victoria-legacy', '2025_06')
    m_file_exists.add_existing_files(const.CONFIG_FILE, './victoria', './victoria-dense', './victoria-legacy')
    m_confirm.return_value = True
    register_migrate()

    invoke(update.update, f'--from-version 0.11.0 {UPDATE_ARGS}')

    assert not any(entry.startswith('mv ') for entry in update_log)
    requests = [r for r in httpretty.latest_requests() if '/migrate' in r.path]
    assert [r.method for r in requests] == ['DELETE', 'POST']
    assert json.loads(requests[1].body)['earliest'] == '2025-06-01T00:00:00+00:00'


@httpretty.activate(allow_net_connect=False)
def test_update_history_migration_running(
    real_history: Path, update_log: List[str], m_file_exists: Mock, m_confirm: Mock
):
    """A later update leaves a running migration alone, and shows how far it is"""
    make_partitions(real_history / 'victoria-legacy', '2025_06')
    m_file_exists.add_existing_files(const.CONFIG_FILE, './victoria', './victoria-dense', './victoria-legacy')
    m_confirm.return_value = True
    register_migrate()
    running = {
        'phase': 'walk',
        'running': True,
        'cancelled': False,
        'earliest': 1748736000,
        'sparse_interval': 60,
        'started': 1790583815,
        'chunks_done': 30,
        'chunks_total': 120,
        'last_error': None,
    }
    httpretty.register_uri(
        httpretty.GET, MIGRATE_URL, body=json.dumps(running), adding_headers={'Content-Type': 'application/json'}
    )

    result = invoke(update.update, f'--from-version {const.CFG_VERSION} {UPDATE_ARGS}')

    assert not any(entry.startswith('mv ') for entry in update_log)
    # Only the status: no discard, no start
    assert migrate_requests() == [('GET', '/history/timeseries/migrate')]
    assert '30 of 120 periods done (25%)' in result.stdout
    m_confirm.assert_not_called()


@httpretty.activate(allow_net_connect=False)
def test_update_history_no_space_abort(
    real_history: Path,
    update_log: List[str],
    m_file_exists: Mock,
    m_free_disk_bytes: Mock,
    m_select: Mock,
    m_setenv: Mock,
):
    """Aborting at the free-space question stops the update before anything changed"""
    make_partitions(real_history / 'victoria', '2024_01')
    m_file_exists.add_existing_files(const.CONFIG_FILE, './victoria')
    m_free_disk_bytes.return_value = 2**20
    m_select.return_value = '0'
    register_migrate()

    invoke(update.update, f'--from-version 0.11.0 {UPDATE_ARGS}', _err=SystemExit)

    assert not any('compose' in entry for entry in update_log)
    assert MOVE_CMD not in update_log
    assert 'make_shared_compose' not in update_log
    assert (real_history / 'victoria').is_dir()
    assert migrate_requests() == []
    m_setenv.assert_not_called()


@httpretty.activate(allow_net_connect=False)
def test_update_history_mount_point(
    real_history: Path, update_log: List[str], m_file_exists: Mock, m_is_mount: Mock, m_error: Mock
):
    make_partitions(real_history / 'victoria', '2024_01')
    m_file_exists.add_existing_files(const.CONFIG_FILE, './victoria')
    m_is_mount.return_value = True

    invoke(update.update, f'--from-version 0.11.0 {UPDATE_ARGS}', _err=SystemExit)

    assert not any('compose' in entry for entry in update_log)
    assert MOVE_CMD not in update_log
    assert m_error.call_count > 0


def test_update_history_explained(real_history: Path, update_log: List[str], m_file_exists: Mock, m_confirm: Mock):
    """Before anything changes, the update says why history moves, and asks to continue"""
    make_partitions(real_history / 'victoria', '2024_01')
    m_file_exists.add_existing_files(const.CONFIG_FILE, './victoria')
    m_confirm.return_value = False

    result = invoke(update.update, f'--from-version 0.11.0 {UPDATE_ARGS}', _err=True)

    assert result.exit_code == 1
    assert 'History moves to two databases (configuration version 0.12.0):' in result.stdout
    assert '1. Moves your history to ./victoria-legacy, unchanged.' in result.stdout
    m_confirm.assert_called_once_with('Do you want to continue with the update?')
    # Nothing changed: no pull, no down, no move
    assert not any('docker' in entry or entry.startswith('mv ') for entry in update_log)


def test_update_configuration_version(update_log: List[str], m_file_exists: Mock, m_info: Mock):
    m_file_exists.add_existing_files(const.CONFIG_FILE)
    invoke(update.update, f'--from-version 0.11.0 {UPDATE_ARGS}')
    m_info.assert_any_call(f'Updating the configuration from version 0.11.0 to {const.CFG_VERSION} ...')

    m_info.reset_mock()
    invoke(update.update, f'--from-version {const.CFG_VERSION} {UPDATE_ARGS}')
    assert not any('Updating the configuration' in c.args[0] for c in m_info.call_args_list)
