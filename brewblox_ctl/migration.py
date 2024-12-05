"""
Manual migration steps
"""

import json
import re
from datetime import datetime
from tempfile import NamedTemporaryFile
from typing import Dict, List, Optional, Tuple

import requests
import urllib3

from . import actions, utils


def _influx_measurements() -> List[str]:
    """
    Fetch all known measurements from Influx
    This requires an InfluxDB docker container with name 'influxdb-migrate'
    to have been started.
    """
    sudo = utils.optsudo()

    raw_measurements = list(
        utils.sh_stream(
            f'{sudo}docker exec influxdb-migrate influx '
            '-database brewblox '
            "-execute 'SHOW MEASUREMENTS' "
            '-format csv'
        )
    )

    measurements = [
        s.strip().split(',')[1]
        for s in raw_measurements[1:]  # ignore line with headers
        if s.strip()
    ]

    return measurements


def _influx_line_count(service: str, args: str) -> Optional[int]:
    sudo = utils.optsudo()
    measurement = f'"brewblox"."downsample_1m"."{service}"'
    points_field = '"m_ Combined Influx points"'
    json_result = utils.sh(
        f'{sudo}docker exec influxdb-migrate influx '
        '-database brewblox '
        f"-execute 'SELECT count({points_field}) FROM {measurement} {args}' "
        '-format json',
        capture=True,
    )

    result = json.loads(json_result)

    try:
        return result['results'][0]['series'][0]['values'][0][1]
    except (IndexError, KeyError):
        return None


def _copy_influx_measurement(
    service: str,
    date: str,
    duration: str,
    target: str,
    offset: int = 0,
):
    """
    Export measurement from Influx, and copy/import to `target`.
    This requires an InfluxDB docker container with name 'influxdb-migrate'
    to have been started.
    """
    QUERY_BATCH_SIZE = 5000
    FILE_BATCH_SIZE = 50000
    FILE_DIR = './influxdb-export'
    sudo = utils.optsudo()
    measurement = f'"brewblox"."downsample_1m"."{service}"'
    args = f'where time > now() - {duration}' if duration else ''

    total_lines = _influx_line_count(service, args)
    offset = max(offset, 0)
    offset -= offset % QUERY_BATCH_SIZE  # Round down to multiple of batch size
    num_lines = offset

    if target == 'file':
        utils.sh(f'mkdir -p {FILE_DIR}')

    if total_lines is None:
        return

    while True:
        generator = utils.sh_stream(
            f'{sudo}docker exec influxdb-migrate influx '
            '-database brewblox '
            f"-execute 'SELECT * FROM {measurement} {args} ORDER BY time LIMIT {QUERY_BATCH_SIZE} OFFSET {offset}' "
            '-format csv'
        )

        headers = next(generator, '').strip()
        time = None

        if not headers:
            return

        fields = [
            f[2:].replace(' ', '\\ ')  # Remove 'm_' prefix and escape spaces
            for f in headers.split(',')[2:]  # Ignore 'name' and 'time' columns
        ]

        with NamedTemporaryFile('w') as tmp:
            for line in generator:
                if not line:
                    continue

                num_lines += 1
                values = line.strip().split(',')
                name = values[0]
                time = values[1]

                # Influx line protocol:
                # MEASUREMENT k1=1,k2=2,k3=3 TIMESTAMP
                tmp.write(f'{name} ')
                tmp.write(','.join((f'{f}={v}' for f, v in zip(fields, values[2:]) if v)))
                tmp.write(f' {time}\n')

            tmp.flush()

            if target == 'victoria':
                with open(tmp.name, 'rb') as rtmp:
                    url = f'{utils.host_url()}/victoria/write'
                    urllib3.disable_warnings()
                    requests.get(url, data=rtmp, verify=False)

            elif target == 'file':
                idx = str(offset // FILE_BATCH_SIZE + 1).rjust(3, '0')
                fname = f'{FILE_DIR}/{service}__{date}__{duration or "all"}__{idx}.lines'
                utils.sh(f'cat "{tmp.name}" >> "{fname}"')

            else:
                raise ValueError(f'Invalid target: {target}')

        offset = 0
        args = f'where time > {time}'
        utils.info(f'{service}: exported {num_lines}/{total_lines} lines')


def migrate_influxdb(
    target: str = 'victoria',
    duration: str = '',
    services: List[str] = [],
    offsets: List[Tuple[str, int]] = [],
):
    """Exports InfluxDB history data.

    The exported data is either immediately imported to the new history database,
    or saved to file.
    """
    opts = utils.get_opts()
    sudo = utils.optsudo()
    date = datetime.now().strftime('%Y%m%d_%H%M')

    utils.warn('Depending on the amount of data, this may take some hours.')
    utils.warn('You can use your system as normal while the migration is in progress.')
    utils.warn('The migration can safely be stopped and restarted or resumed.')
    utils.warn('For more info, see https://brewblox.netlify.app/dev/migration/influxdb.html')

    if opts.dry_run:
        utils.info('Dry run. Skipping migration ...')
        return

    if not utils.file_exists('./influxdb/'):
        utils.info('influxdb/ dir not found. Skipping migration ...')
        return

    utils.info('Starting InfluxDB container ...')

    # Stop container in case previous migration was cancelled
    utils.sh(f'{sudo}docker stop influxdb-migrate > /dev/null', check=False)

    # Start standalone container
    # We'll communicate using 'docker exec', so no need to publish a port
    utils.sh(
        f'{sudo}docker run '
        '--rm -d '
        '--name influxdb-migrate '
        '-v "$(pwd)/influxdb:/var/lib/influxdb" '
        'influxdb:1.8 '
        '> /dev/null'
    )

    # Do a health check until startup is done
    inner_cmd = 'curl --output /dev/null --silent --fail http://localhost:8086/health'
    bash_cmd = f'until $({inner_cmd}); do sleep 1 ; done'
    utils.sh(f"{sudo}docker exec influxdb-migrate bash -c '{bash_cmd}'")

    # Determine relevant measurement
    # Export all of them if not specified by user
    if not services:
        services = _influx_measurements()

    utils.info(f'Exporting services: {", ".join(services)}')

    # Export data and import to target
    for svc in services:
        offset = next((v for v in offsets if v[0] == svc), ('default', 0))[1]
        _copy_influx_measurement(svc, date, duration, target, offset)

    # Stop migration container
    utils.sh(f'{sudo}docker stop influxdb-migrate > /dev/null', check=False)


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
