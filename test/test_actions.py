"""
Tests brewblox_ctl.actions
"""

from socket import AF_INET, AF_INET6, SOCK_STREAM
from unittest.mock import Mock

import pytest
from configobj import ConfigObj
from psutil import AccessDenied, _common
from pytest_mock import MockerFixture

from brewblox_ctl import actions
from brewblox_ctl.testing import matching

TESTED = actions.__name__


def test_make_dotenv(m_write_file: Mock):
    actions.make_dotenv('1.2.3')
    assert 'BREWBLOX_CFG_VERSION=1.2.3' in m_write_file.call_args_list[0][0][1]


def test_make_config_dirs(m_sh: Mock):
    actions.make_config_dirs()
    m_sh.assert_called_with(matching('mkdir -p ./traefik '))


def test_make_tls_certificates(m_sh: Mock, m_file_exists: Mock):
    m_file_exists.return_value = True

    actions.make_tls_certificates()
    assert m_sh.call_count == 1

    actions.make_tls_certificates(True)
    assert m_sh.call_count == 6


def test_make_traefik_config(m_write_file: Mock):
    actions.make_traefik_config()
    assert 'address: :1883/tcp' in m_write_file.call_args_list[0][0][1]
    assert 'accessControlAllowCredentials: true' in m_write_file.call_args_list[1][0][1]


def test_make_shared_compose(m_write_file: Mock):
    actions.make_shared_compose()
    assert '127.0.0.1:9600:9600' in m_write_file.call_args_list[0][0][1]


def test_make_compose(m_read_compose: Mock, m_write_compose: Mock):
    m_read_compose.side_effect = lambda: {}
    actions.make_compose()
    m_write_compose.assert_called_with({'services': {}})

    m_read_compose.side_effect = lambda: {'version': '3.7', 'services': {'spark': {}}}
    actions.make_compose()
    m_write_compose.assert_called_with({'services': {'spark': {}}})

    m_read_compose.side_effect = FileNotFoundError
    actions.make_compose()
    m_write_compose.assert_called_with({'services': {}})


def test_apt_upgrade(m_sh: Mock, m_command_exists: Mock):
    m_command_exists.return_value = False
    actions.apt_upgrade()
    assert m_sh.call_count == 0

    m_command_exists.return_value = True
    actions.apt_upgrade()
    assert m_sh.call_count > 0


def test_make_udev_rules(m_sh: Mock, m_file_exists: Mock):
    m_file_exists.return_value = True
    actions.make_udev_rules()
    assert m_sh.call_count == 0

    m_file_exists.return_value = False
    actions.make_udev_rules()
    assert m_sh.call_count > 0


def test_install_compose_plugin(m_sh: Mock, m_check_ok: Mock, m_command_exists: Mock):
    m_check_ok.return_value = True
    actions.install_compose_plugin()
    assert m_sh.call_count == 0

    m_check_ok.return_value = False
    m_command_exists.return_value = True
    actions.install_compose_plugin()
    assert m_sh.call_count == 1

    m_check_ok.return_value = False
    m_command_exists.return_value = False
    with pytest.raises(SystemExit):
        actions.install_compose_plugin()


def test_check_ports(mocker: MockerFixture,
                     m_confirm: Mock,
                     m_getenv: Mock,
                     m_file_exists: Mock,
                     m_is_compose_up: Mock):
    m_net_connections = mocker.patch(TESTED + '.psutil.net_connections', autospec=True)
    m_net_connections.return_value = []

    m_getenv.side_effect = lambda k, default: default
    actions.check_ports()

    m_file_exists.return_value = False
    actions.check_ports()

    m_is_compose_up.return_value = False
    actions.check_ports()

    # Find a mapped port
    m_net_connections.return_value = [
        _common.sconn(fd=0,
                      family=AF_INET6,
                      type=SOCK_STREAM,
                      laddr=_common.addr('::', 1234),
                      raddr=('::', 44444),
                      status='ESTABLISHED',
                      pid=None),
        _common.sconn(fd=0,
                      family=AF_INET,
                      type=SOCK_STREAM,
                      laddr=_common.addr('0.0.0.0', 80),
                      raddr=_common.addr('::', 44444),
                      status='ESTABLISHED',
                      pid=None),
        _common.sconn(fd=0,
                      family=AF_INET6,
                      type=SOCK_STREAM,
                      laddr=_common.addr('::', 80),
                      raddr=_common.addr('::', 44444),
                      status='ESTABLISHED',
                      pid=None),
    ]
    actions.check_ports()

    m_confirm.return_value = False
    with pytest.raises(SystemExit):
        actions.check_ports()

    # no mapped ports found -> no need for confirm
    m_net_connections.return_value = []
    actions.check_ports()

    # warn and continue on error
    m_net_connections.side_effect = AccessDenied
    actions.check_ports()


def test_install_ctl_package(m_sh: Mock, m_getenv: Mock, m_user_home_exists: Mock, m_file_exists: Mock):
    m_getenv.return_value = 'release'
    m_user_home_exists.return_value = True
    m_file_exists.return_value = True

    actions.install_ctl_package()
    assert m_sh.call_count == 2

    m_sh.reset_mock()
    actions.install_ctl_package('missing')
    assert m_sh.call_count == 1

    m_sh.reset_mock()
    m_file_exists.return_value = False
    actions.install_ctl_package('never')
    assert m_sh.call_count == 1


def test_uninstall_old_ctl_package(m_sh: Mock):
    actions.uninstall_old_ctl_package()
    assert m_sh.call_count > 0


def test_deploy_ctl_wrapper(m_sh: Mock, m_user_home_exists: Mock):
    m_user_home_exists.return_value = True
    actions.make_ctl_entrypoint()
    m_sh.assert_called_with(matching('mkdir -p'))
    m_user_home_exists.return_value = False
    actions.make_ctl_entrypoint()
    m_sh.assert_called_with(matching('sudo cp'))


def test_fix_ipv6(m_sh: Mock, m_is_wsl: Mock, m_command_exists: Mock, m_read_file_sudo: Mock):
    m_is_wsl.return_value = False
    m_read_file_sudo.side_effect = [
        '{}',
        '',
        '{}',
        '{"fixed-cidr-v6": "2001:db8:1::/64"}',
    ]
    m_sh.side_effect = [
        # autodetect config
        """
        /usr/bin/dockerd -H fd:// --containerd=/run/containerd/containerd.sock
        grep --color=auto dockerd
        """,   # ps aux
        None,  # mkdir
        None,  # touch
        None,  # restart

        # with config provided, no restart
        None,  # mkdir
        None,  # touch

        # with config, service command not found
        None,  # mkdir
        None,  # touch

        # with config, config already set
        None,  # mkdir
        None,  # touch
    ]

    actions.fix_ipv6()
    assert m_sh.call_count == 4

    actions.fix_ipv6('/etc/file.json', False)
    assert m_sh.call_count == 4 + 2

    m_command_exists.return_value = False
    actions.fix_ipv6('/etc/file.json')
    assert m_sh.call_count == 4 + 2 + 2

    actions.fix_ipv6('/etc/file.json')
    assert m_sh.call_count == 4 + 2 + 2 + 2

    m_is_wsl.return_value = True
    actions.fix_ipv6('/etc/file.json')
    assert m_sh.call_count == 4 + 2 + 2 + 2


def test_edit_avahi_config(mocker: MockerFixture,
                           m_sh: Mock,
                           m_command_exists: Mock,
                           m_file_exists: Mock,
                           m_info: Mock,
                           m_warn: Mock):
    config = ConfigObj()
    m_config = mocker.patch(TESTED + '.ConfigObj')
    m_config.return_value = config

    # File not found
    m_file_exists.return_value = False
    actions.edit_avahi_config()
    assert m_config.call_count == 0
    assert m_info.call_count == 0
    assert m_warn.call_count == 0
    assert m_sh.call_count == 0

    # File is found for other tests
    m_file_exists.return_value = True

    # Noop for empty config and default settings
    m_sh.reset_mock()
    m_warn.reset_mock()
    config.clear()
    actions.edit_avahi_config()
    assert m_sh.call_count == 0
    assert m_warn.call_count == 0

    # Change config if set
    m_sh.reset_mock()
    m_warn.reset_mock()
    config['server'] = {'use-ipv6': 'no'}
    config['publish'] = {'publish-aaaa-on-ipv4': 'no'}
    config['reflector'] = {'enable-reflector': 'yes'}
    actions.edit_avahi_config()
    assert m_sh.call_count == 1
    assert m_warn.call_count == 0
    assert config['reflector']['enable-reflector'] == 'no'

    # Abort if no changes were made
    m_sh.reset_mock()
    m_warn.reset_mock()
    config['server'] = {'use-ipv6': 'no'}
    config['publish'] = {'publish-aaaa-on-ipv4': 'no'}
    config['reflector'] = {'enable-reflector': 'no'}
    actions.edit_avahi_config()
    assert m_sh.call_count == 0
    assert m_warn.call_count == 0
    assert config['reflector']['enable-reflector'] == 'no'

    # Service command does not exist
    m_sh.reset_mock()
    m_warn.reset_mock()
    config.clear()
    config['reflector'] = {'enable-reflector': 'yes'}
    m_command_exists.return_value = False
    actions.edit_avahi_config()
    assert m_sh.call_count == 0
    assert m_warn.call_count == 1
    assert config['reflector']['enable-reflector'] == 'no'


def test_edit_sshd_config(m_sh: Mock,
                          m_command_exists: Mock,
                          m_file_exists: Mock,
                          m_read_file_sudo: Mock):
    lines = '\n'.join([
        '# Allow client to pass locale environment variables',
        'AcceptEnv LANG LC_*'
    ])
    comment_lines = '\n'.join([
        '# Allow client to pass locale environment variables',
        '#AcceptEnv LANG LC_*'
    ])

    # File not exists
    m_file_exists.return_value = False
    actions.edit_sshd_config()
    assert m_sh.call_count == 0

    # No change
    m_file_exists.return_value = True
    m_read_file_sudo.return_value = comment_lines
    actions.edit_sshd_config()
    assert m_sh.call_count == 0

    # Changed, but no service restart
    m_read_file_sudo.return_value = lines
    m_command_exists.return_value = False
    actions.edit_sshd_config()
    assert m_sh.call_count == 0

    # Changed, full change
    m_read_file_sudo.return_value = lines
    m_command_exists.return_value = True
    actions.edit_sshd_config()
    m_sh.assert_called_with(matching('sudo systemctl restart'))


def test_start_esptool(m_sh: Mock, m_command_exists: Mock):
    m_command_exists.return_value = False

    actions.start_esptool('--chip esp32', 'read_flash', 'coredump.bin')
    m_sh.assert_called_with('sudo -E env "PATH=$PATH" esptool.py --chip esp32 read_flash coredump.bin')
    assert m_sh.call_count == 2

    m_sh.reset_mock()
    m_command_exists.return_value = True
    actions.start_esptool()
    m_sh.assert_called_with('sudo -E env "PATH=$PATH" esptool.py ')
    assert m_sh.call_count == 1
