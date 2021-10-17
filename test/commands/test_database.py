"""
Tests brewblox_ctl.commands.database
"""

import pytest
from brewblox_ctl.commands import database
from brewblox_ctl.testing import invoke

TESTED = database.__name__


@pytest.fixture
def m_utils(mocker):
    m = mocker.patch(TESTED + '.utils', autospec=True)
    return m


@pytest.fixture
def m_migration(mocker):
    m = mocker.patch(TESTED + '.migration', autospec=True)
    return m


def test_from_couchdb(m_utils, m_migration):
    invoke(database.from_couchdb)
    m_utils.check_config.assert_called_once()
    m_utils.confirm_mode.assert_called_once()
    m_migration.migrate_couchdb.assert_called_once()


def test_from_influxdb(m_utils, m_migration):
    invoke(database.from_influxdb, '--duration=1d --offset s1 1000 --offset s2 5000 s1 s2')
    m_utils.check_config.assert_called_once()
    m_utils.confirm_mode.assert_called_once()
    m_migration.migrate_influxdb.assert_called_once_with(
        'victoria', '1d', ['s1', 's2'], [('s1', 1000), ('s2', 5000)]
    )
