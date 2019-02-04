"""
Standalone export script
"""

import glob
import json
import sys
from os import path

import requests
import urllib3

HOST = 'https://localhost/datastore'


def export_couchdb(target_dir):
    # Stop complaining about self-signed certs
    urllib3.disable_warnings()

    dbs = requests.get(HOST + '/_all_dbs', verify=False).json()

    for db in dbs:
        if db.startswith('_'):
            # Skip system databases
            continue

        content = requests.get(
            '{}/{}/_all_docs'.format(HOST, db),
            verify=False,
            params={'include_docs': True})
        docs = [row['doc'] for row in content.json()['rows']]

        for doc in docs:
            doc.pop('_rev')

        fname = '{}/{}.json'.format(target_dir, db)
        with open(fname, 'w') as f:
            print('Exporting to {}...'.format(fname))
            f.write(json.dumps({'docs': docs}, indent=2))


def import_couchdb(target_dir):
    # Stop complaining about self-signed certs
    urllib3.disable_warnings()

    files = glob.glob('{}/*.json'.format(target_dir))

    for fname in files:
        with open(fname) as f:
            content = json.load(f)

        if content.keys() != {'docs'}:
            print('{} is not formatted for CouchDB import'.format(fname))
            continue

        db_name = path.splitext(path.basename(fname))[0]

        requests.put('{}/{}'.format(HOST, db_name), verify=False)
        resp = requests.post(
            '{}/{}/_bulk_docs'.format(HOST, db_name),
            json=content,
            verify=False,
        )
        print('imported', db_name, resp)


if __name__ == '__main__':
    cmd, dir = sys.argv[1], sys.argv[2]
    if cmd == 'import':
        import_couchdb(dir)
    elif cmd == 'export':
        export_couchdb(dir)
    else:
        print('Invalid arguments: {}'.format(sys.argv))
        raise SystemExit(1)
