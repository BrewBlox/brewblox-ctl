"""
Tests brewblox_ctl.commands.database
"""

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, List, Tuple
from unittest.mock import Mock

import httpretty
import pytest
import requests
from pytest_mock import MockerFixture

from brewblox_ctl import actions, const, migration, testing
from brewblox_ctl.commands import database
from brewblox_ctl.models import CtlConfig, CtlOpts
from brewblox_ctl.testing import invoke, matching


# The real clock, before the autouse fixture replaces it
REAL_NOW = migration._now

MIGRATE_URL = 'http://localhost:9600/history/timeseries/migrate'
MIGRATE_PATH = '/history/timeseries/migrate'
DISCARD_PATH = MIGRATE_PATH + '?discard=true'
LEGACY_URL = 'http://victoria-legacy:8428/victoria-legacy'

GiB = 2**30
MiB = 2**20

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
EARLIEST = datetime(2024, 3, 1, tzinfo=timezone.utc)


def month(year: int, mon: int) -> datetime:
    return datetime(year, mon, 1, tzinfo=timezone.utc)


# Legacy partitions: 4 GiB in all.
# All history needs: dense (last two months, 2 GiB) + averages (15% of 4 GiB) + margin (1 GiB) = 3.6 GiB.
# The last 2 years (since 2024-09-26 12:00) need 3.45 GiB, the last year and 6 months 3.3 GiB, nothing 3 GiB.
MONTHS = {
    month(2024, 3): GiB,
    month(2025, 6): GiB,
    month(2026, 8): GiB,
    month(2026, 9): GiB,
}


def make_status(**kwargs) -> dict:
    """A MigrationStatus as the history service returns it"""
    status = {
        'phase': 'walk',
        'cancelled': False,
        'job': 'a1b2c3d4',
        'source_url': LEGACY_URL,
        'earliest': int(EARLIEST.timestamp()),
        'dense_days': 30,
        'sparse_interval': 60,
        'chunk': 3600,
        'legacy_last': NOW.timestamp() - 7200.5,
        'legacy_end': int(NOW.timestamp()) - 7200 + 60,
        'chunks_total': 1000,
        'started': int((NOW - timedelta(hours=2)).timestamp()),
        'finished': None,
        'lost_chunks': [],
        'missing_series': [],
        'running': True,
        'chunks_done': 250,
        'last_error': None,
    }
    status.update(kwargs)
    return status


def reply(method: str, *responses: Tuple[int, Any]):
    """The history service answers `method` requests on /migrate with these responses, in order"""
    httpretty.register_uri(
        method,
        MIGRATE_URL,
        responses=[
            httpretty.Response(body=json.dumps(body), status=status, content_type='application/json')
            for status, body in responses
        ],
    )


def sent() -> List[Tuple[str, str]]:
    return [(req.method, req.path) for req in httpretty.latest_requests()]


def posted() -> dict:
    [req] = [req for req in httpretty.latest_requests() if req.method == 'POST']
    return json.loads(req.body)


def not_answering(mocker: MockerFixture) -> Mock:
    return mocker.patch.object(
        migration.requests,
        'request',
        side_effect=requests.ConnectionError('Connection refused'),
    )


def assert_exit(result, code: int):
    """The command exited with this code, and did not fail with another exception"""
    assert isinstance(result.exception, SystemExit), repr(result.exception)
    assert result.exit_code == code


def record_sh(m_sh: Mock, events: list):
    def side_effect(cmd, *args, **kwargs):
        events.append(cmd)
        return testing.check_sudo(cmd, *args, **kwargs)

    m_sh.side_effect = side_effect


@pytest.fixture(autouse=True)
def m_http():
    httpretty.reset()
    httpretty.enable(allow_net_connect=False)
    yield
    httpretty.disable()
    httpretty.reset()


@pytest.fixture(autouse=True)
def m_now(mocker: MockerFixture):
    return mocker.patch.object(migration, '_now', return_value=NOW)


@pytest.fixture(autouse=True)
def m_sleep(mocker: MockerFixture):
    return mocker.patch.object(migration, 'sleep')


@pytest.fixture
def m_legacy_months(mocker: MockerFixture):
    return mocker.patch.object(migration, 'legacy_months', return_value=dict(MONTHS))


@pytest.fixture
def m_make_shared_compose(mocker: MockerFixture):
    return mocker.patch.object(actions, 'make_shared_compose')


@pytest.fixture
def legacy(m_file_exists: Mock):
    """./victoria-legacy exists"""
    m_file_exists.add_existing_files(const.VICTORIA_LEGACY_DIR)


def test_now():
    now = REAL_NOW()
    assert now.tzinfo == timezone.utc
    assert abs((now - datetime.now(timezone.utc)).total_seconds()) < 60


# migrate-history: refusals


def test_migrate_history_no_legacy(m_error: Mock, m_confirm: Mock):
    result = invoke(database.migrate_history, '', _err=True)
    assert_exit(result, 1)
    m_error.assert_any_call(matching(r'.*no legacy history.*\./victoria-legacy does not exist'))
    assert sent() == []
    m_confirm.assert_not_called()


def test_migrate_history_negative_dense_days(legacy):
    result = invoke(database.migrate_history, '--dense-days -1', _err=True)
    assert_exit(result, 2)
    assert sent() == []


# migrate-history: a new migration


def test_migrate_history_new(
    legacy,
    m_legacy_months: Mock,
    m_confirm: Mock,
    m_confirm_mode: Mock,
    m_select: Mock,
    m_available_memory_bytes: Mock,
    m_free_disk_bytes: Mock,
    m_info: Mock,
    m_sleep: Mock,
):
    m_confirm.return_value = True
    reply('GET', (200, None))
    reply('POST', (200, make_status(phase='seed', chunks_done=None)))

    invoke(database.migrate_history, '')

    m_confirm_mode.assert_called_once()
    m_legacy_months.assert_called_once_with('./victoria-legacy')
    m_available_memory_bytes.assert_called()
    m_free_disk_bytes.assert_called()
    m_select.assert_not_called()  # Everything fits: no question
    m_sleep.assert_not_called()

    # The confirm prompt shows the first date migrated, and an estimate
    m_confirm.assert_called_once_with(
        'Start the history migration in the background? It migrates history since 2024-03-01 (up to 2 h).'
    )

    assert sent() == [('GET', MIGRATE_PATH), ('POST', MIGRATE_PATH)]
    assert posted() == {
        'source_url': LEGACY_URL,
        'earliest': '2024-03-01T00:00:00+00:00',
        'dense_days': 30,
    }

    m_info.assert_any_call(matching(r'.*runs in the background'))
    m_info.assert_any_call('    brewblox-ctl database migrate-history --status')
    m_info.assert_any_call('    brewblox-ctl database remove-legacy-history')


@pytest.mark.parametrize('dense_days', [0, 7, 30, 90])
def test_migrate_history_dense_days(legacy, m_legacy_months: Mock, m_confirm: Mock, dense_days: int):
    m_confirm.return_value = True
    reply('GET', (200, None))
    reply('POST', (200, make_status(dense_days=dense_days)))

    invoke(database.migrate_history, f'--dense-days {dense_days}')
    assert posted()['dense_days'] == dense_days


@pytest.mark.parametrize(
    'retention, earliest',
    [
        # Long enough: the first partition
        ('100y', '2024-03-01T00:00:00+00:00'),
        # Too far back for any date
        ('3000y', '2024-03-01T00:00:00+00:00'),
        # now - retention + 1 day
        ('30d', '2026-08-28T12:00:00+00:00'),
        ('1y', '2025-09-27T12:00:00+00:00'),
        ('1w', '2026-09-20T12:00:00+00:00'),
        # A bare number counts months of 31 days
        ('2', '2026-07-27T12:00:00+00:00'),
        ('2M', '2026-07-27T12:00:00+00:00'),
    ],
)
def test_migrate_history_clamp(
    legacy,
    m_legacy_months: Mock,
    m_get_config: CtlConfig,
    m_confirm: Mock,
    retention: str,
    earliest: str,
):
    m_get_config.victoria.retention = retention
    m_confirm.return_value = True
    reply('GET', (200, None))
    reply('POST', (200, make_status()))

    invoke(database.migrate_history, '')
    assert posted()['earliest'] == earliest
    m_confirm.assert_called_once_with(matching(f'.*since {earliest[:10]} '))


def test_migrate_history_partitions(
    legacy,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    m_file_exists: Mock,
    m_confirm: Mock,
):
    monkeypatch.chdir(tmp_path)
    m_file_exists.add_existing_files(const.VICTORIA_LEGACY_DIR)
    small = tmp_path / 'victoria-legacy/data/small'
    big = tmp_path / 'victoria-legacy/data/big'
    for name in ['2023_11', '2024_01', 'snapshots', '2022_13', 'x2021_01', '2021_1']:
        (small / name).mkdir(parents=True)
        (small / name / 'data.bin').write_bytes(b'0' * 10000)
    (big / '2023_12').mkdir(parents=True)
    (small / '2022_01').write_text('not a partition')  # A file, not a directory

    m_confirm.return_value = True
    reply('GET', (200, None))
    reply('POST', (200, make_status()))

    invoke(database.migrate_history, '')
    assert posted()['earliest'] == '2023-11-01T00:00:00+00:00'


def test_migrate_history_partitions_confirm(
    legacy,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    m_file_exists: Mock,
    m_confirm: Mock,
):
    # A host clock that was once wrong leaves an early partition: the prompt shows where the migration starts
    monkeypatch.chdir(tmp_path)
    m_file_exists.add_existing_files(const.VICTORIA_LEGACY_DIR)
    for name in ['2001_01', '2025_12']:
        (tmp_path / 'victoria-legacy/data/small' / name).mkdir(parents=True)
    m_confirm.return_value = False
    reply('GET', (200, None))

    invoke(database.migrate_history, '')

    m_confirm.assert_called_once_with(matching(r'.*It migrates history since 2001-01-01 \('))


DU_OUTPUT = """8\t./victoria-legacy/data/small/2023_11
4\t./victoria-legacy/data/small/snapshots
4\t./victoria-legacy/data/small/2022_13
12\t./victoria-legacy/data/big/2023_05
16\t./victoria-legacy/data/big/2024_01
"""
DU_CMD = (
    "sudo sh -c 'for d in ./victoria-legacy/data/small/*/ ./victoria-legacy/data/big/*/; "
    + 'do [ -d "$d" ] && du -sk "$d"; done; true\''
)


def test_migrate_history_partitions_sudo(
    legacy,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
    m_file_exists: Mock,
    m_sh_read: Mock,
    m_confirm: Mock,
):
    # The database writes its partitions as root: `du` reads them with sudo
    monkeypatch.chdir(tmp_path)
    m_file_exists.add_existing_files(const.VICTORIA_LEGACY_DIR)
    (tmp_path / 'victoria-legacy/data/small/2023_11').mkdir(parents=True)
    mocker.patch.object(migration.os, 'scandir', side_effect=PermissionError(13, 'Permission denied'))
    m_sh_read.return_value = DU_OUTPUT
    m_confirm.return_value = True
    reply('GET', (200, None))
    reply('POST', (200, make_status()))

    invoke(database.migrate_history, '')

    m_sh_read.assert_any_call(DU_CMD)
    assert posted()['earliest'] == '2023-05-01T00:00:00+00:00'


@pytest.mark.skipif(os.geteuid() == 0, reason='root reads every directory')
@pytest.mark.parametrize('unreadable', ['victoria-legacy/data/small', 'victoria-legacy/data/small/2023_11'])
def test_migrate_history_partitions_unreadable(
    legacy,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    m_file_exists: Mock,
    m_sh_read: Mock,
    m_confirm: Mock,
    unreadable: str,
):
    monkeypatch.chdir(tmp_path)
    m_file_exists.add_existing_files(const.VICTORIA_LEGACY_DIR)
    (tmp_path / 'victoria-legacy/data/small/2023_11').mkdir(parents=True)
    (tmp_path / 'victoria-legacy/data/small/2023_11/part.bin').write_bytes(b'0' * 10000)
    m_sh_read.return_value = DU_OUTPUT
    m_confirm.return_value = True
    reply('GET', (200, None))
    reply('POST', (200, make_status()))

    locked = tmp_path / unreadable
    locked.chmod(0o000)
    try:
        invoke(database.migrate_history, '')
    finally:
        locked.chmod(0o755)

    m_sh_read.assert_any_call(DU_CMD)
    assert posted()['earliest'] == '2023-05-01T00:00:00+00:00'


def test_migrate_history_partitions_sudo_none(
    legacy,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mocker: MockerFixture,
    m_file_exists: Mock,
    m_sh_read: Mock,
    m_confirm: Mock,
    m_info: Mock,
):
    monkeypatch.chdir(tmp_path)
    m_file_exists.add_existing_files(const.VICTORIA_LEGACY_DIR)
    (tmp_path / 'victoria-legacy/data/small').mkdir(parents=True)
    mocker.patch.object(migration.os, 'scandir', side_effect=PermissionError(13, 'Permission denied'))
    m_sh_read.return_value = '4\t./victoria-legacy/data/small/snapshots/\n'
    reply('GET', (200, None))

    invoke(database.migrate_history, '')

    m_info.assert_any_call(matching(r'.*nothing to migrate'))
    m_confirm.assert_not_called()


def test_migrate_history_no_partitions(
    legacy,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    m_file_exists: Mock,
    m_confirm: Mock,
    m_info: Mock,
    m_available_memory_bytes: Mock,
):
    monkeypatch.chdir(tmp_path)
    m_file_exists.add_existing_files(const.VICTORIA_LEGACY_DIR)
    (tmp_path / 'victoria-legacy/data/small/snapshots').mkdir(parents=True)
    reply('GET', (200, None))

    invoke(database.migrate_history, '')

    m_info.assert_any_call(matching(r'.*holds no history: there is nothing to migrate'))
    m_info.assert_any_call('    brewblox-ctl database remove-legacy-history --force')
    assert sent() == [('GET', MIGRATE_PATH)]
    m_confirm.assert_not_called()
    m_available_memory_bytes.assert_not_called()


def test_migrate_history_nothing_to_migrate(
    legacy,
    m_legacy_months: Mock,
    m_confirm: Mock,
    m_info: Mock,
):
    m_legacy_months.return_value = {}
    reply('GET', (200, None))

    invoke(database.migrate_history, '')

    m_info.assert_any_call(matching(r'.*nothing to migrate'))
    m_info.assert_any_call('    brewblox-ctl database remove-legacy-history --force')
    assert sent() == [('GET', MIGRATE_PATH)]
    m_confirm.assert_not_called()


@pytest.mark.parametrize(
    'answers, earliest',
    [
        (['1'], '2025-09-26T12:00:00+00:00'),
        (['2'], '2026-03-27T12:00:00+00:00'),
        ([' 1 '], '2025-09-26T12:00:00+00:00'),
        (['x', '9', '', '2'], '2026-03-27T12:00:00+00:00'),
    ],
)
def test_migrate_history_space_choice(
    legacy,
    m_legacy_months: Mock,
    m_free_disk_bytes: Mock,
    m_select: Mock,
    m_confirm: Mock,
    m_warn: Mock,
    answers: List[str],
    earliest: str,
):
    m_free_disk_bytes.return_value = int(3.4 * GiB)
    m_select.side_effect = answers
    m_confirm.return_value = True
    reply('GET', (200, None))
    reply('POST', (200, make_status()))

    result = invoke(database.migrate_history, '')

    m_warn.assert_any_call(matching(r'.*since 2024-03-01\) needs 3\.6 GB of free disk space, and 3\.4 GB is free'))
    # Abort is the default. The last 2 years do not fit, and are not offered.
    assert m_select.call_count == len(answers)
    m_select.assert_called_with('What do you want to do?', '0')
    assert '0) Abort, and change nothing' in result.output
    assert '1) Migrate the last year, since 2025-09-26 (3.3 GB). Older history is lost.' in result.output
    assert '2) Migrate the last 6 months, since 2026-03-27 (3.3 GB). Older history is lost.' in result.output
    # Migrating nothing is only a choice during the update
    assert 'Migrate nothing' not in result.output
    assert '2 years' not in result.output
    assert '3)' not in result.output
    if len(answers) > 1:
        assert 'Please type a number from 0 to 2, and press ENTER.' in result.output

    assert posted()['earliest'] == earliest
    m_confirm.assert_called_once_with(matching(f'.*since {earliest[:10]} '))


def test_migrate_history_space_all_windows(
    legacy,
    m_legacy_months: Mock,
    m_free_disk_bytes: Mock,
    m_select: Mock,
    m_confirm: Mock,
):
    m_free_disk_bytes.return_value = int(3.5 * GiB)
    m_select.return_value = '1'
    m_confirm.return_value = True
    reply('GET', (200, None))
    reply('POST', (200, make_status()))

    result = invoke(database.migrate_history, '')

    assert '1) Migrate the last 2 years, since 2024-09-26 (3.5 GB)' in result.output
    assert '3) Migrate the last 6 months' in result.output
    assert 'Migrate nothing' not in result.output
    assert posted()['earliest'] == '2024-09-26T12:00:00+00:00'


def test_migrate_history_space_window_before_first(
    legacy,
    m_legacy_months: Mock,
    m_free_disk_bytes: Mock,
    m_select: Mock,
    m_confirm: Mock,
):
    # History since 2025-06: the last 2 years start before it, and are not offered
    m_legacy_months.return_value = {month(2025, 6): GiB, month(2026, 8): GiB, month(2026, 9): GiB}
    m_free_disk_bytes.return_value = int(3.35 * GiB)
    m_select.return_value = '0'
    reply('GET', (200, None))

    result = invoke(database.migrate_history, '', _err=True)

    assert_exit(result, 1)
    assert '2 years' not in result.output
    assert '1) Migrate the last year' in result.output
    m_confirm.assert_not_called()


def test_migrate_history_space_abort(
    legacy,
    m_legacy_months: Mock,
    m_free_disk_bytes: Mock,
    m_select: Mock,
    m_confirm: Mock,
    m_info: Mock,
):
    m_free_disk_bytes.return_value = int(3.4 * GiB)
    m_select.return_value = '0'
    reply('GET', (200, None))

    result = invoke(database.migrate_history, '', _err=True)

    assert_exit(result, 1)
    m_info.assert_any_call('Aborted: nothing changed. Free some disk space, and try again.')
    m_confirm.assert_not_called()
    assert sent() == [('GET', MIGRATE_PATH)]


def test_migrate_history_space_nothing(
    legacy,
    m_legacy_months: Mock,
    m_free_disk_bytes: Mock,
    m_select: Mock,
    m_confirm: Mock,
    m_info: Mock,
):
    m_free_disk_bytes.return_value = int(3.4 * GiB)
    m_select.return_value = '3'
    reply('GET', (200, None))

    result = invoke(database.migrate_history, '', _err=True)

    # Not a choice outside the update: asked again, and aborted after a few tries
    assert_exit(result, 1)
    assert m_select.call_count == migration.MAX_ANSWERS
    m_info.assert_any_call('Aborted: nothing changed. Free some disk space, and try again.')
    m_confirm.assert_not_called()
    assert sent() == [('GET', MIGRATE_PATH)]


def test_migrate_history_space_too_little(
    legacy,
    m_legacy_months: Mock,
    m_free_disk_bytes: Mock,
    m_select: Mock,
    m_confirm: Mock,
    m_error: Mock,
):
    m_free_disk_bytes.return_value = int(2.9 * GiB)
    reply('GET', (200, None))

    result = invoke(database.migrate_history, '', _err=True)

    assert_exit(result, 1)
    # The last 6 months need 3.3 GB: 0.4 GiB short
    m_error.assert_any_call('Free at least 410 MB of disk space, and try again. Nothing changed.')
    m_select.assert_not_called()
    m_confirm.assert_not_called()
    assert sent() == [('GET', MIGRATE_PATH)]


def test_migrate_history_low_memory(
    legacy,
    m_legacy_months: Mock,
    m_available_memory_bytes: Mock,
    m_confirm: Mock,
    m_select: Mock,
    m_warn: Mock,
):
    m_available_memory_bytes.return_value = 200 * MiB
    reply('GET', (200, None))

    result = invoke(database.migrate_history, '', _err=True)

    assert_exit(result, 1)
    m_warn.assert_any_call(matching(r'200 MB of memory is available.*needs about 250 MB'))
    m_warn.assert_any_call('Stop other programs or services to free memory, and try again.')
    m_confirm.assert_not_called()
    m_select.assert_not_called()
    assert sent() == [('GET', MIGRATE_PATH)]


def test_migrate_history_enough_memory(
    legacy,
    m_legacy_months: Mock,
    m_available_memory_bytes: Mock,
    m_confirm: Mock,
):
    m_available_memory_bytes.return_value = 250 * MiB
    m_confirm.return_value = True
    reply('GET', (200, None))
    reply('POST', (200, make_status()))

    invoke(database.migrate_history, '')
    assert sent() == [('GET', MIGRATE_PATH), ('POST', MIGRATE_PATH)]


def test_migrate_history_declined(legacy, m_legacy_months: Mock, m_confirm: Mock, m_info: Mock):
    m_confirm.return_value = False
    reply('GET', (200, None))

    invoke(database.migrate_history, '')

    m_confirm.assert_called_once()
    m_info.assert_any_call('The history migration did not start.')
    assert sent() == [('GET', MIGRATE_PATH)]


@pytest.mark.parametrize(
    'detail, hint',
    [
        ('A migration from http://other:8428/x is not done: discard it to start another one', True),
        ('The migration state is not valid, discard it: ValidationError', True),
        ('The migration cannot start after now', False),
        ('The migration needs the dense database', False),
    ],
)
def test_migrate_history_conflict(
    legacy,
    m_legacy_months: Mock,
    m_confirm: Mock,
    m_error: Mock,
    detail: str,
    hint: bool,
):
    m_confirm.return_value = True
    reply('GET', (200, None))
    reply('POST', (409, {'detail': detail}))

    result = invoke(database.migrate_history, '', _err=True)

    assert_exit(result, 1)
    m_error.assert_any_call(detail)
    discard_calls = [
        c for c in m_error.call_args_list if c.args == ('    brewblox-ctl database migrate-history --discard',)
    ]
    assert len(discard_calls) == (1 if hint else 0)
    # A 409 is not tried again
    assert sent() == [('GET', MIGRATE_PATH), ('POST', MIGRATE_PATH)]


def test_migrate_history_server_error(
    legacy,
    m_legacy_months: Mock,
    m_confirm: Mock,
    m_error: Mock,
    m_sleep: Mock,
    m_info: Mock,
):
    m_confirm.return_value = True
    reply('GET', (200, None))
    reply('POST', (500, {'error': 'ConnectError', 'details': 'victoria-legacy is unreachable'}))

    result = invoke(database.migrate_history, '', _err=True)

    assert_exit(result, 1)
    m_error.assert_any_call(matching(r'The history service failed to answer: .*500.*victoria-legacy is unreachable'))
    assert sent() == [('GET', MIGRATE_PATH)] + [('POST', MIGRATE_PATH)] * (migration.HTTP_RETRIES + 1)
    assert m_sleep.call_count == migration.HTTP_RETRIES
    m_sleep.assert_called_with(migration.HTTP_RETRY_DELAY)
    assert not any('runs in the background' in str(c) for c in m_info.call_args_list)


def test_migrate_history_server_error_then_ok(
    legacy,
    m_legacy_months: Mock,
    m_confirm: Mock,
    m_sleep: Mock,
):
    m_confirm.return_value = True
    reply('GET', (200, None))
    reply(
        'POST',
        (500, {'error': 'ConnectError', 'details': 'victoria-legacy is starting'}),
        (503, {'error': 'x', 'details': 'y'}),
        (200, make_status()),
    )

    invoke(database.migrate_history, '')

    assert sent() == [('GET', MIGRATE_PATH)] + [('POST', MIGRATE_PATH)] * 3
    assert m_sleep.call_count == 2


def test_migrate_history_not_answering(legacy, mocker: MockerFixture, m_error: Mock, m_confirm: Mock):
    m_request = not_answering(mocker)

    result = invoke(database.migrate_history, '', _err=True)

    assert_exit(result, 1)
    m_error.assert_any_call(
        'The history service at http://localhost:9600/history/timeseries did not answer (ConnectionError).'
    )
    m_error.assert_any_call('Check that Brewblox runs (`brewblox-ctl up`), wait a minute, and try again.')
    m_request.assert_called_once_with('GET', MIGRATE_URL, timeout=30)
    m_confirm.assert_not_called()


def test_migrate_history_post_not_answering(
    legacy,
    m_legacy_months: Mock,
    mocker: MockerFixture,
    m_confirm: Mock,
    m_error: Mock,
    m_sleep: Mock,
):
    m_confirm.return_value = True
    ok = Mock(status_code=200)
    ok.json.return_value = None
    m_request = mocker.patch.object(
        migration.requests,
        'request',
        side_effect=[ok] + [requests.ConnectionError('Connection refused')] * (migration.HTTP_RETRIES + 1),
    )

    result = invoke(database.migrate_history, '', _err=True)

    assert_exit(result, 1)
    assert m_request.call_count == migration.HTTP_RETRIES + 2
    assert m_sleep.call_count == migration.HTTP_RETRIES
    m_request.assert_called_with(
        'POST',
        MIGRATE_URL,
        timeout=migration.START_TIMEOUT,
        json={'source_url': LEGACY_URL, 'earliest': '2024-03-01T00:00:00+00:00', 'dense_days': 30},
    )
    m_error.assert_any_call(matching(r'The history service at .* did not answer \(ConnectionError\)'))


@pytest.mark.parametrize(
    'dense_days, armv7, memory, estimate',
    [
        # 939.5 days of 5 s data, 2.5 of them at 1 s: 2 * (937 * 7 + 2.5 * 17) s, plus 20 min for 30 dense days
        (30, False, 4 * GiB, 'up to 2 h'),  # 5761 s: 97 min
        (30, True, 4 * GiB, 'up to 4 h'),  # Small: 14403 s, 241 min
        (30, False, 1 * GiB, 'up to 4 h'),
        (0, False, 4 * GiB, 'up to 89 min'),  # 13203 s / 2.5: 5281.2 s, 88.02 min
    ],
)
def test_migrate_history_estimate(
    legacy,
    m_legacy_months: Mock,
    m_is_armv7: Mock,
    m_total_memory_bytes: Mock,
    m_confirm: Mock,
    m_info: Mock,
    dense_days: int,
    armv7: bool,
    memory: int,
    estimate: str,
):
    seed = f'first the last {dense_days} days, then ' if dense_days else ''
    m_is_armv7.return_value = armv7
    m_total_memory_bytes.return_value = memory
    m_confirm.return_value = True
    reply('GET', (200, None))
    reply('POST', (200, make_status()))

    invoke(database.migrate_history, f'--dense-days {dense_days}')

    m_confirm.assert_called_once_with(
        f'Start the history migration in the background? It migrates history since 2024-03-01 ({estimate}).'
    )
    m_info.assert_any_call(f'Graphs fill in backwards from the update: {seed}back to 2024-03-01 ({estimate}).')


# migrate-history: an existing migration


def test_migrate_history_resume(
    legacy,
    m_legacy_months: Mock,
    m_confirm: Mock,
    m_select: Mock,
    m_available_memory_bytes: Mock,
    m_free_disk_bytes: Mock,
    m_info: Mock,
):
    stored = make_status(
        running=False,
        cancelled=True,
        dense_days=14,
        earliest=int(datetime(2023, 7, 1, tzinfo=timezone.utc).timestamp()),
    )
    reply('GET', (200, stored))
    reply('POST', (200, {**stored, 'running': True, 'cancelled': False}))

    invoke(database.migrate_history, '')

    assert sent() == [('GET', MIGRATE_PATH), ('POST', MIGRATE_PATH)]
    # The stored values, not those of a new migration (first partition 2024-03, 30 days)
    assert posted() == {
        'source_url': LEGACY_URL,
        'earliest': '2023-07-01T00:00:00+00:00',
        'dense_days': 14,
    }
    m_available_memory_bytes.assert_called()
    m_free_disk_bytes.assert_called()
    m_legacy_months.assert_called_once_with('./victoria-legacy')
    # A resume does not ask
    m_confirm.assert_not_called()
    m_select.assert_not_called()
    m_info.assert_any_call('The history migration resumes where it stopped. To follow it, run:')


def test_migrate_history_resume_same_dense_days(legacy, m_legacy_months: Mock):
    stored = make_status(running=False, cancelled=True, dense_days=14)
    reply('GET', (200, stored))
    reply('POST', (200, {**stored, 'running': True, 'cancelled': False}))

    invoke(database.migrate_history, '--dense-days 14')
    assert posted()['dense_days'] == 14


def test_migrate_history_resume_stored_source_url(legacy, m_legacy_months: Mock):
    # The handoff: "Unfinished: resume. Send the stored `source_url` and `dense_days`."
    # History answers 409 when either differs from the stored state.
    stored = make_status(running=False, cancelled=True, source_url='http://victoria-legacy:8428/victoria-legacy/')
    reply('GET', (200, stored))
    reply('POST', (200, {**stored, 'running': True, 'cancelled': False}))

    invoke(database.migrate_history, '')
    assert posted()['source_url'] == 'http://victoria-legacy:8428/victoria-legacy/'


@pytest.mark.parametrize('cancelled', [True, False])
def test_migrate_history_resume_other_dense_days(legacy, m_legacy_months: Mock, m_error: Mock, cancelled: bool):
    stored = make_status(running=False, cancelled=cancelled, dense_days=30)
    reply('GET', (200, stored))

    result = invoke(database.migrate_history, '--dense-days 7', _err=True)

    assert_exit(result, 1)
    m_error.assert_any_call('The history migration started with --dense-days 30.')
    m_error.assert_any_call('    brewblox-ctl database migrate-history --discard')
    assert sent() == [('GET', MIGRATE_PATH)]


def test_migrate_history_resume_low_memory(
    legacy,
    m_legacy_months: Mock,
    m_available_memory_bytes: Mock,
    m_warn: Mock,
):
    m_available_memory_bytes.return_value = 100 * MiB
    reply('GET', (200, make_status(running=False, cancelled=True)))

    result = invoke(database.migrate_history, '', _err=True)

    assert_exit(result, 1)
    m_warn.assert_any_call(matching(r'100 MB of memory is available'))
    assert sent() == [('GET', MIGRATE_PATH)]


@pytest.mark.parametrize(
    'phase, done, total, need',
    [
        # The averages still to come (15% of 4 GiB since 2024-03, times the share not done), and the margin
        ('walk', 250, 1000, 0.15 * (4 * GiB) * 0.75 + 0 + GiB),
        ('walk', 1000, 1000, 0.15 * (4 * GiB) * 0 + 0 + GiB),
        ('walk', 1200, 1000, 0.15 * (4 * GiB) * 0 + 0 + GiB),
        ('walk', None, 1000, 0.15 * (4 * GiB) * 1 + 0 + GiB),
        ('walk', 0, 0, 0.15 * (4 * GiB) * 1 + 0 + GiB),
        # The seed adds the dense database: the last two months
        ('seed', None, 1000, 0.15 * (4 * GiB) * 1 + 2 * GiB + GiB),
    ],
)
@pytest.mark.parametrize('fits', [True, False])
def test_migrate_history_resume_space(
    legacy,
    m_legacy_months: Mock,
    m_free_disk_bytes: Mock,
    m_warn: Mock,
    m_select: Mock,
    phase: str,
    done: int,
    total: int,
    need: float,
    fits: bool,
):
    need = int(-(-need // 1))  # ceil
    m_free_disk_bytes.return_value = need if fits else need - 1
    stored = make_status(running=False, cancelled=True, phase=phase, chunks_done=done, chunks_total=total)
    reply('GET', (200, stored))
    reply('POST', (200, {**stored, 'running': True, 'cancelled': False}))

    result = invoke(database.migrate_history, '', _err=None if fits else True)

    m_select.assert_not_called()  # On resume, the stored earliest counts: no choice
    if fits:
        assert sent() == [('GET', MIGRATE_PATH), ('POST', MIGRATE_PATH)]
        assert posted()['earliest'] == '2024-03-01T00:00:00+00:00'
    else:
        assert_exit(result, 1)
        assert sent() == [('GET', MIGRATE_PATH)]
        m_warn.assert_any_call(matching(r'The rest of the history migration needs .* of free disk space'))
        m_warn.assert_any_call('    brewblox-ctl database migrate-history --discard')


def test_migrate_history_resume_stored_earliest_counts(
    legacy,
    m_legacy_months: Mock,
    m_free_disk_bytes: Mock,
    m_warn: Mock,
):
    # Stored earliest 2026-08: only the last two months count for the averages
    stored = make_status(
        running=False,
        cancelled=True,
        earliest=int(month(2026, 8).timestamp()),
        chunks_done=0,
    )
    m_free_disk_bytes.return_value = int(0.15 * (2 * GiB) + GiB) + 1
    reply('GET', (200, stored))
    reply('POST', (200, {**stored, 'running': True, 'cancelled': False}))

    invoke(database.migrate_history, '')

    assert posted()['earliest'] == '2026-08-01T00:00:00+00:00'


@pytest.mark.parametrize(
    'status, expected',
    [
        (
            make_status(phase='seed', chunks_done=None),
            'is copying the last 30 days of raw history into the dense database.',
        ),
        (
            make_status(phase='walk'),
            'is averaging history since 2024-03-01: 250 of 1000 periods done (25%).',
        ),
    ],
)
@pytest.mark.parametrize('dense_days', ['', '--dense-days 7'])
def test_migrate_history_running(
    legacy,
    m_legacy_months: Mock,
    m_confirm: Mock,
    m_available_memory_bytes: Mock,
    status: dict,
    expected: str,
    dense_days: str,
):
    reply('GET', (200, status))

    result = invoke(database.migrate_history, dense_days)

    assert expected in result.output
    assert sent() == [('GET', MIGRATE_PATH)]
    m_confirm.assert_not_called()
    m_available_memory_bytes.assert_not_called()
    m_legacy_months.assert_not_called()


def test_migrate_history_done(legacy, m_legacy_months: Mock, m_confirm: Mock):
    status = make_status(
        phase='done',
        running=False,
        chunks_done=1000,
        finished=int(NOW.timestamp()),
        lost_chunks=[int(NOW.timestamp()) - 3600],
        missing_series=['spark-one/Temp sensor/value[degC]'],
    )
    reply('GET', (200, status))

    result = invoke(database.migrate_history, '')

    assert 'The history migration is done. It migrated history since 2024-03-01' in result.output
    assert 'Periods of 1 h without averages: 1. Fields without averages: 1.' in result.output
    assert '    field spark-one/Temp sensor/value[degC]' in result.output
    assert '    brewblox-ctl database remove-legacy-history' in result.output
    assert sent() == [('GET', MIGRATE_PATH)]
    m_confirm.assert_not_called()
    m_legacy_months.assert_not_called()


@pytest.mark.parametrize(
    'status, expected',
    [
        (
            make_status(running=False, last_error='The legacy database has samples after the last one'),
            [
                'The history migration stopped: The legacy database has samples after the last one',
                '    brewblox-ctl database migrate-history --discard',
            ],
        ),
        (
            make_status(running=False),
            ['The history service is resuming the migration. Ask again in a minute.'],
        ),
    ],
)
def test_migrate_history_stopped(
    legacy,
    m_legacy_months: Mock,
    m_confirm: Mock,
    status: dict,
    expected: List[str],
):
    reply('GET', (200, status))

    result = invoke(database.migrate_history, '', _err=True)

    assert_exit(result, 1)
    for line in expected:
        assert line in result.output
    assert sent() == [('GET', MIGRATE_PATH)]
    m_confirm.assert_not_called()
    m_legacy_months.assert_not_called()


# migrate-history: dry-run


def test_migrate_history_dry_run_new(
    legacy,
    m_legacy_months: Mock,
    m_get_opts: CtlOpts,
    m_confirm: Mock,
    m_show_data: Mock,
    m_info: Mock,
):
    m_get_opts.dry_run = True
    m_confirm.return_value = True
    reply('GET', (200, None))
    reply('POST', (200, make_status()))

    result = invoke(database.migrate_history, '')

    assert sent() == [('GET', MIGRATE_PATH)]
    m_show_data.assert_any_call(
        f'POST {MIGRATE_URL}',
        {'source_url': LEGACY_URL, 'earliest': '2024-03-01T00:00:00+00:00', 'dense_days': 30},
    )
    assert f'POST {MIGRATE_URL}' in result.output
    m_info.assert_any_call('Starting the history migration ...')


def test_migrate_history_dry_run_resume(legacy, m_legacy_months: Mock, m_get_opts: CtlOpts, m_show_data: Mock):
    m_get_opts.dry_run = True
    reply('GET', (200, make_status(running=False, cancelled=True)))
    reply('POST', (200, make_status()))

    invoke(database.migrate_history, '')

    assert sent() == [('GET', MIGRATE_PATH)]
    m_show_data.assert_any_call(
        f'POST {MIGRATE_URL}',
        {'source_url': LEGACY_URL, 'earliest': '2024-03-01T00:00:00+00:00', 'dense_days': 30},
    )


def test_migrate_history_dry_run_discard(
    m_get_opts: CtlOpts,
    m_confirm: Mock,
    m_show_data: Mock,
):
    m_get_opts.dry_run = True
    m_confirm.return_value = True
    reply('DELETE', (200, None))

    invoke(database.migrate_history, '--discard')

    assert sent() == []
    m_show_data.assert_any_call(f'DELETE {MIGRATE_URL}?discard=true', '')


# migrate-history --status


LOST = [int(NOW.timestamp()) - 3600 * i for i in range(25)]
MISSING = [f'spark-one/sensor-{i}' for i in range(22)]


@pytest.mark.parametrize(
    'status, expected',
    [
        (
            None,
            ['There is no history migration. To start it, run:', 'If the history service just started'],
        ),
        (
            make_status(phase='seed', chunks_done=None, dense_days=14),
            [
                'The history migration (started at ',
                'is copying the last 14 days of raw history into the dense database.',
            ],
        ),
        (
            make_status(phase='walk', chunks_done=333, chunks_total=1000),
            ['is averaging history since 2024-03-01: 333 of 1000 periods done (33%).'],
        ),
        (
            make_status(phase='walk', chunks_done=None),
            ['is averaging history since 2024-03-01: counting the periods already done.'],
        ),
        (
            make_status(phase='walk', chunks_done=0, chunks_total=0),
            ['counting the periods already done.'],
        ),
        (
            make_status(phase='walk', last_error='ReadTimeout(timed out)'),
            ['250 of 1000 periods done (25%).', 'It tries again after an error: ReadTimeout(timed out)'],
        ),
        (
            make_status(phase='done', running=False, chunks_done=1000, finished=int(NOW.timestamp())),
            [
                'The history migration is done. It migrated history since 2024-03-01, and finished at ',
                'Periods of 1 h without averages: 0. Fields without averages: 0.',
                'Check your graphs, and then remove the legacy history with:',
                '    brewblox-ctl database remove-legacy-history',
            ],
        ),
        (
            make_status(phase='done', running=False, finished=None),
            ['and finished at unknown.'],
        ),
        (
            make_status(phase='done', running=False, lost_chunks=LOST, missing_series=MISSING),
            [
                'Periods of 1 h without averages: 25. Fields without averages: 22.',
                '    period ending ',
                '    ... and 5 more periods',
                '    field spark-one/sensor-0',
                '    field spark-one/sensor-19',
                '    ... and 2 more fields',
            ],
        ),
        (
            make_status(running=False, cancelled=True),
            ['The history migration was stopped. To resume it, run:', '    brewblox-ctl database migrate-history'],
        ),
        (
            make_status(running=False, last_error='The migration started with sparse_interval 60s, now it is 30s'),
            [
                'The history migration stopped: The migration started with sparse_interval 60s, now it is 30s',
                'To start again, discard it first:',
                '    brewblox-ctl database migrate-history --discard',
            ],
        ),
        (
            make_status(running=False),
            ['The history service is resuming the migration. Ask again in a minute.'],
        ),
    ],
)
def test_migrate_history_status(
    legacy,
    m_confirm_mode: Mock,
    m_confirm: Mock,
    status: dict,
    expected: List[str],
):
    reply('GET', (200, status))

    result = invoke(database.migrate_history, '--status')

    for line in expected:
        assert line in result.output
    assert sent() == [('GET', MIGRATE_PATH)]
    m_confirm_mode.assert_not_called()
    m_confirm.assert_not_called()


def test_migrate_history_status_losses_limited():
    status = make_status(phase='done', running=False, lost_chunks=LOST, missing_series=MISSING)
    reply('GET', (200, status))

    result = invoke(database.migrate_history, '--status')

    assert result.output.count('    period ending ') == 20
    assert result.output.count('    field ') == 20
    assert 'spark-one/sensor-20' not in result.output


def test_migrate_history_status_no_legacy(m_file_exists: Mock):
    # The status does not need the legacy directory
    reply('GET', (200, make_status()))
    result = invoke(database.migrate_history, '--status')
    assert '250 of 1000 periods done' in result.output


def test_migrate_history_status_not_answering(mocker: MockerFixture, m_error: Mock):
    not_answering(mocker)
    result = invoke(database.migrate_history, '--status', _err=True)
    assert_exit(result, 1)
    m_error.assert_any_call(matching(r'The history service at .* did not answer'))


def test_migrate_history_status_server_error(m_error: Mock, m_sleep: Mock):
    reply('GET', (500, {'error': 'RedisError', 'details': 'down'}))
    result = invoke(database.migrate_history, '--status', _err=True)
    assert_exit(result, 1)
    m_error.assert_any_call(matching(r'The history service failed to answer: HTTPError\(500'))
    assert sent() == [('GET', MIGRATE_PATH)]
    m_sleep.assert_not_called()


def test_migrate_history_status_discard(m_confirm: Mock):
    result = invoke(database.migrate_history, '--status --discard', _err=True)
    assert_exit(result, 2)
    assert '--status and --discard cannot be combined' in result.output
    assert sent() == []
    m_confirm.assert_not_called()


# migrate-history --discard


def test_migrate_history_discard(legacy, m_confirm: Mock, m_confirm_mode: Mock, m_info: Mock):
    m_confirm.return_value = True
    reply('DELETE', (200, None))

    invoke(database.migrate_history, '--discard')

    m_confirm_mode.assert_called_once()
    m_confirm.assert_called_once_with(matching(r'Do you want to discard the history migration\?'), default=False)
    assert sent() == [('DELETE', DISCARD_PATH)]
    assert httpretty.last_request().querystring == {'discard': ['true']}
    m_info.assert_any_call('    brewblox-ctl database migrate-history')


def test_migrate_history_discard_without_legacy(m_confirm: Mock, m_info: Mock):
    # Also possible after the legacy history is removed: then there is nothing to migrate again
    m_confirm.return_value = True
    reply('DELETE', (200, None))
    invoke(database.migrate_history, '--discard')
    assert sent() == [('DELETE', DISCARD_PATH)]
    assert ('To start a new history migration, run:',) not in [c.args for c in m_info.call_args_list]


def test_migrate_history_discard_declined(legacy, m_confirm: Mock):
    m_confirm.return_value = False
    reply('DELETE', (200, None))

    invoke(database.migrate_history, '--discard')

    m_confirm.assert_called_once()
    assert sent() == []


def test_migrate_history_discard_fails(m_confirm: Mock, m_error: Mock, m_info: Mock, m_sleep: Mock):
    m_confirm.return_value = True
    reply('DELETE', (500, {'error': 'RedisError', 'details': 'down'}))

    result = invoke(database.migrate_history, '--discard', _err=True)

    assert_exit(result, 1)
    m_error.assert_any_call(matching(r'The history service failed to answer: HTTPError\(500'))
    assert sent() == [('DELETE', DISCARD_PATH)]
    m_sleep.assert_not_called()
    assert ('To start a new history migration, run:',) not in [c.args for c in m_info.call_args_list]


def test_migrate_history_discard_not_answering(mocker: MockerFixture, m_confirm: Mock, m_error: Mock):
    m_confirm.return_value = True
    not_answering(mocker)
    result = invoke(database.migrate_history, '--discard', _err=True)
    assert_exit(result, 1)
    m_error.assert_any_call(matching(r'The history service at .* did not answer'))


# remove-legacy-history


DONE = make_status(
    phase='done',
    running=False,
    chunks_done=998,
    finished=int(NOW.timestamp()),
    lost_chunks=[int(NOW.timestamp()) - 3600, int(NOW.timestamp()) - 7200],
    missing_series=['spark-one/Temp sensor/value[degC]'],
)


@pytest.fixture
def removal(legacy, m_sh: Mock, m_make_shared_compose: Mock, m_select: Mock, m_confirm: Mock):
    """Records the steps of the removal in order"""
    events = []
    record_sh(m_sh, events)

    def render(legacy_history=None):
        assert legacy_history is False
        events.append('make_shared_compose')

    m_make_shared_compose.side_effect = render
    m_select.return_value = ''
    m_confirm.return_value = True
    return events


def test_remove_legacy_history_no_dir(
    m_info: Mock,
    m_sh: Mock,
    m_confirm: Mock,
    m_select: Mock,
    m_make_shared_compose: Mock,
):
    invoke(database.remove_legacy_history, '')

    m_info.assert_any_call('There is no legacy history to remove: ./victoria-legacy does not exist.')
    assert sent() == []
    m_sh.assert_not_called()
    m_confirm.assert_not_called()
    m_select.assert_not_called()
    m_make_shared_compose.assert_not_called()


def test_remove_legacy_history_no_dir_force(m_sh: Mock, m_make_shared_compose: Mock):
    invoke(database.remove_legacy_history, '--force')
    assert sent() == []
    m_sh.assert_not_called()
    m_make_shared_compose.assert_not_called()


def test_remove_legacy_history(
    removal: list,
    m_confirm_mode: Mock,
    m_confirm: Mock,
    m_select: Mock,
    m_warn: Mock,
):
    reply('GET', (200, DONE))

    result = invoke(database.remove_legacy_history, '')

    m_confirm_mode.assert_called_once()
    # The lists
    assert 'Periods of 1 h without averages: 2. Fields without averages: 1.' in result.output
    assert result.output.count('    period ending ') == 2
    assert '    field spark-one/Temp sensor/value[degC]' in result.output
    m_warn.assert_any_call(
        'This removes ./victoria-legacy. History since 2024-03-01 is then kept as averages of every 60s.'
    )
    m_warn.assert_any_call('This cannot be undone.')
    m_select.assert_called_once_with(matching(r'To copy \./victoria-legacy to another disk first'))
    m_confirm.assert_called_once_with('Do you want to remove ./victoria-legacy?', default=False)

    # Down, render, rm, up: an interrupted removal leaves no service that creates the directory again
    assert removal == [
        'SUDO docker compose down ',
        'make_shared_compose',
        'sudo rm -rf ./victoria-legacy',
        'SUDO docker compose up -d ',
    ]
    assert sent() == [('GET', MIGRATE_PATH)]


def test_remove_legacy_history_compose_down(removal: list, m_is_compose_up: Mock):
    m_is_compose_up.return_value = False
    reply('GET', (200, DONE))

    invoke(database.remove_legacy_history, '')

    assert removal == ['make_shared_compose', 'sudo rm -rf ./victoria-legacy']


@pytest.mark.parametrize(
    'status, expected',
    [
        (None, 'There is no history migration.'),
        (make_status(), '250 of 1000 periods done'),
        (make_status(running=False, cancelled=True), 'The history migration was stopped.'),
        (make_status(running=False, last_error='boom'), 'The history migration stopped: boom'),
        (make_status(running=False), 'The history service is resuming the migration.'),
    ],
)
def test_remove_legacy_history_not_done(
    removal: list,
    m_error: Mock,
    m_select: Mock,
    m_confirm: Mock,
    m_make_shared_compose: Mock,
    status: dict,
    expected: str,
):
    reply('GET', (200, status))

    result = invoke(database.remove_legacy_history, '', _err=True)

    assert_exit(result, 1)
    m_error.assert_any_call('The history migration is not done:')
    m_error.assert_any_call('    brewblox-ctl database remove-legacy-history --force')
    assert expected in result.output
    assert removal == []
    m_select.assert_not_called()
    m_confirm.assert_not_called()
    m_make_shared_compose.assert_not_called()


@pytest.mark.parametrize('status', [None, make_status(), make_status(running=False, last_error='boom')])
def test_remove_legacy_history_force(removal: list, m_warn: Mock, m_info: Mock, status: dict):
    reply('GET', (200, status))
    reply('DELETE', (200, None))

    result = invoke(database.remove_legacy_history, '--force')

    m_warn.assert_any_call(
        'This removes ./victoria-legacy, with the history from before the update that was not migrated.'
    )
    assert 'Periods of 1 h without averages' not in result.output
    assert removal == [
        'SUDO docker compose down ',
        'make_shared_compose',
        'sudo rm -rf ./victoria-legacy',
        'SUDO docker compose up -d ',
    ]
    if status is None:
        # History answered: there is no migration to discard
        assert sent() == [('GET', MIGRATE_PATH)]
        assert ('If a history migration was started, discard it with:',) not in [c.args for c in m_info.call_args_list]
    else:
        # An unfinished migration would try forever to read the removed history
        assert sent() == [('GET', MIGRATE_PATH), ('DELETE', DISCARD_PATH)]


def test_remove_legacy_history_force_discard_fails(removal: list, m_warn: Mock, m_info: Mock):
    reply('GET', (200, make_status()))
    reply('DELETE', (500, {'error': 'RedisError', 'details': 'down'}))

    invoke(database.remove_legacy_history, '--force')

    m_warn.assert_any_call(matching(r'Failed to discard the history migration: HTTPError'))
    m_info.assert_any_call('    brewblox-ctl database migrate-history --discard')
    assert 'sudo rm -rf ./victoria-legacy' in removal


def test_remove_legacy_history_force_done(removal: list, m_warn: Mock):
    reply('GET', (200, DONE))

    result = invoke(database.remove_legacy_history, '--force')

    assert 'Periods of 1 h without averages: 2. Fields without averages: 1.' in result.output
    m_warn.assert_any_call(matching(r'This removes \./victoria-legacy\. History since 2024-03-01 is then kept'))
    assert 'sudo rm -rf ./victoria-legacy' in removal


@pytest.mark.parametrize('failure', ['connection', 'server'])
def test_remove_legacy_history_not_answering(
    removal: list,
    mocker: MockerFixture,
    m_error: Mock,
    m_select: Mock,
    m_confirm: Mock,
    failure: str,
):
    if failure == 'connection':
        not_answering(mocker)
    else:
        reply('GET', (500, {'error': 'x', 'details': 'y'}))

    result = invoke(database.remove_legacy_history, '', _err=True)

    assert_exit(result, 1)
    m_error.assert_any_call(matching(r'The history service failed to answer: '))
    m_error.assert_any_call('Start the services with `brewblox-ctl up`, wait a minute, and try again.')
    m_error.assert_any_call('    brewblox-ctl database remove-legacy-history --force')
    assert removal == []
    m_select.assert_not_called()
    m_confirm.assert_not_called()


@pytest.mark.parametrize('failure', ['connection', 'server'])
def test_remove_legacy_history_not_answering_force(
    removal: list,
    mocker: MockerFixture,
    m_warn: Mock,
    m_info: Mock,
    failure: str,
):
    if failure == 'connection':
        not_answering(mocker)
    else:
        reply('GET', (500, {'error': 'x', 'details': 'y'}))

    invoke(database.remove_legacy_history, '--force')

    m_warn.assert_any_call(matching(r'This removes \./victoria-legacy, with the history .* not migrated'))
    assert removal == [
        'SUDO docker compose down ',
        'make_shared_compose',
        'sudo rm -rf ./victoria-legacy',
        'SUDO docker compose up -d ',
    ]
    # Whether a migration exists is unknown
    m_info.assert_any_call('If a history migration was started, discard it with:')


def test_remove_legacy_history_declined(
    removal: list,
    m_confirm: Mock,
    m_make_shared_compose: Mock,
    m_sh: Mock,
):
    m_confirm.return_value = False
    reply('GET', (200, DONE))

    invoke(database.remove_legacy_history, '')

    m_confirm.assert_called_once()
    assert removal == []
    m_sh.assert_not_called()
    m_make_shared_compose.assert_not_called()


@pytest.fixture
def backup_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, m_file_exists: Mock):
    """A Brewblox directory with ./victoria-legacy, and a backup directory"""
    home = tmp_path / 'brewblox'
    (home / 'victoria-legacy').mkdir(parents=True)
    backup = tmp_path / 'backup'
    backup.mkdir()
    monkeypatch.chdir(home)
    m_file_exists.add_existing_files(const.VICTORIA_LEGACY_DIR)
    return backup


def test_remove_legacy_history_copy(removal: list, backup_dirs: Path, m_select: Mock, m_warn: Mock, m_info: Mock):
    m_select.return_value = f' {backup_dirs} '
    reply('GET', (200, DONE))

    invoke(database.remove_legacy_history, '')

    # tmp_path is one disk
    m_warn.assert_any_call(
        f'{backup_dirs} is on the same disk as ./victoria-legacy: the copy is lost if that disk fails.'
    )
    m_info.assert_any_call(f'Copying ./victoria-legacy to {backup_dirs} ...')
    # Only the legacy database stops for the copy
    assert removal == [
        'SUDO docker compose stop victoria-legacy',
        f'sudo cp -RH --preserve=timestamps -- ./victoria-legacy {backup_dirs}/victoria-legacy',
        'SUDO docker compose down ',
        'make_shared_compose',
        'sudo rm -rf ./victoria-legacy',
        'SUDO docker compose up -d ',
    ]


def test_remove_legacy_history_copy_other_disk(
    removal: list,
    backup_dirs: Path,
    mocker: MockerFixture,
    m_select: Mock,
    m_warn: Mock,
):
    m_select.return_value = str(backup_dirs)
    real_stat = os.stat

    def other_disk(path, *args, **kwargs):
        result = real_stat(path, *args, **kwargs)
        if path == str(backup_dirs):
            return SimpleNamespace(st_dev=result.st_dev + 1, st_mode=result.st_mode)
        return result

    mocker.patch.object(migration.os, 'stat', side_effect=other_disk)
    reply('GET', (200, DONE))

    invoke(database.remove_legacy_history, '')

    assert not any('same disk' in str(c) for c in m_warn.call_args_list)
    copy = f'sudo cp -RH --preserve=timestamps -- ./victoria-legacy {backup_dirs}/victoria-legacy'
    assert removal.index(copy) < removal.index('sudo rm -rf ./victoria-legacy')


def test_remove_legacy_history_copy_not_a_dir(
    removal: list,
    backup_dirs: Path,
    m_select: Mock,
    m_confirm: Mock,
    m_error: Mock,
):
    target = backup_dirs / 'missing'
    m_select.return_value = str(target)
    reply('GET', (200, DONE))

    result = invoke(database.remove_legacy_history, '', _err=True)

    assert_exit(result, 1)
    m_error.assert_any_call(f'{target} is not a directory. Nothing changed.')
    m_confirm.assert_not_called()
    assert removal == []


def test_remove_legacy_history_copy_file(
    removal: list,
    backup_dirs: Path,
    m_select: Mock,
    m_confirm: Mock,
):
    target = backup_dirs / 'file'
    target.write_text('')
    m_select.return_value = str(target)
    reply('GET', (200, DONE))

    result = invoke(database.remove_legacy_history, '', _err=True)

    assert_exit(result, 1)
    m_confirm.assert_not_called()
    assert removal == []


def test_remove_legacy_history_copy_exists(
    removal: list,
    backup_dirs: Path,
    m_select: Mock,
    m_confirm: Mock,
    m_error: Mock,
):
    (backup_dirs / 'victoria-legacy').mkdir()
    m_select.return_value = str(backup_dirs)
    reply('GET', (200, DONE))

    result = invoke(database.remove_legacy_history, '', _err=True)

    assert_exit(result, 1)
    m_error.assert_any_call(f'{backup_dirs} already contains victoria-legacy. Nothing changed.')
    m_confirm.assert_not_called()
    assert removal == []


def test_remove_legacy_history_copy_declined(
    removal: list,
    backup_dirs: Path,
    m_select: Mock,
    m_confirm: Mock,
):
    m_select.return_value = str(backup_dirs)
    m_confirm.return_value = False
    reply('GET', (200, DONE))

    invoke(database.remove_legacy_history, '')

    assert removal == []


# remove-legacy-history: hardening after review


def test_remove_legacy_history_mount(removal: list, m_is_mount: Mock, m_error: Mock, m_confirm: Mock):
    # `rm -rf` cannot remove a mount point: it would empty it, fail, and leave the services down
    m_is_mount.return_value = True
    result = invoke(database.remove_legacy_history, '', _err=True)
    assert_exit(result, 1)
    m_error.assert_any_call(matching(r'\./victoria-legacy is a mount point\. Unmount it'))
    assert removal == []
    assert sent() == []
    m_confirm.assert_not_called()


def test_remove_legacy_history_symlink(removal: list, m_is_symlink: Mock, m_warn: Mock):
    m_is_symlink.return_value = True
    reply('GET', (200, DONE))
    invoke(database.remove_legacy_history, '')
    m_warn.assert_any_call(matching(r'\./victoria-legacy is a symbolic link to .*This only removes the link\.'))
    assert 'sudo rm -rf ./victoria-legacy' in removal


def test_remove_legacy_history_partial(removal: list, mocker: MockerFixture, m_warn: Mock):
    """The user chose to migrate only the last months: older history goes with the directory"""
    mocker.patch.object(migration, 'legacy_months', return_value={month(2023, 1): GiB, month(2026, 9): GiB})
    reply('GET', (200, DONE))
    invoke(database.remove_legacy_history, '')
    m_warn.assert_any_call('History before 2024-03-01 was not migrated, and is removed.')


def test_remove_legacy_history_complete(removal: list, mocker: MockerFixture, m_warn: Mock):
    mocker.patch.object(migration, 'legacy_months', return_value={month(2024, 3): GiB, month(2026, 9): GiB})
    reply('GET', (200, DONE))
    invoke(database.remove_legacy_history, '')
    assert not any('was not migrated' in c[0][0] for c in m_warn.call_args_list)


def test_remove_legacy_history_copy_too_big(
    removal: list,
    backup_dirs: Path,
    mocker: MockerFixture,
    m_select: Mock,
    m_free_disk_bytes: Mock,
    m_confirm: Mock,
    m_error: Mock,
):
    mocker.patch.object(migration, 'dir_size', return_value=2 * GiB)
    m_free_disk_bytes.return_value = GiB
    m_select.return_value = str(backup_dirs)
    reply('GET', (200, DONE))

    result = invoke(database.remove_legacy_history, '', _err=True)

    assert_exit(result, 1)
    m_error.assert_any_call(f'{backup_dirs} has 1.0 GB free, and the copy needs 2.0 GB. Nothing changed.')
    m_free_disk_bytes.assert_called_with(str(backup_dirs))
    m_confirm.assert_not_called()
    assert removal == []


def test_remove_legacy_history_copy_home(
    removal: list,
    backup_dirs: Path,
    monkeypatch: pytest.MonkeyPatch,
    m_select: Mock,
):
    monkeypatch.setenv('HOME', str(backup_dirs.parent))
    m_select.return_value = f'~/{backup_dirs.name}'
    reply('GET', (200, DONE))
    invoke(database.remove_legacy_history, '')
    assert f'sudo cp -RH --preserve=timestamps -- ./victoria-legacy {backup_dirs}/victoria-legacy' in removal


def test_remove_legacy_history_force_copy_then_discard(
    removal: list, backup_dirs: Path, m_select: Mock, m_free_disk_bytes: Mock
):
    """A failed copy changes nothing: the unfinished migration is discarded after it"""
    m_select.return_value = str(backup_dirs)
    reply('GET', (200, make_status()))
    events = removal

    def on_delete(request, uri, headers):
        events.append('DELETE')
        return [200, {**headers, 'content-type': 'application/json'}, 'null']

    httpretty.register_uri('DELETE', MIGRATE_URL, body=on_delete)

    invoke(database.remove_legacy_history, '--force')

    copy = f'sudo cp -RH --preserve=timestamps -- ./victoria-legacy {backup_dirs}/victoria-legacy'
    assert events.index(copy) < events.index('DELETE') < events.index('make_shared_compose')
