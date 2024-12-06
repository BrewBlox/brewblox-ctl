from pathlib import Path
from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from brewblox_ctl import testing, utils
from brewblox_ctl.models import CtlConfig, CtlOpts


@pytest.fixture(autouse=True)
def m_get_config(monkeypatch: pytest.MonkeyPatch):
    cfg = CtlConfig()
    m = Mock(spec=utils.get_config, return_value=cfg)
    monkeypatch.setattr(utils, 'get_config', m)
    return cfg


@pytest.fixture(autouse=True)
def m_get_opts(monkeypatch: pytest.MonkeyPatch):
    opts = CtlOpts()
    m = Mock(spec=utils.get_opts, return_value=opts)
    monkeypatch.setattr(utils, 'get_opts', m)
    return opts


@pytest.fixture(autouse=True)
def m_confirm(monkeypatch: pytest.MonkeyPatch):
    m = Mock(spec=utils.confirm)
    monkeypatch.setattr(utils, 'confirm', m)
    return m


@pytest.fixture(autouse=True)
def m_select(monkeypatch: pytest.MonkeyPatch):
    m = Mock(spec=utils.select)
    monkeypatch.setattr(utils, 'select', m)
    return m


@pytest.fixture(autouse=True)
def m_confirm_usb(monkeypatch: pytest.MonkeyPatch):
    m = Mock(spec=utils.confirm_usb)
    monkeypatch.setattr(utils, 'confirm_usb', m)
    return m


@pytest.fixture(autouse=True)
def m_confirm_mode(monkeypatch: pytest.MonkeyPatch):
    m = Mock(spec=utils.confirm_mode)
    monkeypatch.setattr(utils, 'confirm_mode', m)
    return m


@pytest.fixture(autouse=True)
def m_getenv(monkeypatch: pytest.MonkeyPatch):
    m = Mock(spec=utils.getenv)
    monkeypatch.setattr(utils, 'getenv', m)
    return m


@pytest.fixture(autouse=True)
def m_envdict(monkeypatch: pytest.MonkeyPatch):
    m = Mock(spec=utils.envdict)
    m.side_effect = lambda _: {}
    monkeypatch.setattr(utils, 'envdict', m)
    return m


@pytest.fixture(autouse=True)
def m_setenv(monkeypatch: pytest.MonkeyPatch):
    m = Mock(spec=utils.setenv)
    monkeypatch.setattr(utils, 'setenv', m)
    return m


@pytest.fixture(autouse=True)
def m_clearenv(monkeypatch: pytest.MonkeyPatch):
    m = Mock(spec=utils.clearenv)
    monkeypatch.setattr(utils, 'clearenv', m)
    return m


@pytest.fixture(autouse=True)
def m_file_exists(monkeypatch: pytest.MonkeyPatch):
    existing_files = set()

    def file_exists_side_effect(path: str) -> bool:
        print(f'Checking: {path} ')
        resolved_path = Path(path).resolve() if not Path(path).is_absolute() else Path(path)
        return str(resolved_path) in existing_files

    m = Mock(spec=utils.file_exists, side_effect=file_exists_side_effect)

    # Add helper methods to update the mock's behavior
    def add_existing_files(*files):
        # Convert relative paths to absolute based on cwd
        nonlocal existing_files
        existing_files.clear()
        for file in files:
            resolved_path = Path(file).resolve() if not Path(file).is_absolute() else Path(file)
            existing_files.add(str(resolved_path))

    def clear_existing_files():
        existing_files.clear()  # Clear all existing files

    m.add_existing_files = add_existing_files
    m.clear_existing_files = clear_existing_files

    monkeypatch.setattr(utils, 'file_exists', m)
    return m


@pytest.fixture(autouse=True)
def m_command_exists(monkeypatch: pytest.MonkeyPatch):
    m = Mock(spec=utils.command_exists)
    m.return_value = True
    monkeypatch.setattr(utils, 'command_exists', m)
    return m


@pytest.fixture(autouse=True)
def m_is_armv6(monkeypatch: pytest.MonkeyPatch):
    m = Mock(spec=utils.is_armv6)
    m.return_value = False
    monkeypatch.setattr(utils, 'is_armv6', m)
    return m


@pytest.fixture(autouse=True)
def m_is_wsl(monkeypatch: pytest.MonkeyPatch):
    m = Mock(spec=utils.is_wsl)
    m.return_value = False
    monkeypatch.setattr(utils, 'is_wsl', m)
    return m


@pytest.fixture(autouse=True)
def m_is_root(monkeypatch: pytest.MonkeyPatch):
    m = Mock(spec=utils.is_root)
    m.return_value = False
    monkeypatch.setattr(utils, 'is_root', m)
    return m


@pytest.fixture(autouse=True)
def m_is_docker_user(monkeypatch: pytest.MonkeyPatch):
    m = Mock(spec=utils.is_docker_user)
    m.return_value = True
    monkeypatch.setattr(utils, 'is_docker_user', m)
    return m


@pytest.fixture(autouse=True)
def m_has_docker_rights(monkeypatch: pytest.MonkeyPatch):
    m = Mock(spec=utils.has_docker_rights)
    m.return_value = False
    monkeypatch.setattr(utils, 'has_docker_rights', m)
    return m


@pytest.fixture(autouse=True)
def m_is_brewblox_dir(monkeypatch: pytest.MonkeyPatch):
    m = Mock(spec=utils.is_brewblox_dir)
    m.return_value = True
    monkeypatch.setattr(utils, 'is_brewblox_dir', m)
    return m


@pytest.fixture(autouse=True)
def m_is_empty_dir(monkeypatch: pytest.MonkeyPatch):
    m = Mock(spec=utils.is_empty_dir)
    m.return_value = False
    monkeypatch.setattr(utils, 'is_empty_dir', m)
    return m


@pytest.fixture(autouse=True)
def m_user_home_exists(monkeypatch: pytest.MonkeyPatch):
    m = Mock(spec=utils.user_home_exists)
    m.return_value = True
    monkeypatch.setattr(utils, 'user_home_exists', m)
    return m


@pytest.fixture(autouse=True)
def m_is_compose_up(monkeypatch: pytest.MonkeyPatch):
    m = Mock(spec=utils.is_compose_up)
    m.return_value = True
    monkeypatch.setattr(utils, 'is_compose_up', m)
    return m


@pytest.fixture(autouse=True)
def m_optsudo(monkeypatch: pytest.MonkeyPatch):
    m = Mock(spec=utils.optsudo)
    m.return_value = 'SUDO '
    monkeypatch.setattr(utils, 'optsudo', m)
    return m


@pytest.fixture(autouse=True)
def m_sh(monkeypatch: pytest.MonkeyPatch):
    m = Mock(spec=utils.sh)
    m.side_effect = testing.check_sudo
    monkeypatch.setattr(utils, 'sh', m)
    return m


@pytest.fixture(autouse=True)
def m_sh_stream(monkeypatch: pytest.MonkeyPatch):
    m = Mock(spec=utils.sh_stream)
    monkeypatch.setattr(utils, 'sh_stream', m)
    return m


@pytest.fixture(autouse=True)
def m_check_ok(monkeypatch: pytest.MonkeyPatch):
    m = Mock(spec=utils.check_ok)
    m.return_value = True
    monkeypatch.setattr(utils, 'check_ok', m)
    return m


@pytest.fixture(autouse=True)
def m_info(mocker: MockerFixture):
    s = mocker.spy(utils, 'info')
    return s


@pytest.fixture(autouse=True)
def m_warn(mocker: MockerFixture):
    s = mocker.spy(utils, 'warn')
    return s


@pytest.fixture(autouse=True)
def m_error(mocker: MockerFixture):
    s = mocker.spy(utils, 'error')
    return s


@pytest.fixture(autouse=True)
def m_show_data(mocker: MockerFixture):
    s = mocker.spy(utils, 'show_data')
    return s


@pytest.fixture(autouse=True)
def m_hostname(monkeypatch: pytest.MonkeyPatch):
    m = Mock(spec=utils.hostname)
    m.return_value = 'localhost'
    monkeypatch.setattr(utils, 'hostname', m)
    return m


@pytest.fixture(autouse=True)
def m_host_lan_ip(monkeypatch: pytest.MonkeyPatch):
    m = Mock(spec=utils.host_lan_ip)
    m.return_value = '192.168.0.1'
    monkeypatch.setattr(utils, 'host_lan_ip', m)
    return m


@pytest.fixture(autouse=True)
def m_host_ip_addresses(monkeypatch: pytest.MonkeyPatch):
    m = Mock(spec=utils.host_ip_addresses)
    m.return_value = ['192.168.0.1']
    monkeypatch.setattr(utils, 'host_ip_addresses', m)
    return m


@pytest.fixture(autouse=True)
def m_read_file(monkeypatch: pytest.MonkeyPatch):
    m = Mock(spec=utils.read_file)
    m.return_value = ''
    monkeypatch.setattr(utils, 'read_file', m)
    return m


@pytest.fixture(autouse=True)
def m_read_file_sudo(monkeypatch: pytest.MonkeyPatch):
    m = Mock(spec=utils.read_file_sudo)
    m.return_value = ''
    monkeypatch.setattr(utils, 'read_file_sudo', m)
    return m


@pytest.fixture(autouse=True)
def m_write_file(monkeypatch: pytest.MonkeyPatch):
    m = Mock(spec=utils.write_file)
    monkeypatch.setattr(utils, 'write_file', m)
    return m


@pytest.fixture(autouse=True)
def m_write_file_sudo(monkeypatch: pytest.MonkeyPatch):
    m = Mock(spec=utils.write_file_sudo)
    monkeypatch.setattr(utils, 'write_file_sudo', m)
    return m


@pytest.fixture(autouse=True)
def m_read_yaml(monkeypatch: pytest.MonkeyPatch):
    m = Mock(spec=utils.read_yaml)
    m.side_effect = dict
    monkeypatch.setattr(utils, 'read_yaml', m)
    return m


@pytest.fixture(autouse=True)
def m_write_yaml(monkeypatch: pytest.MonkeyPatch):
    m = Mock(spec=utils.write_yaml)
    monkeypatch.setattr(utils, 'write_yaml', m)
    return m


@pytest.fixture(autouse=True)
def m_dump_yaml(monkeypatch: pytest.MonkeyPatch):
    m = Mock(spec=utils.dump_yaml)
    m.return_value = ''
    monkeypatch.setattr(utils, 'dump_yaml', m)
    return m


@pytest.fixture(autouse=True)
def m_read_compose(monkeypatch: pytest.MonkeyPatch):
    m = Mock(spec=utils.read_compose)
    monkeypatch.setattr(utils, 'read_compose', m)
    return m


@pytest.fixture(autouse=True)
def m_write_compose(monkeypatch: pytest.MonkeyPatch):
    m = Mock(spec=utils.write_compose)
    monkeypatch.setattr(utils, 'write_compose', m)
    return m


@pytest.fixture(autouse=True)
def m_read_shared_compose(monkeypatch: pytest.MonkeyPatch):
    m = Mock(spec=utils.read_shared_compose)
    monkeypatch.setattr(utils, 'read_shared_compose', m)
    return m


@pytest.fixture(autouse=True)
def m_write_shared_compose(monkeypatch: pytest.MonkeyPatch):
    m = Mock(spec=utils.write_shared_compose)
    monkeypatch.setattr(utils, 'write_shared_compose', m)
    return m


@pytest.fixture(autouse=True)
def m_list_services(monkeypatch: pytest.MonkeyPatch):
    m = Mock(spec=utils.list_services)
    m.side_effect = lambda _: []
    monkeypatch.setattr(utils, 'list_services', m)
    return m
