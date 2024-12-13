"""
Tests brewblox_ctl.commands.snapshot
"""

from pathlib import Path
from unittest.mock import Mock

import pytest.__main__
from pytest_mock import MockerFixture

from brewblox_ctl import utils
from brewblox_ctl.commands import snapshot
from brewblox_ctl.testing import invoke, matching

TESTED = snapshot.__name__


@pytest.fixture(autouse=True)
def m_actions(mocker: MockerFixture):
    return mocker.patch(TESTED + '.actions', autospec=True)


def test_save(m_sh: Mock, m_file_exists: Mock):
    invoke(snapshot.save)
    m_sh.assert_any_call(matching(r'sudo tar -C .* -czf'))


def test_save_defaults(m_sh: Mock, m_file_exists: Mock):
    invoke(snapshot.save)
    cwd = Path().resolve().name
    m_sh.assert_any_call(matching(r'sudo tar -C .* -czf ../brewblox-snapshot.tar.gz ' + cwd))


def test_save_file_exists(m_sh: Mock, m_file_exists: Mock, m_confirm: Mock, m_is_compose_up: Mock):
    m_file_exists.add_existing_files('../brewblox-snapshot.tar.gz')
    m_confirm.return_value = False
    m_is_compose_up.return_value = False

    invoke(snapshot.save)
    assert m_sh.call_count == 0

    m_confirm.return_value = True

    invoke(snapshot.save)
    assert m_sh.call_count == 4


def test_save_overwrite(m_file_exists: Mock):
    m_file_exists.add_existing_files('docker-compose.yml', '../brewblox-snapshot.tar.gz')
    invoke(snapshot.save, '--force')


def test_load(m_file_exists: Mock):
    utils.get_opts().dry_run = True
    invoke(snapshot.load)


def test_load_defaults(m_sh: Mock, m_file_exists: Mock):
    utils.get_opts().dry_run = True
    invoke(snapshot.load)
    cwd = Path().resolve().name + '/'
    m_sh.assert_any_call(matching(r'.*' + cwd))


def test_load_empty(m_file_exists: Mock):
    utils.get_opts().dry_run = False
    # temp dir exists, but was never populated
    # listdir will return empty
    invoke(snapshot.load, _err=True)


def test_load_with_requirements_txt(m_sh: Mock, m_file_exists: Mock, m_actions: Mock):
    utils.get_opts().dry_run = True
    m_file_exists.add_existing_files('requirements.txt')
    invoke(snapshot.load)
    m_sh.assert_any_call('uv run python3 -m pip install -r requirements.txt')
    m_sh.assert_called_with('rm requirements.txt')
    m_actions.install_ctl_package.assert_not_called()


def test_load_with_ctl_tarball(m_sh: Mock, m_file_exists: Mock, m_actions: Mock):
    utils.get_opts().dry_run = True
    m_file_exists.add_existing_files('brewblox-ctl.tar.gz')
    invoke(snapshot.load)
    m_sh.assert_any_call('uv run python3 -m pip install brewblox-ctl.tar.gz')
    m_sh.assert_called_with('rm brewblox-ctl.tar.gz')
    m_actions.install_ctl_package.assert_not_called()


def test_dir_not_empty(m_sh: Mock, m_confirm: Mock):
    utils.get_opts().dry_run = True
    rm_command = f'sudo rm -rf {Path().cwd()}/*'

    # Case 1: m_confirm returns False
    m_confirm.return_value = False
    invoke(snapshot.load)
    assert not any(call[0][0] == rm_command for call in m_sh.call_args_list), f"Unexpected call to '{rm_command}'"

    # Case 2: m_confirm returns True
    m_confirm.return_value = True
    m_sh.reset_mock()
    invoke(snapshot.load)
    assert any(call[0][0] == rm_command for call in m_sh.call_args_list), f"Expected call to '{rm_command}'"


def test_load_no_packages_in_snapshot(m_sh: Mock, m_file_exists: Mock, m_actions: Mock):
    utils.get_opts().dry_run = True
    invoke(snapshot.load)
    m_actions.install_ctl_package.assert_called()
