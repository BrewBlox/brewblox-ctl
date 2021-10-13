"""
Tests brewblox_ctl.actions
"""

import pytest
from brewblox_ctl import actions
from brewblox_ctl.testing import check_sudo

TESTED = actions.__name__


@pytest.fixture
def m_utils(mocker):
    m = mocker.patch(TESTED + '.utils')
    m.optsudo.return_value = 'SUDO '
    return m


@pytest.fixture
def m_sh(mocker):
    m = mocker.patch(TESTED + '.sh')
    m.side_effect = check_sudo
    return m


def test_makecert(m_utils, m_sh):
    actions.makecert('./traefik')
    assert m_sh.call_count == 4


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


def test_port_check(m_utils, m_sh):
    m_utils.getenv.side_effect = lambda k, default: default
    actions.check_ports()

    m_utils.path_exists.return_value = False
    actions.check_ports()

    # Find a mapped port
    m_sh.return_value = '\n'.join([
        'tcp6 0 0 :::1234 :::* LISTEN 11557/docker-proxy',
        'tcp6 0 0 :::80 :::* LISTEN 11557/docker-proxy',
        'tcp6 0 0 :::1234 :::* LISTEN 11557/docker-proxy'
    ])
    actions.check_ports()

    m_utils.confirm.return_value = False
    with pytest.raises(SystemExit):
        actions.check_ports()

    # no mapped ports found -> no need for confirm
    m_sh.return_value = ''
    actions.check_ports()


def test_download_ctl(m_utils, m_sh, mocker):
    m_utils.getenv.return_value = 'release'
    m_utils.user_home_exists.return_value = True

    actions.download_ctl()
    assert m_sh.call_count == 5

    m_sh.reset_mock()
    m_utils.user_home_exists.return_value = False
    actions.download_ctl()
    assert m_sh.call_count == 4
