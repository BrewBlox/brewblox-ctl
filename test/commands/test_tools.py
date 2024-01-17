"""
Tests brewblox_ctl.commands.tools
"""
import pytest

from brewblox_ctl.commands import tools
from brewblox_ctl.testing import invoke

TESTED = tools.__name__


@pytest.fixture
def m_utils(mocker):
    m = mocker.patch(TESTED + '.utils', autospec=True)
    m.optsudo.return_value = 'SUDO '
    m.docker_tag.side_effect = lambda v: v
    return m


def test_esptool(m_utils):
    invoke(tools.esptool, 'write_flash coredump.bin')
    m_utils.start_esptool.assert_called_with('write_flash', 'coredump.bin')

    invoke(tools.esptool, '--help')
    m_utils.start_esptool.assert_called_with('--help')

    invoke(tools.esptool, '--click-help')
    assert m_utils.start_esptool.call_count == 2


def test_dotenv(m_utils):
    invoke(tools.dotenv, 'set key value')
    m_utils.start_dotenv.assert_called_with('set', 'key', 'value')
