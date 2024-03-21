"""
Tests brewblox_ctl.http
"""

import json
from unittest.mock import Mock, call, mock_open

import pytest
from pytest_mock import MockerFixture

from brewblox_ctl.commands import http
from brewblox_ctl.testing import invoke

TESTED = http.__name__


@pytest.fixture(autouse=True)
def m_retry_interval(mocker: MockerFixture):
    return mocker.patch(TESTED + '.RETRY_INTERVAL_S', 0.001)


@pytest.fixture
def m_wait(mocker: MockerFixture):
    return mocker.patch(TESTED + '.wait')


@pytest.fixture
def m_requests(mocker: MockerFixture):
    m = mocker.patch(TESTED + '.requests')
    for meth in http.METHODS:
        getattr(m, meth).return_value.text = meth + '-response'
    return m


def test_wait(m_requests: Mock):
    invoke(http.http, ['wait', 'url'])
    assert m_requests.get.call_count == 1


def test_wait_timeout(mocker: MockerFixture, m_requests: Mock):
    mocker.patch(TESTED + '.RETRY_COUNT', 5)
    m_requests.get.return_value.raise_for_status.side_effect = http.ConnectionError

    result = invoke(http.http, ['wait', 'url'], _err=True)
    assert isinstance(result.exception, TimeoutError)
    assert m_requests.get.call_count == 5


def test_http_wait(m_requests: Mock, m_wait: Mock):
    invoke(http.http, ['wait', 'url'])
    assert m_wait.call_count == 1
    assert m_requests.call_count == 0


def test_http_methods(m_requests: Mock):
    invoke(http.http, ['get', 'url'])

    assert m_requests.get.call_args_list == [
        call('url', headers={}, params={}, verify=False)
    ]
    assert m_requests.post.call_count == 0

    m_requests.post.return_value.json.return_value = {'happy': True}
    invoke(http.http, ['post', 'url', '--pretty'])
    assert m_requests.post.call_args_list == [
        call('url', headers={}, params={}, verify=False)
    ]


def test_http_body(m_requests: Mock):
    body = {'var1': 1, 'var2': 'val'}
    invoke(http.http, ['post', 'url', '-d', json.dumps(body)])
    invoke(http.http, ['post', 'url', '-d', json.dumps(body), '--json-body=false'])

    assert m_requests.post.call_args_list == [
        call('url', headers={}, params={}, verify=False, json=body),
        call('url', headers={}, params={}, verify=False, data=json.dumps(body))
    ]


def test_http_body_conflict(m_requests: Mock):
    invoke(http.http, ['post', 'url', '-d', 'text', '-f', 'myfile.json'], _err=True)
    assert m_requests.post.call_count == 0


def test_http_file_body(mocker: MockerFixture, m_requests: Mock):
    body = {'var1': 1, 'var2': 'val'}
    open_mock = mocker.patch(TESTED + '.open', mock_open(read_data=json.dumps(body)))

    invoke(http.http, ['post', 'url', '-f', 'file.json'])
    invoke(http.http, ['post', 'url', '-f', 'file.json', '--json-body=false'])

    assert m_requests.post.call_args_list == [
        call('url', headers={}, params={}, verify=False, json=body),
        call('url', headers={}, params={}, verify=False, data=json.dumps(body))
    ]
    assert open_mock.call_args_list == [
        call('file.json'),
        call('file.json'),
    ]


def test_http_error(m_requests: Mock):
    m_requests.post.return_value.raise_for_status.side_effect = http.ConnectionError
    body = {'var1': 1, 'var2': 'val'}
    invoke(http.http, ['post', 'url', '-d', json.dumps(body)], _err=True)


def test_allow_http_error(m_requests: Mock):
    m_requests.post.return_value.raise_for_status.side_effect = http.ConnectionError
    body = {'var1': 1, 'var2': 'val'}
    invoke(http.http, ['post', 'url', '-d', json.dumps(body), '--allow-fail'])


def test_output(m_requests: Mock):
    result = invoke(http.http, ['get', 'url'])
    assert result.stdout == 'get-response\n'

    result = invoke(http.http, ['get', 'url', '--quiet'])
    assert result.stdout == ''
