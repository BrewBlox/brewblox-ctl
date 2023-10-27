"""
Tests brewblox_ctl.actions
"""

from socket import AF_INET, AF_INET6, SOCK_STREAM

import pytest
from configobj import ConfigObj
from psutil import AccessDenied, _common

from brewblox_ctl import actions
from brewblox_ctl.testing import check_sudo, matching

TESTED = actions.__name__


@pytest.fixture
def m_utils(mocker):
    m = mocker.patch(TESTED + '.utils', autospec=True)
    m.optsudo.return_value = 'SUDO '
    return m


@pytest.fixture
def m_sh(mocker):
    m = mocker.patch(TESTED + '.sh', autospec=True)
    m.side_effect = check_sudo
    return m


def test_makecert(m_utils, m_sh):
    m_utils.hostname.return_value = 'hostname'
    m_utils.host_ip_addresses.return_value = ['192.168.0.1']
    actions.makecert('./traefik')
    assert m_sh.call_count == 3


def test_update_system_packages(m_utils, m_sh):
    m_utils.command_exists.return_value = False
    actions.update_system_packages()
    assert m_sh.call_count == 0

    m_utils.command_exists.return_value = True
    actions.update_system_packages()
    assert m_sh.call_count > 0
    assert m_utils.info.call_count == 1


def test_add_particle_udev_rules(m_utils, m_sh):
    m_utils.path_exists.return_value = True
    actions.add_particle_udev_rules()
    assert m_sh.call_count == 0

    m_utils.path_exists.return_value = False
    actions.add_particle_udev_rules()
    assert m_sh.call_count > 0
    assert m_utils.info.call_count == 1


def test_check_compose_plugin(m_utils, m_sh, mocker):
    m_utils.check_ok.return_value = True
    actions.check_compose_plugin()
    assert m_sh.call_count == 0

    m_utils.check_ok.return_value = False
    m_utils.command_exists.return_value = True
    actions.check_compose_plugin()
    assert m_sh.call_count == 1

    m_utils.check_ok.return_value = False
    m_utils.command_exists.return_value = False
    with pytest.raises(SystemExit):
        actions.check_compose_plugin()


def test_check_ports(m_utils, m_sh, mocker):
    m_net_connections = mocker.patch(TESTED + '.psutil.net_connections', autospec=True)
    m_net_connections.return_value = []

    m_utils.getenv.side_effect = lambda k, default: default
    actions.check_ports()

    m_utils.path_exists.return_value = False
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

    m_utils.confirm.return_value = False
    with pytest.raises(SystemExit):
        actions.check_ports()

    # no mapped ports found -> no need for confirm
    m_net_connections.return_value = []
    actions.check_ports()

    # warn and continue on error
    m_net_connections.side_effect = AccessDenied
    actions.check_ports()


def test_install_ctl_package(m_utils, m_sh, mocker):
    m_utils.getenv.return_value = 'release'
    m_utils.user_home_exists.return_value = True
    m_utils.path_exists.return_value = True

    actions.install_ctl_package()
    assert m_sh.call_count == 2

    m_sh.reset_mock()
    actions.install_ctl_package('missing')
    assert m_sh.call_count == 1

    m_sh.reset_mock()
    m_utils.path_exists.return_value = False
    actions.install_ctl_package('never')
    assert m_sh.call_count == 1


def test_uninstall_old_ctl_package(m_utils, m_sh):
    actions.uninstall_old_ctl_package()
    assert m_sh.call_count > 0


def test_deploy_ctl_wrapper(m_utils, m_sh):
    m_utils.user_home_exists.return_value = True
    actions.deploy_ctl_wrapper()
    m_sh.assert_called_with(matching('mkdir -p'))
    m_utils.user_home_exists.return_value = False
    actions.deploy_ctl_wrapper()
    m_sh.assert_called_with(matching('sudo cp'))


def test_fix_ipv6(mocker, m_utils, m_sh):
    m_utils.is_wsl.return_value = False
    m_sh.side_effect = [
        # autodetect config
        """
        /usr/bin/dockerd -H fd:// --containerd=/run/containerd/containerd.sock
        grep --color=auto dockerd
        """,   # ps aux
        None,  # mkdir
        None,  # touch
        '{}',  # read file
        None,  # write file
        None,  # restart

        # with config provided, no restart
        None,  # mkdir
        None,  # touch
        '',    # empty file
        None,  # write file

        # with config, service command not found
        None,  # mkdir
        None,  # touch
        '{}',  # read file
        None,  # write file

        # with config, config already set
        None,  # mkdir
        None,  # touch
        '{"fixed-cidr-v6": "2001:db8:1::/64"}',  # read file
    ]

    actions.fix_ipv6()
    assert m_sh.call_count == 6

    actions.fix_ipv6('/etc/file.json', False)
    assert m_sh.call_count == 6 + 4

    m_utils.command_exists.return_value = False
    actions.fix_ipv6('/etc/file.json')
    assert m_sh.call_count == 6 + 4 + 4

    actions.fix_ipv6('/etc/file.json')
    assert m_sh.call_count == 6 + 4 + 4 + 3

    m_utils.is_wsl.return_value = True
    actions.fix_ipv6('/etc/file.json')
    assert m_sh.call_count == 6 + 4 + 4 + 3


def test_edit_avahi_config(mocker, m_utils, m_sh):
    config = ConfigObj()
    m_path = mocker.patch(TESTED + '.Path').return_value
    m_config = mocker.patch(TESTED + '.ConfigObj')
    m_config.return_value = config

    # File not found
    m_path.exists.return_value = False
    actions.edit_avahi_config()
    assert m_config.call_count == 0
    assert m_utils.info.call_count == 0
    assert m_utils.warn.call_count == 0
    assert m_sh.call_count == 0

    # By default, the value is not set
    # Do not change an explicit 'no' value
    m_path.exists.return_value = True
    m_sh.reset_mock()
    m_utils.warn.reset_mock()
    config['reflector'] = {'enable-reflector': 'no'}
    actions.edit_avahi_config()
    assert m_sh.call_count == 3
    assert m_utils.warn.call_count == 0
    assert config['reflector']['enable-reflector'] == 'no'

    # Empty config
    m_sh.reset_mock()
    m_utils.warn.reset_mock()
    config.clear()
    actions.edit_avahi_config()
    assert m_sh.call_count == 3
    assert m_utils.warn.call_count == 0
    assert config['reflector']['enable-reflector'] == 'yes'

    # Abort if no changes were made
    m_sh.reset_mock()
    m_utils.warn.reset_mock()
    config['server'] = {'use-ipv6': 'no'}
    config['publish'] = {'publish-aaaa-on-ipv4': 'no'}
    config['reflector'] = {'enable-reflector': 'yes'}
    actions.edit_avahi_config()
    assert m_sh.call_count == 0
    assert m_utils.warn.call_count == 0
    assert config['reflector']['enable-reflector'] == 'yes'

    # Service command does not exist
    m_sh.reset_mock()
    m_utils.warn.reset_mock()
    m_utils.command_exists.return_value = False
    config.clear()
    actions.edit_avahi_config()
    assert m_sh.call_count == 2
    assert m_utils.warn.call_count == 1
    assert config['reflector']['enable-reflector'] == 'yes'


def test_disable_ssh_accept_env(m_utils, m_sh, mocker):
    m_file = mocker.patch(TESTED + '.Path').return_value
    lines = '\n'.join([
        '# Allow client to pass locale environment variables',
        'AcceptEnv LANG LC_*'
    ])
    comment_lines = '\n'.join([
        '# Allow client to pass locale environment variables',
        '#AcceptEnv LANG LC_*'
    ])

    # File not exists
    m_file.exists.return_value = False
    actions.disable_ssh_accept_env()
    assert m_sh.call_count == 0

    # No change
    m_file.exists.return_value = True
    m_file.read_text.return_value = comment_lines
    actions.disable_ssh_accept_env()
    assert m_sh.call_count == 0

    # Changed, but no sevice restart
    m_file.read_text.return_value = lines
    m_utils.command_exists.return_value = False
    actions.disable_ssh_accept_env()
    m_sh.assert_called_with(matching('sudo cp'))

    # Changed, full change
    m_file.read_text.return_value = lines
    m_utils.command_exists.return_value = True
    actions.disable_ssh_accept_env()
    m_sh.assert_called_with(matching('sudo systemctl restart'))
