"""
Tests brewblox_ctl.fixes
"""

import pytest
from brewblox_ctl import fixes
from brewblox_ctl.testing import check_sudo
from configobj import ConfigObj

TESTED = fixes.__name__


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


def test_fix_ipv6(mocker, m_utils, m_sh):
    m_utils.is_wsl.return_value = False
    m_sh.side_effect = [
        # autodetect config
        """
        /usr/bin/dockerd -H fd:// --containerd=/run/containerd/containerd.sock
        grep --color=auto dockerd
        """,   # ps aux
        None,  # touch
        '{}',  # read file
        None,  # write file
        None,  # restart

        # with config provided, no restart
        None,  # touch
        '',    # empty file
        None,  # write file

        # with config, service command not found
        None,  # touch
        '{}',  # read file
        None,  # write file

        # with config, config already set
        None,  # touch
        '{"fixed-cidr-v6": "2001:db8:1::/64"}',  # read file
    ]

    fixes.fix_ipv6()
    assert m_sh.call_count == 5

    fixes.fix_ipv6('/etc/file.json', False)
    assert m_sh.call_count == 5 + 3

    m_utils.command_exists.return_value = False
    fixes.fix_ipv6('/etc/file.json')
    assert m_sh.call_count == 5 + 3 + 3

    fixes.fix_ipv6('/etc/file.json')
    assert m_sh.call_count == 5 + 3 + 3 + 2

    m_utils.is_wsl.return_value = True
    fixes.fix_ipv6('/etc/file.json')
    assert m_sh.call_count == 5 + 3 + 3 + 2


def test_unset_avahi_reflection(mocker, m_utils, m_sh):
    config = ConfigObj()
    m_config = mocker.patch(TESTED + '.ConfigObj')
    m_config.return_value = config

    # File not found
    m_config.side_effect = OSError
    fixes.unset_avahi_reflection()
    assert m_utils.warn.call_count == 1
    assert m_sh.call_count == 0

    # By default, the value is not set
    # This should be a noop
    m_sh.reset_mock()
    m_utils.warn.reset_mock()
    m_config.side_effect = None
    config.clear()
    fixes.unset_avahi_reflection()
    assert m_sh.call_count == 0
    assert m_utils.warn.call_count == 0
    assert not config

    # enable-reflector is set
    m_sh.reset_mock()
    m_utils.warn.reset_mock()
    config['reflector'] = {'enable-reflector': 'yes', 'other': 'yes'}
    fixes.unset_avahi_reflection()
    assert m_sh.call_count == 3
    assert m_utils.warn.call_count == 0
    assert config['reflector'] == {'other': 'yes'}

    # Service command does not exist
    m_sh.reset_mock()
    m_utils.warn.reset_mock()
    m_utils.command_exists.return_value = False
    config.clear()
    config['reflector'] = {'enable-reflector': 'yes', 'other': 'yes'}
    fixes.unset_avahi_reflection()
    assert m_sh.call_count == 2
    assert m_utils.warn.call_count == 1
    assert config['reflector'] == {'other': 'yes'}
