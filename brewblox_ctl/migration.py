"""
Manual migration steps
"""

import json
from contextlib import suppress
from datetime import datetime
from tempfile import NamedTemporaryFile
from typing import List, Optional, Tuple

import requests
import urllib3

from brewblox_ctl import actions, const, sh, utils


def migrate_compose_split():
    # Splitting compose configuration between docker-compose.yml and docker-compose.shared.yml
    # Version pinning (0.2.2) will happen automatically
    utils.info('Moving system services to docker-compose.shared.yml...')
    config = utils.read_compose()
    sys_names = [
        'mdns',
        'eventbus',
        'influx',
        'datastore',
        'history',
        'ui',
        'traefik',
    ]
    usr_config = {
        'version': config['version'],
        'services': {key: svc for (key, svc) in config['services'].items() if key not in sys_names}
    }
    utils.write_compose(usr_config)


def migrate_compose_datastore():
    # The couchdb datastore service is gone
    # Older services may still rely on it
    utils.info('Removing `depends_on` fields from docker-compose.yml...')
    config = utils.read_compose()
    for svc in config['services'].values():
        with suppress(KeyError):
            del svc['depends_on']
    utils.write_compose(config)

    # Init dir. It will be filled during upped_migrate
    utils.info('Creating redis/ dir...')
    sh('mkdir -p redis/')


def migrate_ipv6_fix():
    # Undo disable-ipv6
    sh('sudo sed -i "/net.ipv6.*.disable_ipv6 = 1/d" /etc/sysctl.conf', check=False)
    actions.fix_ipv6()


def migrate_couchdb():
    urllib3.disable_warnings()
    sudo = utils.optsudo()
    opts = utils.ctx_opts()
    redis_url = utils.datastore_url()
    couch_url = 'http://localhost:5984'

    utils.info('Migrating datastore from CouchDB to Redis...')

    if opts.dry_run:
        utils.info('Dry run. Skipping migration...')
        return

    if not utils.path_exists('./couchdb/'):
        utils.info('couchdb/ dir not found. Skipping migration...')
        return

    utils.info('Starting a temporary CouchDB container on port 5984...')
    sh(f'{sudo}docker rm -f couchdb-migrate', check=False)
    sh(f'{sudo}docker run --rm -d'
        ' --name couchdb-migrate'
        ' -v "$(pwd)/couchdb/:/opt/couchdb/data/"'
        ' -p "5984:5984"'
        ' treehouses/couchdb:2.3.1')
    sh(f'{const.CLI} http wait {couch_url}')
    sh(f'{const.CLI} http wait {redis_url}/ping')

    resp = requests.get(f'{couch_url}/_all_dbs')
    resp.raise_for_status()
    dbs = resp.json()

    for db in ['brewblox-ui-store', 'brewblox-automation']:
        if db in dbs:
            resp = requests.get(f'{couch_url}/{db}/_all_docs',
                                params={'include_docs': True})
            resp.raise_for_status()
            docs = [v['doc'] for v in resp.json()['rows']]
            # Drop invalid names
            docs[:] = [d for d in docs if len(d['_id'].split('__', 1)) == 2]
            for d in docs:
                segments = d['_id'].split('__', 1)
                d['namespace'] = f'{db}:{segments[0]}'
                d['id'] = segments[1]
                del d['_rev']
                del d['_id']
            resp = requests.post(f'{redis_url}/mset',
                                 json={'values': docs},
                                 verify=False)
            resp.raise_for_status()
            utils.info(f'Migrated {len(docs)} entries from {db}')

    if 'spark-service' in dbs:
        resp = requests.get(f'{couch_url}/spark-service/_all_docs',
                            params={'include_docs': True})
        resp.raise_for_status()
        docs = [v['doc'] for v in resp.json()['rows']]
        for d in docs:
            d['namespace'] = 'spark-service'
            d['id'] = d['_id']
            del d['_rev']
            del d['_id']
        resp = requests.post(f'{redis_url}/mset',
                             json={'values': docs},
                             verify=False)
        resp.raise_for_status()
        utils.info(f'Migrated {len(docs)} entries from spark-service')

    sh(f'{sudo}docker stop couchdb-migrate')
    sh('sudo mv couchdb/ couchdb-migrated-' + datetime.now().strftime('%Y%m%d'))


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
        ))

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
    json_result = sh(f'{sudo}docker exec influxdb-migrate influx '
                     '-database brewblox '
                     f"-execute 'SELECT count({points_field}) FROM {measurement} {args}' "
                     '-format json',
                     capture=True)

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
    offset -= (offset % QUERY_BATCH_SIZE)  # Round down to multiple of batch size
    num_lines = offset

    if target == 'file':
        sh(f'mkdir -p {FILE_DIR}')

    if total_lines is None:
        return

    while True:
        generator = utils.sh_stream(
            f'{sudo}docker exec influxdb-migrate influx '
            '-database brewblox '
            f"-execute 'SELECT * FROM {measurement} {args} ORDER BY time LIMIT {QUERY_BATCH_SIZE} OFFSET {offset}' "
            '-format csv')

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
                tmp.write(
                    ','.join((
                        f'{f}={v}'
                        for f, v in zip(fields, values[2:])
                        if v
                    ))
                )
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
                sh(f'cat "{tmp.name}" >> "{fname}"')

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
    opts = utils.ctx_opts()
    sudo = utils.optsudo()
    date = datetime.now().strftime('%Y%m%d_%H%M')

    utils.warn('Depending on the amount of data, this may take some hours.')
    utils.warn('You can use your system as normal while the migration is in progress.')
    utils.warn('The migration can safely be stopped and restarted or resumed.')
    utils.warn('For more info, see https://brewblox.netlify.app/dev/migration/influxdb.html')

    if opts.dry_run:
        utils.info('Dry run. Skipping migration...')
        return

    if not utils.path_exists('./influxdb/'):
        utils.info('influxdb/ dir not found. Skipping migration...')
        return

    utils.info('Starting InfluxDB container...')

    # Stop container in case previous migration was cancelled
    sh(f'{sudo}docker stop influxdb-migrate > /dev/null', check=False)

    # Start standalone container
    # We'll communicate using 'docker exec', so no need to publish a port
    sh(f'{sudo}docker run '
       '--rm -d '
       '--name influxdb-migrate '
       '-v "$(pwd)/influxdb:/var/lib/influxdb" '
       'influxdb:1.8 '
       '> /dev/null')

    # Do a health check until startup is done
    inner_cmd = 'curl --output /dev/null --silent --fail http://localhost:8086/health'
    bash_cmd = f'until $({inner_cmd}); do sleep 1 ; done'
    sh(f"{sudo}docker exec influxdb-migrate bash -c '{bash_cmd}'")

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
    sh(f'{sudo}docker stop influxdb-migrate > /dev/null', check=False)


def migrate_ghcr_images():
    # We migrated all brewblox images from Docker Hub to Github Container Registry
    utils.info('Migrating brewblox images to ghcr.io registry...')
    config = utils.read_compose()
    for name, svc in config['services'].items():
        img: str = svc['image']
        if img.startswith('brewblox/'):
            utils.info(f'Editing "{name}"...')
            svc['image'] = 'ghcr.io/' + img
    utils.write_compose(config)
