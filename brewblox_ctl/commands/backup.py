"""
Saving / loading backups
"""


import json
import zipfile
from contextlib import suppress
from datetime import datetime
from glob import glob
from os import getgid, getuid, mkdir
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory

import click
import requests
import urllib3
import yaml
from brewblox_ctl import click_helpers, const, sh, utils
from brewblox_ctl.commands import http
from dotenv import load_dotenv


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Top-level commands"""


@cli.group()
def backup():
    """Save or load backups."""


@backup.command()
@click.option('--save-compose/--no-save-compose',
              default=True,
              help='Include docker-compose.yml in backup.')
@click.option('--ignore-spark-error',
              is_flag=True,
              help='Skip unreachable or disconnected Spark services')
def save(save_compose, ignore_spark_error):
    """Create a backup of Brewblox settings.

    A zip archive containing JSON/YAML files is created in the ./backup/ directory.
    The archive name will include current date and time to ensure uniqueness.

    The backup is not exported to any kind of remote/cloud storage.

    To use this command in scripts, run it as `brewblox-ctl --quiet backup save`.
    Its only output to stdout will be the absolute path to the created backup.

    The command will fail if any of the Spark services could not be contacted.

    As it does not make any destructive changes to configuration,
    this command is not affected by --dry-run.

    \b
    Stored data:
    - .env
    - docker-compose.yml.   (Optional)
    - Datastore databases.
    - Spark service blocks.
    - Node-RED data.
    - Mosquitto config files.

    \b
    NOT stored:
    - History data.

    """
    utils.check_config()
    urllib3.disable_warnings()

    file = f'backup/brewblox_backup_{datetime.now().strftime("%Y%m%d_%H%M")}.zip'
    with suppress(FileExistsError):
        mkdir(Path('backup/').resolve())

    store_url = utils.datastore_url()

    utils.info('Waiting for the datastore...')
    http.wait(store_url + '/ping', info_updates=True)

    config = utils.read_compose()
    sparks = [
        k for k, v in config['services'].items()
        if v.get('image', '').startswith('brewblox/brewblox-devcon-spark')
    ]
    zipf = zipfile.ZipFile(file, 'w', zipfile.ZIP_DEFLATED)

    # Always save .env
    utils.info('Exporting .env')
    zipf.write('.env')

    # Always save datastore
    utils.info('Exporting datastore')
    resp = requests.post(store_url + '/mget',
                         json={'namespace': '', 'filter': '*'},
                         verify=False)
    resp.raise_for_status()
    zipf.writestr('global.redis.json', resp.text)

    if save_compose:
        utils.info('Exporting docker-compose.yml')
        zipf.write('docker-compose.yml')

    for spark in sparks:
        utils.info(f'Exporting Spark blocks from `{spark}`')
        resp = requests.post(f'{utils.host_url()}/{spark}/blocks/backup/save', verify=False)
        try:
            resp.raise_for_status()
            zipf.writestr(spark + '.spark.json', resp.text)
        except Exception as ex:
            if ignore_spark_error:
                utils.info(f'Skipping Spark `{spark}` due to error: {str(ex)}')
            else:
                raise ex

    for fname in [
        *glob('node-red/*.js*'),
        *glob('node-red/lib/**/*.js*'),
        *glob('mosquitto/*.conf'),
    ]:
        zipf.write(fname)

    zipf.close()
    click.echo(Path(file).resolve())
    utils.info('Done!')


def mset(data):
    with NamedTemporaryFile('w') as tmp:
        utils.show_data('datastore', data)
        json.dump(data, tmp)
        tmp.flush()
        sh(f'{const.CLI} http post --quiet {utils.datastore_url()}/mset -f {tmp.name}')


@backup.command()
@click.argument('archive')
@click.option('--load-env/--no-load-env',
              default=True,
              help='Load and write .env file. Read .env values.')
@click.option('--load-compose/--no-load-compose',
              default=True,
              help='Load and write docker-compose.yml.')
@click.option('--load-datastore/--no-load-datastore',
              default=True,
              help='Load and write datastore entries.')
@click.option('--load-spark/--no-load-spark',
              default=True,
              help='Load and write Spark blocks.')
@click.option('--load-node-red/--no-load-node-red',
              default=True,
              help='Load and write Node-RED data.')
@click.option('--load-mosquitto/--no-load-mosquitto',
              default=True,
              help='Load and write Mosquitto config files.')
@click.option('--update/--no-update',
              default=True,
              help='Run brewblox-ctl update after loading the backup.')
def load(archive,
         load_env,
         load_compose,
         load_datastore,
         load_spark,
         load_node_red,
         load_mosquitto,
         update):
    """Load and apply Brewblox settings backup.

    This function uses files generated by `brewblox-ctl backup save` as input.
    You can use the --load-XXXX options to partially load the backup.

    This does not attempt to merge data: it will overwrite current docker-compose.yml,
    datastore entries, and Spark blocks.

    Blocks on Spark services not in the backup file will not be affected.

    If dry-run is enabled, it will echo all configuration from the backup archive.

    Steps:
        - Write .env
        - Read .env values
        - Write docker-compose.yml, run `docker-compose up`.
        - Write all datastore files found in backup.
        - Write all Spark blocks found in backup.
        - Write Node-RED config files found in backup.
        - Write Mosquitto config files found in backup.
        - Run brewblox-ctl update
    """
    utils.check_config()
    utils.confirm_mode()
    urllib3.disable_warnings()

    sudo = utils.optsudo()
    host_url = utils.host_url()
    store_url = utils.datastore_url()

    zipf = zipfile.ZipFile(archive, 'r', zipfile.ZIP_DEFLATED)
    available = zipf.namelist()
    redis_file = 'global.redis.json'
    couchdb_files = [v for v in available if v.endswith('.datastore.json')]
    spark_files = [v for v in available if v.endswith('.spark.json')]
    node_red_files = [v for v in available if v.startswith('node-red/')]
    mosquitto_files = [v for v in available if v.startswith('mosquitto/')]

    if load_env and '.env' in available:
        utils.info('Loading .env file')
        with NamedTemporaryFile('w') as tmp:
            data = zipf.read('.env').decode()
            utils.info('Writing .env')
            utils.show_data('.env', data)
            tmp.write(data)
            tmp.flush()
            sh(f'cp -f {tmp.name} .env')

        utils.info('Reading .env values')
        load_dotenv(Path('.env').resolve())

    if load_compose:
        if 'docker-compose.yml' in available:
            utils.info('Loading docker-compose.yml')
            config = yaml.safe_load(zipf.read('docker-compose.yml'))
            # Older services may still depend on the `datastore` service
            # The `depends_on` config is useless anyway in a brewblox system
            for svc in config['services'].values():
                with suppress(KeyError):
                    del svc['depends_on']
            utils.write_compose(config)
            sh(f'{sudo}docker-compose up -d')
        else:
            utils.info('docker-compose.yml file not found in backup archive')

    if load_datastore:
        if redis_file in available or couchdb_files:
            utils.info('Waiting for the datastore...')
            sh(f'{const.CLI} http wait {store_url}/ping')
            # Wipe UI/Automation, but leave Spark files
            mdelete_cmd = '{} http post {}/mdelete --quiet -d \'{{"namespace":"{}", "filter":"*"}}\''
            sh(mdelete_cmd.format(const.CLI, store_url, 'brewblox-ui-store'))
            sh(mdelete_cmd.format(const.CLI, store_url, 'brewblox-automation'))
        else:
            utils.info('No datastore files found in backup archive')

        if redis_file in available:
            data = json.loads(zipf.read(redis_file).decode())
            utils.info(f'Loading {len(data["values"])} entries from Redis datastore')
            mset(data)

        # Backwards compatibility for UI/automation files from CouchDB
        # The IDs here are formatted as {moduleId}__{objId}
        # The module ID becomes part of the Redis namespace
        for db in ['brewblox-ui-store', 'brewblox-automation']:
            fname = f'{db}.datastore.json'
            if fname not in available:
                continue
            docs = json.loads(zipf.read(fname).decode())
            # Drop invalid names (not prefixed with module ID)
            docs[:] = [d for d in docs if len(d['_id'].split('__', 1)) == 2]
            # Add namespace / ID fields
            for d in docs:
                segments = d['_id'].split('__', 1)
                d['namespace'] = f'{db}:{segments[0]}'
                d['id'] = segments[1]
                del d['_id']
            utils.info(f'Loading {len(docs)} entries from database `{db}`')
            mset({'values': docs})

        # Backwards compatibility for Spark service files
        # There is no module ID field here
        spark_db = 'spark-service'
        spark_fname = f'{spark_db}.datastore.json'
        if spark_fname in available:
            docs = json.loads(zipf.read(spark_fname).decode())
            for d in docs:
                d['namespace'] = spark_db
                d['id'] = d['_id']
                del d['_id']
            utils.info(f'Loading {len(docs)} entries from database `{spark_db}`')
            mset({'values': docs})

    if load_spark:
        sudo = utils.optsudo()

        if not spark_files:
            utils.info('No Spark files found in backup archive')

        for f in spark_files:
            spark = f[:-len('.spark.json')]
            utils.info(f'Writing blocks to Spark service `{spark}`')
            with NamedTemporaryFile('w') as tmp:
                data = json.loads(zipf.read(f).decode())
                utils.show_data(spark, data)
                json.dump(data, tmp)
                tmp.flush()
                sh(f'{const.CLI} http post {host_url}/{spark}/blocks/backup/load -f {tmp.name}')
                sh(f'{sudo}docker-compose restart {spark}')

    if load_node_red and node_red_files:
        sudo = ''
        if [getgid(), getuid()] != [1000, 1000]:
            sudo = 'sudo '

        with TemporaryDirectory() as tmpdir:
            zipf.extractall(tmpdir, members=node_red_files)
            sh('mkdir -p ./node-red')
            sh(f'{sudo}chown 1000:1000 ./node-red/')
            sh(f'{sudo}chown -R 1000:1000 {tmpdir}')
            sh(f'{sudo}cp -rfp {tmpdir}/node-red/* ./node-red/')

    if load_mosquitto and mosquitto_files:
        zipf.extractall(members=mosquitto_files)

    zipf.close()

    if update:
        utils.info('Updating brewblox...')
        sh(f'{const.CLI} update')

    utils.info('Done!')
