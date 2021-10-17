"""
Tests brewblox_ctl.commands.docker
"""

import pytest
from brewblox_ctl.commands import docker
from brewblox_ctl.testing import check_sudo, invoke

TESTED = docker.__name__


@pytest.fixture
def m_utils(mocker):
    m = mocker.patch(TESTED + '.utils', autospec=True)
    m.optsudo.return_value = 'SUDO '
    return m


@pytest.fixture
def m_sh(mocker):
    m = mocker.patch(TESTED + '.sh', autospec=True)
    m.side_effect = check_sudo
    return m


def test_up(m_utils, m_sh):
    invoke(docker.up, '--quiet svc')
    m_sh.assert_called_once_with('SUDO docker-compose up -d --quiet svc')


def test_down(m_utils, m_sh):
    invoke(docker.down, '--quiet')
    m_sh.assert_called_once_with('SUDO docker-compose down --quiet')


def test_restart(m_utils, m_sh):
    invoke(docker.restart, '--quiet svc')
    m_sh.assert_called_once_with('SUDO docker-compose up -d --force-recreate --quiet svc')


def test_follow(m_utils, m_sh):
    invoke(docker.follow, 'spark-one spark-two')
    m_sh.assert_called_with('SUDO docker-compose logs --follow spark-one spark-two')
    invoke(docker.follow)
    m_sh.assert_called_with('SUDO docker-compose logs --follow ')


def test_kill(m_utils, m_sh):
    invoke(docker.kill)
    m_sh.assert_called_once_with('SUDO docker rm --force $(SUDO docker ps -aq)', check=False)

    m_sh.return_value = ''
    invoke(docker.kill, '--zombies')
    assert m_sh.call_count == 1 + 2

    m_sh.return_value = '\n'.join([
        'Proto Recv-Q Send-Q Local Address  Foreign Address  State   PID/Program name',
        'tcp        0      0 0.0.0.0:80     0.0.0.0:*        LISTEN  5990/docker-proxy',
        'tcp        0      0 127.0.0.53:53  0.0.0.0:*        LISTEN  1632/systemd-resolv',
        'tcp        0      0 0.0.0.0:22     0.0.0.0:*        LISTEN  1787/sshd: /usr/sbi',
        'tcp        0      0 0.0.0.0:1883   0.0.0.0:*        LISTEN  138969/docker-proxy',
    ])

    invoke(docker.kill, '--zombies')
    assert m_sh.call_count == 1 + 2 + 5
