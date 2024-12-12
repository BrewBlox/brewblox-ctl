"""
Tests brewblox_ctl.commands.database
"""

from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from brewblox_ctl.commands import database
from brewblox_ctl.testing import invoke

TESTED = database.__name__


@pytest.fixture
def m_migration(mocker: MockerFixture):
    m = mocker.patch(TESTED + '.migration', autospec=True)
    return m


def test_from_influxdb(m_migration: Mock, m_confirm_mode: Mock):
    invoke(database.from_influxdb, '--duration=1d --offset s1 1000 --offset s2 5000 s1 s2')
    m_confirm_mode.assert_called_once()
    m_migration.migrate_influxdb.assert_called_once_with('victoria', '1d', ['s1', 's2'], [('s1', 1000), ('s2', 5000)])
