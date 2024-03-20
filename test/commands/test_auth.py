"""
Tests brewblox_ctl.commands.auth
"""

import pytest

from brewblox_ctl.commands import auth
from brewblox_ctl.testing import invoke

TESTED = auth.__name__


@pytest.fixture
def m_auth_users(mocker):
    m = mocker.patch(TESTED + '.auth_users', autospec=True)
    return m


def test_add(m_auth_users):
    invoke(auth.add, '--username=test --password=face')
    m_auth_users.add_user.assert_called_with('test', 'face')

    invoke(auth.add, '--username=empty --password=""')
    m_auth_users.add_user.assert_called_with('empty', '')

    invoke(auth.add, '--username usr')
    m_auth_users.add_user.assert_called_with('usr', None)


def test_remove(m_auth_users):
    invoke(auth.remove, '--username=test')
    m_auth_users.remove_user.assert_called_once_with('test')
