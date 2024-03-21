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
    m = mocker.patch(TESTED + '.actions', autospec=True)
    return m


def test_save(m_sh: Mock, m_file_exists: Mock):
    m_file_exists.return_value = False
    invoke(snapshot.save)
    m_sh.assert_any_call(matching(r'sudo tar -C .* -czf'))


def test_save_defaults(m_sh: Mock, m_file_exists: Mock):
    m_file_exists.return_value = False

    invoke(snapshot.save)
    cwd = Path('.').resolve().name
    m_sh.assert_any_call(matching(r'sudo tar -C .* -czf ../brewblox-snapshot.tar.gz ' + cwd))


def test_save_file_exists(m_sh: Mock, m_file_exists: Mock, m_confirm: Mock, m_is_compose_up: Mock):
    m_file_exists.return_value = True
    m_confirm.return_value = False
    m_is_compose_up.return_value = False

    invoke(snapshot.save)
    assert m_sh.call_count == 0

    m_confirm.return_value = True

    invoke(snapshot.save)
    assert m_sh.call_count == 2


def test_save_overwrite(m_file_exists: Mock):
    m_file_exists.side_effect = [
        True,  # compose file in dir
        True,  # output file
    ]
    invoke(snapshot.save, '--force')


def test_load(m_file_exists: Mock):
    utils.get_opts().dry_run = True
    m_file_exists.return_value = False
    invoke(snapshot.load)


def test_load_defaults(m_sh: Mock, m_file_exists: Mock):
    utils.get_opts().dry_run = True
    m_file_exists.return_value = False
    invoke(snapshot.load)
    cwd = Path('.').resolve().name + '/'
    m_sh.assert_any_call(matching(r'.*' + cwd))


def test_load_empty(m_file_exists: Mock):
    utils.get_opts().dry_run = False
    m_file_exists.return_value = False

    # temp dir exists, but was never populated
    # listdir will return empty
    invoke(snapshot.load, _err=True)
