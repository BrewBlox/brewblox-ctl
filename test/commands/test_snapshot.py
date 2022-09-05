"""
Tests brewblox_ctl.commands.snapshot
"""


import re
from pathlib import Path

import pytest
from brewblox_ctl.commands import snapshot
from brewblox_ctl.testing import check_sudo, invoke, matching

TESTED = snapshot.__name__


@pytest.fixture(autouse=True)
def m_input(mocker):
    m = mocker.patch(TESTED + '.input')
    return m


@pytest.fixture
def m_actions(mocker):
    m = mocker.patch(TESTED + '.actions', autospec=True)
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


def test_save(m_utils, m_sh):
    m_utils.path_exists.return_value = False
    invoke(snapshot.save)
    m_sh.assert_any_call(matching(r'sudo tar .* -czf'))


def test_save_invalid_name(m_utils, m_sh):
    invoke(snapshot.save, '--name /file/', _err=True)


def test_save_defaults(m_utils, m_sh):
    m_utils.path_exists.return_value = False

    invoke(snapshot.save)
    cwd = Path('.').resolve()
    m_sh.assert_called_with(matching(
        r'sudo tar -C' +
        ' ' + re.escape(str(cwd.parent)) +
        r' --exclude .+/\.venv --exclude .+/influxdb\* --exclude .+/couchdb\*' +
        r' -czf /.*/brewblox-snapshot-\d{8}-\d{4}\.tar\.gz' +
        ' ' + re.escape(cwd.name)))


def test_save_no_timestamp(m_utils, m_sh):
    m_utils.path_exists.return_value = False

    invoke(snapshot.save, '--no-timestamp')
    cwd = Path('.').resolve()
    m_sh.assert_called_with(matching(
        r'sudo tar -C' +
        ' ' + re.escape(str(cwd.parent)) +
        r' --exclude .+/\.venv --exclude .+/influxdb\* --exclude .+/couchdb\*' +
        r' -czf /.*/brewblox-snapshot.tar\.gz' +
        ' ' + re.escape(cwd.name)))


def test_save_file_exists(m_utils, m_sh):
    m_utils.path_exists.return_value = True
    m_utils.confirm.return_value = False

    invoke(snapshot.save)
    assert m_sh.call_count == 0

    m_utils.confirm.return_value = True

    invoke(snapshot.save)
    assert m_sh.call_count == 2


def test_save_no_history(m_utils, m_sh):
    m_utils.path_exists.return_value = False
    invoke(snapshot.save, '--no-history')
    m_sh.assert_any_call(matching(r'sudo tar .* --exclude .+/victoria/\*'))


def test_save_overwrite(m_utils, m_sh):
    m_utils.path_exists.side_effect = [
        True,  # compose file in dir
        True,  # output file
    ]
    invoke(snapshot.save, '--force')


def test_load(m_actions, m_utils, m_sh):
    m_utils.path_exists.return_value = False
    invoke(snapshot.load, '.env')


def test_load_defaults(m_actions, m_utils, m_sh):
    m_utils.path_exists.return_value = False
    invoke(snapshot.load, '.env')
    cwd = Path('.').resolve().name + '/'
    m_sh.assert_called_with(matching(r'.*' + cwd))


def test_load_empty(m_actions, m_utils, m_sh):
    m_utils.path_exists.return_value = False
    m_utils.ctx_opts.return_value.dry_run = False

    # temp dir exists, but was never populated
    # listdir will return empty
    invoke(snapshot.load, '.env', _err=True)
