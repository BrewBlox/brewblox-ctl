"""
Tests brewblox_ctl.commands.diagnostic
"""

from pathlib import Path

import pytest

from brewblox_ctl.commands import diagnostic
from brewblox_ctl.testing import check_sudo, invoke

TESTED = diagnostic.__name__


@pytest.fixture
def m_utils(mocker):
    m = mocker.patch(TESTED + '.utils', autospec=True)
    m.optsudo.return_value = 'SUDO '
    m.read_compose.return_value = {
        'services': {
            'spark-one': {},
        }
    }
    m.read_shared_compose.return_value = {
        'services': {
            'history': {},
            'ui': {},
        }
    }
    m.list_services.return_value = [
        'sparkey',
        'spock',
    ]
    return m


@pytest.fixture
def m_sh(mocker):
    m = mocker.patch(TESTED + '.sh', autospec=True)
    m.side_effect = check_sudo
    return m


def test_log(m_utils, m_sh):
    invoke(diagnostic.log, '--add-compose --upload')
    invoke(diagnostic.log, '--no-add-compose --no-upload')
    invoke(diagnostic.log, '--no-add-system')


def test_log_service_error(m_utils, m_sh):
    m_utils.read_compose.side_effect = FileNotFoundError
    invoke(diagnostic.log)


def test_coredump(m_utils, m_sh):
    invoke(diagnostic.coredump)
    assert m_utils.file_netcat.call_count == 1
    assert m_utils.start_esptool.call_count == 1

    m_utils.start_esptool.reset_mock()
    m_utils.file_netcat.reset_mock()
    m_utils.command_exists.return_value = False
    invoke(diagnostic.coredump, '--no-upload')
    assert m_utils.start_esptool.call_count == 1
    assert m_utils.file_netcat.call_count == 0


def test_termbin(m_utils):
    invoke(diagnostic.termbin, 'file')
    m_utils.file_netcat.assert_called_once_with('termbin.com', 9999, Path('file'))
