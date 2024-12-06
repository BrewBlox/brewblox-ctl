"""
Tests brewblox_ctl.commands.configuration
"""

from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from brewblox_ctl.commands import configuration
from brewblox_ctl.testing import invoke

TESTED = configuration.__name__


@pytest.fixture(autouse=True)
def m_actions(mocker: MockerFixture):
    return mocker.patch(TESTED + '.actions', autospec=True)


def test_inspect():
    invoke(configuration.inspect)


def test_apply(m_file_exists: Mock):
    m_file_exists.add_existing_files('brewblox.yml')
    invoke(configuration.apply)

    m_file_exists.clear_existing_files()
    invoke(configuration.apply)
