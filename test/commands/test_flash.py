"""
Tests brewblox_ctl.commands.flash
"""

from unittest.mock import Mock

import pytest
from brewblox_ctl import const
from brewblox_ctl.commands import flash
from brewblox_ctl.testing import check_sudo, invoke

TESTED = flash.__name__


@pytest.fixture
def m_usb(mocker):
    m = mocker.patch(TESTED + '.usb', autospec=True)
    return m


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


def test_find_usb_spark(m_usb, m_utils, m_sh):
    m_usb.core.find.side_effect = [
        # too many
        ['Spark 2'],
        ['Spark 3'],
        [],
        # too few
        [],
        [],
        [],
        # success
        [],
        [],
        ['Spark 4']
    ]

    assert flash.find_usb_spark() == 'Spark 4'
    assert m_utils.confirm_usb.call_count == 2


def test_photon_flash(m_usb, m_utils, m_sh):
    m_dev = Mock()
    m_dev.idProduct = const.PID_PHOTON
    m_usb.core.find.side_effect = [
        [],
        [],
        [m_dev]
    ]
    invoke(flash.flash, '--release develop --pull')
    m_sh.assert_called_with(
        'SUDO docker run -it --rm --privileged -v /dev:/dev --pull always ' +
        'brewblox/firmware-flasher:develop flash')


def test_p1_flash(m_usb, m_utils, m_sh):
    m_dev = Mock()
    m_dev.idProduct = const.PID_P1
    m_usb.core.find.side_effect = [
        [],
        [],
        [m_dev]
    ]
    invoke(flash.flash, '--release develop --pull')
    m_sh.assert_called_with(
        'SUDO docker run -it --rm --privileged -v /dev:/dev --pull always ' +
        'brewblox/firmware-flasher:develop flash')


def test_esp_flash(m_usb, m_utils, m_sh):
    m_dev = Mock()
    m_dev.idProduct = const.PID_ESP32
    m_usb.core.find.side_effect = [
        [],
        [],
        [m_dev]
    ]
    invoke(flash.flash, '--release develop --pull')
    m_sh.assert_called_with(
        'SUDO docker run -it --rm --privileged ' +
        '-v /dev:/dev -w /app/firmware --entrypoint bash --pull always ' +
        'brewblox/brewblox-devcon-spark:develop flash')


def test_invalid_flash(m_usb, m_utils, m_sh):
    m_dev = Mock()
    m_dev.idProduct = 123
    m_usb.core.find.side_effect = [
        [],
        [],
        [m_dev]
    ]
    invoke(flash.flash, _err=True)


def test_wifi(m_usb, m_utils, m_sh, mocker):
    mocker.patch(TESTED + '.LISTEN_MODE_WAIT_S', 0.0001)
    m_find = mocker.patch(TESTED + '.usb.core.find')
    m_utils.ctx_opts.return_value.dry_run = False

    m_find.reset_mock()
    m_sh.reset_mock()
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
    m_find.reset_mock()
    m_sh.reset_mock()
    m_find.side_effect = [Mock(), None]  # particle
    invoke(flash.wifi)
    m_sh.assert_called_once_with('miniterm.py -q /dev/ttyACM0 2>/dev/null')
    assert m_find.return_value.call_count == 0


def test_particle(m_utils, m_sh):
    invoke(flash.particle, '--release develop --pull -c testey')
    assert m_sh.call_count == 2
    m_sh.assert_called_with(
        'SUDO docker run -it --rm --privileged -v /dev:/dev --pull always ' +
        'brewblox/firmware-flasher:develop testey')
