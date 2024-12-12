"""
Tests brewblox_ctl.commands.service
"""

from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from brewblox_ctl.commands import service
from brewblox_ctl.testing import invoke

TESTED = service.__name__


@pytest.fixture(autouse=True)
def m_utils(m_read_compose: Mock):
    m_read_compose.side_effect = lambda: {
        'services': {
            'spark-one': {},
        }
    }


def test_restart_services(m_confirm: Mock):
    m_confirm.side_effect = [False, True]
    ctx = Mock()
    service.restart_services(ctx)
    assert ctx.invoke.call_count == 0

    service.restart_services(ctx)
    assert ctx.invoke.call_count == 1


def test_show(m_list_services: Mock):
    m_list_services.return_value = ['s1', 's2']
    invoke(service.show, '--image brewblox ')
    m_list_services.assert_called_once_with('brewblox')


def test_remove(mocker: MockerFixture):
    mocker.patch(TESTED + '.restart_services')
    invoke(service.remove, 'spark-one')
    invoke(service.remove, 'spark-none')
    invoke(service.remove)


def test_pull(mocker: MockerFixture, m_sh: Mock):
    m_restart = mocker.patch(TESTED + '.restart_services')

    invoke(service.pull)
    m_sh.assert_called_with('SUDO docker compose pull ')

    invoke(service.pull, 'ui eventbus')
    m_sh.assert_called_with('SUDO docker compose pull ui eventbus')

    assert m_restart.call_count == 2
