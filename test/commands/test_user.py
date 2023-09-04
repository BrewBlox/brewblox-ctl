"""
Tests brewblox_ctl.commands.user
"""

import pytest

from brewblox_ctl.commands import user
from brewblox_ctl.testing import invoke

TESTED = user.__name__


@pytest.fixture
def m_sh(mocker):
    m = mocker.patch(TESTED + '.utils.sh', autospec=True)
    return m


def test_add(m_sh):
    invoke(user.add, '--username=test --password=face')
    assert m_sh.call_count == 2
    invoke(user.add, '--username=: --password=face', _err=True)
    assert m_sh.call_count == 2


def test_remove(m_sh, mocker):

    m_read = mocker.patch(TESTED + '.utils.read_users')
    m_read.side_effect = lambda: {'test': 'password_hash'}
    m_write = mocker.patch(TESTED + '.utils.write_users')

    invoke(user.remove, '--username=test')
    m_write.assert_called_with({})

    m_write.reset_mock()
    invoke(user.remove, '--username=other')
    m_write.assert_not_called()
