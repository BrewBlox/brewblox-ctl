"""
Tests brewblox_ctl.commands.diagnostic
"""

from pathlib import Path
from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from brewblox_ctl.commands import diagnostic
from brewblox_ctl.testing import invoke

TESTED = diagnostic.__name__


@pytest.fixture(autouse=True)
def m_utils(m_read_compose: Mock, m_read_shared_compose: Mock, m_list_services: Mock):
    m_read_compose.side_effect = lambda: {
        'services': {
            'spark-one': {},
        }
    }
    m_read_shared_compose.side_effect = lambda: {
        'services': {
            'history': {},
            'ui': {},
        }
    }
    m_list_services.side_effect = lambda _: [
        'sparkey',
        'spock',
    ]


@pytest.fixture(autouse=True)
def m_file_netcat(mocker: MockerFixture):
    m = mocker.patch(TESTED + '.actions.file_netcat', autospec=True)
    return m


@pytest.fixture(autouse=True)
def m_start_esptool(mocker: MockerFixture):
    m = mocker.patch(TESTED + '.actions.start_esptool', autospec=True)
    return m


@pytest.fixture()
def m_discover_tty(mocker: MockerFixture):
    def gen():
        yield from []

    m = mocker.patch(TESTED + '.discovery.discover_esp_spark_tty', autospec=True)
    m.side_effect = gen
    return m


def test_log():
    invoke(diagnostic.log, '--add-compose --upload')
    invoke(diagnostic.log, '--no-add-compose --no-upload')
    invoke(diagnostic.log, '--no-add-system')


def test_log_service_error(m_read_compose: Mock):
    m_read_compose.side_effect = FileNotFoundError
    invoke(diagnostic.log)


def test_coredump(m_start_esptool: Mock, m_file_netcat: Mock, m_command_exists: Mock):
    invoke(diagnostic.coredump)
    assert m_file_netcat.call_count == 1
    assert m_start_esptool.call_count == 1

    m_start_esptool.reset_mock()
    m_file_netcat.reset_mock()
    m_command_exists.return_value = False
    invoke(diagnostic.coredump, '--no-upload')
    assert m_start_esptool.call_count == 1
    assert m_file_netcat.call_count == 0


def test_monitor(m_sh: Mock, m_discover_tty: Mock):
    invoke(diagnostic.monitor)
    assert m_sh.call_count == 0

    def gen():
        yield from ['/dev/ttyUSB0']
    m_discover_tty.side_effect = gen

    invoke(diagnostic.monitor)
    m_sh.assert_called_with('sudo -E env "PATH=$PATH" pyserial-miniterm --raw /dev/ttyUSB0 115200')


def test_termbin(m_file_netcat: Mock):
    invoke(diagnostic.termbin, 'file')
    m_file_netcat.assert_called_once_with('termbin.com', 9999, Path('file'))
