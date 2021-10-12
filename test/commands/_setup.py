"""
Tests brewblox_ctl.commands.setup
"""

import pytest
from brewblox_ctl.testing import check_sudo, invoke

from brewblox_ctl.commands import setup

TESTED = setup.__name__


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


def test_simple(m_utils, m_sh):
    m_utils.path_exists.return_value = False
    invoke(setup.setup)


def test_setup_port_check(m_utils, m_sh, mocker):
    m_check = mocker.patch(TESTED + '.check_ports')

    invoke(setup.setup, '--no-port-check')
    assert m_check.call_count == 0

    invoke(setup.setup)
    assert m_check.call_count == 1

    invoke(setup.setup, '--port-check')
    assert m_check.call_count == 2


def test_port_check(m_utils, m_sh):
    m_utils.getenv.side_effect = lambda k, default: default
    setup.check_ports()

    m_utils.path_exists.return_value = False
    setup.check_ports()

    # Find a mapped port
    m_sh.return_value = '\n'.join([
        'tcp6 0 0 :::1234 :::* LISTEN 11557/docker-proxy',
        'tcp6 0 0 :::80 :::* LISTEN 11557/docker-proxy',
        'tcp6 0 0 :::1234 :::* LISTEN 11557/docker-proxy'
    ])
    setup.check_ports()

    m_utils.confirm.return_value = False
    with pytest.raises(SystemExit):
        setup.check_ports()

    # no mapped ports found -> no need for confirm
    m_sh.return_value = ''
    setup.check_ports()


def test_setup_unconfirmed(m_utils, m_sh, mocker):
    mocker.patch(TESTED + '.check_ports')
    m_utils.confirm.return_value = False

    invoke(setup.setup)


def test_no_pull(m_utils, m_sh):
    m_utils.path_exists.return_value = False

    invoke(setup.setup)
    num_normal = m_sh.call_count

    m_sh.reset_mock()
    invoke(setup.setup, '--no-pull')
    assert m_sh.call_count == num_normal - 1


def test_no_avahi(m_utils, m_sh):
    m_utils.path_exists.return_value = False
    invoke(setup.setup, '--no-avahi-config')
    assert m_utils.enable_mdns_reflection.call_count == 0
