"""
Tests brewblox_ctl.commands.update
"""

from unittest.mock import Mock

import pytest
from packaging.version import Version
from pytest_mock import MockerFixture

from brewblox_ctl import const, utils
from brewblox_ctl.commands import update
from brewblox_ctl.testing import invoke

TESTED = update.__name__

STORE_URL = 'https://localhost:9600/history/datastore'


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
