"""
Tests brewblox_ctl.migration
"""

import json
from functools import partial

import httpretty
import pytest

from brewblox_ctl import migration
from brewblox_ctl.testing import check_sudo

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
def m_actions(mocker):
    m = mocker.patch(TESTED + '.actions', autospec=True)
    return m


@pytest.fixture
def m_utils(mocker):
    m = mocker.patch(TESTED + '.utils', autospec=True)
    m.optsudo.return_value = 'SUDO '
    m.getenv.return_value = '/usr/local/bin'
    m.datastore_url.return_value = STORE_URL
    m.read_compose.side_effect = lambda: {
        'version': '3.7',
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
            }
        }}
    return m


@pytest.fixture
def m_sh(mocker):
    m = mocker.patch(TESTED + '.sh', autospec=True)
    m.side_effect = check_sudo
    return m


def test_migrate_compose_split(m_utils):
    m_utils.read_compose.side_effect = lambda: {
        'version': '3.7',
        'services': {
            'my-service': {},
            'eventbus': {}
        }}

    migration.migrate_compose_split()

    m_utils.write_compose.assert_called_once_with({
        'version': '3.7',
        'services': {
            'my-service': {},
        },
    })


def test_migrate_compose_datastore(m_utils, m_sh):
    migration.migrate_compose_datastore()

    m_utils.write_compose.assert_called_once_with({
        'version': '3.7',
        'services': {
            'spark-one': {
                'image': 'ghcr.io/brewblox/brewblox-devcon-spark:rpi-edge',
            },
            'plaato': {
                'image': 'brewblox/brewblox-plaato:rpi-edge',
            },
            'automation': {
                'image': 'brewblox/brewblox-automation:${BREWBLOX_RELEASE}',
            }
        }})
    m_sh.assert_called_once_with('mkdir -p redis/')


def test_migrate_ipv6_fix(m_actions, m_utils, m_sh):
    migration.migrate_ipv6_fix()

    assert m_sh.call_count == 1
    assert m_actions.fix_ipv6.call_count == 1


def test_migrate_couchdb_dry(m_utils, m_sh):
    m_utils.ctx_opts.return_value.dry_run = True

    migration.migrate_couchdb()

    assert m_sh.call_count == 0


def test_migrate_couchdb_not_found(m_utils, m_sh):
    m_utils.ctx_opts.return_value.dry_run = False
    m_utils.path_exists.return_value = False

    migration.migrate_couchdb()

    assert m_sh.call_count == 0


@httpretty.activate(allow_net_connect=False)
def test_migrate_couchdb_empty(m_utils, m_sh, mocker):
    m_utils.ctx_opts.return_value.dry_run = False
    httpretty.register_uri(
        httpretty.GET,
        'http://localhost:5984/_all_dbs',
        body=json.dumps(['unused']),  # no known databases found -> nothing migrated
        adding_headers={'ContentType': 'application/json'},
    )
    migration.migrate_couchdb()
    assert len(httpretty.latest_requests()) == 1


@httpretty.activate(allow_net_connect=False)
def test_migrate_couchdb(m_utils, m_sh, mocker):
    m_utils.ctx_opts.return_value.dry_run = False
    httpretty.register_uri(
        httpretty.GET,
        'http://localhost:5984/_all_dbs',
        body=json.dumps(['brewblox-ui-store', 'spark-service']),
        adding_headers={'ContentType': 'application/json'},
    )
    httpretty.register_uri(
        httpretty.GET,
        'http://localhost:5984/brewblox-ui-store/_all_docs',
        body=json.dumps({'rows': [
            {'doc': {'_id': 'module__obj', '_rev': '1234', 'k': 'v'}},
            {'doc': {'_id': 'invalid', '_rev': '1234', 'k': 'v'}},
        ]}),
        adding_headers={'ContentType': 'application/json'},
    )
    httpretty.register_uri(
        httpretty.GET,
        'http://localhost:5984/spark-service/_all_docs',
        body=json.dumps({'rows': [
            {'doc': {'_id': 'spaced__id', '_rev': '1234', 'k': 'v'}},
            {'doc': {'_id': 'valid', '_rev': '1234', 'k': 'v'}},
        ]}),
        adding_headers={'ContentType': 'application/json'},
    )
    httpretty.register_uri(
        httpretty.POST,
        STORE_URL + '/mset',
        body='{"values":[]}',
        adding_headers={'ContentType': 'application/json'},
    )

    migration.migrate_couchdb()
    assert len(httpretty.latest_requests()) == 5


def test_influx_measurements(m_utils):
    m_utils.sh_stream.side_effect = csv_measurement_stream

    assert migration._influx_measurements() == ['s1', 's2']


def test_influx_line_count(m_utils, m_sh):
    m_sh.return_value = \
        '{"results":[{"series":[{"name":"spark-one","columns":["time","count"],"values":[[0,825518]]}]}]}'
    assert migration._influx_line_count('spark-one', '') == 825518

    m_sh.return_value = '{"results":[{}]}'
    assert migration._influx_line_count('spark-one', '') is None


def test_copy_influx_measurement_file(m_utils, m_sh, mocker):
    m_utils.sh_stream.side_effect = partial(csv_data_stream, {})
    mocker.patch(TESTED + '.NamedTemporaryFile', wraps=migration.NamedTemporaryFile)
    mocker.patch(TESTED + '._influx_line_count', return_value=1000)

    migration._copy_influx_measurement('sparkey', 'today', '1d', 'file')
    assert m_sh.call_count == 4


@httpretty.activate(allow_net_connect=False)
def test_copy_influx_measurement_victoria(m_utils, m_sh, mocker):
    m_utils.host_url.return_value = 'https://localhost'
    m_utils.sh_stream.side_effect = partial(csv_data_stream, {})
    mocker.patch(TESTED + '.NamedTemporaryFile', wraps=migration.NamedTemporaryFile)
    mocker.patch(TESTED + '._influx_line_count', return_value=1000)

    httpretty.register_uri(
        httpretty.GET,
        'https://localhost/victoria/write',
    )

    migration._copy_influx_measurement('sparkey', 'today', '1d', 'victoria')
    assert len(httpretty.latest_requests()) == 3
    assert m_sh.call_count == 0


def test_copy_influx_measurement_empty(m_utils, m_sh, mocker):
    def empty(cmd):
        yield ''
        return
    m_utils.sh_stream.side_effect = empty
    m_tmp = mocker.patch(TESTED + '.NamedTemporaryFile', wraps=migration.NamedTemporaryFile)
    mocker.patch(TESTED + '._influx_line_count', return_value=None)

    migration._copy_influx_measurement('sparkey', 'today', '1d', 'file')
    assert m_tmp.call_count == 0


def test_copy_influx_measurement_error(m_utils, m_sh, mocker):
    m_utils.sh_stream.side_effect = partial(csv_data_stream, {})
    mocker.patch(TESTED + '.NamedTemporaryFile', wraps=migration.NamedTemporaryFile)
    mocker.patch(TESTED + '._influx_line_count', return_value=1000)

    with pytest.raises(ValueError):
        migration._copy_influx_measurement('sparkey', 'today', '1d', 'space magic')


def test_migrate_influxdb(m_utils, m_sh, mocker):
    m_meas = mocker.patch(TESTED + '._influx_measurements')
    m_meas.return_value = ['s1', 's2']
    m_copy = mocker.patch(TESTED + '._copy_influx_measurement')

    # Dry run noop
    m_utils.ctx_opts.return_value.dry_run = True
    m_utils.path_exists.return_value = True
    migration.migrate_influxdb('victoria', '1d', [])
    assert m_meas.call_count == 0
    assert m_copy.call_count == 0

    # No influx data dir found
    m_utils.ctx_opts.return_value.dry_run = False
    m_utils.path_exists.return_value = False
    migration.migrate_influxdb('victoria', '1d', [])
    assert m_meas.call_count == 0
    assert m_copy.call_count == 0

    # preconditions OK, services predefined
    m_utils.ctx_opts.return_value.dry_run = False
    m_utils.path_exists.return_value = True
    migration.migrate_influxdb('victoria', '1d', ['s1', 's2', 's3'])
    assert m_meas.call_count == 0
    assert m_copy.call_count == 3

    # preconditions OK, services wildcard
    m_utils.ctx_opts.return_value.dry_run = False
    m_utils.path_exists.return_value = True
    migration.migrate_influxdb('victoria', '1d', [])
    assert m_meas.call_count == 1
    assert m_copy.call_count == 3 + 2


def test_migrate_ghcr_images(m_utils):
    migration.migrate_ghcr_images()
    m_utils.write_compose.assert_called_once_with({
        'version': '3.7',
        'services': {
            'spark-one': {
                'image': 'ghcr.io/brewblox/brewblox-devcon-spark:rpi-edge',
                'depends_on': ['datastore'],
            },
            'plaato': {
                'image': 'ghcr.io/brewblox/brewblox-plaato:rpi-edge',
            },
            'automation': {
                'image': 'ghcr.io/brewblox/brewblox-automation:${BREWBLOX_RELEASE}',
            }
        }})
