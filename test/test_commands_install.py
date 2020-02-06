"""
Tests brewblox_ctl.commands.install
"""


import pytest
from click.testing import CliRunner

from brewblox_ctl.commands import install

TESTED = install.__name__


def invoke(*args, _ok=True, **kwargs):
    result = CliRunner().invoke(*args, **kwargs)
    if bool(result.exception) is _ok:
        print(result.stdout)
        raise AssertionError('{}, expected exc: {}'.format(result, _ok))


@pytest.fixture(autouse=True)
def m_sleep(mocker):
    m = mocker.patch(TESTED + '.sleep')
    return m


@pytest.fixture
def m_utils(mocker):
    m = mocker.patch(TESTED + '.utils')
    m.optsudo.return_value = 'SUDO '
    return m


@pytest.fixture
def m_sh(mocker):
    m = mocker.patch(TESTED + '.sh')
    return m


def test_install_short(m_utils, m_sh):
    m_utils.path_exists.return_value = False
    invoke(install.install, '--use-defaults')
    assert m_sh.call_count == 4
