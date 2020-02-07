"""
Tests brewblox_ctl.http
"""

import json
from unittest.mock import call, mock_open

import pytest

from brewblox_ctl.commands import http
from brewblox_ctl.testing import invoke

TESTED = http.__name__


@pytest.fixture
def mock_wait(mocker):
    return mocker.patch(TESTED + '.wait')


@pytest.fixture
def mock_requests(mocker):
    m = mocker.patch(TESTED + '.requests')
    for meth in http.METHODS:
        getattr(m, meth).return_value.text = meth + '-response'
    return m


@pytest.fixture
def mock_retry_interval(mocker):
    return mocker.patch(TESTED + '.RETRY_INTERVAL_S', 0.001)


def test_wait(mock_requests, mock_retry_interval):
    invoke(http.http, ['wait', 'url'])
    assert mock_requests.get.call_count == 1


def test_wait_timeout(mocker, mock_requests, mock_retry_interval):
    mocker.patch(TESTED + '.RETRY_COUNT', 5)
    mock_requests.get.return_value.raise_for_status.side_effect = http.ConnectionError

    result = invoke(http.http, ['wait', 'url'], _err=True)
    assert isinstance(result.exception, TimeoutError)
    assert mock_requests.get.call_count == 5


def test_http_wait(mock_requests, mock_wait):
    invoke(http.http, ['wait', 'url'])
    assert mock_wait.call_count == 1
    assert mock_requests.call_count == 0


def test_http_methods(mock_requests):
    invoke(http.http, ['get', 'url'])

    assert mock_requests.get.call_args_list == [
        call('url', headers={}, params={}, verify=False)
    ]
    assert mock_requests.post.call_count == 0

    invoke(http.http, ['post', 'url', '--pretty'])
    assert mock_requests.post.call_args_list == [
        call('url', headers={}, params={}, verify=False)
    ]


def test_http_body(mock_requests):
    body = {'var1': 1, 'var2': 'val'}
    invoke(http.http, ['post', 'url', '-d', json.dumps(body)])
    invoke(http.http, ['post', 'url', '-d', json.dumps(body), '--json-body=false'])

    assert mock_requests.post.call_args_list == [
        call('url', headers={}, params={}, verify=False, json=body),
        call('url', headers={}, params={}, verify=False, data=json.dumps(body))
    ]


def test_http_body_conflict(mock_requests):
    invoke(http.http, ['post', 'url', '-d', 'text', '-f', 'myfile.json'], _err=True)
    assert mock_requests.post.call_count == 0


def test_http_file_body(mocker, mock_requests):
    body = {'var1': 1, 'var2': 'val'}
    open_mock = mocker.patch(TESTED + '.open', mock_open(read_data=json.dumps(body)))

    invoke(http.http, ['post', 'url', '-f', 'file.json'])
    invoke(http.http, ['post', 'url', '-f', 'file.json', '--json-body=false'])

    assert mock_requests.post.call_args_list == [
        call('url', headers={}, params={}, verify=False, json=body),
        call('url', headers={}, params={}, verify=False, data=json.dumps(body))
    ]
    assert open_mock.call_args_list == [
        call('file.json'),
        call('file.json'),
    ]


def test_http_error(mock_requests):
    mock_requests.post.return_value.raise_for_status.side_effect = http.ConnectionError
    body = {'var1': 1, 'var2': 'val'}
    invoke(http.http, ['post', 'url', '-d', json.dumps(body)], _err=True)


def test_allow_http_error(mock_requests):
    mock_requests.post.return_value.raise_for_status.side_effect = http.ConnectionError
    body = {'var1': 1, 'var2': 'val'}
    invoke(http.http, ['post', 'url', '-d', json.dumps(body), '--allow-fail'])


def test_output(mock_requests):
    result = invoke(http.http, ['get', 'url'])
    assert result.stdout == 'get-response\n'

    result = invoke(http.http, ['get', 'url', '--quiet'])
    assert result.stdout == ''
