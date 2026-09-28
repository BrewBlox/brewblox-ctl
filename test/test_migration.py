"""
Tests brewblox_ctl.migration
"""

import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from subprocess import CalledProcessError
from typing import List, Optional
from unittest.mock import DEFAULT, Mock, call

import httpretty
import pytest
import requests
from packaging.version import Version
from pytest_mock import MockerFixture

from brewblox_ctl import const, migration, utils

TESTED = migration.__name__


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


# History migration (configuration version 0.12.0)

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
MIGRATE_URL = 'http://localhost:9600/history/timeseries/migrate'
PING_URL = 'http://localhost:9600/history/datastore/ping'
MiB = 2**20
GiB = 2**30


def utc(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


def ts(*args) -> int:
    return int(utc(*args).timestamp())


STARTED = ts(2026, 9, 26, 10, 0)
FINISHED = ts(2026, 9, 27, 8, 15)


def make_status(**kwargs) -> dict:
    """A MigrationStatus of the history service, as JSON"""
    status = {
        'phase': 'walk',
        'cancelled': False,
        'job': 'f00dcafe',
        'source_url': const.VICTORIA_LEGACY_URL,
        'earliest': ts(2019, 3, 1),
        'dense_days': 30,
        'sparse_interval': 60,
        'chunk': 3600,
        'legacy_last': ts(2026, 9, 26, 9, 59) + 0.5,
        'legacy_end': ts(2026, 9, 26, 10, 0),
        'chunks_total': 1000,
        'started': STARTED,
        'finished': None,
        'lost_chunks': [],
        'missing_series': [],
        'running': True,
        'chunks_done': 250,
        'last_error': None,
    }
    status.update(kwargs)
    return status


def monthly(first: datetime, last: datetime, size: int) -> dict:
    """Partition sizes: `size` for every month from `first` to `last`"""
    months = {}
    month = first
    while month <= last:
        months[month] = size
        month = month.replace(year=month.year + month.month // 12, month=month.month % 12 + 1)
    return months


# 81 months of 1 GiB: 2020-01 to 2026-09
HISTORY = monthly(utc(2020, 1, 1), utc(2026, 9, 1), GiB)


def need_bytes(averaged: int, dense: int = 2, size: int = GiB) -> int:
    """Free space for averages of `averaged` months, plus the dense database and the margin"""
    return math.ceil(dense * size + 0.15 * (averaged * size) + GiB)


def file_blocks(path: Path) -> int:
    """Bytes on disk of the files in `path`, as the file system reports them"""
    return sum(p.lstat().st_blocks * 512 for p in path.rglob('*') if p.is_file() and not p.is_symlink())


def write_partition(legacy: Path, kind: str, name: str, size: int) -> Path:
    """Writes a partition directory as Victoria Metrics does: part directories with files"""
    part = legacy / 'data' / kind / name / f'{size:016X}'
    part.mkdir(parents=True, exist_ok=True)
    (part / 'values.bin').write_bytes(os.urandom(size))
    (part / 'metadata.json').write_text('{}')
    return part.parent


def response(status: int, body=None) -> requests.Response:
    resp = requests.Response()
    resp.status_code = status
    resp.reason = 'reason'
    resp.encoding = 'utf-8'
    resp._content = json.dumps(body).encode()
    return resp


def messages(spy: Mock) -> List[str]:
    return [c[0][0] for c in spy.call_args_list]


@pytest.fixture
def m_now(mocker: MockerFixture) -> Mock:
    return mocker.patch(TESTED + '._now', return_value=NOW)


@pytest.fixture
def m_sleep(mocker: MockerFixture) -> Mock:
    return mocker.patch(TESTED + '.sleep')


@pytest.fixture
def m_request(mocker: MockerFixture) -> Mock:
    return mocker.patch(TESTED + '.requests.request')


@pytest.fixture
def m_retries(mocker: MockerFixture):
    mocker.patch(TESTED + '.HTTP_RETRIES', 2)


def test_format_local(local_tz):
    local_tz('America/New_York')
    # The first partition month starts at midnight UTC: the evening before in New York
    assert migration.format_date(utc(2019, 3, 1)) == '2019-02-28'
    assert migration.format_timestamp(ts(2019, 3, 1)) == '2019-02-28 19:00'
    local_tz('Europe/Amsterdam')
    assert migration.format_date(utc(2019, 3, 1)) == '2019-03-01'
    assert migration.format_timestamp(ts(2019, 3, 1)) == '2019-03-01 01:00'


def test_now():
    before = datetime.now(timezone.utc)
    now = migration._now()
    assert now.utcoffset() == timedelta(0)
    assert before <= now <= datetime.now(timezone.utc)


@pytest.mark.parametrize(
    'value, expected',
    [
        (0, '0 MB'),
        (1, '1 MB'),
        (MiB, '1 MB'),
        (MiB + 1, '2 MB'),
        (GiB - 1, '1024 MB'),
        (GiB, '1.0 GB'),
        (1.5 * GiB, '1.5 GB'),
        (100 * GiB, '100.0 GB'),
    ],
)
def test_format_bytes(value: float, expected: str):
    assert migration.format_bytes(value) == expected


def test_format_date():
    assert migration.format_date(utc(2019, 3, 1)) == '2019-03-01'
    assert migration.format_date(utc(2020, 12, 31, 23, 59)) == '2020-12-31'


def test_format_timestamp():
    assert migration.format_timestamp(ts(2019, 3, 7, 23, 6, 40)) == '2019-03-07 23:06'
    assert migration.format_timestamp(ts(2026, 9, 26, 10, 0) + 0.9) == '2026-09-26 10:00'


@pytest.mark.parametrize(
    'month, expected',
    [
        (utc(2019, 1, 1), utc(2019, 2, 1)),
        (utc(2019, 11, 1), utc(2019, 12, 1)),
        (utc(2019, 12, 1), utc(2020, 1, 1)),
    ],
)
def test_next_month(month: datetime, expected: datetime):
    assert migration._next_month(month) == expected


@pytest.mark.parametrize(
    'files, expected',
    [
        ([], False),
        (['./victoria'], True),
        (['./victoria', './victoria-legacy'], False),
        (['./victoria', './victoria-dense'], False),
        (['./victoria', './victoria-legacy', './victoria-dense'], False),
        (['./victoria-legacy'], False),
        (['./victoria-legacy', './victoria-dense'], False),
    ],
)
def test_legacy_history_unmoved(m_file_exists: Mock, files: List[str], expected: bool):
    m_file_exists.add_existing_files(*files)
    assert migration.legacy_history_unmoved() is expected


@pytest.mark.parametrize(
    'version, files, expected',
    [
        ('0.11.0', ['./victoria'], True),
        ('0.9.0', ['./victoria'], True),
        ('0.12.0', ['./victoria'], False),
        ('0.13.0', ['./victoria'], False),
        ('0.11.0', ['./victoria', './victoria-legacy'], False),
        ('0.11.0', ['./victoria', './victoria-dense'], False),
        ('0.11.0', [], False),
    ],
)
def test_history_move_pending(m_file_exists: Mock, version: str, files: List[str], expected: bool):
    m_file_exists.add_existing_files(*files)
    assert migration.history_move_pending(Version(version)) is expected


@pytest.mark.parametrize(
    'env_version, files, expected',
    [
        ('0.11.0', ['./victoria'], True),
        ('0.11.0', ['./victoria', './victoria-legacy'], False),
        ('0.11.0', ['./victoria', './victoria-dense'], False),
        ('0.11.0', [], False),
        ('0.12.0', ['./victoria'], False),
        # Without a version, the directory was never set up: its history counts as old
        (None, ['./victoria'], True),
        ('', ['./victoria'], True),
        (None, ['./victoria', './victoria-dense'], False),
    ],
)
def test_history_update_pending(
    m_getenv: Mock,
    m_file_exists: Mock,
    env_version: Optional[str],
    files: List[str],
    expected: bool,
):
    m_getenv.return_value = env_version
    m_file_exists.add_existing_files(*files)
    assert migration.history_update_pending() is expected
    m_getenv.assert_called_with(const.ENV_KEY_CFG_VERSION)


@pytest.mark.parametrize(
    'version, files, expected',
    [
        ('0.11.0', ['./victoria'], True),
        ('0.11.0', ['./victoria-legacy'], True),
        # Moved by an update that did not finish
        ('0.11.0', ['./victoria', './victoria-legacy', './victoria-dense'], True),
        # A restored older .env
        ('0.11.0', ['./victoria', './victoria-dense'], False),
        ('0.11.0', [], False),
        ('0.12.0', ['./victoria'], False),
        ('0.12.0', ['./victoria', './victoria-legacy', './victoria-dense'], False),
    ],
)
def test_history_migration_pending(m_file_exists: Mock, version: str, files: List[str], expected: bool):
    m_file_exists.add_existing_files(*files)
    assert migration.history_migration_pending(Version(version)) is expected


def test_check_legacy_movable(m_is_mount: Mock, m_is_symlink: Mock, m_confirm: Mock, m_sh: Mock, m_warn: Mock):
    migration.check_legacy_movable()
    m_is_mount.assert_called_once_with('./victoria')
    m_is_symlink.assert_called_once_with('./victoria')
    assert m_confirm.call_count == 0
    assert m_warn.call_count == 0
    assert m_sh.call_count == 0


def test_check_legacy_movable_mount(m_is_mount: Mock, m_confirm: Mock, m_error: Mock, m_sh: Mock):
    m_is_mount.return_value = True
    with pytest.raises(SystemExit) as exc:
        migration.check_legacy_movable()
    assert exc.value.code == 1
    assert 'mount point' in m_error.call_args_list[0][0][0]
    assert any('./victoria-legacy' in c[0][0] for c in m_error.call_args_list[1:])
    assert m_confirm.call_count == 0
    assert m_sh.call_count == 0


@pytest.mark.parametrize('accept', [True, False])
def test_check_legacy_movable_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    m_is_symlink: Mock,
    m_confirm: Mock,
    m_warn: Mock,
    m_sh: Mock,
    accept: bool,
):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / 'disk' / 'victoria'
    target.mkdir(parents=True)
    (tmp_path / 'victoria').symlink_to(target, target_is_directory=True)
    m_is_symlink.return_value = True
    m_confirm.return_value = accept

    if accept:
        migration.check_legacy_movable()
    else:
        with pytest.raises(SystemExit) as exc:
            migration.check_legacy_movable()
        assert exc.value.code == 1

    m_confirm.assert_called_once_with('Do you want to continue?', default=False)
    warnings = messages(m_warn)
    assert os.path.realpath(target) in warnings[0]
    assert os.path.realpath(target) in warnings[1]
    assert os.getcwd() in warnings[2]
    assert m_sh.call_count == 0


def test_move_legacy_history(m_sh: Mock):
    migration.move_legacy_history()
    m_sh.assert_called_once_with('mv ./victoria ./victoria-legacy')


def test_disk_usage(tmp_path: Path):
    write_partition(tmp_path, 'small', '2019_03', 50_000)
    partition = write_partition(tmp_path, 'small', '2019_03', 70_000)
    total = migration._disk_usage(str(partition))
    assert total == file_blocks(partition)
    assert total >= 120_000


def test_disk_usage_sparse(tmp_path: Path):
    """Bytes on disk, not file sizes"""
    with open(tmp_path / 'sparse.bin', 'wb') as f:
        f.truncate(100 * MiB)
    assert migration._disk_usage(str(tmp_path)) < MiB


@pytest.mark.skipif(os.geteuid() == 0, reason='root reads every directory')
def test_disk_usage_unreadable(tmp_path: Path):
    partition = write_partition(tmp_path, 'small', '2019_03', 1000)
    part = next(partition.iterdir())
    part.chmod(0)
    try:
        with pytest.raises(PermissionError):
            migration._disk_usage(str(partition))
    finally:
        part.chmod(0o755)


def test_legacy_months(tmp_path: Path, m_sh: Mock):
    legacy = tmp_path / 'victoria-legacy'
    small_2019_03 = write_partition(legacy, 'small', '2019_03', 5_000)
    big_2019_03 = write_partition(legacy, 'big', '2019_03', 200_000)
    small_2019_12 = write_partition(legacy, 'small', '2019_12', 7_000)
    big_2020_01 = write_partition(legacy, 'big', '2020_01', 9_000)
    # Not partitions
    for name in ['snapshots', '2019_13', '2019_00', '2019_3', '19_03', 'x2019_04', '2019_04x']:
        write_partition(legacy, 'small', name, 1_000)
    (legacy / 'data' / 'small' / '2019_05').write_bytes(b'a file, not a directory')
    (legacy / 'data' / 'big' / '2019_06').symlink_to(small_2019_03, target_is_directory=True)
    write_partition(legacy, 'indexdb', '2019_07', 1_000)

    months = migration.legacy_months(str(legacy))
    assert type(months) is dict
    assert months == {
        utc(2019, 3, 1): file_blocks(small_2019_03) + file_blocks(big_2019_03),
        utc(2019, 12, 1): file_blocks(small_2019_12),
        utc(2020, 1, 1): file_blocks(big_2020_01),
    }
    assert min(months.values()) > 0
    assert m_sh.call_count == 0


def test_legacy_months_missing(tmp_path: Path, m_sh: Mock):
    legacy = tmp_path / 'victoria-legacy'
    assert migration.legacy_months(str(legacy)) == {}
    (legacy / 'data').mkdir(parents=True)
    assert migration.legacy_months(str(legacy)) == {}
    (legacy / 'data' / 'small' / 'snapshots').mkdir(parents=True)
    assert migration.legacy_months(str(legacy)) == {}
    assert m_sh.call_count == 0


DU_CMD = (
    "sudo sh -c 'for d in ./victoria-legacy/data/small/*/ ./victoria-legacy/data/big/*/; "
    + 'do [ -d "$d" ] && du -sk "$d"; done; true\''
)
DU_OUTPUT = '\n'.join(
    [
        '1024\t./victoria-legacy/data/small/2019_03',
        '2048\t./victoria-legacy/data/big/2019_03',
        '4\t./victoria-legacy/data/small/snapshots',
        '8\t./victoria-legacy/data/small/2019_13',
        '8\t./victoria-legacy/data/small/2019_00',
        '16\t./victoria-legacy/data/small/2019_3',
        '32\t./victoria-legacy/data/small/2020_01',
        '64\t./victoria-legacy/data/big/2019_12',
        '128\t./victoria-legacy/indexdb/2019_11',
        '',
    ]
)
DU_MONTHS = {
    utc(2019, 3, 1): 3072 * 1024,
    utc(2019, 12, 1): 64 * 1024,
    utc(2020, 1, 1): 32 * 1024,
}


def test_legacy_months_sudo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture, m_sh_read: Mock, m_error: Mock
):
    monkeypatch.chdir(tmp_path)
    write_partition(tmp_path / 'victoria-legacy', 'small', '2019_03', 1000)
    mocker.patch(TESTED + '._disk_usage', side_effect=PermissionError(13, 'Permission denied'))
    m_sh_read.return_value = DU_OUTPUT

    assert migration.legacy_months('./victoria-legacy') == DU_MONTHS
    m_sh_read.assert_called_once_with(DU_CMD)

    # No partitions
    m_sh_read.return_value = ''
    assert migration.legacy_months('./victoria-legacy') == {}

    # sudo failed: unknown is not empty
    m_sh_read.side_effect = CalledProcessError(1, 'sudo')
    with pytest.raises(SystemExit):
        migration.legacy_months('./victoria-legacy')
    assert 'Failed to read' in m_error.call_args[0][0]


@pytest.mark.skipif(os.geteuid() == 0, reason='root reads every directory')
def test_legacy_months_unreadable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, m_sh_read: Mock):
    """Months read before the error are not counted twice"""
    monkeypatch.chdir(tmp_path)
    legacy = tmp_path / 'victoria-legacy'
    write_partition(legacy, 'small', '2019_03', 1000)
    write_partition(legacy, 'big', '2019_03', 1000)
    big = legacy / 'data' / 'big'
    big.chmod(0)
    m_sh_read.return_value = DU_OUTPUT
    try:
        months = migration.legacy_months('./victoria-legacy')
    finally:
        big.chmod(0o755)
    assert months == DU_MONTHS
    m_sh_read.assert_called_once_with(DU_CMD)


@pytest.mark.parametrize('vanished', ['file', 'part'])
def test_legacy_months_vanished(tmp_path: Path, mocker: MockerFixture, m_sh: Mock, vanished: str):
    """
    Before the update, the legacy database still runs: it merges the parts of the current month,
    and removes the merged ones. Files that disappear during the scan are not counted.
    """
    legacy = tmp_path / 'victoria'
    partition = write_partition(legacy, 'small', '2026_09', 8000)
    gone = partition / 'merged'
    gone.mkdir()
    (gone / 'values.bin').write_bytes(os.urandom(5000))
    expected = file_blocks(partition) - (file_blocks(gone) if vanished == 'part' else 0)
    gone_file = gone / 'values.bin'
    if vanished == 'file':
        expected -= gone_file.lstat().st_blocks * 512

    real_lstat = os.lstat
    real_scandir = os.scandir

    def lstat(path, *args, **kwargs):
        if vanished == 'file' and Path(path) == gone_file:
            raise FileNotFoundError(2, 'No such file or directory', str(path))
        return real_lstat(path, *args, **kwargs)

    def scandir(path='.', *args, **kwargs):
        if vanished == 'part' and Path(path) == gone:
            raise FileNotFoundError(2, 'No such file or directory', str(path))
        return real_scandir(path, *args, **kwargs)

    mocker.patch.object(os, 'lstat', lstat)
    mocker.patch.object(os, 'scandir', scandir)

    assert migration.legacy_months(str(legacy)) == {utc(2026, 9, 1): expected}


SIZES = {
    utc(2019, 3, 1): 1000,
    utc(2019, 12, 1): 2000,
    utc(2020, 1, 1): 4000,
}


def test_dense_space():
    assert migration.dense_space(SIZES) == 6000
    assert migration.dense_space({utc(2019, 3, 1): 1000}) == 1000
    assert migration.dense_space({}) == 0
    # The newest two months, whatever their order or size
    assert migration.dense_space({utc(2020, 1, 1): 4, utc(2019, 3, 1): 1000, utc(2019, 12, 1): 2}) == 6


@pytest.mark.parametrize(
    'earliest, averaged',
    [
        (utc(2019, 1, 1), 7000),
        (utc(2019, 3, 1), 7000),
        (utc(2019, 3, 31, 23, 59), 7000),
        (utc(2019, 4, 1), 6000),
        (utc(2019, 12, 31), 6000),
        (utc(2020, 1, 1), 4000),
        (utc(2020, 1, 15), 4000),
        (utc(2020, 2, 1), 0),
    ],
)
def test_averages_space(earliest: datetime, averaged: int):
    assert migration.averages_space(SIZES, earliest) == pytest.approx(0.15 * averaged)


def test_migration_space():
    assert migration.migration_space(SIZES, None) == 6000 + GiB
    assert migration.migration_space(SIZES, utc(2019, 3, 1)) == 6000 + 1050 + GiB
    assert migration.migration_space(SIZES, utc(2020, 1, 1)) == 6000 + 600 + GiB
    # Rounded up to whole bytes
    assert migration.migration_space({utc(2019, 3, 1): 1001}, utc(2019, 3, 1)) == 1001 + 151 + GiB
    assert isinstance(migration.migration_space(SIZES, utc(2019, 3, 1)), int)


def test_choose_migration_fits(m_now: Mock, m_select: Mock, m_warn: Mock, m_free_disk_bytes: Mock, capsys):
    assert migration.choose_migration(HISTORY) == utc(2020, 1, 1)

    m_free_disk_bytes.return_value = need_bytes(81)
    assert migration.choose_migration(HISTORY) == utc(2020, 1, 1)

    assert m_select.call_count == 0
    assert m_warn.call_count == 0
    assert capsys.readouterr().out == ''


def choice_lines(out: str) -> List[str]:
    return [line for line in out.splitlines() if line[:1].isdigit()]


def test_choose_migration_abort(
    m_now: Mock,
    m_select: Mock,
    m_free_disk_bytes: Mock,
    m_warn: Mock,
    m_info: Mock,
    m_error: Mock,
    m_sh: Mock,
    capsys,
):
    m_free_disk_bytes.return_value = 5 * GiB
    m_select.return_value = '0'
    with pytest.raises(SystemExit) as exc:
        migration.choose_migration(HISTORY, update=True)
    assert exc.value.code == 1

    m_select.assert_called_once_with('What do you want to do?', '0')
    warning = m_warn.call_args_list[0][0][0]
    assert 'since 2020-01-01' in warning
    assert migration.format_bytes(need_bytes(81)) in warning
    assert '5.0 GB is free' in warning
    # Two years do not fit
    assert choice_lines(capsys.readouterr().out) == [
        '0) Abort, and change nothing',
        f'1) Migrate the last year, since 2025-09-26 ({migration.format_bytes(need_bytes(13))}). '
        + 'Older history is lost.',
        f'2) Migrate the last 6 months, since 2026-03-27 ({migration.format_bytes(need_bytes(7))}). '
        + 'Older history is lost.',
        f'3) Migrate nothing, and only log new history ({migration.format_bytes(need_bytes(0))}). '
        + 'You can migrate later.',
    ]
    m_info.assert_called_once_with('Aborted: nothing changed. Free some disk space, and try again.')
    assert m_error.call_count == 0
    assert m_sh.call_count == 0


@pytest.mark.parametrize(
    'free, answer, expected',
    [
        (5 * GiB, '1', NOW - timedelta(days=365)),
        (5 * GiB, ' 2 ', NOW - timedelta(days=183)),
        (5 * GiB, '3', None),
        (7 * GiB, '1', NOW - timedelta(days=730)),
        (7 * GiB, '2', NOW - timedelta(days=365)),
        (7 * GiB, '4', None),
        (need_bytes(81) - 1, '1', NOW - timedelta(days=730)),
    ],
)
def test_choose_migration_choice(
    m_now: Mock,
    m_select: Mock,
    m_free_disk_bytes: Mock,
    free: int,
    answer: str,
    expected: Optional[datetime],
):
    m_free_disk_bytes.return_value = free
    m_select.return_value = answer
    assert migration.choose_migration(HISTORY, update=True) == expected
    assert m_select.call_count == 1


def test_choose_migration_not_update(m_now: Mock, m_select: Mock, m_free_disk_bytes: Mock, capsys):
    # Outside the update, migrating nothing is the same as aborting
    m_free_disk_bytes.return_value = 5 * GiB
    m_select.return_value = '3'
    with pytest.raises(SystemExit):
        migration.choose_migration(HISTORY)
    assert 'Migrate nothing' not in capsys.readouterr().out
    assert m_select.call_count == migration.MAX_ANSWERS


def test_choose_migration_invalid(m_now: Mock, m_select: Mock, m_free_disk_bytes: Mock, capsys):
    m_free_disk_bytes.return_value = 5 * GiB
    m_select.side_effect = ['', 'x', '4', '-1', '1']
    assert migration.choose_migration(HISTORY, update=True) == NOW - timedelta(days=365)
    assert m_select.call_count == 5
    assert capsys.readouterr().out.count('Please type a number from 0 to 3, and press ENTER.') == 4

    # It gives up after a few invalid answers
    m_select.side_effect = None
    m_select.return_value = 'x'
    with pytest.raises(SystemExit):
        migration.choose_migration(HISTORY, update=True)


def test_choose_migration_windows_after_first(m_now: Mock, m_select: Mock, m_free_disk_bytes: Mock, capsys):
    """A window that starts before the first month would migrate everything"""
    months = monthly(utc(2026, 1, 1), utc(2026, 9, 1), GiB)
    m_free_disk_bytes.return_value = need_bytes(9) - 1
    m_select.return_value = '0'
    with pytest.raises(SystemExit):
        migration.choose_migration(months, update=True)
    assert choice_lines(capsys.readouterr().out) == [
        '0) Abort, and change nothing',
        f'1) Migrate the last 6 months, since 2026-03-27 ({migration.format_bytes(need_bytes(7))}). '
        + 'Older history is lost.',
        f'2) Migrate nothing, and only log new history ({migration.format_bytes(need_bytes(0))}). '
        + 'You can migrate later.',
    ]


def test_choose_migration_nothing_fits(
    m_now: Mock,
    m_select: Mock,
    m_free_disk_bytes: Mock,
    m_error: Mock,
    capsys,
):
    m_free_disk_bytes.return_value = need_bytes(0) - GiB // 2
    with pytest.raises(SystemExit) as exc:
        migration.choose_migration(HISTORY, update=True)
    assert exc.value.code == 1
    m_error.assert_called_once_with('Free at least 512 MB of disk space, and try again. Nothing changed.')

    # Outside the update, the shortest migration counts
    m_error.reset_mock()
    with pytest.raises(SystemExit):
        migration.choose_migration(HISTORY)
    need = need_bytes(7) - (need_bytes(0) - GiB // 2)
    m_error.assert_called_once_with(
        f'Free at least {migration.format_bytes(need)} of disk space, and try again. Nothing changed.'
    )
    assert m_select.call_count == 0
    assert choice_lines(capsys.readouterr().out) == []


@pytest.mark.parametrize(
    'phase, done, total, remaining, dense',
    [
        ('walk', 250, 1000, 0.75, False),
        ('walk', None, 1000, 1, False),
        ('walk', 0, 0, 1, False),
        ('walk', 1000, 1000, 0, False),
        ('walk', 1200, 1000, 0, False),  # a recount may differ
        ('seed', None, 1000, 1, True),
    ],
)
def test_check_resume_space(
    m_free_disk_bytes: Mock,
    m_warn: Mock,
    phase: str,
    done: Optional[int],
    total: int,
    remaining: float,
    dense: bool,
):
    # The stored earliest counts: 13 months since 2025-09, not all 81
    status = make_status(phase=phase, earliest=ts(2025, 9, 1), chunks_done=done, chunks_total=total)
    need = math.ceil(0.15 * (13 * GiB) * remaining + (2 * GiB if dense else 0) + GiB)

    m_free_disk_bytes.return_value = need
    assert migration.check_resume_space(HISTORY, status) is True
    assert m_warn.call_count == 0

    m_free_disk_bytes.return_value = need - 1
    assert migration.check_resume_space(HISTORY, status) is False
    assert migration.format_bytes(need) in m_warn.call_args_list[0][0][0]
    m_warn.assert_called_with(f'    {migration.DISCARD_CMD}')


def test_check_free_memory(m_available_memory_bytes: Mock, m_warn: Mock):
    assert migration.check_free_memory() is True
    m_available_memory_bytes.return_value = 250 * MiB
    assert migration.check_free_memory() is True
    assert m_warn.call_count == 0

    m_available_memory_bytes.return_value = 250 * MiB - 1
    assert migration.check_free_memory() is False
    assert '250 MB' in m_warn.call_args_list[0][0][0]
    m_warn.assert_called_with('Stop other programs or services to free memory, and try again.')


@pytest.mark.parametrize(
    'retention, earliest, expected',
    [
        ('100y', utc(2019, 3, 1), utc(2019, 3, 1)),
        ('30d', utc(2019, 3, 1), NOW - timedelta(days=30) + timedelta(days=1)),
        ('30d', NOW - timedelta(days=10), NOW - timedelta(days=10)),
        ('30d', NOW - timedelta(days=29), NOW - timedelta(days=29)),
        ('1y', utc(2019, 3, 1), NOW - timedelta(days=364)),
        ('12', utc(2019, 3, 1), NOW - timedelta(days=12 * 31 - 1)),
        ('10000y', utc(2019, 3, 1), utc(2019, 3, 1)),
        ('10000y', utc(1, 1, 1), utc(1, 1, 1)),
    ],
)
def test_clamp_earliest(m_now: Mock, retention: str, earliest: datetime, expected: datetime):
    utils.get_config().victoria.retention = retention
    assert migration.clamp_earliest(earliest) == expected


def test_request(m_request: Mock, m_sleep: Mock):
    m_request.return_value = response(200)
    assert migration._request('GET') is m_request.return_value
    m_request.assert_called_once_with('GET', MIGRATE_URL, timeout=30)

    m_request.reset_mock()
    migration._request('POST', retries=3, timeout=300, json={'dense_days': 30})
    m_request.assert_called_once_with('POST', MIGRATE_URL, timeout=300, json={'dense_days': 30})
    assert m_sleep.call_count == 0


def test_request_retry_5xx(m_request: Mock, m_sleep: Mock):
    responses = [response(503), response(500), response(200)]
    m_request.side_effect = responses
    assert migration._request('DELETE', retries=5, params={'discard': 'true'}) is responses[2]
    assert m_request.call_count == 3
    assert m_sleep.call_args_list == [call(migration.HTTP_RETRY_DELAY)] * 2

    # The last answer, when all failed
    responses = [response(503), response(502), response(500)]
    m_request.reset_mock()
    m_sleep.reset_mock()
    m_request.side_effect = responses
    assert migration._request('GET', retries=2) is responses[2]
    assert m_request.call_count == 3
    assert m_sleep.call_count == 2

    # No retries
    responses = [response(503)]
    m_request.reset_mock()
    m_sleep.reset_mock()
    m_request.side_effect = responses
    assert migration._request('GET') is responses[0]
    assert m_sleep.call_count == 0


def test_request_retry_exception(m_request: Mock, m_sleep: Mock):
    ok = response(200)
    m_request.side_effect = [requests.ConnectionError('refused'), requests.Timeout('slow'), ok]
    assert migration._request('GET', retries=2) is ok
    assert m_sleep.call_count == 2

    m_request.reset_mock()
    m_sleep.reset_mock()
    m_request.side_effect = [
        response(503),
        requests.ConnectionError('refused'),
        requests.ConnectionError('still refused'),
    ]
    with pytest.raises(requests.ConnectionError, match='still refused'):
        migration._request('GET', retries=2)
    assert m_request.call_count == 3
    assert m_sleep.call_count == 2

    m_request.reset_mock()
    m_sleep.reset_mock()
    m_request.side_effect = [requests.ConnectionError('refused')]
    with pytest.raises(requests.ConnectionError):
        migration._request('GET')
    assert m_sleep.call_count == 0


@pytest.mark.parametrize('status', [400, 404, 409, 422])
def test_request_no_retry_4xx(m_request: Mock, m_sleep: Mock, status: int):
    resp = response(status, {'detail': 'refused'})
    m_request.side_effect = [resp]
    assert migration._request('POST', retries=5) is resp
    assert m_request.call_count == 1
    assert m_sleep.call_count == 0


@httpretty.activate(allow_net_connect=False)
def test_request_http(m_sleep: Mock):
    httpretty.register_uri(
        httpretty.GET,
        MIGRATE_URL,
        responses=[
            httpretty.Response(body='{}', status=503),
            httpretty.Response(body='null', status=200),
        ],
    )
    resp = migration._request('GET', retries=1)
    assert resp.status_code == 200
    assert resp.json() is None
    assert m_sleep.call_count == 1


def test_raise_for_status():
    for status in [200, 201, 204, 302, 399]:
        migration._raise_for_status(response(status))

    with pytest.raises(migration.MigrationConflictError) as exc:
        migration._raise_for_status(response(409, {'detail': 'The migration is running'}))
    assert str(exc.value) == 'The migration is running'

    with pytest.raises(migration.MigrationConflictError) as exc:
        migration._raise_for_status(response(409, {'error': 'other'}))
    assert str(exc.value) == '{"error": "other"}'

    for status in [400, 404, 422, 500, 503]:
        resp = response(status, {'error': 'boom', 'details': 'oops'})
        with pytest.raises(requests.HTTPError) as exc:
            migration._raise_for_status(resp)
        assert exc.value.response is resp
        assert str(status) in str(exc.value)
        assert 'boom' in str(exc.value)
        assert not isinstance(exc.value, migration.MigrationConflictError)


@httpretty.activate(allow_net_connect=False)
def test_migration_status(m_sleep: Mock):
    httpretty.register_uri(httpretty.GET, MIGRATE_URL, body='null')
    assert migration.migration_status() is None

    status = make_status()
    httpretty.register_uri(httpretty.GET, MIGRATE_URL, body=json.dumps(status))
    assert migration.migration_status() == status
    assert httpretty.last_request().method == 'GET'

    httpretty.register_uri(httpretty.GET, MIGRATE_URL, status=500, body=json.dumps({'error': 'x', 'details': 'y'}))
    with pytest.raises(requests.HTTPError):
        migration.migration_status()
    assert m_sleep.call_count == 0


@httpretty.activate(allow_net_connect=False)
def test_discard_migration(m_sleep: Mock, m_show_data: Mock):
    httpretty.register_uri(httpretty.DELETE, MIGRATE_URL, body='null')
    migration.discard_migration()
    req = httpretty.last_request()
    assert req.method == 'DELETE'
    assert req.path == '/history/timeseries/migrate?discard=true'
    assert req.querystring == {'discard': ['true']}
    m_show_data.assert_called_once_with(f'DELETE {MIGRATE_URL}?discard=true', '')


@httpretty.activate(allow_net_connect=False)
def test_discard_migration_retries(m_sleep: Mock):
    httpretty.register_uri(
        httpretty.DELETE,
        MIGRATE_URL,
        responses=[
            httpretty.Response(body='', status=503),
            httpretty.Response(body='', status=502),
            httpretty.Response(body='null', status=200),
        ],
    )
    migration.discard_migration(retries=2)
    assert m_sleep.call_count == 2

    # Without retries, a failure raises
    httpretty.reset()
    httpretty.register_uri(httpretty.DELETE, MIGRATE_URL, status=503, body='')
    with pytest.raises(requests.HTTPError):
        migration.discard_migration()
    assert m_sleep.call_count == 2

    httpretty.reset()
    httpretty.register_uri(httpretty.DELETE, MIGRATE_URL, status=500, body='')
    with pytest.raises(requests.HTTPError):
        migration.discard_migration(retries=2)
    assert m_sleep.call_count == 4


@httpretty.activate(allow_net_connect=False)
def test_discard_migration_dry_run(m_show_data: Mock):
    utils.get_opts().dry_run = True
    migration.discard_migration(retries=30)
    assert httpretty.latest_requests() == []
    m_show_data.assert_called_once_with(f'DELETE {MIGRATE_URL}?discard=true', '')


START_BODY = {
    'source_url': 'http://victoria-legacy:8428/victoria-legacy',
    'earliest': '2019-03-01T00:00:00+00:00',
    'dense_days': 30,
}


@httpretty.activate(allow_net_connect=False)
def test_start_migration(m_sleep: Mock):
    status = make_status(phase='seed', chunks_done=None)
    httpretty.register_uri(httpretty.POST, MIGRATE_URL, body=json.dumps(status))
    assert migration.start_migration(utc(2019, 3, 1), 30) == status

    req = httpretty.last_request()
    body = json.loads(req.body)
    assert body == START_BODY
    assert datetime.fromisoformat(body['earliest']) == utc(2019, 3, 1)
    assert datetime.fromisoformat(body['earliest']).utcoffset() == timedelta(0)
    assert req.headers['Content-Type'] == 'application/json'
    assert m_sleep.call_count == 0


def test_start_migration_request(m_request: Mock):
    m_request.return_value = response(200, make_status())
    migration.start_migration(utc(2019, 3, 1), 7)
    m_request.assert_called_once_with(
        'POST',
        MIGRATE_URL,
        timeout=migration.START_TIMEOUT,
        json={**START_BODY, 'dense_days': 7},
    )


@httpretty.activate(allow_net_connect=False)
def test_start_migration_retries(m_sleep: Mock):
    """Right after the update, the legacy database may need a while to open"""
    error = json.dumps({'error': 'ConnectError', 'details': 'victoria-legacy'})
    httpretty.register_uri(
        httpretty.POST,
        MIGRATE_URL,
        responses=[
            httpretty.Response(body=error, status=500),
            httpretty.Response(body=error, status=500),
            httpretty.Response(body=json.dumps(make_status()), status=200),
        ],
    )
    assert migration.start_migration(utc(2019, 3, 1), 30) == make_status()
    assert m_sleep.call_count == 2


@httpretty.activate(allow_net_connect=False)
def test_start_migration_conflict(m_sleep: Mock):
    httpretty.register_uri(
        httpretty.POST,
        MIGRATE_URL,
        status=409,
        body=json.dumps({'detail': 'The migration is done'}),
    )
    with pytest.raises(migration.MigrationConflictError, match='The migration is done'):
        migration.start_migration(utc(2019, 3, 1), 30)
    assert m_sleep.call_count == 0


@httpretty.activate(allow_net_connect=False)
def test_start_migration_dry_run(m_show_data: Mock):
    utils.get_opts().dry_run = True
    assert migration.start_migration(utc(2019, 3, 1), 30) is None
    assert httpretty.latest_requests() == []
    m_show_data.assert_called_once_with(f'POST {MIGRATE_URL}', START_BODY)


LOST = [ts(2020, 1, 1) + 3600 * i for i in range(1, 26)]
MISSING = [f'spark-one/sensor-{i}/value[degC]' for i in range(22)]


def test_print_migration_losses(capsys):
    migration.print_migration_losses(make_status(lost_chunks=LOST, missing_series=MISSING))
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == '25 periods of 1 h could not be migrated:'
    assert lines[1] == '    the period ending 2020-01-01 01:00'
    assert lines[20] == '    the period ending 2020-01-01 20:00'
    assert lines[21] == '    ... and 5 more periods'
    assert lines[22] == '22 fields could not be migrated:'
    assert lines[23] == '    spark-one/sensor-0/value[degC]'
    assert lines[42] == '    spark-one/sensor-19/value[degC]'
    assert lines[43] == '    ... and 2 more fields'
    assert len(lines) == 44

    migration.print_migration_losses(make_status(lost_chunks=LOST[:2], missing_series=MISSING[:2]), limit=2)
    assert capsys.readouterr().out.splitlines() == [
        '2 periods of 1 h could not be migrated:',
        '    the period ending 2020-01-01 01:00',
        '    the period ending 2020-01-01 02:00',
        '2 fields could not be migrated:',
        '    spark-one/sensor-0/value[degC]',
        '    spark-one/sensor-1/value[degC]',
    ]

    migration.print_migration_losses(make_status(lost_chunks=LOST[:3], missing_series=MISSING[:1]), limit=2)
    assert capsys.readouterr().out.splitlines() == [
        '3 periods of 1 h could not be migrated:',
        '    the period ending 2020-01-01 01:00',
        '    the period ending 2020-01-01 02:00',
        '    ... and 1 more periods',
        '1 field could not be migrated:',
        '    spark-one/sensor-0/value[degC]',
    ]

    # Without the period size
    migration.print_migration_losses({'lost_chunks': LOST[:1]})
    migration.print_migration_losses({'chunk': 90, 'lost_chunks': LOST[:1]})
    assert capsys.readouterr().out.splitlines() == [
        '1 period could not be migrated:',
        '    the period ending 2020-01-01 01:00',
        '1 period of 90 s could not be migrated:',
        '    the period ending 2020-01-01 01:00',
    ]

    migration.print_migration_losses(make_status())
    migration.print_migration_losses({})
    assert capsys.readouterr().out.splitlines() == ['Every field was migrated, with no gaps.'] * 2


RUNNING_SINCE = 'The history migration (started at 2026-09-26 10:00) is averaging history since 2019-03-01'
SEEDING = (
    'The history migration (started at 2026-09-26 10:00) is copying '
    'the last {} days of raw history into the dense database.'
)
DONE_SINCE = 'The history migration is done. It migrated history since 2019-03-01'
RESUMING = ['The history service is resuming the migration. Ask again in a minute.']


@pytest.mark.parametrize(
    'status, expected',
    [
        (
            None,
            [
                'There is no history migration. To start it, run:',
                f'    {migration.MIGRATE_CMD}',
                'If the history service just started, and a migration ran before, ask again in a minute.',
                'If a migration ran before, and the history service cannot read it, discard it with:',
                f'    {migration.DISCARD_CMD}',
            ],
        ),
        (make_status(phase='seed', chunks_done=None), [SEEDING.format(30)]),
        (
            make_status(phase='seed', dense_days=7, chunks_done=None, last_error='ReadTimeout(slow)'),
            [SEEDING.format(7), 'It tries again after an error: ReadTimeout(slow)'],
        ),
        (make_status(chunks_done=None), [f'{RUNNING_SINCE}: counting the periods already done.']),
        (make_status(chunks_done=0, chunks_total=0), [f'{RUNNING_SINCE}: counting the periods already done.']),
        (make_status(chunks_done=0), [f'{RUNNING_SINCE}: 0 of 1000 periods done (0%).']),
        (make_status(chunks_done=250), [f'{RUNNING_SINCE}: 250 of 1000 periods done (25%).']),
        (make_status(chunks_done=999), [f'{RUNNING_SINCE}: 999 of 1000 periods done (99%).']),
        (
            make_status(chunks_done=250, last_error='ConnectError(victoria)'),
            [
                f'{RUNNING_SINCE}: 250 of 1000 periods done (25%).',
                'It tries again after an error: ConnectError(victoria)',
            ],
        ),
        (
            make_status(
                phase='done',
                running=False,
                chunks_done=998,
                finished=FINISHED,
                lost_chunks=LOST[:2],
                missing_series=['spark-one/old/value'],
            ),
            [
                f'{DONE_SINCE}, and finished at 2026-09-27 08:15.',
                '2 periods of 1 h could not be migrated:',
                '    the period ending 2020-01-01 01:00',
                '    the period ending 2020-01-01 02:00',
                '1 field could not be migrated:',
                '    spark-one/old/value',
                'Check your graphs, and then remove the legacy history with:',
                f'    {migration.REMOVE_CMD}',
            ],
        ),
        (
            make_status(phase='done', running=False, chunks_done=1000, finished=None),
            [
                f'{DONE_SINCE}, and finished at unknown.',
                'Every field was migrated, with no gaps.',
                'Check your graphs, and then remove the legacy history with:',
                f'    {migration.REMOVE_CMD}',
            ],
        ),
        (
            make_status(running=False, cancelled=True),
            ['The history migration was stopped. To resume it, run:', f'    {migration.MIGRATE_CMD}'],
        ),
        (
            make_status(phase='seed', running=False, cancelled=True, chunks_done=None),
            ['The history migration was stopped. To resume it, run:', f'    {migration.MIGRATE_CMD}'],
        ),
        (
            make_status(
                running=False,
                last_error='The legacy database has samples after the last one the migration found',
            ),
            [
                'The history migration stopped: '
                + 'The legacy database has samples after the last one the migration found',
                'To start again, discard it first:',
                f'    {migration.DISCARD_CMD}',
                f'    {migration.MIGRATE_CMD}',
            ],
        ),
        (make_status(running=False), RESUMING),
        (make_status(phase='seed', running=False, chunks_done=None), RESUMING),
    ],
)
def test_print_migration_status(capsys, m_file_exists: Mock, status: Optional[dict], expected: List[str]):
    m_file_exists.add_existing_files(const.VICTORIA_LEGACY_DIR)
    migration.print_migration_status(status)
    assert stdout(capsys) == expected


@pytest.mark.parametrize(
    'status, expected',
    [
        (None, ['There is no history migration, and no legacy history to migrate.']),
        (
            make_status(phase='done', running=False, chunks_done=1000, finished=FINISHED),
            [
                f'{DONE_SINCE}, and finished at 2026-09-27 08:15.',
                'Every field was migrated, with no gaps.',
                'The legacy history was removed.',
            ],
        ),
    ],
)
def test_print_migration_status_removed(capsys, status: Optional[dict], expected: List[str]):
    # After remove-legacy-history
    migration.print_migration_status(status)
    assert stdout(capsys) == expected


def stdout(capsys) -> List[str]:
    # conftest's file_exists mock prints the paths it checks
    return [v for v in capsys.readouterr().out.splitlines() if not v.startswith('Checking: ')]


def test_print_migration_started(m_info: Mock):
    migration.print_migration_started(utc(2019, 3, 1), 30)
    msgs = messages(m_info)
    assert 'Graphs fill in backwards from the update: first the last 30 days, then back to 2019-03-01.' in msgs
    assert any('in the background' in m for m in msgs)
    assert any('continues after restarts' in m for m in msgs)
    assert msgs.index(f'    {migration.STATUS_CMD}') < msgs.index(f'    {migration.REMOVE_CMD}')


@httpretty.activate(allow_net_connect=False)
def test_offer_migration(m_now: Mock, m_confirm: Mock, m_info: Mock, m_sleep: Mock):
    httpretty.register_uri(httpretty.POST, MIGRATE_URL, body=json.dumps(make_status(phase='seed')))
    m_confirm.return_value = True

    assert migration.offer_migration(utc(2019, 3, 1), 30) is True
    m_confirm.assert_called_once_with(
        'Start the history migration in the background? It migrates history since 2019-03-01.'
    )
    assert json.loads(httpretty.last_request().body) == START_BODY
    assert f'    {migration.STATUS_CMD}' in messages(m_info)


@httpretty.activate(allow_net_connect=False)
def test_offer_migration_clamped(m_now: Mock, m_confirm: Mock, m_sleep: Mock):
    utils.get_config().victoria.retention = '30d'
    httpretty.register_uri(httpretty.POST, MIGRATE_URL, body=json.dumps(make_status(phase='seed')))
    m_confirm.return_value = True

    assert migration.offer_migration(utc(2019, 3, 1), 30) is True
    # 29 days: 26.5 days of 5 s data and 2.5 days of 1 s data
    m_confirm.assert_called_once_with(
        'Start the history migration in the background? It migrates history since 2026-08-28.'
    )
    assert json.loads(httpretty.last_request().body) == {
        **START_BODY,
        'earliest': '2026-08-28T12:00:00+00:00',
    }


@httpretty.activate(allow_net_connect=False)
def test_offer_migration_declined(m_now: Mock, m_confirm: Mock, m_info: Mock):
    m_confirm.return_value = False
    assert migration.offer_migration(utc(2019, 3, 1), 30) is False
    assert httpretty.latest_requests() == []
    # The caller says what comes next
    assert m_info.call_count == 0


@httpretty.activate(allow_net_connect=False)
def test_offer_migration_dry_run(m_now: Mock, m_confirm: Mock, m_info: Mock):
    utils.get_opts().dry_run = True
    m_confirm.return_value = True
    assert migration.offer_migration(utc(2019, 3, 1), 30) is True
    assert httpretty.latest_requests() == []


def test_print_nothing_to_migrate(m_info: Mock):
    migration.print_nothing_to_migrate()
    assert './victoria-legacy holds no history' in m_info.call_args_list[0][0][0]
    m_info.assert_called_with(f'    {migration.REMOVE_CMD} --force')


def test_prepare_history_update_not_pending(mocker: MockerFixture, m_file_exists: Mock, m_is_mount: Mock):
    m_months = mocker.patch(TESTED + '.legacy_months')
    m_file_exists.add_existing_files('./victoria')
    assert migration.prepare_history_update(Version('0.12.0')) is None

    m_file_exists.add_existing_files('./victoria', './victoria-dense')
    assert migration.prepare_history_update(Version('0.11.0')) is None

    assert m_months.call_count == 0
    assert m_is_mount.call_count == 0


def test_prepare_history_update_move(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    m_now: Mock,
    m_file_exists: Mock,
    m_is_mount: Mock,
    m_is_symlink: Mock,
    m_select: Mock,
    m_sh: Mock,
):
    monkeypatch.chdir(tmp_path)
    first = write_partition(tmp_path / 'victoria', 'small', '2019_03', 4000)
    last = write_partition(tmp_path / 'victoria', 'small', '2026_09', 8000)
    m_file_exists.add_existing_files('./victoria')

    assert migration.prepare_history_update(Version('0.11.0')) == migration.LegacyHistory(
        months={utc(2019, 3, 1): file_blocks(first), utc(2026, 9, 1): file_blocks(last)},
        earliest=utc(2019, 3, 1),
    )
    m_is_mount.assert_called_once_with('./victoria')
    m_is_symlink.assert_called_once_with('./victoria')
    assert m_select.call_count == 0
    assert m_sh.call_count == 0


def test_prepare_history_update_moved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    m_file_exists: Mock,
    m_is_mount: Mock,
    m_is_symlink: Mock,
):
    """An update that did not finish moved ./victoria already"""
    monkeypatch.chdir(tmp_path)
    legacy = write_partition(tmp_path / 'victoria-legacy', 'big', '2020_01', 4000)
    write_partition(tmp_path / 'victoria', 'small', '2026_09', 1000)  # the new long-term database
    (tmp_path / 'victoria-dense').mkdir()
    m_file_exists.add_existing_files('./victoria', './victoria-legacy', './victoria-dense')

    assert migration.prepare_history_update(Version('0.11.0')) == migration.LegacyHistory(
        months={utc(2020, 1, 1): file_blocks(legacy)},
        earliest=utc(2020, 1, 1),
    )
    assert m_is_mount.call_count == 0
    assert m_is_symlink.call_count == 0


def test_prepare_history_update_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    m_file_exists: Mock,
    m_select: Mock,
    m_free_disk_bytes: Mock,
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'victoria' / 'data' / 'small' / 'snapshots').mkdir(parents=True)
    m_file_exists.add_existing_files('./victoria')

    assert migration.prepare_history_update(Version('0.11.0')) == migration.LegacyHistory(months={}, earliest=None)
    assert m_select.call_count == 0
    assert m_free_disk_bytes.call_count == 0


def test_prepare_history_update_mount(mocker: MockerFixture, m_file_exists: Mock, m_is_mount: Mock):
    m_months = mocker.patch(TESTED + '.legacy_months')
    m_is_mount.return_value = True
    m_file_exists.add_existing_files('./victoria')
    with pytest.raises(SystemExit) as exc:
        migration.prepare_history_update(Version('0.11.0'))
    assert exc.value.code == 1
    assert m_months.call_count == 0


@pytest.mark.parametrize('accept', [True, False])
def test_prepare_history_update_symlink(
    mocker: MockerFixture,
    m_file_exists: Mock,
    m_is_symlink: Mock,
    m_confirm: Mock,
    accept: bool,
):
    m_months = mocker.patch(TESTED + '.legacy_months', return_value={})
    m_is_symlink.return_value = True
    m_confirm.return_value = accept
    m_file_exists.add_existing_files('./victoria')
    if accept:
        assert migration.prepare_history_update(Version('0.11.0')) == migration.LegacyHistory({}, None)
        m_months.assert_called_once_with('./victoria')
    else:
        with pytest.raises(SystemExit):
            migration.prepare_history_update(Version('0.11.0'))
        assert m_months.call_count == 0


def test_prepare_history_update_space(
    mocker: MockerFixture,
    m_now: Mock,
    m_file_exists: Mock,
    m_free_disk_bytes: Mock,
    m_select: Mock,
    m_sh: Mock,
):
    mocker.patch(TESTED + '.legacy_months', return_value=HISTORY)
    m_file_exists.add_existing_files('./victoria')
    m_free_disk_bytes.return_value = 5 * GiB

    m_select.return_value = '2'
    assert migration.prepare_history_update(Version('0.11.0')) == migration.LegacyHistory(
        months=HISTORY,
        earliest=NOW - timedelta(days=183),
    )

    m_select.return_value = '3'
    assert migration.prepare_history_update(Version('0.11.0')) == migration.LegacyHistory(
        months=HISTORY,
        earliest=None,
    )

    m_select.return_value = '0'
    with pytest.raises(SystemExit) as exc:
        migration.prepare_history_update(Version('0.11.0'))
    assert exc.value.code == 1
    assert m_sh.call_count == 0


LEGACY = migration.LegacyHistory(
    months={utc(2019, 3, 1): GiB, utc(2026, 9, 1): GiB},
    earliest=utc(2019, 3, 1),
)
DENSE_NOTICE = (
    './victoria-dense keeps raw history for 30d, and takes up to that plus a month on disk: '
    + 'about 10 MB a day for 200 fields logged every second.'
)


def request_methods() -> List[str]:
    return [req.method for req in httpretty.latest_requests()]


@httpretty.activate(allow_net_connect=False)
def test_migrate_history_after_update(
    m_now: Mock,
    m_sleep: Mock,
    m_sh: Mock,
    m_confirm: Mock,
    m_info: Mock,
    m_warn: Mock,
):
    events = []

    def on_sh(cmd, *args, **kwargs):
        events.append(('sh', cmd))
        return DEFAULT

    def on_delete(request, uri, headers):
        events.append(('DELETE', request.querystring))
        return [200, headers, 'null']

    def on_post(request, uri, headers):
        events.append(('POST', json.loads(request.body)))
        return [200, headers, json.dumps(make_status(phase='seed', chunks_done=None))]

    def on_confirm(question, *args, **kwargs):
        events.append(('confirm', question))
        return True

    m_sh.side_effect = on_sh
    m_confirm.side_effect = on_confirm
    httpretty.register_uri(httpretty.DELETE, MIGRATE_URL, body=on_delete)
    httpretty.register_uri(httpretty.POST, MIGRATE_URL, body=on_post)

    migration.migrate_history_after_update(LEGACY)

    assert events == [
        ('sh', f'{const.CURL_WAIT} {PING_URL}'),
        ('DELETE', {'discard': ['true']}),
        ('confirm', 'Start the history migration in the background? It migrates history since 2019-03-01.'),
        ('POST', START_BODY),
    ]
    assert m_warn.call_count == 0
    msgs = messages(m_info)
    assert f'    {migration.STATUS_CMD}' in msgs
    assert msgs[0] == DENSE_NOTICE


@httpretty.activate(allow_net_connect=False)
def test_migrate_history_after_update_discard_retries(m_now: Mock, m_sleep: Mock, m_confirm: Mock, m_warn: Mock):
    httpretty.register_uri(
        httpretty.DELETE,
        MIGRATE_URL,
        responses=[
            httpretty.Response(body='', status=503),
            httpretty.Response(body='', status=502),
            httpretty.Response(body='null', status=200),
        ],
    )
    httpretty.register_uri(httpretty.POST, MIGRATE_URL, body=json.dumps(make_status(phase='seed')))
    m_confirm.return_value = True

    migration.migrate_history_after_update(LEGACY)
    assert m_sleep.call_count == 2
    assert m_confirm.call_count == 1
    assert request_methods()[-1] == 'POST'
    assert m_warn.call_count == 0


@pytest.mark.parametrize('failure', ['wait', 'server', 'connection', 'conflict'])
@httpretty.activate(allow_net_connect=False)
def test_migrate_history_after_update_discard_failed(
    mocker: MockerFixture,
    m_sleep: Mock,
    m_sh: Mock,
    m_confirm: Mock,
    m_warn: Mock,
    m_retries,
    failure: str,
):
    if failure == 'wait':
        m_sh.side_effect = CalledProcessError(7, 'curl')
    elif failure == 'server':
        httpretty.register_uri(httpretty.DELETE, MIGRATE_URL, status=500, body='{}')
    elif failure == 'connection':
        mocker.patch(TESTED + '.requests.request', side_effect=requests.ConnectionError('refused'))
    else:
        httpretty.register_uri(httpretty.DELETE, MIGRATE_URL, status=409, body='{"detail": "conflict"}')
    httpretty.register_uri(httpretty.POST, MIGRATE_URL, body=json.dumps(make_status()))

    migration.migrate_history_after_update(LEGACY)

    warnings = messages(m_warn)
    if failure == 'wait':
        assert warnings[0] == 'The history service did not answer, and the history migration did not start.'
    else:
        assert warnings[0].startswith('Failed to clear the state of an earlier history migration')
    assert warnings[-2:] == [f'    {migration.DISCARD_CMD}', f'    {migration.MIGRATE_CMD}']
    assert m_confirm.call_count == 0
    assert 'POST' not in request_methods()


@httpretty.activate(allow_net_connect=False)
def test_migrate_history_after_update_nothing(m_confirm: Mock, m_info: Mock, m_available_memory_bytes: Mock):
    httpretty.register_uri(httpretty.DELETE, MIGRATE_URL, body='null')
    migration.migrate_history_after_update(migration.LegacyHistory(months={}, earliest=None))
    assert request_methods() == ['DELETE']
    assert m_confirm.call_count == 0
    assert m_info.call_args_list[-2][0][0].startswith('./victoria-legacy holds no history')
    m_info.assert_called_with(f'    {migration.REMOVE_CMD} --force')


@httpretty.activate(allow_net_connect=False)
def test_migrate_history_after_update_not_migrated(m_confirm: Mock, m_warn: Mock):
    """The user chose to migrate nothing before the update"""
    httpretty.register_uri(httpretty.DELETE, MIGRATE_URL, body='null')
    migration.migrate_history_after_update(migration.LegacyHistory(months=LEGACY.months, earliest=None))
    assert request_methods() == ['DELETE']
    assert m_confirm.call_count == 0
    msgs = messages(m_warn)
    assert 'Graphs do not show it until it is migrated. To migrate it, run:' in msgs
    assert f'    {migration.MIGRATE_CMD}' in msgs
    assert msgs[-1] == f'    {migration.REMOVE_CMD} --force'


@httpretty.activate(allow_net_connect=False)
def test_migrate_history_after_update_memory(m_confirm: Mock, m_warn: Mock, m_available_memory_bytes: Mock):
    m_available_memory_bytes.return_value = 100 * MiB
    httpretty.register_uri(httpretty.DELETE, MIGRATE_URL, body='null')
    migration.migrate_history_after_update(LEGACY)
    assert request_methods() == ['DELETE']
    assert m_confirm.call_count == 0
    m_warn.assert_called_with(f'    {migration.MIGRATE_CMD}')


@httpretty.activate(allow_net_connect=False)
def test_migrate_history_after_update_declined(m_now: Mock, m_confirm: Mock, m_info: Mock, m_warn: Mock):
    m_confirm.return_value = False
    httpretty.register_uri(httpretty.DELETE, MIGRATE_URL, body='null')
    migration.migrate_history_after_update(LEGACY)
    assert request_methods() == ['DELETE']
    m_warn.assert_called_with(f'    {migration.MIGRATE_CMD}')
    # The dense database exists either way
    assert DENSE_NOTICE in messages(m_info)


def test_migrate_history_after_update_no_terminal(m_now: Mock, m_confirm: Mock, m_request: Mock, m_warn: Mock):
    # The update goes on, and writes its version
    m_request.return_value = response(200)
    m_confirm.side_effect = EOFError
    migration.migrate_history_after_update(LEGACY)
    m_warn.assert_called_with(f'    {migration.MIGRATE_CMD}')


@pytest.mark.parametrize(
    'status, body',
    [
        (409, {'detail': 'The migration is done'}),
        (500, {'error': 'ConnectError', 'details': 'victoria-legacy'}),
    ],
)
@httpretty.activate(allow_net_connect=False)
def test_migrate_history_after_update_start_failed(
    m_now: Mock,
    m_sleep: Mock,
    m_confirm: Mock,
    m_info: Mock,
    m_warn: Mock,
    m_retries,
    status: int,
    body: dict,
):
    m_confirm.return_value = True
    httpretty.register_uri(httpretty.DELETE, MIGRATE_URL, body='null')
    httpretty.register_uri(httpretty.POST, MIGRATE_URL, status=status, body=json.dumps(body))
    migration.migrate_history_after_update(LEGACY)

    assert 'POST' in request_methods()
    warnings = messages(m_warn)
    assert warnings[0].startswith('Failed to start the history migration')
    assert warnings[-1] == f'    {migration.MIGRATE_CMD}'
    assert f'    {migration.STATUS_CMD}' not in messages(m_info)


def test_migrate_history_after_update_start_connection(
    m_now: Mock,
    m_sleep: Mock,
    m_request: Mock,
    m_confirm: Mock,
    m_warn: Mock,
    m_retries,
):
    def request(method, *args, **kwargs):
        if method == 'DELETE':
            return response(200)
        raise requests.ConnectionError('refused')

    m_request.side_effect = request
    m_confirm.return_value = True
    migration.migrate_history_after_update(LEGACY)
    assert [c[0][0] for c in m_request.call_args_list] == ['DELETE', 'POST', 'POST', 'POST']
    assert messages(m_warn)[0].startswith('Failed to start the history migration: ConnectionError(refused)')


@httpretty.activate(allow_net_connect=False)
def test_migrate_history_after_update_dry_run(m_now: Mock, m_sh: Mock, m_confirm: Mock, m_info: Mock):
    utils.get_opts().dry_run = True
    m_confirm.return_value = True
    migration.migrate_history_after_update(LEGACY)
    assert httpretty.latest_requests() == []
    m_sh.assert_called_once_with(f'{const.CURL_WAIT} {PING_URL}', silent=True)
    assert m_confirm.call_count == 1
    assert DENSE_NOTICE in messages(m_info)


# Hardening after review


@pytest.mark.parametrize(
    'volumes, expected',
    [
        (None, []),
        ([], []),
        (['/mnt/ssd/victoria:/victoria-metrics-data'], [('docker-compose.yml', '/mnt/ssd/victoria')]),
        (['/mnt/ssd/victoria:/victoria-metrics-data:rw'], [('docker-compose.yml', '/mnt/ssd/victoria')]),
        (
            [{'type': 'bind', 'source': '/mnt/ssd', 'target': '/victoria-metrics-data'}],
            [('docker-compose.yml', '/mnt/ssd')],
        ),
        (['/etc/localtime:/etc/localtime:ro', {'source': '/x', 'target': '/other'}], []),
    ],
)
def test_history_volume_overrides(m_file_exists: Mock, m_read_yaml: Mock, volumes, expected):
    m_file_exists.add_existing_files('docker-compose.shared.yml', 'docker-compose.yml')
    service = {} if volumes is None else {'volumes': volumes}
    m_read_yaml.side_effect = lambda fname: {'services': {'victoria': service}}
    assert migration.history_volume_overrides() == expected
    # The shared file is ours
    assert [c[0][0] for c in m_read_yaml.call_args_list] == ['docker-compose.yml']


def test_history_volume_overrides_missing(m_file_exists: Mock, m_read_yaml: Mock):
    m_read_yaml.side_effect = lambda fname: None
    assert migration.history_volume_overrides() == []
    m_read_yaml.assert_not_called()
    m_file_exists.add_existing_files('docker-compose.yml')
    assert migration.history_volume_overrides() == []


def test_check_legacy_movable_override(m_file_exists: Mock, m_read_yaml: Mock, m_error: Mock, m_sh: Mock):
    """A volume in docker-compose.yml replaces ./victoria: moving the empty ./victoria would lose the history"""
    m_file_exists.add_existing_files('docker-compose.yml')
    m_read_yaml.side_effect = lambda fname: {
        'services': {'victoria': {'volumes': ['/mnt/ssd/victoria:/victoria-metrics-data']}}
    }
    with pytest.raises(SystemExit):
        migration.check_legacy_movable()
    m_error.assert_any_call('docker-compose.yml keeps the history of the `victoria` service in /mnt/ssd/victoria.')
    assert m_sh.call_count == 0


def test_detail():
    assert migration._detail(response(409, {'detail': 'The migration is running'})) == 'The migration is running'
    assert migration._detail(response(409, ['not', 'a', 'dict'])) == '["not", "a", "dict"]'
    resp = response(409)
    resp._content = b'<html>'
    assert migration._detail(resp) == '<html>'


def test_start_migration_running(m_request: Mock, m_sleep: Mock):
    """A try that started the job, but whose answer did not arrive"""
    running = make_status(phase='seed', chunks_done=None)
    m_request.side_effect = [
        requests.ReadTimeout('timed out'),
        response(409, {'detail': migration.RUNNING_DETAIL}),
        response(200, running),
    ]
    assert migration.start_migration(utc(2019, 3, 1), 30) == running
    assert [c[0][0] for c in m_request.call_args_list] == ['POST', 'POST', 'GET']


def test_start_migration_stored_source(m_request: Mock):
    m_request.return_value = response(200, make_status())
    migration.start_migration(utc(2019, 3, 1), 30, 'http://other:8428/x')
    assert m_request.call_args[1]['json']['source_url'] == 'http://other:8428/x'


def test_pull_history_images(m_sh: Mock, m_error: Mock):
    migration.pull_history_images()
    assert [c[0][0] for c in m_sh.call_args_list] == [
        f'SUDO docker pull {const.VICTORIA_IMAGE}',
        f'SUDO docker pull {const.VICTORIA_LEGACY_IMAGE}',
    ]

    m_sh.side_effect = CalledProcessError(1, 'docker pull')
    with pytest.raises(SystemExit):
        migration.pull_history_images()
    m_error.assert_called_with('Nothing changed. Fix the problem above, and run brewblox-ctl update again.')


INTERVAL_CHANGED = [
    'The history migration stopped: it started with a sparse_interval of 60s, and now it is 30s.',
    'To resume it where it stopped, set `victoria.sparse_interval` back to 60s in brewblox.yml, and run:',
    '    brewblox-ctl config apply',
    'Or discard it, and start again at 30s. The averages already made at 60s stay:',
    f'    {migration.DISCARD_CMD}',
    f'    {migration.MIGRATE_CMD}',
]


@pytest.mark.parametrize(
    'status',
    [
        make_status(running=False, last_error='The migration started with sparse_interval 60s, now it is 30s'),
        # Cancelled: a resume would be refused
        make_status(running=False, cancelled=True),
        # After a restart of history, before it wrote the reason
        make_status(running=False),
    ],
)
def test_print_migration_status_interval_changed(capsys, m_get_config, m_file_exists: Mock, status: dict):
    """Setting the interval back resumes the migration: the status offers that, and the discard"""
    m_get_config.victoria.sparse_interval = '30s'
    m_file_exists.add_existing_files(const.VICTORIA_LEGACY_DIR)
    migration.print_migration_status(status)
    assert stdout(capsys) == INTERVAL_CHANGED


def test_print_migration_status_interval_same(capsys, m_get_config, m_file_exists: Mock):
    # The other stop (the legacy database grew after a rollback): only a discard gets past it
    m_get_config.victoria.sparse_interval = '1m'
    m_file_exists.add_existing_files(const.VICTORIA_LEGACY_DIR)
    migration.print_migration_status(make_status(running=False, last_error='The legacy database has newer samples'))
    out = stdout(capsys)
    assert out[0] == 'The history migration stopped: The legacy database has newer samples'
    assert 'brewblox-ctl config apply' not in '\n'.join(out)
    assert out[-2:] == [f'    {migration.DISCARD_CMD}', f'    {migration.MIGRATE_CMD}']


def test_print_migration_status_interval_running(capsys, m_get_config, m_file_exists: Mock):
    # A running migration is not stopped, whatever the configuration says now
    m_get_config.victoria.sparse_interval = '30s'
    migration.print_migration_status(make_status())
    assert 'brewblox-ctl config apply' not in '\n'.join(stdout(capsys))


@pytest.mark.parametrize(
    'seconds, expected',
    [
        (60, 'one value per minute'),
        (3600, 'one value per hour'),
        (86400, 'one value per day'),
        (300, 'one value every 300 s'),
    ],
)
def test_format_interval(seconds: int, expected: str):
    assert migration.format_interval(seconds) == expected


def test_print_migration_losses_fields_only(capsys):
    migration.print_migration_losses({'chunk': 3600, 'missing_series': ['spark-one/a']})
    assert capsys.readouterr().out.splitlines() == ['1 field could not be migrated:', '    spark-one/a']


REMINDER = './victoria-legacy still holds your history from before configuration version 0.12.0 (about 1.0 GB).'


@pytest.fixture
def m_reminder(mocker: MockerFixture, m_file_exists: Mock):
    m_file_exists.add_existing_files(const.VICTORIA_LEGACY_DIR)
    return mocker.patch(TESTED + '.legacy_months', return_value={utc(2024, 1, 1): GiB // 2, utc(2024, 2, 1): GiB // 2})


def test_remind_legacy_history_none(m_file_exists: Mock, m_sh: Mock, m_request: Mock, m_info: Mock):
    migration.remind_legacy_history()
    m_sh.assert_not_called()
    m_request.assert_not_called()
    m_info.assert_not_called()


def test_remind_legacy_history_done(m_reminder, m_sh: Mock, m_request: Mock, m_info: Mock, capsys):
    m_request.return_value = response(200, make_status(phase='done', running=False))
    migration.remind_legacy_history()
    m_info.assert_called_once_with(REMINDER)
    # A short wait: services just started
    m_sh.assert_called_once_with(f'{migration.REMINDER_WAIT} {PING_URL}', silent=True)
    out = stdout(capsys)
    assert any(line.startswith('The history migration is done.') for line in out)
    assert out[-1] == f'    {migration.REMOVE_CMD}'


def test_remind_legacy_history_running(m_reminder, m_sh: Mock, m_request: Mock, capsys):
    m_request.return_value = response(200, make_status(chunks_done=250))
    migration.remind_legacy_history()
    assert '250 of 1000 periods done (25%)' in ' '.join(stdout(capsys))


@pytest.mark.parametrize('failure', ['wait', 'request'])
def test_remind_legacy_history_not_answering(m_reminder, m_sh: Mock, m_request: Mock, m_info: Mock, failure: str):
    if failure == 'wait':
        m_sh.side_effect = CalledProcessError(22, 'curl')
    else:
        m_request.side_effect = requests.ConnectionError('refused')
    migration.remind_legacy_history()
    assert [c.args[0] for c in m_info.call_args_list] == [
        REMINDER,
        'The history service did not answer yet. To see whether its migration is done, run:',
        f'    {migration.STATUS_CMD}',
    ]
