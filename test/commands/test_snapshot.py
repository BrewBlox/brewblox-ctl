"""
Tests brewblox_ctl.commands.snapshot
"""


import pytest.__main__
from brewblox_ctl.commands import snapshot
from brewblox_ctl.testing import check_sudo, invoke, matching

TESTED = snapshot.__name__


@pytest.fixture(autouse=True)
def m_input(mocker):
    m = mocker.patch(TESTED + '.input')
    return m


@pytest.fixture
def m_utils(mocker):
    m = mocker.patch(TESTED + '.utils')
    m.optsudo.return_value = 'SUDO '
    m.is_brewblox_cwd.return_value = False
    m.docker_tag.side_effect = lambda v: v
    return m


@pytest.fixture
def m_sh(mocker):
    m = mocker.patch(TESTED + '.sh')
    m.side_effect = check_sudo
    return m


def test_brewblox_cwd_error(m_utils, m_sh):
    m_utils.is_brewblox_cwd.return_value = True

    invoke(snapshot.save, _err=True)
    invoke(snapshot.load, _err=True)


def test_brewblox_save_invalid_dir(m_utils, m_sh):
    m_utils.path_exists.return_value = False

    invoke(snapshot.save, _err=True)


def test_save(m_utils, m_sh):
    m_utils.path_exists.side_effect = [
        True,  # compose file in dir
        False,  # output file
    ]
    invoke(snapshot.save)
    m_sh.assert_any_call(matching(r'sudo tar -czf'))


def test_save_file_exists(m_utils, m_sh):
    m_utils.path_exists.side_effect = [
        True,  # compose file in dir
        True,  # output file
    ]
    invoke(snapshot.save, _err=True)


def test_save_overwrite(m_utils, m_sh):
    m_utils.path_exists.side_effect = [
        True,  # compose file in dir
        True,  # output file
    ]
    invoke(snapshot.save, '--force')


def test_load(m_utils, m_sh):
    m_utils.path_exists.return_value = False
    invoke(snapshot.load)


def test_load_empty(m_utils, m_sh):
    m_utils.path_exists.return_value = False
    m_utils.ctx_opts.return_value.dry_run = False

    # temp dir exists, but was never populated
    # listdir will return empty
    invoke(snapshot.load, _err=True)


def test_load_output_exists(m_utils, m_sh):
    m_utils.path_exists.return_value = True
    invoke(snapshot.load, _err=True)
    invoke(snapshot.load, '--force')
