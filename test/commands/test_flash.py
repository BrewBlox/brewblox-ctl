"""
Tests brewblox_ctl.commands.flash
"""

from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from brewblox_ctl import const, utils
from brewblox_ctl.commands import flash
from brewblox_ctl.testing import invoke

TESTED = flash.__name__


@pytest.fixture
def m_usb(mocker: MockerFixture):
    m = mocker.patch(TESTED + '.usb', autospec=True)
    return m


def test_run_flasher(m_sh: Mock):
    flash.run_flasher('taggart', True, 'do-stuff')
    m_sh.assert_any_call(
        'SUDO docker run -it --rm --privileged -v /dev:/dev --pull always ' +
        'ghcr.io/brewblox/brewblox-firmware-flasher:taggart do-stuff')


def test_find_usb_spark(m_usb: Mock):
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


def test_photon_flash(m_usb: Mock, m_sh: Mock):
    m_dev = Mock()
    m_dev.idProduct = const.PID_PHOTON
    m_usb.core.find.side_effect = [
        [],
        [],
        [m_dev]
    ]
    invoke(flash.flash, '--release develop --pull')
    m_sh.assert_any_call(
        'SUDO docker run -it --rm --privileged -v /dev:/dev --pull always ' +
        'ghcr.io/brewblox/brewblox-firmware-flasher:develop flash')


def test_p1_flash(m_usb: Mock, m_sh: Mock):
    m_dev = Mock()
    m_dev.idProduct = const.PID_P1
    m_usb.core.find.side_effect = [
        [],
        [],
        [m_dev]
    ]
    invoke(flash.flash, '--release develop --pull')
    m_sh.assert_any_call(
        'SUDO docker run -it --rm --privileged -v /dev:/dev --pull always ' +
        'ghcr.io/brewblox/brewblox-firmware-flasher:develop flash')


def test_esp_flash(m_usb: Mock, m_sh: Mock):
    m_dev = Mock()
    m_dev.idProduct = const.PID_ESP32
    m_usb.core.find.side_effect = [
        [],
        [],
        [m_dev]
    ]
    invoke(flash.flash, '--release develop --pull')
    m_sh.assert_any_call(
        'SUDO docker run -it --rm --privileged -v /dev:/dev --pull always ' +
        'ghcr.io/brewblox/brewblox-firmware-flasher:develop flash')


def test_invalid_flash(m_usb: Mock):
    m_dev = Mock()
    m_dev.idProduct = 123
    m_usb.core.find.side_effect = [
        [],
        [],
        [m_dev]
    ]
    invoke(flash.flash, _err=True)


def test_wifi(m_sh: Mock, mocker: MockerFixture):
    mocker.patch(TESTED + '.LISTEN_MODE_WAIT_S', 0.0001)
    m_find = mocker.patch(TESTED + '.usb.core.find')
    m_get_string = mocker.patch(TESTED + '.usb.util.get_string', autospec=True)
    m_get_string.return_value = 'XXXXXX'
    utils.get_opts().dry_run = False

    m_find.reset_mock()
    m_sh.reset_mock()
    m_find.side_effect = [Mock(), None]  # particle
    invoke(flash.wifi)
    m_sh.assert_called_once_with('pyserial-miniterm -q /dev/ttyACM0 2>/dev/null')

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
    utils.get_opts().dry_run = True
    m_find.reset_mock()
    m_sh.reset_mock()
    m_find.side_effect = [Mock(), None]  # particle
    invoke(flash.wifi)
    m_sh.assert_called_once_with('pyserial-miniterm -q /dev/ttyACM0 2>/dev/null')
    assert m_find.return_value.call_count == 0


def test_particle(m_sh: Mock):
    invoke(flash.particle, '--release develop --pull -c testey')
    assert m_sh.call_count == 3
    m_sh.assert_any_call(
        'SUDO docker run -it --rm --privileged -v /dev:/dev --pull always ' +
        'ghcr.io/brewblox/brewblox-firmware-flasher:develop testey')
