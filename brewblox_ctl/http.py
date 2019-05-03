"""
HTTP convenience commands
"""

import json
from contextlib import suppress
from time import sleep

import click
import requests
import urllib3
from requests.exceptions import ConnectionError, HTTPError

from brewblox_ctl import click_helpers

RETRY_COUNT = 60
RETRY_INTERVAL_S = 10


def wait(url):
    for i in range(RETRY_COUNT):
        with suppress(ConnectionError, HTTPError):
            print('Connecting {}, attempt {}/{}'.format(url, i+1, RETRY_COUNT))
            requests.get(url, verify=False).raise_for_status()
            print('Success!')
            return

        sleep(RETRY_INTERVAL_S)
    raise TimeoutError('Retry attempts exhausted')


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Click group and entrypoint"""


@cli.command()
@click.argument('method', required=True,
                type=click.Choice(['wait', 'get', 'put', 'post', 'patch', 'delete']))
@click.argument('url', required=True)
@click.option('--json-body', type=click.BOOL, default=True, help='Set JSON content headers')
@click.option('-f', '--file', help='Load file and send as body')
@click.option('-d', '--data', help='Request body')
@click.option('-H', '--header', multiple=True, type=(str, str))
@click.option('-p', '--param', help='URL parameter', multiple=True, type=(str, str))
def http(method, url, json_body, file, data, header, param):
    """Send HTTP requests (debugging tool)"""
    urllib3.disable_warnings()

    if method == 'wait':
        return wait(url)

    body = None
    kwargs = {
        'headers': dict(header),
        'params': dict(param),
        'verify': False,
    }

    if file and data:
        raise ValueError('Unable to process both file and data body')
    elif file:
        with open(file) as f:
            body = f.read()
    elif data:
        body = data

    if body:
        if json_body:
            kwargs['json'] = json.loads(body)
        else:
            kwargs['data'] = body

    resp = getattr(requests, method)(url, **kwargs)
    try:
        print(resp.text)
        resp.raise_for_status()
    except Exception as ex:
        print('Error:', ex)
        raise SystemExit(1)
