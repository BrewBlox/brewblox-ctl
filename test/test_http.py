"""
Tests brewblox_ctl.http
"""

import json
from unittest.mock import call, mock_open

import pytest
from click.testing import CliRunner

from brewblox_ctl import http

TESTED = http.__name__


@pytest.fixture
def mock_wait(mocker):
    return mocker.patch(TESTED + '.wait')


@pytest.fixture
def mock_requests(mocker):
    m = mocker.patch(TESTED + '.requests')
    m.status_code = 200
    return m


@pytest.fixture
def mock_retry_interval(mocker):
    return mocker.patch(TESTED + '.RETRY_INTERVAL_S', 0.001)


def test_wait(mock_requests, mock_retry_interval):
    http.wait('url')
    assert mock_requests.get.call_count == 1


def test_wait_timeout(mocker, mock_requests, mock_retry_interval):
    mocker.patch(TESTED + '.RETRY_COUNT', 5)
    mock_requests.get.return_value.raise_for_status.side_effect = http.ConnectionError

    with pytest.raises(TimeoutError):
        http.wait('url')
    assert mock_requests.get.call_count == 5


def test_http_wait(mock_requests, mock_wait):
    runner = CliRunner()
    result = runner.invoke(http.http, ['wait', 'url'])
    assert result.exit_code == 0
    assert mock_wait.call_count == 1
    assert mock_requests.call_count == 0


def test_http_methods(mock_requests):
    runner = CliRunner()
    result = runner.invoke(http.http, ['get', 'url'])

    assert mock_requests.get.call_args_list == [
        call('url', headers={}, params={}, verify=False)
    ]
    assert result.exit_code == 0
    assert mock_requests.post.call_count == 0

    runner.invoke(http.http, ['post', 'url'])
    assert mock_requests.post.call_args_list == [
        call('url', headers={}, params={}, verify=False)
    ]


def test_http_body(mock_requests):
    body = {'var1': 1, 'var2': 'val'}
    runner = CliRunner()
    runner.invoke(http.http, ['post', 'url', '-d', json.dumps(body)])
    runner.invoke(http.http, ['post', 'url', '-d', json.dumps(body), '--json-body=false'])

    assert mock_requests.post.call_args_list == [
        call('url', headers={}, params={}, verify=False, json=body),
        call('url', headers={}, params={}, verify=False, data=json.dumps(body))
    ]


def test_http_body_conflict(mock_requests):
    runner = CliRunner()
    result = runner.invoke(http.http, ['post', 'url', '-d', 'text', '-f', 'myfile.json'])
    assert result.exit_code != 0
    assert mock_requests.post.call_count == 0


def test_http_file_body(mocker, mock_requests):
    body = {'var1': 1, 'var2': 'val'}
    open_mock = mocker.patch(TESTED + '.open', mock_open(read_data=json.dumps(body)))

    runner = CliRunner()
    runner.invoke(http.http, ['post', 'url', '-f', 'file.json'])
    runner.invoke(http.http, ['post', 'url', '-f', 'file.json', '--json-body=false'])

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
    runner = CliRunner()
    result = runner.invoke(http.http, ['post', 'url', '-d', json.dumps(body)])
    assert result.exit_code != 0
