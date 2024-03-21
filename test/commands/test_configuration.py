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
    m = mocker.patch(TESTED + '.actions', autospec=True)
    return m


def test_inspect():
    invoke(configuration.inspect)


def test_apply(m_file_exists: Mock):
    invoke(configuration.apply)

    m_file_exists.return_value = False
    invoke(configuration.apply)
