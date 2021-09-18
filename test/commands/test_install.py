"""
Tests brewblox_ctl.commands.install
"""


from unittest.mock import Mock

import pytest.__main__
from brewblox_ctl.commands import install
from brewblox_ctl.testing import check_sudo, invoke, matching

TESTED = install.__name__
SNAPSHOT = install.snapshot.__name__


@pytest.fixture(autouse=True)
def m_sleep(mocker):
    m = mocker.patch(TESTED + '.sleep')
    return m


@pytest.fixture(autouse=True)
def m_input(mocker):
    m = mocker.patch(TESTED + '.input')
    return m


@pytest.fixture
def m_utils(mocker):
    m = mocker.patch(TESTED + '.utils')
    m.optsudo.return_value = 'SUDO '
    m.docker_tag.side_effect = lambda v: v
    return m


@pytest.fixture
def m_sh(mocker):
    m = mocker.patch(TESTED + '.sh')
    m.side_effect = check_sudo
    return m


@pytest.fixture(autouse=True)
def m_snapshot_utils(mocker):
    m = mocker.patch(SNAPSHOT + '.utils')
    m.optsudo.return_value = 'SUDO '
    m.is_brewblox_cwd.return_value = False
    m.docker_tag.side_effect = lambda v: v
    return m


@pytest.fixture(autouse=True)
def m_snapshot_sh(mocker):
    m = mocker.patch(SNAPSHOT + '.sh')
    m.side_effect = check_sudo
    return m


def test_install_short(m_utils, m_sh):
    m_utils.path_exists.return_value = False
    m_utils.command_exists.side_effect = [
        False,  # apt
        True,  # docker
        True,  # docker-compose
    ]
    invoke(install.install, '--use-defaults')
    assert m_sh.call_count == 3


def test_install_full(m_utils, m_sh):
    m_utils.path_exists.return_value = False
    m_utils.is_docker_user.return_value = False
    m_utils.command_exists.side_effect = [
        True,  # apt
        False,  # docker
        False,  # docker-compose
    ]
    invoke(install.install)
    assert m_sh.call_count == 6


def test_install_snapshot(m_utils, m_sh):
    m_utils.path_exists.return_value = False
    m_utils.is_docker_user.return_value = False
    m_utils.command_exists.side_effect = [
        True,  # apt
        False,  # docker
        False,  # docker-compose
    ]
    invoke(install.install, '--snapshot brewblox.tar.gz')
    assert m_sh.call_count == 4


def test_install_decline(m_utils, m_sh):
    m_utils.path_exists.return_value = False
    m_utils.is_docker_user.return_value = False
    m_utils.confirm.return_value = False
    m_utils.command_exists.side_effect = [
        True,  # apt
        False,  # docker
    ]
    invoke(install.install, '--dir ./brewblox --no-reboot')
    print(m_utils.confirm.call_args_list)
    assert m_utils.confirm.call_count == 4

    m_utils.confirm.reset_mock()
    m_utils.command_exists.side_effect = [
        True,  # apt
        False,  # docker
    ]

    invoke(install.install)


def test_install_existing_declined(m_utils, m_sh):
    m_utils.path_exists.return_value = True
    m_utils.is_docker_user.return_value = True
    m_utils.confirm.side_effect = [
        True,  # Use defaults
        False,  # No to overwrite
    ]
    m_utils.command_exists.side_effect = [
        True,  # apt
        False,  # docker
    ]
    invoke(install.install)
    m_sh.assert_not_called()


def test_install_existing_continue(m_utils, m_sh):
    m_utils.path_exists.return_value = True
    m_utils.confirm.side_effect = [
        True,  # ok using dir
        True,  # continue existing dir
        False,  # prompt reboot
    ]
    m_utils.is_docker_user.return_value = True
    m_utils.command_exists.side_effect = [
        False,  # apt
        True,  # docker
    ]
    invoke(install.install, '--no-use-defaults')
    m_utils.confirm.assert_any_call(matching(r'.*brewblox` directory already exists.*'))
    assert m_sh.call_count == 3
    m_sh.assert_called_with('sudo reboot')


def test_init_force(m_utils, m_sh):
    m_utils.path_exists.return_value = True
    m_utils.is_empty_dir.return_value = False
    m_utils.confirm.return_value = False
    m_utils.is_brewblox_dir.return_value = True
    m_utils.confirm.return_value = False

    invoke(install.init)
    assert m_sh.call_count == 0

    invoke(install.init, '--force')
    assert m_sh.call_count > 0


def test_init_invalid_dir(m_utils, m_sh):
    m_utils.path_exists.return_value = True
    m_utils.is_empty_dir.return_value = False
    m_utils.is_brewblox_dir.return_value = False

    invoke(install.init, _err=FileExistsError)


def test_run_particle_flasher(m_utils, m_sh):
    install.run_particle_flasher('taggart', True, 'do-stuff')
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
    assert install.discover_usb_sparks() == ['Spark v3', 'Spark v4', 'Spark v2']


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

    assert install.prompt_usb_spark() == 'Spark v3'
    assert m_utils.confirm_usb.call_count == 2


def test_particle_flash(m_utils, m_sh):
    m_sh.return_value = '\n'.join([
        'Bus 004 Device 002: ID 05e3:0616',
        'Bus 004 Device 001: ID 1d6b:0003',
        'Bus 003 Device 006: ID 2b04:c008',  # P1
    ])
    invoke(install.flash, '--release develop --pull')
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
    invoke(install.flash, '--release develop --pull')
    assert m_sh.call_count == 3
    m_sh.assert_called_with(
        'SUDO docker run -it --rm --privileged ' +
        '-v /dev:/dev -w /app/firmware --entrypoint bash --pull always ' +
        'brewblox/brewblox-devcon-spark:develop flash')


def test_invalid_flash(m_utils, m_sh, mocker):
    mocker.patch(TESTED + '.prompt_usb_spark').return_value = 'Spark NaN'
    invoke(install.flash, _err=True)


def test_wifi(m_utils, m_sh, mocker):
    mocker.patch(TESTED + '.LISTEN_MODE_WAIT_S', 0.0001)
    m_find = mocker.patch(TESTED + '.usb.core.find')
    m_glob = mocker.patch(TESTED + '.glob')
    m_glob.return_value = ['GLOB_PATH']
    m_utils.ctx_opts.return_value.dry_run = False

    m_find.reset_mock()
    m_sh.reset_mock()
    m_find.side_effect = [Mock(), None]  # particle
    invoke(install.wifi)
    m_sh.assert_called_once_with('miniterm.py -q GLOB_PATH 2>/dev/null')

    m_find.reset_mock()
    m_sh.reset_mock()
    m_glob.return_value = []  # expect path to fallback to /dev/ttyACM0
    m_find.side_effect = [Mock(), None]  # particle
    invoke(install.wifi)
    m_sh.assert_called_once_with('miniterm.py -q /dev/ttyACM0 2>/dev/null')

    m_find.reset_mock()
    m_sh.reset_mock()
    m_find.side_effect = [None, Mock()]  # ESP
    invoke(install.wifi)
    assert m_sh.call_count == 0
    assert m_find.call_count == 2

    m_find.reset_mock()
    m_sh.reset_mock()
    m_find.side_effect = [None, None, None, Mock()]  # ESP, second try
    invoke(install.wifi)
    assert m_sh.call_count == 0
    assert m_find.call_count == 4

    # No USB calls should be made in dry runs
    m_utils.ctx_opts.return_value.dry_run = True
    m_glob.return_value = ['GLOB_PATH']
    m_find.reset_mock()
    m_sh.reset_mock()
    m_find.side_effect = [Mock(), None]  # particle
    invoke(install.wifi)
    m_sh.assert_called_once_with('miniterm.py -q GLOB_PATH 2>/dev/null')
    assert m_find.return_value.call_count == 0


def test_particle(m_utils, m_sh):
    invoke(install.particle, '--release develop --pull -c testey')
    assert m_sh.call_count == 2
    m_sh.assert_called_with(
        'SUDO docker run -it --rm --privileged -v /dev:/dev --pull always ' +
        'brewblox/firmware-flasher:develop testey')


def test_fix_ipv6(m_utils, m_sh):
    invoke(install.fix_ipv6)
    assert m_utils.fix_ipv6.call_count == 1
