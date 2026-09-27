"""
Tests brewblox_ctl.commands.backup
"""

import json
import zipfile
from pathlib import Path
from unittest.mock import Mock, call

import httpretty
import pytest
import yaml
from pytest_mock import MockerFixture
from requests import HTTPError

from brewblox_ctl.commands import backup
from brewblox_ctl.testing import invoke, matching

TESTED = backup.__name__
HOST_URL = 'https://localhost:9600'
STORE_URL = HOST_URL + '/history/datastore'


@pytest.fixture(autouse=True)
def m_getgid(mocker: MockerFixture):
    m = mocker.patch(TESTED + '.getgid')
    m.return_value = 1000
    return m


@pytest.fixture(autouse=True)
def m_getuid(mocker: MockerFixture):
    m = mocker.patch(TESTED + '.getuid')
    m.return_value = 1000
    return m


@pytest.fixture(autouse=True)
def m_glob(mocker: MockerFixture):
    m = mocker.patch(TESTED + '.glob', autospec=True)
    m.return_value = [
        'node-red/settings.js',
        'node-red/flows.json',
        'node-red/lib/flows/flows.json',
    ]
    return m


@pytest.fixture(autouse=True)
def m_load_dotenv(mocker: MockerFixture):
    m = mocker.patch(TESTED + '.load_dotenv', autospec=True)
    return m


def zipf_names():
    return [
        '.env',
        'docker-compose.yml',
        'global.redis.json',
        'spark-one.spark.json',
        'brewblox-ui-store.datastore.json',
        'spark-service.datastore.json',
        'spark-two.spark.json',
        'node-red/settings.js',
        'node-red/flows.json',
        'node-red/lib/flows/flows.json',
        'mosquitto/forward.conf',
        'tilt/devices.yml',
    ]


def zipf_read():
    return [
        b'BREWBLOX_RELEASE=9001',
        yaml.safe_dump(
            {
                'version': '3.7',
                'services': {
                    'spark-one': {
                        'image': 'ghcr.io/brewblox/brewblox-devcon-spark:rpi-edge',
                        'depends_on': ['datastore'],
                    },
                    'plaato': {
                        'image': 'brewblox/brewblox-plaato:rpi-edge',
                    },
                },
            }
        ).encode(),
        json.dumps({'values': []}).encode(),
        json.dumps(
            [
                {'_id': 'module__obj', '_rev': '1234', 'k': 'v'},
                {'_id': 'invalid', '_rev': '4321', 'k': 'v'},
            ]
        ).encode(),
        json.dumps(
            [
                {'_id': 'spark-id', '_rev': '1234', 'k': 'v'},
            ]
        ).encode(),
        json.dumps({'blocks': []}).encode(),
        json.dumps({'blocks': [], 'other': []}).encode(),
    ]


def redis_data():
    return {
        'values': [
            {'id': 'id1', 'namespace': 'n1', 'k': 'v1'},
            {'id': 'id2', 'namespace': 'n2', 'k': 'v2'},
            {'id': 'id3', 'namespace': 'n3', 'k': 'v3'},
        ]
    }


def blocks_data():
    return {'blocks': []}


@pytest.fixture
def m_zipf(mocker: MockerFixture):
    m: Mock = mocker.patch(TESTED + '.zipfile.ZipFile').return_value
    m.namelist.return_value = zipf_names()
    m.read.side_effect = zipf_read()
    return m


def set_responses():
    httpretty.register_uri(
        httpretty.GET,
        STORE_URL + '/ping',
        body=json.dumps({'ping': 'pong'}),
        adding_headers={'ContentType': 'application/json'},
    )
    httpretty.register_uri(
        httpretty.POST,
        STORE_URL + '/mdelete',
        body=json.dumps({'count': 1234}),
        adding_headers={'ContentType': 'application/json'},
    )
    httpretty.register_uri(
        httpretty.POST,
        STORE_URL + '/mget',
        body=json.dumps(redis_data()),
        adding_headers={'ContentType': 'application/json'},
    )
    httpretty.register_uri(
        httpretty.POST,
        STORE_URL + '/mset',
        body=json.dumps(redis_data()),
        adding_headers={'ContentType': 'application/json'},
    )
    httpretty.register_uri(
        httpretty.POST,
        HOST_URL + '/spark-one/blocks/backup/save',
        body=json.dumps(blocks_data()),
        adding_headers={'ContentType': 'application/json'},
    )
    httpretty.register_uri(
        httpretty.POST,
        HOST_URL + '/spark-two/blocks/backup/save',
        body=json.dumps(blocks_data()),
        adding_headers={'ContentType': 'application/json'},
    )


@pytest.fixture
def f_read_compose(m_read_compose: Mock):
    m_read_compose.return_value = {
        'services': {
            'spark-one': {
                'image': 'ghcr.io/brewblox/brewblox-devcon-spark:rpi-edge',
            },
            'plaato': {
                'image': 'brewblox/brewblox-plaato:rpi-edge',
            },
        }
    }


@httpretty.activate(allow_net_connect=False)
def test_save_backup(mocker: MockerFixture, f_read_compose):
    set_responses()
    m_mkdir = mocker.patch(TESTED + '.mkdir')
    m_zipfile = mocker.patch(TESTED + '.zipfile.ZipFile')

    invoke(backup.save)

    m_mkdir.assert_called_once_with(Path('backup/').resolve())
    m_zipfile.assert_called_once_with(matching(r'^backup/brewblox_backup_\d{8}_\d{4}.zip'), 'w', zipfile.ZIP_DEFLATED)
    m_zipfile.return_value.write.assert_any_call('docker-compose.yml')
    assert m_zipfile.return_value.writestr.call_args_list == [
        call('global.redis.json', json.dumps(redis_data())),
        call('spark-one.spark.json', json.dumps(blocks_data())),
    ]
    # get datastore, get spark
    assert len(httpretty.latest_requests()) == 2


@httpretty.activate(allow_net_connect=False)
def test_save_backup_no_compose(mocker: MockerFixture, m_zipf: Mock, f_read_compose):
    set_responses()
    mocker.patch(TESTED + '.mkdir')
    invoke(backup.save, '--no-save-compose')
    assert m_zipf.write.call_count == 13  # env + 4x glob


@httpretty.activate(allow_net_connect=False)
def test_save_backup_spark_err(mocker: MockerFixture, m_zipf, f_read_compose):
    set_responses()
    mocker.patch(TESTED + '.mkdir')
    m_zipfile = mocker.patch(TESTED + '.zipfile.ZipFile')

    httpretty.register_uri(
        httpretty.POST,
        HOST_URL + '/spark-one/blocks/backup/save',
        body='MEEEP',
        adding_headers={'ContentType': 'application/json'},
        status=500,
    )

    invoke(backup.save, '--no-save-compose', _err=HTTPError)

    assert m_zipfile.return_value.writestr.call_args_list == [
        call('global.redis.json', json.dumps(redis_data())),
    ]
    # get datastore, get spark
    assert len(httpretty.latest_requests()) == 2


@httpretty.activate(allow_net_connect=False)
def test_save_backup_ignore_spark_err(mocker: MockerFixture, m_zipf, f_read_compose):
    set_responses()
    mocker.patch(TESTED + '.mkdir')
    m_zipfile = mocker.patch(TESTED + '.zipfile.ZipFile')

    httpretty.register_uri(
        httpretty.POST,
        HOST_URL + '/spark-one/blocks/backup/save',
        body='MEEEP',
        adding_headers={'ContentType': 'application/json'},
        status=500,
    )

    invoke(backup.save, '--no-save-compose --ignore-spark-error')

    assert m_zipfile.return_value.writestr.call_args_list == [
        call('global.redis.json', json.dumps(redis_data())),
    ]
    # get datastore, get spark
    assert len(httpretty.latest_requests()) == 2


def test_load_backup_empty(m_sh: Mock, m_zipf):
    m_zipf.namelist.return_value = []

    invoke(backup.load, 'fname')
    assert m_sh.call_count == 1  # Only the update


def test_load_backup(mocker: MockerFixture, m_zipf):
    m_tmp = mocker.patch(TESTED + '.NamedTemporaryFile', wraps=backup.NamedTemporaryFile)
    invoke(backup.load, 'fname')
    assert m_zipf.read.call_count == 7
    assert m_tmp.call_count == 6


def test_load_backup_none(m_sh, m_zipf):
    invoke(
        backup.load,
        ' '.join(
            [
                'fname',
                '--no-load-compose',
                '--no-load-datastore',
                '--no-load-spark',
                '--no-load-node-red',
                '--no-load-mosquitto',
                '--no-load-tilt',
                '--no-update',
            ]
        ),
    )
    assert m_zipf.read.call_count == 1
    assert m_sh.call_count == 1


def test_load_backup_missing(mocker: MockerFixture, m_zipf):
    m_tmp = mocker.patch(TESTED + '.NamedTemporaryFile', wraps=backup.NamedTemporaryFile)
    m_zipf.namelist.return_value = zipf_names()[2:]
    m_zipf.read.side_effect = zipf_read()[2:]
    invoke(backup.load, 'fname')
    assert m_zipf.read.call_count == 5
    assert m_tmp.call_count == 5


def test_load_backup_other_uid(mocker: MockerFixture, m_sh, m_zipf, m_getuid):
    m_getuid.return_value = 1001
    mocker.patch(TESTED + '.NamedTemporaryFile', wraps=backup.NamedTemporaryFile)
    invoke(backup.load, 'fname')
    m_sh.assert_any_call('sudo chown 1000:1000 ./node-red/')


# The history migration's state: it describes the history databases, which are not in the backup
MIGRATION_STATE = {'namespace': 'brewblox-history', 'id': 'migration', 'job': 'abcd', 'phase': 'walk'}
# Documents that share only the namespace or the id
KEPT_VALUES = [
    {'namespace': 'brewblox-history', 'id': 'other', 'k': 'v'},
    {'namespace': 'brewblox-ui-store', 'id': 'migration', 'k': 'v'},
    {'namespace': 'n1', 'id': 'id1', 'k': 'v1'},
]


def redis_data_with_migration():
    return {'values': [KEPT_VALUES[0], MIGRATION_STATE, *KEPT_VALUES[1:]]}


@httpretty.activate(allow_net_connect=False)
def test_save_backup_skips_migration_state(mocker: MockerFixture, f_read_compose):
    set_responses()
    httpretty.register_uri(
        httpretty.POST,
        STORE_URL + '/mget',
        body=json.dumps(redis_data_with_migration()),
        adding_headers={'ContentType': 'application/json'},
    )
    mocker.patch(TESTED + '.mkdir')
    m_zipfile = mocker.patch(TESTED + '.zipfile.ZipFile')

    invoke(backup.save)

    written = {c.args[0]: c.args[1] for c in m_zipfile.return_value.writestr.call_args_list}
    assert json.loads(written['global.redis.json']) == {'values': KEPT_VALUES}


@httpretty.activate(allow_net_connect=False)
def test_save_backup_only_migration_state(mocker: MockerFixture, f_read_compose):
    set_responses()
    httpretty.register_uri(
        httpretty.POST,
        STORE_URL + '/mget',
        body=json.dumps({'values': [MIGRATION_STATE]}),
        adding_headers={'ContentType': 'application/json'},
    )
    mocker.patch(TESTED + '.mkdir')
    m_zipfile = mocker.patch(TESTED + '.zipfile.ZipFile')

    invoke(backup.save)

    written = {c.args[0]: c.args[1] for c in m_zipfile.return_value.writestr.call_args_list}
    assert json.loads(written['global.redis.json']) == {'values': []}


def test_load_backup_skips_migration_state(mocker: MockerFixture, m_zipf: Mock, m_sh: Mock, m_info: Mock):
    """A backup made before the state was skipped may contain it"""
    contents = zipf_read()
    contents[2] = json.dumps(redis_data_with_migration()).encode()
    m_zipf.read.side_effect = contents
    m_mset = mocker.patch(TESTED + '.mset', wraps=backup.mset)

    invoke(backup.load, 'fname')

    # The first mset loads global.redis.json
    assert m_mset.call_args_list[0] == call({'values': KEPT_VALUES})
    assert all(MIGRATION_STATE not in c.args[0]['values'] for c in m_mset.call_args_list)
    m_info.assert_any_call('Loading 3 entries from Redis datastore')

    # Each mset posts its data once
    mset_cmds = [c.args[0] for c in m_sh.call_args_list if '/mset' in c.args[0]]
    assert len(mset_cmds) == m_mset.call_count


def test_is_migration_state():
    assert backup.is_migration_state(MIGRATION_STATE)
    assert backup.is_migration_state({'namespace': 'brewblox-history', 'id': 'migration'})
    for value in KEPT_VALUES:
        assert not backup.is_migration_state(value)
    assert not backup.is_migration_state({})
