"""
Tests brewblox_ctl.commands.service
"""

from unittest.mock import Mock

import pytest

from brewblox_ctl.commands import service
from brewblox_ctl.testing import check_sudo, invoke

TESTED = service.__name__


@pytest.fixture
def m_utils(mocker):
    m = mocker.patch(TESTED + '.utils', autospec=True)
    m.optsudo.return_value = 'SUDO '
    m.read_compose.side_effect = lambda: {
        'services': {
            'spark-one': {},
        }
    }
    return m


@pytest.fixture
def m_sh(mocker):
    m = mocker.patch(TESTED + '.sh', autospec=True)
    m.side_effect = check_sudo
    return m


def test_restart_services(m_utils):
    m_utils.confirm.side_effect = [
        False,
        True
    ]
    ctx = Mock()
    service.restart_services(ctx)
    assert ctx.invoke.call_count == 0

    service.restart_services(ctx)
    assert ctx.invoke.call_count == 1


def test_show(m_utils, m_sh):
    m_utils.list_services.return_value = ['s1', 's2']
    invoke(service.show, '--image brewblox --file docker-compose.shared.yml')
    m_utils.list_services.assert_called_once_with('brewblox', 'docker-compose.shared.yml')


def test_remove(m_utils, m_sh, mocker):
    mocker.patch(TESTED + '.restart_services')
    invoke(service.remove, 'spark-one')
    invoke(service.remove, 'spark-none')
    invoke(service.remove)


def test_ports(m_utils, m_sh):
    invoke(service.ports)
    assert m_utils.setenv.call_count == 4


def test_expose_from_empty(m_utils, m_sh):
    m_utils.confirm.return_value = False
    m_utils.read_compose.side_effect = lambda: {
        'services': {
            'testey': {}
        }
    }

    invoke(service.expose, '-d eventbus 5672:5672')
    m_utils.write_compose.assert_not_called()
    invoke(service.expose, _err=True)  # missing argument
    invoke(service.expose, 'eventbus 1234.5', _err=True)  # Invalid value
    invoke(service.expose, 'eventbus 123:', _err=True)  # Invalid value
    invoke(service.expose, 'eventbus global', _err=True)  # Invalid value

    invoke(service.expose, 'eventbus 5672:5672')
    m_utils.write_compose.assert_called_with({
        'services': {
            'eventbus': {
                'ports': [
                    '5672:5672'
                ]
            }
        }
    })

    invoke(service.expose, 'influx 8086:8086')
    m_utils.write_compose.assert_called_with({
        'services': {
            'influx': {
                'ports': [
                    '8086:8086'
                ]
            }
        }
    })


def test_expose_from_set(m_utils, m_sh):
    m_utils.confirm.return_value = False
    m_utils.read_compose.side_effect = lambda: {
        'services': {
            'eventbus': {
                'ports': ['5672:5672']
            }
        }
    }

    invoke(service.expose, 'eventbus 5672:5672')
    m_utils.write_compose.assert_not_called()

    invoke(service.expose, '-d eventbus 5672:5672')
    m_utils.write_compose.assert_called_with({
        'services': {}
    })

    invoke(service.expose, 'influx 8086:8086')
    m_utils.write_compose.assert_called_with({
        'services': {
            'influx': {
                'ports': [
                    '8086:8086'
                ]
            },
            'eventbus': {
                'ports': [
                    '5672:5672'
                ]
            }
        }
    })


def test_expose_from_full(m_utils, m_sh):
    m_utils.confirm.return_value = False
    m_utils.read_compose.side_effect = lambda: {
        'services': {
            'eventbus': {
                'other': True,
                'ports': ['5672:5672']
            }
        }
    }

    invoke(service.expose, '-d eventbus 5672:5672')
    m_utils.write_compose.assert_called_with({
        'services': {
            'eventbus': {
                'other': True,
            }
        }
    })


def test_pull(m_utils, m_sh, mocker):
    m_restart = mocker.patch(TESTED + '.restart_services')

    invoke(service.pull)
    m_sh.assert_called_with('SUDO docker compose pull ')

    invoke(service.pull, 'ui eventbus')
    m_sh.assert_called_with('SUDO docker compose pull ui eventbus')

    assert m_restart.call_count == 2
