"""
Standalone export script
"""

import json
import sys

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


if __name__ == '__main__':
    export_couchdb(sys.argv[1])
