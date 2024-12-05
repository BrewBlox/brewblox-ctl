"""
Tests brewblox_ctl.commands.tools
"""

from unittest.mock import Mock

import pytest

from brewblox_ctl.commands import tools
from brewblox_ctl.testing import invoke

TESTED = tools.__name__


@pytest.fixture
def m_actions(mocker):
    m = mocker.patch(TESTED + '.actions', autospec=True)
    return m


def test_esptool(m_actions: Mock):
    invoke(tools.esptool, 'write_flash coredump.bin')
    m_actions.start_esptool.assert_called_with('write_flash', 'coredump.bin')

    invoke(tools.esptool, '--help')
    m_actions.start_esptool.assert_called_with('--help')

    invoke(tools.esptool, '--click-help')
    assert m_actions.start_esptool.call_count == 2


def test_dotenv(m_actions: Mock):
    invoke(tools.dotenv, 'set key value')
    m_actions.start_dotenv.assert_called_with('set', 'key', 'value')
