"""
Tests brewblox_ctl.commands.auth
"""

import pytest

from brewblox_ctl import const
from brewblox_ctl.commands import auth
from brewblox_ctl.testing import invoke

TESTED = auth.__name__


@pytest.fixture
def m_utils(mocker):
    m = mocker.patch(TESTED + '.utils', autospec=True)
    return m


@pytest.fixture
def m_auth_users(mocker):
    m = mocker.patch(TESTED + '.auth_users', autospec=True)
    return m


@pytest.fixture
def m_sh(mocker):
    m = mocker.patch(TESTED + '.utils.sh', autospec=True)
    return m


def test_init(m_utils, m_auth_users):
    invoke(auth.enable)
    m_utils.setenv.assert_called_with(const.ENV_KEY_AUTH_ENABLED, 'True')
    m_auth_users.add_user.assert_called_with(None, None)

    invoke(auth.disable)
    m_utils.setenv.assert_called_with(const.ENV_KEY_AUTH_ENABLED, 'False')
    assert m_auth_users.add_user.call_count == 1

    m_utils.confirm.return_value = False
    invoke(auth.enable)
    m_utils.setenv.assert_called_with(const.ENV_KEY_AUTH_ENABLED, 'True')
    assert m_auth_users.add_user.call_count == 1


def test_add(m_utils, m_auth_users):
    invoke(auth.add, '--username=test --password=face')
    m_auth_users.add_user.assert_called_with('test', 'face')

    invoke(auth.add, '--username=empty --password=""')
    m_auth_users.add_user.assert_called_with('empty', '')

    invoke(auth.add, '--username usr')
    m_auth_users.add_user.assert_called_with('usr', None)


def test_remove(m_utils, m_auth_users):
    invoke(auth.remove, '--username=test')
    m_auth_users.remove_user.assert_called_once_with('test')
