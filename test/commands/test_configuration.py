"""
Tests brewblox_ctl.commands.configuration
"""

from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from brewblox_ctl import const
from brewblox_ctl.commands import configuration
from brewblox_ctl.models import CtlConfig
from brewblox_ctl.testing import invoke

TESTED = configuration.__name__


@pytest.fixture(autouse=True)
def m_actions(mocker: MockerFixture):
    return mocker.patch(TESTED + '.actions', autospec=True)


@pytest.fixture(autouse=True)
def m_cfg_version(m_getenv: Mock) -> Mock:
    # BREWBLOX_CFG_VERSION in .env: the directory is up to date
    m_getenv.return_value = const.CFG_VERSION
    return m_getenv


def sh_cmds(m_sh: Mock):
    return [c.args[0] for c in m_sh.call_args_list]


def test_inspect():
    invoke(configuration.inspect)


def test_apply(m_file_exists: Mock):
    m_file_exists.add_existing_files('brewblox.yml')
    invoke(configuration.apply)

    m_file_exists.clear_existing_files()
    invoke(configuration.apply)


@pytest.mark.parametrize(
    'version, files',
    [
        # Up to date
        (const.CFG_VERSION, ['./victoria']),
        (const.CFG_VERSION, ['./victoria', './victoria-dense']),
        # The update moved the history, but did not finish
        ('0.11.0', ['./victoria', './victoria-dense', './victoria-legacy']),
        ('0.11.0', ['./victoria-legacy']),
        # A backup of before 0.12.0 restored an older .env on a directory with the dense database
        ('0.11.0', ['./victoria', './victoria-dense']),
        # No history
        ('0.11.0', []),
        # No BREWBLOX_CFG_VERSION in .env, and the history is not the legacy one
        (None, ['./victoria', './victoria-dense']),
    ],
)
def test_apply_no_history_update(
    m_get_config: CtlConfig,
    m_getenv: Mock,
    m_file_exists: Mock,
    m_actions: Mock,
    m_sh: Mock,
    m_error: Mock,
    version,
    files,
):
    m_getenv.return_value = version
    m_file_exists.add_existing_files(const.CONFIG_FILE, *files)

    invoke(configuration.apply)

    m_error.assert_not_called()
    m_actions.make_config_dirs.assert_called_once_with()
    m_actions.make_shared_compose.assert_called_once_with()
    m_actions.make_compose.assert_called_once_with()
    # Services are stopped while the configuration changes, and started again
    assert sh_cmds(m_sh) == ['SUDO docker compose down ', 'SUDO docker compose up -d ']


@pytest.mark.parametrize('version', ['0.11.0', '0.9.0', None])
def test_apply_history_update_pending(
    m_getenv: Mock,
    m_file_exists: Mock,
    m_actions: Mock,
    m_sh: Mock,
    m_is_compose_up: Mock,
    m_error: Mock,
    version,
):
    """
    ./victoria holds the history of before 0.12.0.
    The new configuration would open it with a newer database, which cannot be undone.
    Only the update may generate it, after it moved the history.
    """
    m_getenv.return_value = version
    m_file_exists.add_existing_files(const.CONFIG_FILE, './victoria')

    invoke(configuration.apply, _err=SystemExit)

    assert m_error.call_count > 0
    assert any('brewblox-ctl update' in c.args[0] for c in m_error.call_args_list)
    # Nothing changed: services not stopped, no configuration generated
    m_is_compose_up.assert_not_called()
    m_sh.assert_not_called()
    assert m_actions.mock_calls == []
