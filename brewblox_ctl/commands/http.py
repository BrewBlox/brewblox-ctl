"""
HTTP convenience commands
"""

import json
from contextlib import suppress
from pprint import pprint
from time import sleep

import click
import requests
import urllib3
from requests.exceptions import ConnectionError, HTTPError

from brewblox_ctl import click_helpers, utils

RETRY_COUNT = 60
RETRY_INTERVAL_S = 10
METHODS = ['wait', 'get', 'put', 'post', 'patch', 'delete']


def wait(url, info_updates=False):
    echo = utils.info if info_updates else click.echo
    for i in range(RETRY_COUNT):
        with suppress(ConnectionError, HTTPError):
            echo('Connecting {}, attempt {}/{}'.format(url, i+1, RETRY_COUNT))
            requests.get(url, verify=False).raise_for_status()
            echo('Success!')
            return

        sleep(RETRY_INTERVAL_S)
    raise TimeoutError('Retry attempts exhausted')


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Click group and entrypoint"""


@cli.command(hidden=True)
@click.argument('method', required=True, type=click.Choice(METHODS))
@click.argument('url', required=True)
@click.option('--json-body', type=click.BOOL, default=True, help='Set JSON content headers.')
@click.option('-f', '--file', help='Load file and send as body.')
@click.option('-d', '--data', help='Request body.')
@click.option('-H', '--header', multiple=True, type=(str, str))
@click.option('-p', '--param', multiple=True, type=(str, str))
@click.option('-q', '--quiet', is_flag=True, help='Do not print the response. Takes precedence over --pretty.')
@click.option('--pretty', is_flag=True, help='Pretty-print JSON response.')
@click.option('--allow-fail', is_flag=True, help='Do not throw on HTTP errors.')
def http(method, url, json_body, file, data, header, param, quiet, pretty, allow_fail):
    """Send HTTP requests"""
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
        if not quiet:
            if pretty and json_body:
                pprint(resp.json())
            else:
                click.echo(resp.text)
        resp.raise_for_status()
    except Exception as ex:
        if not allow_fail:
            click.echo('Error: {}'.format(ex))
            raise SystemExit(1)
