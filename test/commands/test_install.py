"""
Tests brewblox_ctl.commands.install
"""

from unittest.mock import Mock

import pytest.__main__
from pytest_mock import MockerFixture

from brewblox_ctl import utils
from brewblox_ctl.commands import install
from brewblox_ctl.testing import invoke

TESTED = install.__name__
SNAPSHOT = install.snapshot.__name__


@pytest.fixture(autouse=True)
def m_sleep(mocker: MockerFixture):
    return mocker.patch(TESTED + '.sleep')


@pytest.fixture(autouse=True)
def m_input(mocker: MockerFixture):
    return mocker.patch(TESTED + '.input')


@pytest.fixture
def m_opts(mocker: MockerFixture):
    m = mocker.patch(TESTED + '.InstallOptions')
    m.return_value.user_info = ('username', 'password')
    return m.return_value


@pytest.fixture
def m_actions(mocker: MockerFixture):
    return mocker.patch(TESTED + '.actions', autospec=True)


@pytest.fixture
def m_auth_users(mocker: MockerFixture):
    m = mocker.patch(TESTED + '.auth_users', autospec=True)
    m.prompt_user_info.return_value = ('username', 'password')
    return m


@pytest.fixture
def m_snapshot_actions(mocker: MockerFixture):
    return mocker.patch(SNAPSHOT + '.actions', autospec=True)


def test_check_compatibility(mocker: MockerFixture, m_confirm: Mock, m_is_armv6: Mock):
    opts = install.InstallOptions()
    mocker.patch(TESTED + '.SystemExit', RuntimeError)

    m_is_armv6.return_value = True
    m_confirm.return_value = True
    opts.check_compatibility()

    m_confirm.return_value = False
    with pytest.raises(RuntimeError):
        opts.check_compatibility()

    m_is_armv6.return_value = False
    opts.check_compatibility()


def test_check_confirm_opts(m_confirm: Mock):
    opts = install.InstallOptions()

    # use_defaults will be true, skip_confirm not asked
    m_confirm.return_value = True

    opts.check_confirm_opts()

    assert opts.use_defaults is True
    assert opts.skip_confirm is True
    assert m_confirm.call_count == 1

    # use_defaults False -> explicitly ask skip_confirm
    m_confirm.reset_mock()
    m_confirm.return_value = False

    opts.check_confirm_opts()

    assert opts.use_defaults is False
    assert opts.skip_confirm is False
    assert m_confirm.call_count == 2


def test_check_system_opts(m_confirm: Mock, m_command_exists: Mock):
    opts = install.InstallOptions()

    # no use defaults -> prompt
    m_command_exists.add_existing_commands('apt-get')
    m_confirm.return_value = True
    opts.check_system_opts()
    assert opts.apt_install is True
    assert m_confirm.call_count == 1

    # use defaults -> no prompt
    opts.use_defaults = True
    m_confirm.reset_mock()
    m_confirm.return_value = False
    opts.check_system_opts()
    assert opts.apt_install is True
    assert m_confirm.call_count == 0

    # apt not found -> no prompt
    opts.use_defaults = False
    m_confirm.reset_mock()
    m_confirm.return_value = True
    m_command_exists.clear_existing_commands()
    opts.check_system_opts()
    assert opts.apt_install is False
    assert m_confirm.call_count == 0


def test_check_docker_opts(m_confirm: Mock, m_command_exists: Mock, m_is_docker_user: Mock):
    opts = install.InstallOptions()

    # Clean env -> prompt to install, add, pull
    m_is_docker_user.return_value = False
    m_confirm.return_value = True
    opts.check_docker_opts()
    assert opts.docker_install is True
    assert opts.docker_group_add is True
    assert opts.docker_pull is True
    assert m_confirm.call_count == 3

    # use_defaults set -> no prompt
    opts.use_defaults = True
    m_confirm.reset_mock()
    m_is_docker_user.return_value = False
    m_confirm.return_value = True
    opts.check_docker_opts()
    assert opts.docker_install is True
    assert opts.docker_group_add is True
    assert opts.docker_pull is True
    assert m_confirm.call_count == 0

    # existing install -> only pull
    opts.use_defaults = False
    m_confirm.reset_mock()
    m_command_exists.add_existing_commands('docker')
    m_is_docker_user.return_value = True
    m_confirm.return_value = True
    opts.check_docker_opts()
    assert opts.docker_install is False
    assert opts.docker_group_add is False
    assert opts.docker_pull is True
    assert m_confirm.call_count == 1


def test_check_reboot_opts(m_confirm: Mock, m_is_docker_user: Mock):
    opts = install.InstallOptions()

    opts.docker_install = False
    opts.docker_group_add = False
    m_is_docker_user.return_value = False
    m_confirm.return_value = True

    opts.check_reboot_opts()
    assert opts.reboot_needed is False
    assert m_confirm.call_count == 0

    opts.docker_install = True
    opts.check_reboot_opts()
    assert opts.reboot_needed is True
    assert m_confirm.call_count == 1


def test_check_init_opts(m_confirm: Mock, m_file_exists: Mock):
    opts = install.InstallOptions()

    m_file_exists.add_existing_files(
        './docker-compose.yml', './auth/', './redis/', './victoria/', './traefik/', './mosquitto/', './spark/backup/'
    )
    m_confirm.return_value = True
    opts.check_init_opts()
    assert opts.init_compose is False
    assert opts.init_auth is False
    assert opts.init_datastore is False
    assert opts.init_history is False
    assert opts.init_gateway is False
    assert opts.init_eventbus is False
    assert opts.init_spark_backup is False

    m_file_exists.clear_existing_files()
    opts.check_init_opts()
    assert opts.init_compose is True
    assert opts.init_auth is True
    assert opts.init_datastore is True
    assert opts.init_history is True
    assert opts.init_gateway is True
    assert opts.init_eventbus is True
    assert opts.init_spark_backup is True
    assert m_confirm.call_count == 7


def test_install_basic(m_actions: Mock, m_input: Mock, m_sh: Mock, m_opts: Mock):
    invoke(install.install)
    assert m_sh.call_count == 15  # do everything
    assert m_input.call_count == 1  # prompt reboot

    m_sh.reset_mock()
    m_input.reset_mock()
    m_opts.prompt_reboot = False
    invoke(install.install)
    assert m_sh.call_count == 15  # do everything
    assert m_input.call_count == 0  # no reboot prompt


def test_install_minimal(m_actions: Mock, m_input: Mock, m_sh: Mock, m_opts: Mock, m_is_compose_up: Mock):
    m_is_compose_up.return_value = False
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
    assert m_sh.call_count == 0


def test_install_snapshot(m_actions: Mock, m_input: Mock, m_sh: Mock, m_opts: Mock, m_snapshot_actions: Mock):
    utils.get_opts().dry_run = True
    invoke(install.install, '--snapshot brewblox.tar.gz')
    assert m_opts.check_init_opts.call_count == 0
    assert m_sh.call_count > 0


def test_makecert(m_actions: Mock):
    invoke(install.makecert)
    m_actions.make_tls_certificates.assert_called_once_with(True, (), None)
