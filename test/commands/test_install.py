"""
Tests brewblox_ctl.commands.install
"""


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


def test_prepare_flasher(m_utils, m_sh):
    install.prepare_flasher('taggart', True)
    m_sh.assert_any_call('SUDO docker pull brewblox/firmware-flasher:taggart')
    m_sh.assert_any_call('SUDO docker-compose down')

    # No-op call
    m_sh.reset_mock()
    m_utils.path_exists.return_value = False

    install.prepare_flasher('taggart', False)
    m_sh.assert_not_called()


def test_run_flasher(m_utils, m_sh):
    install.run_flasher('taggart', 'do-stuff')
    m_sh.assert_called_with(
        'SUDO docker run -it --rm --privileged -v /dev:/dev ' +
        'brewblox/firmware-flasher:taggart do-stuff')


def test_flash(m_utils, m_sh):
    invoke(install.flash, '--release develop --pull')
    assert m_sh.call_count == 3
    m_sh.assert_called_with(
        'SUDO docker run -it --rm --privileged -v /dev:/dev ' +
        'brewblox/firmware-flasher:develop flash')


def test_wifi(m_utils, m_sh):
    invoke(install.wifi, '--release develop --pull')
    # Disabled for now
    # assert m_sh.call_count == 3


def test_particle(m_utils, m_sh):
    invoke(install.particle, '--release develop --pull -c testey')
    assert m_sh.call_count == 3
    m_sh.assert_called_with(
        'SUDO docker run -it --rm --privileged -v /dev:/dev ' +
        'brewblox/firmware-flasher:develop testey')


def test_disable_ipv6(m_utils, m_sh):
    m_sh.return_value = '1\n'
    invoke(install.disable_ipv6)
    assert m_sh.call_count == 1

    m_sh.return_value = 'wat\n'
    m_utils.ctx_opts.return_value.dry_run = False
    invoke(install.disable_ipv6)
    assert m_sh.call_count == 2

    m_sh.return_value = '0\n'
    invoke(install.disable_ipv6)
    assert m_sh.call_count == 3 + 4
