"""
Tests brewblox_ctl.commands.fix
"""

import pytest

from brewblox_ctl.commands import fix
from brewblox_ctl.testing import invoke

TESTED = fix.__name__


@pytest.fixture
def m_actions(mocker):
    m = mocker.patch(TESTED + '.actions', autospec=True)
    return m


def test_ipv6(m_actions):
    invoke(fix.ipv6, '--config-file=/dummy')
    m_actions.fix_ipv6.assert_called_once_with('/dummy')


def test_avahi(m_actions):
    invoke(fix.avahi)
    m_actions.edit_avahi_config.assert_called_once_with()
