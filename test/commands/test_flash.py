"""
Tests brewblox_ctl.commands.flash
"""

from unittest.mock import Mock

import pytest
from brewblox_ctl.commands import flash
from brewblox_ctl.testing import check_sudo, invoke

TESTED = flash.__name__


@pytest.fixture
def m_utils(mocker):
    m = mocker.patch(TESTED + '.utils', autospec=True)
    m.optsudo.return_value = 'SUDO '
    m.docker_tag.side_effect = lambda v: v
    return m


@pytest.fixture
def m_sh(mocker):
    m = mocker.patch(TESTED + '.sh', autospec=True)
    m.side_effect = check_sudo
    return m


def test_run_particle_flasher(m_utils, m_sh):
    flash.run_particle_flasher('taggart', True, 'do-stuff')
    m_sh.assert_called_with(
        'SUDO docker run -it --rm --privileged -v /dev:/dev --pull always ' +
        'brewblox/firmware-flasher:taggart do-stuff')


def test_discover_usb_sparks(m_utils, m_sh):
    m_sh.return_value = '\n'.join([
        'Bus 004 Device 002: ID 05e3:0616',
        'Bus 004 Device 001: ID 1d6b:0003',
        'Bus 003 Device 006: ID 2b04:c008',  # P1
        'Bus 003 Device 006: ID 10c4:ea60',  # ESP
        'Bus 003 Device 006: ID 2b04:d006',  # Photon
    ])
    assert flash.discover_usb_sparks() == ['Spark v3', 'Spark v4', 'Spark v2']


def test_prompt_usb_spark(m_utils, m_sh):
    m_sh.side_effect = [
        '\n'.join([
            'Bus 004 Device 002: ID 05e3:0616',
            'Bus 004 Device 001: ID 1d6b:0003',
            'Bus 003 Device 006: ID 2b04:c008',  # P1
            'Bus 003 Device 006: ID 10c4:ea60',  # ESP
            'Bus 003 Device 006: ID 2b04:d006',  # Photon
        ]),
        '',
        '\n'.join([
            'Bus 004 Device 001: ID 1d6b:0003',
            'Bus 003 Device 006: ID 2b04:c008',  # P1
        ]),
    ]

    assert flash.prompt_usb_spark() == 'Spark v3'
    assert m_utils.confirm_usb.call_count == 2


def test_particle_flash(m_utils, m_sh):
    m_sh.return_value = '\n'.join([
        'Bus 004 Device 002: ID 05e3:0616',
        'Bus 004 Device 001: ID 1d6b:0003',
        'Bus 003 Device 006: ID 2b04:c008',  # P1
    ])
    invoke(flash.flash, '--release develop --pull')
    assert m_sh.call_count == 3
    m_sh.assert_called_with(
        'SUDO docker run -it --rm --privileged -v /dev:/dev --pull always ' +
        'brewblox/firmware-flasher:develop flash')


def test_esp_flash(m_utils, m_sh):
    m_sh.return_value = '\n'.join([
        'Bus 004 Device 002: ID 05e3:0616',
        'Bus 004 Device 001: ID 1d6b:0003',
        'Bus 003 Device 006: ID 10c4:ea60',  # ESP
    ])
    invoke(flash.flash, '--release develop --pull')
    assert m_sh.call_count == 3
    m_sh.assert_called_with(
        'SUDO docker run -it --rm --privileged ' +
        '-v /dev:/dev -w /app/firmware --entrypoint bash --pull always ' +
        'brewblox/brewblox-devcon-spark:develop flash')


def test_invalid_flash(m_utils, m_sh, mocker):
    mocker.patch(TESTED + '.prompt_usb_spark').return_value = 'Spark NaN'
    invoke(flash.flash, _err=True)


def test_wifi(m_utils, m_sh, mocker):
    mocker.patch(TESTED + '.LISTEN_MODE_WAIT_S', 0.0001)
    m_find = mocker.patch(TESTED + '.usb.core.find')
    m_glob = mocker.patch(TESTED + '.glob')
    m_glob.return_value = ['GLOB_PATH']
    m_utils.ctx_opts.return_value.dry_run = False

    m_find.reset_mock()
    m_sh.reset_mock()
    m_find.side_effect = [Mock(), None]  # particle
    invoke(flash.wifi)
    m_sh.assert_called_once_with('miniterm.py -q GLOB_PATH 2>/dev/null')

    m_find.reset_mock()
    m_sh.reset_mock()
    m_glob.return_value = []  # expect path to fallback to /dev/ttyACM0
    m_find.side_effect = [Mock(), None]  # particle
    invoke(flash.wifi)
    m_sh.assert_called_once_with('miniterm.py -q /dev/ttyACM0 2>/dev/null')

    m_find.reset_mock()
    m_sh.reset_mock()
    m_find.side_effect = [None, Mock()]  # ESP
    invoke(flash.wifi)
    assert m_sh.call_count == 0
    assert m_find.call_count == 2

    m_find.reset_mock()
    m_sh.reset_mock()
    m_find.side_effect = [None, None, None, Mock()]  # ESP, second try
    invoke(flash.wifi)
    assert m_sh.call_count == 0
    assert m_find.call_count == 4

    # No USB calls should be made in dry runs
    m_utils.ctx_opts.return_value.dry_run = True
    m_glob.return_value = ['GLOB_PATH']
    m_find.reset_mock()
    m_sh.reset_mock()
    m_find.side_effect = [Mock(), None]  # particle
    invoke(flash.wifi)
    m_sh.assert_called_once_with('miniterm.py -q GLOB_PATH 2>/dev/null')
    assert m_find.return_value.call_count == 0


def test_particle(m_utils, m_sh):
    invoke(flash.particle, '--release develop --pull -c testey')
    assert m_sh.call_count == 2
    m_sh.assert_called_with(
        'SUDO docker run -it --rm --privileged -v /dev:/dev --pull always ' +
        'brewblox/firmware-flasher:develop testey')


# def test_fix_ipv6(m_utils, m_sh):
#     invoke(flash.fix_ipv6)
#     assert m_utils.fix_ipv6.call_count == 1