"""
Tests brewblox_ctl.commands.env
"""


import pytest
from click.testing import CliRunner

from brewblox_ctl import const
from brewblox_ctl.commands import env

TESTED = env.__name__


def invoke(*args, _ok=True, **kwargs):
    result = CliRunner().invoke(*args, **kwargs)
    if bool(result.exception) is _ok:
        print(result.stdout)
        raise AssertionError('{}, expected exc: {}'.format(result, _ok))


@pytest.fixture
def m_utils(mocker):
    m = mocker.patch(TESTED + '.utils')
    m.optsudo.return_value = 'SUDO '
    return m


def test_skip_confirm(m_utils):
    invoke(env.skip_confirm)
    m_utils.setenv.assert_called_with(const.SKIP_CONFIRM_KEY, 'true')

    invoke(env.skip_confirm, ['FALSE'])
    m_utils.setenv.assert_called_with(const.SKIP_CONFIRM_KEY, 'false')

    invoke(env.skip_confirm, ['NOPE'], _ok=False)
    assert m_utils.setenv.call_count == 2


def test_list_env(m_utils, mocker):
    m = mocker.patch(TESTED + '.dotenv.dotenv_values')
    m.return_value = {'k1': 'v1', 'k2': 'v2'}
    invoke(env.list_env)

    m.return_value = {}
    invoke(env.list_env)

    assert m.call_count == 2


def test_get_env(m_utils, mocker):
    m_utils.getenv.return_value = 'v1'
    invoke(env.get_env, 'k1')
    m_utils.getenv.assert_called_once_with('k1', '')


def test_set_env(m_utils):
    invoke(env.set_env, _ok=False)
    invoke(env.set_env, ['k1', 'k2'])
    m_utils.setenv.assert_called_once_with('k1', 'k2')
