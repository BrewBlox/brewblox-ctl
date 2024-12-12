"""
Tests brewblox_ctl.auth_users
"""

from unittest.mock import Mock

from pytest_mock import MockerFixture

from brewblox_ctl import auth_users, utils

TESTED = auth_users.__name__


class MatchingHash:
    def __init__(self, value: str):
        self._value = value

    def __eq__(self, hash):
        return auth_users.pbkdf2_sha512.verify(self._value, hash)

    def __repr__(self) -> str:
        return f'<MatchingHash for {self._value}>'


def test_read_users(m_file_exists: Mock, m_read_file_sudo: Mock):
    m_read_file_sudo.return_value = '\n'.join(['usr1:hashed_password_1', 'usr2:hashed_password_2'])
    m_file_exists.add_existing_files('./auth/users.passwd')

    assert auth_users.read_users() == {
        'usr1': 'hashed_password_1',
        'usr2': 'hashed_password_2',
    }

    m_file_exists.clear_existing_files()
    assert auth_users.read_users() == {}


def test_write_users(m_sh: Mock, m_write_file_sudo: Mock):
    opts = utils.get_opts()
    opts.verbose = False
    opts.dry_run = True

    auth_users.write_users({'usr': 'passwd'})
    assert m_write_file_sudo.call_count == 1
    assert m_sh.call_count == 1

    opts.dry_run = False
    auth_users.write_users({'usr': 'passwd'})
    assert m_write_file_sudo.call_count == 2
    assert m_sh.call_count == 2


def test_prompt_user_info(mocker: MockerFixture):
    m_prompt = mocker.patch(TESTED + '.click.prompt')
    m_prompt.side_effect = ['', ':', 'name']
    m_getpass = mocker.patch(TESTED + '.getpass')
    m_getpass.return_value = 'password'
    assert auth_users.prompt_user_info(None, None) == ('name', 'password')


def test_add_user(mocker: MockerFixture):
    m_prompt = mocker.patch(TESTED + '.click.prompt')
    m_prompt.return_value = 'usr'
    m_getpass = mocker.patch(TESTED + '.getpass')
    m_getpass.return_value = 'passwd'
    m_read_users = mocker.patch(TESTED + '.read_users')
    m_read_users.side_effect = lambda: {'existing': '***'}
    m_write_users = mocker.patch(TESTED + '.write_users')

    auth_users.add_user('name', 'pass')
    assert m_prompt.call_count == 0
    assert m_getpass.call_count == 0
    m_write_users.assert_called_with({'existing': '***', 'name': MatchingHash('pass')})


def test_remove_user(mocker: MockerFixture):
    opts = utils.get_opts()
    opts.dry_run = False
    m_read_users = mocker.patch(TESTED + '.read_users', autospec=True)
    m_read_users.side_effect = lambda: {'usr': 'passwd'}
    m_write_users = mocker.patch(TESTED + '.write_users', autospec=True)

    auth_users.remove_user('santa')
    assert m_write_users.call_count == 0

    auth_users.remove_user('usr')
    m_write_users.assert_called_with({})
