"""
Tests brewblox_ctl.migration
"""

from functools import partial
from unittest.mock import Mock

import httpretty
import pytest
from pytest_mock import MockerFixture

from brewblox_ctl import migration, utils

TESTED = migration.__name__


STORE_URL = 'https://localhost/history/datastore'


def csv_measurement_stream(cmd):
    yield 'name,name'
    yield 'name,s1'
    yield 'name,s2'


def csv_data_stream(opts, cmd):
    if opts.setdefault('calls', 0) < 3:
        opts['calls'] += 1
        yield 'name,time,m_k1,m_k2,m_k3'
        yield 'sparkey,1626096480000000000,10,20,30'
        yield 'sparkey,1626096480000000001,11,21,31'
        yield 'sparkey,1626096480000000002,12,22,32'
        yield 'sparkey,1626096480000000003,13,23,33'
        yield ''
    else:
        return


@pytest.fixture
def m_actions(mocker: MockerFixture):
    m = mocker.patch(TESTED + '.actions', autospec=True)
    return m


@pytest.fixture
def m_utils(m_getenv: Mock, m_read_compose: Mock):
    m_getenv.return_value = '/usr/local/bin'
    m_read_compose.side_effect = lambda: {
        'services': {
            'spark-one': {
                'image': 'ghcr.io/brewblox/brewblox-devcon-spark:rpi-edge',
                'depends_on': ['datastore'],
            },
            'plaato': {
                'image': 'brewblox/brewblox-plaato:rpi-edge',
            },
            'automation': {
                'image': 'brewblox/brewblox-automation:${BREWBLOX_RELEASE}',
            },
        }
    }


def test_influx_measurements(m_sh_stream: Mock):
    m_sh_stream.side_effect = csv_measurement_stream

    assert migration._influx_measurements() == ['s1', 's2']


def test_influx_line_count(m_sh: Mock):
    m_sh.return_value = (
        '{"results":[{"series":[{"name":"spark-one","columns":["time","count"],"values":[[0,825518]]}]}]}'
    )
    assert migration._influx_line_count('spark-one', '') == 825518

    m_sh.return_value = '{"results":[{}]}'
    assert migration._influx_line_count('spark-one', '') is None


def test_copy_influx_measurement_file(mocker: MockerFixture, m_sh: Mock, m_sh_stream: Mock):
    m_sh_stream.side_effect = partial(csv_data_stream, {})
    mocker.patch(TESTED + '.NamedTemporaryFile', wraps=migration.NamedTemporaryFile)
    mocker.patch(TESTED + '._influx_line_count', return_value=1000)

    migration._copy_influx_measurement('sparkey', 'today', '1d', 'file')
    assert m_sh.call_count == 4


@httpretty.activate(allow_net_connect=False)
def test_copy_influx_measurement_victoria(mocker: MockerFixture, m_sh: Mock, m_sh_stream: Mock):
    m_sh_stream.side_effect = partial(csv_data_stream, {})
    mocker.patch(TESTED + '.NamedTemporaryFile', wraps=migration.NamedTemporaryFile)
    mocker.patch(TESTED + '._influx_line_count', return_value=1000)

    httpretty.register_uri(
        httpretty.GET,
        'http://localhost:9600/victoria/write',
    )

    migration._copy_influx_measurement('sparkey', 'today', '1d', 'victoria')
    assert len(httpretty.latest_requests()) == 3
    assert m_sh.call_count == 0


def test_copy_influx_measurement_empty(mocker: MockerFixture, m_sh_stream: Mock):
    def empty(cmd):
        yield ''

    m_sh_stream.side_effect = empty
    m_tmp = mocker.patch(TESTED + '.NamedTemporaryFile', wraps=migration.NamedTemporaryFile)
    mocker.patch(TESTED + '._influx_line_count', return_value=None)

    migration._copy_influx_measurement('sparkey', 'today', '1d', 'file')
    assert m_tmp.call_count == 0


def test_copy_influx_measurement_error(mocker: MockerFixture, m_sh_stream: Mock):
    m_sh_stream.side_effect = partial(csv_data_stream, {})
    mocker.patch(TESTED + '.NamedTemporaryFile', wraps=migration.NamedTemporaryFile)
    mocker.patch(TESTED + '._influx_line_count', return_value=1000)

    with pytest.raises(ValueError):
        migration._copy_influx_measurement('sparkey', 'today', '1d', 'space magic')


def test_migrate_influxdb(mocker: MockerFixture, m_file_exists: Mock):
    opts = utils.get_opts()
    m_meas = mocker.patch(TESTED + '._influx_measurements')
    m_meas.return_value = ['s1', 's2']
    m_copy = mocker.patch(TESTED + '._copy_influx_measurement')

    # Dry run noop
    opts.dry_run = True
    m_file_exists.add_existing_files('./influxdb')
    migration.migrate_influxdb('victoria', '1d', [])
    assert m_meas.call_count == 0
    assert m_copy.call_count == 0

    # No influx data dir found
    opts.dry_run = False
    m_file_exists.clear_existing_files()
    migration.migrate_influxdb('victoria', '1d', [])
    assert m_meas.call_count == 0
    assert m_copy.call_count == 0

    # preconditions OK, services predefined
    opts.dry_run = False
    m_file_exists.add_existing_files('./influxdb')
    migration.migrate_influxdb('victoria', '1d', ['s1', 's2', 's3'])
    assert m_meas.call_count == 0
    assert m_copy.call_count == 3

    # preconditions OK, services wildcard
    opts.dry_run = False
    migration.migrate_influxdb('victoria', '1d', [])
    assert m_meas.call_count == 1
    assert m_copy.call_count == 3 + 2


def test_migrate_ghcr_images(m_read_compose: Mock, m_write_compose: Mock):
    m_read_compose.side_effect = lambda: {
        'version': '3.7',
        'services': {
            'spark-one': {
                'image': 'ghcr.io/brewblox/brewblox-devcon-spark:edge',
            },
            'spark-two': {
                'image': 'brewblox/brewblox-devcon-spark:feature-branch',
            },
            'spark-three': {
                'image': 'brewblox/brewblox-devcon-spark:$BREWBLOX_RELEASE',
            },
            'plaato': {
                'image': 'brewblox/brewblox-plaato:rpi-edge',
            },
            'automation': {
                'image': 'brewblox/brewblox-automation:${BREWBLOX_RELEASE}',
            },
            'spark-fallback': {
                'image': 'brewblox/brewblox-devcon-spark:${BREWBLOX_RELEASE:-develop}',
            },
            'third-party': {
                'image': 'external/image:tag',
            },
            'extension': {
                'command': 'updated from shared compose',
            },
        },
    }
    migration.migrate_ghcr_images()
    m_write_compose.assert_called_once_with(
        {
            'version': '3.7',
            'services': {
                'spark-one': {
                    'image': 'ghcr.io/brewblox/brewblox-devcon-spark:edge',
                },
                'spark-two': {
                    'image': 'brewblox/brewblox-devcon-spark:feature-branch',
                },
                'spark-three': {
                    'image': 'ghcr.io/brewblox/brewblox-devcon-spark:$BREWBLOX_RELEASE',
                },
                'plaato': {
                    'image': 'ghcr.io/brewblox/brewblox-plaato:edge',
                },
                'automation': {
                    'image': 'ghcr.io/brewblox/brewblox-automation:${BREWBLOX_RELEASE}',
                },
                'spark-fallback': {
                    'image': 'ghcr.io/brewblox/brewblox-devcon-spark:${BREWBLOX_RELEASE:-develop}',
                },
                'third-party': {
                    'image': 'external/image:tag',
                },
                'extension': {
                    'command': 'updated from shared compose',
                },
            },
        }
    )


def test_migrate_tilt_images(m_read_compose: Mock, m_write_compose: Mock):
    m_read_compose.side_effect = lambda: {
        'version': '3.7',
        'services': {
            'spark-one': {
                'image': 'ghcr.io/brewblox/brewblox-devcon-spark:edge',
            },
            'tilt': {
                'image': 'ghcr.io/brewblox/brewblox-tilt:feature-branch',
                'network_mode': 'host',
                'volumes': ['./share:/share'],
            },
            'tilt-new': {
                'image': 'ghcr.io/brewblox/brewblox-tilt:feature-branch',
                'volumes': [
                    {
                        'type': 'bind',
                        'source': '/var/run/dbus',
                        'target': '/var/run/dbus',
                    }
                ],
            },
            'third-party': {
                'image': 'external/image:tag',
            },
            'extension': {
                'command': 'updated from shared compose',
            },
        },
    }
    migration.migrate_tilt_images()
    m_write_compose.assert_called_once_with(
        {
            'version': '3.7',
            'services': {
                'spark-one': {
                    'image': 'ghcr.io/brewblox/brewblox-devcon-spark:edge',
                },
                'tilt': {
                    'image': 'ghcr.io/brewblox/brewblox-tilt:feature-branch',
                    'volumes': [
                        './share:/share',
                        {
                            'type': 'bind',
                            'source': '/var/run/dbus',
                            'target': '/var/run/dbus',
                        },
                    ],
                },
                'tilt-new': {
                    'image': 'ghcr.io/brewblox/brewblox-tilt:feature-branch',
                    'volumes': [
                        {
                            'type': 'bind',
                            'source': '/var/run/dbus',
                            'target': '/var/run/dbus',
                        }
                    ],
                },
                'third-party': {
                    'image': 'external/image:tag',
                },
                'extension': {
                    'command': 'updated from shared compose',
                },
            },
        }
    )

    # No-op if no tilt services
    m_read_compose.side_effect = lambda: {'version': '3.7', 'services': {}}
    migration.migrate_tilt_images()
    assert m_write_compose.call_count == 1


def test_migrate_env_config(m_envdict: Mock):
    config = utils.get_config()

    # empty
    migration.migrate_env_config()
    assert not config.environment

    # full
    m_envdict.side_effect = lambda _: {
        'BREWBLOX_CFG_VERSION': '0.1.2',
        'BREWBLOX_RELEASE': 'fancypants',
        'BREWBLOX_CTL_RELEASE': 'veryfancypants',
        'BREWBLOX_UPDATE_SYSTEM_PACKAGES': 'False',
        'BREWBLOX_SKIP_CONFIRM': 'False',
        'BREWBLOX_AUTH_ENABLED': 'true',
        'BREWBLOX_DEBUG': 'true',
        'BREWBLOX_PORT_HTTP': '81',
        'BREWBLOX_PORT_HTTPS': '444',
        'BREWBLOX_PORT_MQTT': '1884',
        'BREWBLOX_PORT_MQTTS': '8884',
        'BREWBLOX_PORT_ADMIN': '9601',
        'COMPOSE_PROJECT_NAME': 'brewblox2',
        'COMPOSE_FILE': 'docker-compose.shared.yml:docker-compose.yml:are-you-sure.yml',
        'USERNAME': 'henk',
        'PASSWORD': 'secret',
        'special': 'true',
    }
    migration.migrate_env_config()

    assert config.release == 'fancypants'
    assert config.ctl_release == 'veryfancypants'
    assert config.system.apt_upgrade is False
    assert config.skip_confirm is False
    assert config.auth.enabled is True
    assert config.debug is True
    assert config.ports.http == 81
    assert config.ports.https == 444
    assert config.ports.mqtt == 1884
    assert config.ports.mqtts == 8884
    assert config.ports.admin == 9601
    assert config.compose.project == 'brewblox2'
    assert config.compose.files == [
        'docker-compose.shared.yml',
        'docker-compose.yml',
        'are-you-sure.yml',
    ]
    assert config.environment == {
        'USERNAME': 'henk',
        'PASSWORD': 'secret',
        'special': 'true',
    }
