"""
Manual migration steps
"""

import math
import os
import re
import shlex
from collections import defaultdict
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from subprocess import CalledProcessError
from time import sleep
from typing import Dict, List, Optional, Tuple

import click
import requests
from packaging.version import Version

from . import actions, const, utils
from .models import parse_retention


def migrate_ghcr_images():
    # We migrated all brewblox images from Docker Hub to Github Container Registry
    # At this point, we also stop supporting the "rpi-" prefix for ARM32 images
    utils.info('Migrating brewblox images to ghcr.io registry ...')
    config = utils.read_compose()
    for name, svc in config['services'].items():
        img: str = svc.get('image', '')  # empty string won't match regex
        # Image must:
        # - Start with "brewblox/"
        # - Have a tag from a default channel. We're not migrating feature branch tags.
        # Image may:
        # - Have a tag that starts with "rpi-". We'll remove this during replacement.
        # - Have either a `$BREWBLOX_RELEASE`, `${BREWBLOX_RELEASE}`, or `${BREWBLOX_RELEASE:-default}` tag.
        changed = re.sub(
            r'^brewblox/([\w\-]+)\:(rpi\-)?((\$\{?BREWBLOX_RELEASE(:\-\w+)?\}?)|develop|edge)$',
            r'ghcr.io/brewblox/\1:\3',
            img,
        )
        if changed != img:
            utils.info(f'Editing "{name}" ...')
            svc['image'] = changed

    utils.write_compose(config)


def migrate_tilt_images():
    # The tilt service was changed to use host D-Bus instead of the Bluetooth adapter directly
    # Required changes:
    # - /var/run/dbus must be mounted
    # - service does not have to be run in host mode

    config = utils.read_compose()
    changed = False

    for name, svc in config['services'].items():
        svc: Dict

        # Check whether this is a Tilt image
        if not svc.get('image', '').startswith('ghcr.io/brewblox/brewblox-tilt'):
            continue

        utils.info(f'Migrating `{name}` image configuration ...')

        if svc.get('network_mode') == 'host':
            changed = True
            del svc['network_mode']

        dbus_volume = {
            'type': 'bind',
            'source': '/var/run/dbus',
            'target': '/var/run/dbus',
        }

        volumes: List[Dict] = svc.get('volumes', [])
        if dbus_volume not in volumes:
            changed = True
            svc['volumes'] = [*volumes, dbus_volume]

    if changed:
        utils.write_compose(config)


def migrate_env_config():
    # brewblox.yml was introduced as centralized config file
    # Previous config was stored in .env
    # We want to retrieve those settings

    envdict = utils.envdict('.env')

    def popget(key: str):
        try:
            return envdict.pop(key)
        except KeyError:
            return None

    config = utils.get_config()

    if value := popget('BREWBLOX_CFG_VERSION'):
        pass  # not inserted in config

    if value := popget('BREWBLOX_RELEASE'):
        config.release = value

    if value := popget('BREWBLOX_CTL_RELEASE'):
        config.ctl_release = value

    if value := popget('BREWBLOX_UPDATE_SYSTEM_PACKAGES'):
        config.system.apt_upgrade = utils.strtobool(value)

    if value := popget('BREWBLOX_SKIP_CONFIRM'):
        config.skip_confirm = utils.strtobool(value)

    if value := popget('BREWBLOX_AUTH_ENABLED'):
        config.auth.enabled = utils.strtobool(value)

    if value := popget('BREWBLOX_DEBUG'):
        config.debug = utils.strtobool(value)

    if value := popget('BREWBLOX_PORT_HTTP'):
        config.ports.http = int(value)

    if value := popget('BREWBLOX_PORT_HTTPS'):
        config.ports.https = int(value)

    if value := popget('BREWBLOX_PORT_MQTT'):
        config.ports.mqtt = int(value)

    if value := popget('BREWBLOX_PORT_MQTTS'):
        config.ports.mqtts = int(value)

    if value := popget('BREWBLOX_PORT_ADMIN'):
        config.ports.admin = int(value)

    if value := popget('COMPOSE_PROJECT_NAME'):
        config.compose.project = value

    if value := popget('COMPOSE_FILE'):
        config.compose.files = value.split(':')

    config.environment = envdict  # assign leftovers
    actions.make_brewblox_config(config)


# History migration (configuration version 0.12.0)
#
# Before 0.12.0, one database kept every raw sample.
# The update moves its directory to ./victoria-legacy, unchanged, and creates the new databases:
# `victoria` keeps long-term averages, and `victoria-dense` keeps raw samples for a while.
# The history service converts the legacy database in the background.
# It first copies the last days of raw samples into the dense database,
# and then imports averages into the long-term database, walking back from the update to the earliest time.

# Days of raw samples the migration copies into the dense database
MIGRATION_DENSE_DAYS = 30
# The long-term averages take about this share of the legacy database's size for the same period.
# Measured: 3% of 1 s data, 13% of 5 s data from noisy analog sensors.
AVERAGES_SHARE = 0.15
# Disk space kept free: a merge writes its new part before it removes the old ones,
# the databases turn read-only when the disk is nearly full, and the datastore and images share the disk.
SPACE_MARGIN = 2**30
# The legacy database adds 100-150 MB while it answers the migration's queries
MIN_AVAILABLE_MEMORY = 250 * 2**20
# Shorter migrations, offered when all history does not fit on disk
MIGRATION_WINDOWS = [
    ('the last 2 years', timedelta(days=730)),
    ('the last year', timedelta(days=365)),
    ('the last 6 months', timedelta(days=183)),
]

# Work per day of legacy history on a Raspberry Pi 3: 5 s data, and 1 s data since the Spark logs every second.
# The job pauses as long as each chunk took, so it takes about twice as long.
MIGRATION_DAY_SECONDS = 7
MIGRATION_DAY_SECONDS_1S = 17
MIGRATION_1S_SINCE = datetime(2026, 9, 24, tzinfo=timezone.utc)
# Copying 30 days of raw samples into the dense database on a Raspberry Pi 3
MIGRATION_SEED_SECONDS = 20 * 60
# Hosts that are not small are about this many times faster (a Pi 4)
MIGRATION_SPEEDUP = 2.5

# Retries while history, or the legacy database it reads, is starting
HTTP_RETRIES = 30
HTTP_RETRY_DELAY = 10
# Starting a migration reads the legacy database before the answer
START_TIMEOUT = 300
# The answer to a start while the job runs
RUNNING_DETAIL = 'The migration is running'

# Victoria Metrics keeps each UTC month in a partition directory: data/{small,big}/YYYY_MM
PARTITION_NAME = re.compile(r'(\d{4})_(\d{2})')
PARTITION_DU_LINE = re.compile(r'(\d+)\s+\S*/data/(?:small|big)/(\d{4})_(\d{2})/?\s*')
# Invalid answers to a question before it aborts
MAX_ANSWERS = 5
# Where each history database keeps its data in its container
VICTORIA_DATA_TARGET = '/victoria-metrics-data'

MIGRATE_CMD = 'brewblox-ctl database migrate-history'
DISCARD_CMD = 'brewblox-ctl database migrate-history --discard'
STATUS_CMD = 'brewblox-ctl database migrate-history --status'
REMOVE_CMD = 'brewblox-ctl database remove-legacy-history'


class MigrationConflictError(Exception):
    """The history service refused the request (409)"""


@dataclass
class LegacyHistory:
    # Bytes on disk of each monthly partition of the legacy database, by the start of its month (UTC)
    months: Dict[datetime, int]
    # Where the migration starts. None to migrate nothing.
    earliest: Optional[datetime]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def format_bytes(value: float) -> str:
    if value >= 2**30:
        return f'{value / 2**30:.1f} GB'
    return f'{math.ceil(value / 2**20)} MB'


def format_minutes(minutes: int) -> str:
    # The estimate is for a slow host: others are done sooner
    if minutes < 90:
        return f'up to {minutes} min'
    return f'up to {round(minutes / 60)} h'


def format_date(value: datetime) -> str:
    # In local time, as the timestamps and the graphs in the UI
    return value.astimezone().strftime('%Y-%m-%d')


def format_timestamp(value: float) -> str:
    return datetime.fromtimestamp(value).strftime('%Y-%m-%d %H:%M')


def _next_month(month: datetime) -> datetime:
    return month.replace(year=month.year + month.month // 12, month=month.month % 12 + 1)


def migrated_since(status: dict) -> datetime:
    """
    The start of the history that the migration covers.

    The stored `earliest` is where the walk starts:
    one interval before the interval that holds the requested time.
    """
    return datetime.fromtimestamp(status['earliest'] + status['sparse_interval'], timezone.utc)


def cfg_version() -> Version:
    """The configuration version of this directory. Without one, it was never set up."""
    return Version(utils.getenv(const.ENV_KEY_CFG_VERSION) or '0.0.0')


def legacy_history_unmoved() -> bool:
    """
    Whether ./victoria still holds the history from before configuration version 0.12.0.

    The migration needs it moved to ./victoria-legacy, before a newer database opens it.
    From 0.12.0 on, ./victoria-dense exists next to ./victoria.
    """
    return (
        utils.file_exists(const.VICTORIA_DIR)
        and not utils.file_exists(const.VICTORIA_LEGACY_DIR)
        and not utils.file_exists(const.VICTORIA_DENSE_DIR)
    )


def history_move_pending(version: Version) -> bool:
    """Whether a directory at configuration `version` needs ./victoria moved to ./victoria-legacy"""
    return version < Version(const.HISTORY_DENSE_VERSION) and legacy_history_unmoved()


def history_update_pending() -> bool:
    """
    Whether this directory still waits for the update that moves its history.

    Configuration generated before that would open the history with a newer database, which cannot be undone.
    """
    return history_move_pending(cfg_version())


def history_migration_pending(version: Version) -> bool:
    """Whether an update from `version` offers the history migration"""
    return version < Version(const.HISTORY_DENSE_VERSION) and (
        legacy_history_unmoved() or utils.file_exists(const.VICTORIA_LEGACY_DIR)
    )


def history_volume_overrides() -> List[Tuple[str, str]]:
    """The directories that compose files other than docker-compose.shared.yml bind to the `victoria` database"""
    found = []
    for fname in utils.get_config().compose.files:
        if Path(fname).name == const.COMPOSE_SHARED_FILE.name or not utils.file_exists(fname):
            continue
        service = ((utils.read_yaml(fname) or {}).get('services') or {}).get('victoria') or {}
        for volume in service.get('volumes') or []:
            if isinstance(volume, str) and volume.split(':')[1:2] == [VICTORIA_DATA_TARGET]:
                found.append((fname, volume.split(':')[0]))
            elif isinstance(volume, dict) and volume.get('target') == VICTORIA_DATA_TARGET:
                found.append((fname, str(volume.get('source'))))
    return found


def check_legacy_movable():
    """Stops before anything changed if the history in ./victoria cannot be moved as it should"""
    legacy = const.VICTORIA_LEGACY_DIR
    if utils.is_mount(const.VICTORIA_DIR):
        utils.error(f'{const.VICTORIA_DIR} is a mount point: it cannot be moved to {legacy}.')
        utils.error('To keep all history on that disk, move the whole Brewblox directory to it, and try again.')
        utils.error(
            f'You can also mount the disk on {legacy} instead, and try again. '
            + f'New history is then kept on the disk of {Path.cwd()}.'
        )
        raise SystemExit(1)

    overrides = history_volume_overrides()
    if overrides:
        for fname, source in overrides:
            utils.error(f'{fname} keeps the history of the `victoria` service in {source}.')
        utils.error(f'The update moves the history to {legacy}, and creates new databases.')
        utils.error(f'Remove that volume from the `victoria` service, move its history to {legacy}, and try again.')
        raise SystemExit(1)

    if utils.is_symlink(const.VICTORIA_DIR):
        target = os.path.realpath(const.VICTORIA_DIR)
        utils.warn(f'{const.VICTORIA_DIR} is a symbolic link to {target}.')
        utils.warn(f'The link is moved to {legacy}, and the history stays in {target}.')
        utils.warn(
            f'The new databases are created in {const.VICTORIA_DIR} and {const.VICTORIA_DENSE_DIR}, '
            + f'on the disk of {Path.cwd()}.'
        )
        if not utils.confirm('Do you want to continue?', default=False):
            utils.info('Nothing changed.')
            raise SystemExit(1)


def move_legacy_history():
    """Moves the history from before 0.12.0 aside, unchanged. Services must be stopped."""
    utils.info(f'Moving {const.VICTORIA_DIR} to {const.VICTORIA_LEGACY_DIR} ...')
    utils.sh(f'mv {const.VICTORIA_DIR} {const.VICTORIA_LEGACY_DIR}')


def _disk_usage(path: str) -> int:
    """Bytes on disk of the files in `path`, as `du` counts them"""

    def fail(ex: OSError):
        if not isinstance(ex, FileNotFoundError):  # else removed by the running database
            raise ex

    total = 0
    for root, _, files in os.walk(path, onerror=fail):
        for name in files:
            with suppress(FileNotFoundError):
                total += os.lstat(os.path.join(root, name)).st_blocks * 512
    return total


def _sudo_read(cmd: str) -> str:
    try:
        return utils.sh_read(f"sudo sh -c '{cmd}'")
    except CalledProcessError as ex:
        utils.error(f'Failed to read the history database: {utils.strex(ex)}')
        raise SystemExit(1) from ex


def dir_size(path: str) -> int:
    """Bytes on disk of a database directory, read with sudo if needed"""
    try:
        return _disk_usage(path)
    except PermissionError:
        return int(_sudo_read(f'du -sk {path}').split()[0]) * 1024


def legacy_months(legacy_dir: str) -> Dict[datetime, int]:
    """
    The monthly partitions of the legacy database, and their size on disk.

    The database writes them as root. If they cannot be read, `du` reads them with sudo.
    """
    months: Dict[datetime, int] = defaultdict(int)
    try:
        for kind in ['small', 'big']:
            base = Path(legacy_dir, 'data', kind)
            if not base.is_dir():
                continue
            for entry in sorted(os.scandir(base), key=lambda v: v.name):
                match = PARTITION_NAME.fullmatch(entry.name)
                if match and entry.is_dir(follow_symlinks=False) and 1 <= int(match[2]) <= 12:
                    month = datetime(int(match[1]), int(match[2]), 1, tzinfo=timezone.utc)
                    months[month] += _disk_usage(entry.path)
    except PermissionError:
        months.clear()
        dirs = f'{legacy_dir}/data/small/*/ {legacy_dir}/data/big/*/'
        output = _sudo_read(f'for d in {dirs}; do [ -d "$d" ] && du -sk "$d"; done; true')
        for line in output.splitlines():
            match = PARTITION_DU_LINE.fullmatch(line)
            if match and 1 <= int(match[3]) <= 12:
                month = datetime(int(match[2]), int(match[3]), 1, tzinfo=timezone.utc)
                months[month] += int(match[1]) * 1024
    return dict(months)


def dense_space(months: Dict[datetime, int]) -> float:
    """
    Disk space of the dense database: about the legacy database's last two months.

    The migration copies the last days of raw samples, with their irregular timestamps.
    New samples take less, and the database drops whole months once they expired.
    """
    return sum(months[month] for month in sorted(months)[-2:])


def averages_space(months: Dict[datetime, int], earliest: datetime) -> float:
    """Disk space of the averages of the months since `earliest`"""
    return AVERAGES_SHARE * sum(size for month, size in months.items() if _next_month(month) > earliest)


def migration_space(months: Dict[datetime, int], earliest: Optional[datetime]) -> int:
    """
    Disk space the new databases need next to the legacy database, to migrate from `earliest`.

    The legacy database stays until it is removed.
    Without `earliest`, nothing is migrated, and only new history is logged.
    """
    averages = 0 if earliest is None else averages_space(months, earliest)
    return math.ceil(dense_space(months) + averages + SPACE_MARGIN)


def choose_migration(months: Dict[datetime, int], update: bool = False) -> Optional[datetime]:
    """
    Checks the free disk space for a new migration.

    Returns where to start the migration.
    If all history does not fit, the user chooses to abort, or to migrate less.
    During the update, the user can also choose to migrate nothing: then it returns None.
    Only choices that fit are offered.
    """
    first = clamp_earliest(min(months))
    free = utils.free_disk_bytes()
    need = migration_space(months, first)
    if need <= free:
        return first

    utils.warn(
        f'Migrating all history (since {format_date(first)}) needs {format_bytes(need)} of free disk space, '
        + f'and {format_bytes(free)} is free.'
    )
    utils.warn('The current history is kept until you remove it after the migration, and the new databases add to it.')

    now = _now()
    candidates: List[Tuple[str, Optional[datetime], int]] = []
    for label, window in MIGRATION_WINDOWS:
        earliest = clamp_earliest(now - window)
        if earliest > first:
            need = migration_space(months, earliest)
            label = f'Migrate {label}, since {format_date(earliest)} ({format_bytes(need)}). Older history is lost.'
            candidates.append((label, earliest, need))
    if update:
        need = migration_space(months, None)
        label = f'Migrate nothing, and only log new history ({format_bytes(need)}). You can migrate later.'
        candidates.append((label, None, need))

    choices = [(label, earliest) for label, earliest, need in candidates if need <= free]
    if not choices:
        least = min(need for _, _, need in candidates) if candidates else need
        utils.error(f'Free at least {format_bytes(least - free)} of disk space, and try again. Nothing changed.')
        raise SystemExit(1)

    click.echo('0) Abort, and change nothing')
    for idx, (label, _) in enumerate(choices, start=1):
        click.echo(f'{idx}) {label}')

    for _ in range(MAX_ANSWERS):
        answer = utils.select('What do you want to do?', '0').strip()
        if answer == '0':
            break
        if answer.isdigit() and 1 <= int(answer) <= len(choices):
            return choices[int(answer) - 1][1]
        click.echo(f'Please type a number from 0 to {len(choices)}, and press ENTER.')

    utils.info('Aborted: nothing changed. Free some disk space, and try again.')
    raise SystemExit(1)


def check_resume_space(months: Dict[datetime, int], status: dict) -> bool:
    """Checks the free disk space for the rest of a migration that started earlier"""
    earliest = datetime.fromtimestamp(status['earliest'], timezone.utc)
    done = status.get('chunks_done') or 0
    total = status.get('chunks_total') or 0
    remaining = 1 - min(done / total, 1) if total else 1
    need = math.ceil(
        averages_space(months, earliest) * remaining
        + (dense_space(months) if status['phase'] == 'seed' else 0)
        + SPACE_MARGIN
    )
    free = utils.free_disk_bytes()
    if need <= free:
        return True

    utils.warn(
        f'The rest of the history migration needs {format_bytes(need)} of free disk space, '
        + f'and {format_bytes(free)} is free.'
    )
    utils.warn('Free some disk space, or discard the migration to start a shorter one:')
    utils.warn(f'    {DISCARD_CMD}')
    return False


def check_free_memory() -> bool:
    available = utils.available_memory_bytes()
    if available >= MIN_AVAILABLE_MEMORY:
        return True

    utils.warn(
        f'{format_bytes(available)} of memory is available, '
        + f'and the history migration needs about {format_bytes(MIN_AVAILABLE_MEMORY)}.'
    )
    utils.warn('Stop other programs or services to free memory, and try again.')
    return False


def clamp_earliest(earliest: datetime) -> datetime:
    """
    The long-term database drops imports older than its retention.
    The migration walks backwards, and imports its oldest averages last: a day of margin keeps them.
    """
    retention = parse_retention(utils.get_config().victoria.retention)
    try:
        return max(earliest, _now() - retention + timedelta(days=1))
    except OverflowError:  # before the year 1
        return earliest


def estimate_minutes(earliest: datetime, dense_days: int) -> int:
    """A rough estimate of how long the migration runs"""
    now = _now()
    days = max((now - earliest).total_seconds() / 86400, 0)
    days_1s = max((now - max(earliest, MIGRATION_1S_SINCE)).total_seconds() / 86400, 0)
    work = (days - days_1s) * MIGRATION_DAY_SECONDS + days_1s * MIGRATION_DAY_SECONDS_1S
    seconds = 2 * work + MIGRATION_SEED_SECONDS * dense_days / 30
    if not actions.host_profile().small:
        seconds /= MIGRATION_SPEEDUP
    return max(math.ceil(seconds / 60), 1)


def _migrate_url() -> str:
    return f'{utils.timeseries_url()}/migrate'


def _request(method: str, retries: int = 0, timeout: float = 30, **kwargs) -> requests.Response:
    """Sends a request to the history service, and tries again while it fails or does not answer"""
    for attempt in range(1, retries + 1):
        try:
            resp = requests.request(method, _migrate_url(), timeout=timeout, **kwargs)
            if resp.status_code < 500:
                return resp
            reason = f'{resp.status_code} {resp.reason}'
        except requests.RequestException as ex:
            reason = type(ex).__name__
        utils.info(f'The history service failed to answer ({reason}). Trying again ({attempt}/{retries}) ...')
        sleep(HTTP_RETRY_DELAY)
    return requests.request(method, _migrate_url(), timeout=timeout, **kwargs)


def _detail(resp: requests.Response) -> str:
    try:
        return resp.json().get('detail', resp.text)
    except (ValueError, AttributeError):
        return resp.text


def _raise_for_status(resp: requests.Response):
    if resp.status_code == 409:
        raise MigrationConflictError(_detail(resp))
    if resp.status_code >= 400:
        raise requests.HTTPError(f'{resp.status_code} {resp.reason}: {resp.text}', response=resp)


def migration_status() -> Optional[dict]:
    """The status of the migration, or None without one"""
    resp = _request('GET')
    _raise_for_status(resp)
    return resp.json()


def discard_migration(retries: int = 0, message: str = 'Discarding the history migration ...'):
    """Stops the migration, and deletes its state"""
    utils.info(message)
    utils.show_data(f'DELETE {_migrate_url()}?discard=true', '')
    if utils.get_opts().dry_run:
        return
    _raise_for_status(_request('DELETE', retries=retries, params={'discard': 'true'}))


def start_migration(
    earliest: datetime,
    dense_days: int,
    source_url: str = const.VICTORIA_LEGACY_URL,
) -> Optional[dict]:
    """Starts a new migration, or resumes one. The job runs in the history service."""
    body = {
        'source_url': source_url,
        'earliest': earliest.isoformat(),
        'dense_days': dense_days,
    }
    utils.info('Starting the history migration ...')
    utils.show_data(f'POST {_migrate_url()}', body)
    if utils.get_opts().dry_run:
        return None
    resp = _request('POST', retries=HTTP_RETRIES, timeout=START_TIMEOUT, json=body)
    if resp.status_code == 409 and _detail(resp) == RUNNING_DETAIL:
        # An earlier try started it, but its answer did not arrive
        return migration_status()
    _raise_for_status(resp)
    return resp.json()


def print_migration_losses(status: dict, limit: int = 20):
    lost = status.get('lost_chunks') or []
    missing = status.get('missing_series') or []
    chunk = status.get('chunk')
    period = '' if not chunk else f' of {chunk // 3600} h' if chunk % 3600 == 0 else f' of {chunk} s'
    click.echo(f'Periods{period} without averages: {len(lost)}. Fields without averages: {len(missing)}.')
    for value in lost[:limit]:
        click.echo(f'    period ending {format_timestamp(value)}')
    if len(lost) > limit:
        click.echo(f'    ... and {len(lost) - limit} more periods')
    for name in missing[:limit]:
        click.echo(f'    field {name}')
    if len(missing) > limit:
        click.echo(f'    ... and {len(missing) - limit} more fields')


def print_migration_status(status: Optional[dict]):
    legacy = utils.file_exists(const.VICTORIA_LEGACY_DIR)

    if status is None:
        if not legacy:
            click.echo('There is no history migration, and no legacy history to migrate.')
            return
        click.echo('There is no history migration. To start it, run:')
        click.echo(f'    {MIGRATE_CMD}')
        click.echo('If the history service just started, and a migration ran before, ask again in a minute.')
        # The history service also answers null for a stored migration that it cannot read
        click.echo('If a migration ran before, and the history service cannot read it, discard it with:')
        click.echo(f'    {DISCARD_CMD}')
        return

    since = format_date(migrated_since(status))
    started = format_timestamp(status['started'])

    if status['phase'] == 'done':
        finished = format_timestamp(status['finished']) if status.get('finished') else 'unknown'
        click.echo(f'The history migration is done. It migrated history since {since}, and finished at {finished}.')
        print_migration_losses(status)
        if legacy:
            click.echo('Check your graphs, and then remove the legacy history with:')
            click.echo(f'    {REMOVE_CMD}')
        else:
            click.echo('The legacy history was removed.')
        return

    if status['running']:
        if status['phase'] == 'seed':
            click.echo(
                f'The history migration (started at {started}) is copying '
                + f'the last {status["dense_days"]} days of raw history into the dense database.'
            )
        else:
            done = status.get('chunks_done')
            total = status.get('chunks_total')
            if done is None or not total:
                progress = 'counting the periods already done'
            else:
                progress = f'{done} of {total} periods done ({math.floor(100 * done / total)}%)'
            click.echo(f'The history migration (started at {started}) is averaging history since {since}: {progress}.')
        if status.get('last_error'):
            click.echo(f'It tries again after an error: {status["last_error"]}')
        return

    if status.get('cancelled'):
        click.echo('The history migration was stopped. To resume it, run:')
        click.echo(f'    {MIGRATE_CMD}')
        return

    if status.get('last_error'):
        click.echo(f'The history migration stopped: {status["last_error"]}')
        click.echo('To start again, discard it first:')
        click.echo(f'    {DISCARD_CMD}')
        click.echo(f'    {MIGRATE_CMD}')
        return

    click.echo('The history service is resuming the migration. Ask again in a minute.')


def print_migration_started(earliest: datetime, dense_days: int, minutes: int):
    seed = f'first the last {dense_days} days, then ' if dense_days else ''
    utils.info('The history migration runs in the background, inside the history service.')
    utils.info('It continues after restarts, and when your SSH session ends: you do not have to wait for it.')
    utils.info(
        f'Graphs fill in backwards from the update: {seed}back to {format_date(earliest)} ({format_minutes(minutes)}).'
    )
    utils.info('Until the migration reaches a period, graphs of that period are empty.')
    utils.info('New history is logged and shown as usual.')
    utils.info('To follow the migration, run:')
    utils.info(f'    {STATUS_CMD}')
    utils.info('Once it is done, check your graphs, and then run:')
    utils.info(f'    {REMOVE_CMD}')


def print_not_migrated():
    utils.warn(f'History from before the update is kept in {const.VICTORIA_LEGACY_DIR}.')
    utils.warn('Graphs do not show it until it is migrated. To migrate it, run:')
    utils.warn(f'    {MIGRATE_CMD}')


def print_nothing_to_migrate():
    utils.info(f'{const.VICTORIA_LEGACY_DIR} holds no history: there is nothing to migrate. To remove it, run:')
    utils.info(f'    {REMOVE_CMD} --force')


def print_dense_notice():
    config = utils.get_config()
    utils.info(
        f'{const.VICTORIA_DENSE_DIR} keeps raw history for {config.victoria.dense_retention}, '
        + 'and takes up to that plus a month on disk: about 10 MB a day for 200 fields logged every second.'
    )
    utils.info(f'It only holds recent raw history: the long-term averages are in {const.VICTORIA_DIR}.')


def offer_migration(earliest: datetime, dense_days: int) -> bool:
    """Asks to start a new migration since `earliest`. Returns whether it started."""
    earliest = clamp_earliest(earliest)
    minutes = estimate_minutes(earliest, dense_days)
    if not utils.confirm(
        'Start the history migration in the background? '
        + f'It migrates history since {format_date(earliest)} ({format_minutes(minutes)}).'
    ):
        return False

    start_migration(earliest, dense_days)
    print_migration_started(earliest, dense_days, minutes)
    return True


def explain_history_update(moving: bool):
    """Why history moves to two databases, and what the update does with it"""
    victoria = utils.get_config().victoria
    legacy = const.VICTORIA_LEGACY_DIR
    lines = [
        '',
        f'History moves to two databases (configuration version {const.HISTORY_DENSE_VERSION}):',
        f'  - {const.VICTORIA_DENSE_DIR} keeps every value as it was logged, for {victoria.dense_retention}.',
        f'  - {const.VICTORIA_DIR} keeps averages of every {victoria.sparse_interval}, for {victoria.retention}.',
        'Graphs of recent days show every value, and graphs of months or years stay fast.',
        'Long-term history takes far less disk space than when every value is kept,',
        'and both databases write to disk less often, which spares SD cards.',
        '',
        'This update:',
        f'  1. Moves your history to {legacy}, unchanged.'
        if moving
        else f'  1. Keeps your history in {legacy}: an earlier update moved it there.',
        '  2. Creates the new databases.',
        '  3. When the services run again, offers to migrate your history in the background:',
        f'     the last {MIGRATION_DENSE_DAYS} days with every value, and older history as averages.',
        f'Your history from before the update stays in {legacy} until you remove it.',
        '',
    ]
    for line in lines:
        click.echo(line)


def prepare_history_update(prev_version: Version) -> Optional[LegacyHistory]:
    """
    Before the update changes anything: check the history migration.

    ./victoria must be movable, and the migration must fit on disk.
    Returns None when the update does not concern the migration:
    it is already at 0.12.0, or there is no legacy history.
    Otherwise it returns the size of the legacy history (no months when it is empty),
    and where to start migrating it (None to migrate nothing).
    """
    if not history_migration_pending(prev_version):
        return None

    moving = history_move_pending(prev_version)
    explain_history_update(moving)
    if not utils.confirm('Do you want to continue with the update?'):
        utils.info('Nothing changed.')
        raise SystemExit(1)

    if moving:
        check_legacy_movable()
        legacy_dir = const.VICTORIA_DIR
    else:  # moved by an update that did not finish
        legacy_dir = const.VICTORIA_LEGACY_DIR

    utils.info('Checking the disk space for the history migration ...')
    months = legacy_months(legacy_dir)
    if not months:
        return LegacyHistory(months={}, earliest=None)
    return LegacyHistory(months=months, earliest=choose_migration(months, update=True))


def pull_history_images():
    """
    Pulls the images of the new history databases while the services still run.

    The update renders them before it pulls: without these, a failed pull leaves services that cannot start.
    """
    sudo = utils.optsudo()
    utils.info('Pulling history database images ...')
    try:
        utils.sh(f'{sudo}docker pull {const.VICTORIA_IMAGE}')
        utils.sh(f'{sudo}docker pull {const.VICTORIA_LEGACY_IMAGE}')
    except CalledProcessError as ex:
        utils.error(f'Failed to pull docker images: {utils.strex(ex)}')
        utils.error('Nothing changed. Fix the problem above, and run brewblox-ctl update again.')
        raise SystemExit(1) from ex


def migrate_history_after_update(legacy: LegacyHistory):
    """
    Offers to start the migration once the services run again.

    An earlier update may have left a migration state that no longer fits the new databases.
    It is discarded first. If that fails, nothing starts.
    """
    print_dense_notice()

    utils.info('Waiting for the history service ...')
    try:
        # It answers errors while it starts: only the outcome matters
        utils.sh(f'{const.CURL_WAIT} {utils.datastore_url()}/ping', silent=True)
    except CalledProcessError:
        utils.warn('The history service did not answer, and the history migration did not start.')
        utils.warn('To see why, run `brewblox-ctl follow history`. Once it runs, start the migration with:')
        utils.warn(f'    {DISCARD_CMD}')
        utils.warn(f'    {MIGRATE_CMD}')
        return

    try:
        discard_migration(retries=HTTP_RETRIES, message='Clearing the state of any earlier history migration ...')
    except (requests.RequestException, MigrationConflictError) as ex:
        utils.warn(f'Failed to clear the state of an earlier history migration: {utils.strex(ex)}')
        utils.warn('The history migration did not start. To start it, run:')
        utils.warn(f'    {DISCARD_CMD}')
        utils.warn(f'    {MIGRATE_CMD}')
        return

    if not legacy.months:
        print_nothing_to_migrate()
        return

    if legacy.earliest is None:
        print_not_migrated()
        utils.warn('To remove it instead, run:')
        utils.warn(f'    {REMOVE_CMD} --force')
        return

    if not check_free_memory():
        print_not_migrated()
        return

    try:
        started = offer_migration(legacy.earliest, MIGRATION_DENSE_DAYS)
    except EOFError:  # no terminal
        started = False
    except (requests.RequestException, MigrationConflictError) as ex:
        utils.warn(f'Failed to start the history migration: {utils.strex(ex)}')
        started = False

    if not started:
        print_not_migrated()


@contextmanager
def history_errors():
    """Exits with a message when the history service refuses a request, or does not answer"""
    try:
        yield
    except MigrationConflictError as ex:
        utils.error(str(ex))
        if 'discard' in str(ex).lower():
            utils.error('To discard it, run:')
            utils.error(f'    {DISCARD_CMD}')
        raise SystemExit(1) from ex
    except (requests.ConnectionError, requests.Timeout) as ex:
        utils.error(f'The history service at {utils.timeseries_url()} did not answer ({type(ex).__name__}).')
        utils.error('Check that Brewblox runs (`brewblox-ctl up`), wait a minute, and try again.')
        raise SystemExit(1) from ex
    except requests.RequestException as ex:
        utils.error(f'The history service failed to answer: {utils.strex(ex)}')
        raise SystemExit(1) from ex


def migrate_history(dense_days: Optional[int]):
    """Starts or resumes the migration of the legacy history"""
    with history_errors():
        _migrate_history(dense_days)


def _migrate_history(dense_days: Optional[int]):
    if not utils.file_exists(const.VICTORIA_LEGACY_DIR):
        utils.error(f'There is no legacy history to migrate: {const.VICTORIA_LEGACY_DIR} does not exist.')
        raise SystemExit(1)

    status = migration_status()

    if status is not None:
        if status['running'] or status['phase'] == 'done':
            print_migration_status(status)
            return

        if dense_days is not None and dense_days != status['dense_days']:
            utils.error(f'The history migration started with --dense-days {status["dense_days"]}.')
            utils.error('To start again with another value, discard it first:')
            utils.error(f'    {DISCARD_CMD}')
            raise SystemExit(1)

        if not status.get('cancelled'):
            # Stopped after an error that only a discard gets past, or not resumed yet after a restart
            print_migration_status(status)
            raise SystemExit(1)

        months = legacy_months(const.VICTORIA_LEGACY_DIR)
        if not check_free_memory() or not check_resume_space(months, status):
            raise SystemExit(1)

        # The history service keeps the stored `earliest`
        earliest = datetime.fromtimestamp(status['earliest'], timezone.utc)
        start_migration(earliest, status['dense_days'], status['source_url'])
        utils.info('The history migration resumes where it stopped. To follow it, run:')
        utils.info(f'    {STATUS_CMD}')
        return

    months = legacy_months(const.VICTORIA_LEGACY_DIR)
    if not months:
        print_nothing_to_migrate()
        return

    if not check_free_memory():
        raise SystemExit(1)

    earliest = choose_migration(months)
    if not offer_migration(earliest, MIGRATION_DENSE_DAYS if dense_days is None else dense_days):
        utils.info('The history migration did not start.')


def show_migration_status():
    with history_errors():
        print_migration_status(migration_status())


def discard_migration_confirmed():
    if not utils.confirm(
        'Do you want to discard the history migration? It stops, and a new migration starts from the beginning.',
        default=False,
    ):
        return
    with history_errors():
        discard_migration()
    if utils.file_exists(const.VICTORIA_LEGACY_DIR):
        utils.info('To start a new history migration, run:')
        utils.info(f'    {MIGRATE_CMD}')


def _copy_legacy_history(backup_dir: str):
    """Copies the legacy history. Only the legacy database stops: it must not change during the copy."""
    legacy = const.VICTORIA_LEGACY_DIR
    sudo = utils.optsudo()
    target = Path(backup_dir, Path(legacy).name)
    utils.sh(f'{sudo}docker compose stop victoria-legacy', check=False)
    utils.info(f'Copying {legacy} to {backup_dir} ...')
    try:
        # Follows a link to the history, and does not keep the owner: FAT disks cannot
        utils.sh(f'sudo cp -RH --preserve=timestamps -- {legacy} {shlex.quote(str(target))}')
    except CalledProcessError as ex:
        utils.sh(f'sudo rm -rf -- {shlex.quote(str(target))}', check=False)
        utils.sh(f'{sudo}docker compose start victoria-legacy', check=False)
        utils.error(f'Failed to copy {legacy}: {utils.strex(ex)}')
        utils.error(f'Nothing was removed, and {target} was removed again.')
        raise SystemExit(1) from ex


def remove_legacy_history(force: bool):
    """Removes the legacy history once the migration is done"""
    legacy = const.VICTORIA_LEGACY_DIR
    if not utils.file_exists(legacy):
        utils.info(f'There is no legacy history to remove: {legacy} does not exist.')
        return

    if utils.is_mount(legacy):
        utils.error(f'{legacy} is a mount point. Unmount it (and remove it from /etc/fstab), and try again.')
        utils.error('The history on that disk is then no longer used. You can remove it yourself.')
        raise SystemExit(1)

    status = None
    known = True  # Whether the state of the migration is known
    try:
        status = migration_status()
    except (requests.RequestException, MigrationConflictError) as ex:
        known = False
        if not force:
            utils.error(f'The history service failed to answer: {utils.strex(ex)}')
            utils.error('Start the services with `brewblox-ctl up`, wait a minute, and try again.')
            utils.error(
                'If the history service cannot start, and you accept losing history that was not migrated, run:'
            )
            utils.error(f'    {REMOVE_CMD} --force')
            raise SystemExit(1) from ex

    done = status is not None and status['phase'] == 'done'
    if not done and not force:
        utils.error('The history migration is not done:')
        print_migration_status(status)
        utils.error('To remove the legacy history anyway, run:')
        utils.error(f'    {REMOVE_CMD} --force')
        raise SystemExit(1)

    config = utils.get_config()
    if done:
        since = migrated_since(status)
        print_migration_losses(status)
        utils.warn(
            f'This removes {legacy}. History since {format_date(since)} is then kept '
            + f'as averages of every {config.victoria.sparse_interval}.'
        )
        months = legacy_months(legacy)
        # The migration plans its start up to a few intervals before or after the month it was given
        if months and min(months) < since - timedelta(days=1):
            utils.warn(f'History before {format_date(since)} was not migrated, and is removed.')
    else:
        utils.warn(f'This removes {legacy}, with the history from before the update that was not migrated.')
    if utils.is_symlink(legacy):
        target = os.path.realpath(legacy)
        utils.warn(f'{legacy} is a symbolic link to {target}. This only removes the link.')
        utils.warn(f'Remove {target} yourself once you do not need it.')
    utils.warn('This cannot be undone.')

    backup_dir = os.path.expanduser(
        utils.select(
            f'To copy {legacy} to another disk first, type a directory on that disk. To skip the copy, press ENTER.'
        ).strip()
    )
    if backup_dir:
        if not Path(backup_dir).is_dir():
            utils.error(f'{backup_dir} is not a directory. Nothing changed.')
            raise SystemExit(1)
        if Path(backup_dir, Path(legacy).name).exists():
            utils.error(f'{backup_dir} already contains {Path(legacy).name}. Nothing changed.')
            raise SystemExit(1)
        size = dir_size(legacy)
        free = utils.free_disk_bytes(backup_dir)
        if size > free:
            utils.error(
                f'{backup_dir} has {format_bytes(free)} free, and the copy needs {format_bytes(size)}. Nothing changed.'
            )
            raise SystemExit(1)
        if os.stat(backup_dir).st_dev == os.stat(legacy).st_dev:
            utils.warn(f'{backup_dir} is on the same disk as {legacy}: the copy is lost if that disk fails.')

    if not utils.confirm(f'Do you want to remove {legacy}?', default=False):
        return

    if backup_dir:
        _copy_legacy_history(backup_dir)

    # An unfinished migration would try forever to read the removed history
    if status is not None and not done:
        try:
            discard_migration()
        except (requests.RequestException, MigrationConflictError) as ex:
            utils.warn(f'Failed to discard the history migration: {utils.strex(ex)}')
            known = False

    with utils.downed_services():
        # First, so that an interrupted removal does not leave a service that creates it again
        actions.make_shared_compose(legacy_history=False)
        utils.info(f'Removing {legacy} ...')
        utils.sh(f'sudo rm -rf {legacy}')

    if not known:
        utils.info('If a history migration was started, discard it with:')
        utils.info(f'    {DISCARD_CMD}')
