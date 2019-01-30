"""
Standalone import script
"""

import glob
import json
import sys
from os import path

import requests
import urllib3

HOST = 'https://localhost/datastore'


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
    import_couchdb(sys.argv[1])
