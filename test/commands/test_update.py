"""
Tests brewblox_ctl.commands.update
"""

import pytest
from packaging.version import Version

from brewblox_ctl import const
from brewblox_ctl.commands import update
from brewblox_ctl.testing import check_sudo, invoke

TESTED = update.__name__

STORE_URL = 'https://localhost/history/datastore'


class DummyError(Exception):
    pass


@pytest.fixture
def m_actions(mocker):
    m = mocker.patch(TESTED + '.actions', autospec=True)
    return m


@pytest.fixture
def m_utils(mocker):
    m = mocker.patch(TESTED + '.utils', autospec=True)
    m.optsudo.return_value = 'SUDO '
    m.getenv.return_value = '/usr/local/bin:/home/pi/.local/bin'
    m.datastore_url.return_value = STORE_URL
    m.user_home_exists.return_value = False  # Tested explicitly
    m.read_compose.side_effect = lambda: {
        'version': '3.7',
        'services': {
            'spark-one': {
                'image': 'brewblox/brewblox-devcon-spark:rpi-edge',
                'depends_on': ['datastore'],
            },
            'plaato': {
                'image': 'brewblox/brewblox-plaato:rpi-edge',
            },
            'mcguffin': {
                'image': 'brewblox/brewblox-mcguffin:${BREWBLOX_RELEASE}',
            }
        }}
    return m


@pytest.fixture
def m_sh(mocker):
    m = mocker.patch(TESTED + '.sh', autospec=True)
    m.side_effect = check_sudo
    return m


def test_update_ctl(m_actions, m_utils, m_sh):
    invoke(update.update_ctl)
    m_actions.install_ctl_package.assert_called_once_with()
    m_actions.uninstall_old_ctl_package.assert_called_once_with()
    m_actions.deploy_ctl_wrapper.assert_called_once_with()
    m_sh.assert_not_called()


def test_update(m_actions, m_utils, m_sh, mocker):
    mocker.patch(TESTED + '.migration')

    invoke(update.update, '--from-version 0.0.1', input='\n')
    invoke(update.update, f'--from-version {const.CFG_VERSION} --no-update-ctl --prune')
    invoke(update.update, '--from-version 0.0.1 --update-ctl-done --prune')
    invoke(update.update, _err=True)
    invoke(update.update, '--from-version 0.0.0 --prune', _err=True)
    invoke(update.update, '--from-version 9001.0.0 --prune', _err=True)
    invoke(update.update,
           '--from-version 0.0.1 --no-pull --no-update-ctl' +
           ' --no-migrate --no-prune --no-update-system-packages')

    m_utils.getenv.return_value = None
    invoke(update.update, f'--from-version {const.CFG_VERSION} --no-update-ctl --prune')


def test_check_version(m_utils, mocker):
    mocker.patch(TESTED + '.const.CFG_VERSION', '1.2.3')
    mocker.patch(TESTED + '.SystemExit', DummyError)

    update.check_version(Version('1.2.2'))

    with pytest.raises(DummyError):
        update.check_version(Version('0.0.0'))

    with pytest.raises(DummyError):
        update.check_version(Version('1.3.0'))


def test_bind_localtime(m_utils):
    m_utils.read_compose.side_effect = lambda: {
        'version': '3.7',
        'services': {
            'spark-one': {
                'image': 'brewblox/brewblox-devcon-spark:rpi-edge',
            },
            'spark-two': {
                'image': 'brewblox/brewblox-devcon-spark:rpi-edge',
                'volumes': ['/data:/data']
            },
            'plaato': {
                'image': 'brewblox/brewblox-plaato:rpi-edge',
                'volumes': ['/etc/localtime:/etc/localtime:ro']
            },
            'mcguffin': {
                'image': 'brewblox/brewblox-mcguffin:${BREWBLOX_RELEASE}',
                'volumes': [{
                    'type': 'bind',
                    'source': '/etc/localtime',
                    'target': '/etc/localtime',
                    'read_only': True,
                }]
            }
        }}

    update.bind_localtime()
    m_utils.write_compose.assert_called_once_with({
        'version': '3.7',
        'services': {
            'spark-one': {
                'image': 'brewblox/brewblox-devcon-spark:rpi-edge',
                'volumes': [{
                    'type': 'bind',
                    'source': '/etc/localtime',
                    'target': '/etc/localtime',
                    'read_only': True,
                }]
            },
            'spark-two': {
                'image': 'brewblox/brewblox-devcon-spark:rpi-edge',
                'volumes': [
                    '/data:/data',
                    {
                        'type': 'bind',
                        'source': '/etc/localtime',
                        'target': '/etc/localtime',
                        'read_only': True,
                    }
                ]
            },
            'plaato': {
                'image': 'brewblox/brewblox-plaato:rpi-edge',
                'volumes': ['/etc/localtime:/etc/localtime:ro']
            },
            'mcguffin': {
                'image': 'brewblox/brewblox-mcguffin:${BREWBLOX_RELEASE}',
                'volumes': [{
                    'type': 'bind',
                    'source': '/etc/localtime',
                    'target': '/etc/localtime',
                    'read_only': True,
                }]
            }
        }})


def test_bind_spark_backup(m_utils):
    m_utils.read_compose.side_effect = lambda: {
        'version': '3.7',
        'services': {
            'spark-one': {
                'image': 'brewblox/brewblox-devcon-spark:rpi-edge',
            },
            'spark-two': {
                'image': 'brewblox/brewblox-devcon-spark:rpi-edge',
                'volumes': ['/data:/data']
            },
            'spark-three': {
                'image': 'brewblox/brewblox-devcon-spark:rpi-edge',
                'volumes': [{
                    'type': 'bind',
                    'source': './custom/backup/dir',
                    'target': '/app/backup',
                }]
            },
            'plaato': {
                'image': 'brewblox/brewblox-plaato:rpi-edge',
                'volumes': ['/etc/localtime:/etc/localtime:ro']
            },
            'mcguffin': {
                'image': 'brewblox/brewblox-mcguffin:${BREWBLOX_RELEASE}',
                'volumes': [{
                    'type': 'bind',
                    'source': '/etc/localtime',
                    'target': '/etc/localtime',
                    'read_only': True,
                }]
            }
        }}

    update.bind_spark_backup()
    m_utils.write_compose.assert_called_once_with({
        'version': '3.7',
        'services': {
            'spark-one': {
                'image': 'brewblox/brewblox-devcon-spark:rpi-edge',
                'volumes': [{
                    'type': 'bind',
                    'source': './spark/backup',
                    'target': '/app/backup',
                }]
            },
            'spark-two': {
                'image': 'brewblox/brewblox-devcon-spark:rpi-edge',
                'volumes': [
                    '/data:/data',
                    {
                        'type': 'bind',
                        'source': './spark/backup',
                        'target': '/app/backup',
                    }
                ]
            },
            'spark-three': {
                'image': 'brewblox/brewblox-devcon-spark:rpi-edge',
                'volumes': [{
                    'type': 'bind',
                    'source': './custom/backup/dir',
                    'target': '/app/backup',
                }]
            },
            'plaato': {
                'image': 'brewblox/brewblox-plaato:rpi-edge',
                'volumes': ['/etc/localtime:/etc/localtime:ro']
            },
            'mcguffin': {
                'image': 'brewblox/brewblox-mcguffin:${BREWBLOX_RELEASE}',
                'volumes': [{
                    'type': 'bind',
                    'source': '/etc/localtime',
                    'target': '/etc/localtime',
                    'read_only': True,
                }]
            }
        }})


def test_bind_noop(m_utils):
    m_utils.read_shared_compose.side_effect = lambda: {
        'version': '3.7',
        'services': {
            'redis': {
                'image': 'redis:6.0',
            },
        }
    }
    m_utils.read_compose.side_effect = lambda: {
        'version': '3.7',
        'services': {
            'redis': {
                'image': 'redis:6.0',
            },
        }
    }

    update.bind_localtime()
    update.bind_spark_backup()
    m_utils.write_compose.assert_not_called()
