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
    m.get_opts.return_value.dry_run = False
    return m


@pytest.fixture
def m_sh(mocker):
    m = mocker.patch(TESTED + '.utils.sh', autospec=True)
    return m


def test_init(m_utils):
    invoke(auth.enable)
    m_utils.setenv.assert_called_with(const.ENV_KEY_AUTH_ENABLED, 'True')
    m_utils.add_user.assert_called_with(None, None)

    invoke(auth.disable)
    m_utils.setenv.assert_called_with(const.ENV_KEY_AUTH_ENABLED, 'False')
    assert m_utils.add_user.call_count == 1

    m_utils.confirm.return_value = False
    invoke(auth.enable)
    m_utils.setenv.assert_called_with(const.ENV_KEY_AUTH_ENABLED, 'True')
    assert m_utils.add_user.call_count == 1


def test_add(m_utils):
    invoke(auth.add, '--username=test --password=face')
    m_utils.add_user.assert_called_with('test', 'face')

    invoke(auth.add, '--username=empty --password=""')
    m_utils.add_user.assert_called_with('empty', '')

    invoke(auth.add, '--username usr')
    m_utils.add_user.assert_called_with('usr', None)


def test_remove(m_utils):
    invoke(auth.remove, '--username=test')
    m_utils.remove_user.assert_called_once_with('test')
