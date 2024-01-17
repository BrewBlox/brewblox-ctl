"""
Tests brewblox_ctl.commands.install
"""


import pytest.__main__

from brewblox_ctl.commands import install
from brewblox_ctl.testing import check_sudo, invoke

TESTED = install.__name__
SNAPSHOT = install.snapshot.__name__


@pytest.fixture(autouse=True)
def m_sleep(mocker):
    m = mocker.patch(TESTED + '.sleep')
    return m


@pytest.fixture(autouse=True)
def m_input(mocker):
    m = mocker.patch(TESTED + '.input')
    return m


@pytest.fixture
def m_opts(mocker):
    m = mocker.patch(TESTED + '.InstallOptions')
    m.return_value.user_info = ('username', 'password')
    return m.return_value


@pytest.fixture
def m_actions(mocker):
    m = mocker.patch(TESTED + '.actions', autospec=True)
    return m


@pytest.fixture
def m_utils(mocker):
    m = mocker.patch(TESTED + '.utils', autospec=True)
    m.optsudo.return_value = 'SUDO '
    m.docker_tag.side_effect = lambda v: v
    m.prompt_user_info.return_value = ('username', 'password')
    return m


@pytest.fixture
def m_sh(mocker):
    m = mocker.patch(TESTED + '.sh', autospec=True)
    m.side_effect = check_sudo
    return m


@pytest.fixture
def m_snapshot_actions(mocker):
    m = mocker.patch(SNAPSHOT + '.actions', autospec=True)
    return m


@pytest.fixture(autouse=True)
def m_snapshot_utils(mocker):
    m = mocker.patch(SNAPSHOT + '.utils', autospec=True)
    m.optsudo.return_value = 'SUDO '
    m.docker_tag.side_effect = lambda v: v
    return m


@pytest.fixture(autouse=True)
def m_snapshot_sh(mocker):
    m = mocker.patch(SNAPSHOT + '.sh', autospec=True)
    m.side_effect = check_sudo
    return m


def test_check_confirm_opts(m_utils):
    opts = install.InstallOptions()

    # use_defaults will be true, skip_confirm not asked
    m_utils.confirm.return_value = True

    opts.check_confirm_opts()

    assert opts.use_defaults is True
    assert opts.skip_confirm is True
    assert m_utils.confirm.call_count == 1

    # use_defaults False -> explicitly ask skip_confirm
    m_utils.confirm.reset_mock()
    m_utils.confirm.return_value = False

    opts.check_confirm_opts()

    assert opts.use_defaults is False
    assert opts.skip_confirm is False
    assert m_utils.confirm.call_count == 2


def test_check_system_opts(m_utils):
    opts = install.InstallOptions()

    # no use defaults -> prompt
    m_utils.command_exists.return_value = True
    m_utils.confirm.return_value = True
    opts.check_system_opts()
    assert opts.apt_install is True
    assert m_utils.confirm.call_count == 1

    # use defaults -> no prompt
    opts.use_defaults = True
    m_utils.confirm.reset_mock()
    m_utils.confirm.return_value = False
    opts.check_system_opts()
    assert opts.apt_install is True
    assert m_utils.confirm.call_count == 0

    # apt not found -> no prompt
    opts.use_defaults = False
    m_utils.confirm.reset_mock()
    m_utils.confirm.return_value = True
    m_utils.command_exists.return_value = False
    opts.check_system_opts()
    assert opts.apt_install is False
    assert m_utils.confirm.call_count == 0


def test_check_docker_opts(m_utils):
    opts = install.InstallOptions()

    # Clean env -> prompt to install, add, pull
    m_utils.command_exists.return_value = False
    m_utils.is_docker_user.return_value = False
    m_utils.confirm.return_value = True
    opts.check_docker_opts()
    assert opts.docker_install is True
    assert opts.docker_group_add is True
    assert opts.docker_pull is True
    assert m_utils.confirm.call_count == 3

    # use_defaults set -> no prompt
    opts.use_defaults = True
    m_utils.confirm.reset_mock()
    m_utils.command_exists.return_value = False
    m_utils.is_docker_user.return_value = False
    m_utils.confirm.return_value = True
    opts.check_docker_opts()
    assert opts.docker_install is True
    assert opts.docker_group_add is True
    assert opts.docker_pull is True
    assert m_utils.confirm.call_count == 0

    # existing install -> only pull
    opts.use_defaults = False
    m_utils.confirm.reset_mock()
    m_utils.command_exists.return_value = True
    m_utils.is_docker_user.return_value = True
    m_utils.confirm.return_value = True
    opts.check_docker_opts()
    assert opts.docker_install is False
    assert opts.docker_group_add is False
    assert opts.docker_pull is True
    assert m_utils.confirm.call_count == 1


def test_check_reboot_opts(m_utils):
    opts = install.InstallOptions()

    opts.docker_install = False
    opts.docker_group_add = False
    m_utils.is_docker_user.return_value = False
    m_utils.confirm.return_value = True

    opts.check_reboot_opts()
    assert opts.reboot_needed is False
    assert m_utils.confirm.call_count == 0

    opts.docker_install = True
    opts.check_reboot_opts()
    assert opts.reboot_needed is True
    assert m_utils.confirm.call_count == 1


def test_check_init_opts(m_utils):
    opts = install.InstallOptions()

    m_utils.confirm.return_value = True
    m_utils.path_exists.return_value = True
    opts.check_init_opts()
    assert opts.init_compose is False
    assert opts.init_auth is False
    assert opts.init_datastore is False
    assert opts.init_history is False
    assert opts.init_gateway is False
    assert opts.init_eventbus is False
    assert opts.init_spark_backup is False

    m_utils.path_exists.return_value = False
    opts.check_init_opts()
    assert opts.init_compose is True
    assert opts.init_auth is True
    assert opts.init_datastore is True
    assert opts.init_history is True
    assert opts.init_gateway is True
    assert opts.init_eventbus is True
    assert opts.init_spark_backup is True
    assert m_utils.confirm.call_count == 7


def test_install_basic(m_utils, m_actions, m_input, m_sh, m_opts):
    invoke(install.install)
    assert m_sh.call_count == 15  # do everything
    assert m_input.call_count == 1  # prompt reboot

    m_sh.reset_mock()
    m_input.reset_mock()
    m_opts.prompt_reboot = False
    invoke(install.install)
    assert m_sh.call_count == 15  # do everything
    assert m_input.call_count == 0  # no reboot prompt


def test_install_minimal(m_utils, m_actions, m_input, m_sh, m_opts):
    m_opts.apt_install = False
    m_opts.docker_install = False
    m_opts.docker_group_add = False
    m_opts.docker_pull = False
    m_opts.reboot_needed = False
    m_opts.init_compose = False
    m_opts.init_auth = False
    m_opts.init_datastore = False
    m_opts.init_history = False
    m_opts.init_gateway = False
    m_opts.init_eventbus = False
    m_opts.init_spark_backup = False
    m_opts.user_info = None

    invoke(install.install)
    assert m_sh.call_count == 3  # Only the bare minimum


def test_install_snapshot(m_utils, m_actions, m_input, m_sh, m_opts, m_snapshot_sh, m_snapshot_actions):
    invoke(install.install, '--snapshot brewblox.tar.gz')
    assert m_opts.check_init_opts.call_count == 0
    assert m_snapshot_sh.call_count > 0


def test_makecert(m_utils, m_actions):
    invoke(install.makecert)
    m_actions.makecert.assert_called_once_with('./traefik', True, (), None)
