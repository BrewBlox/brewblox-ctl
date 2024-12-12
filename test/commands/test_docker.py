"""
Tests brewblox_ctl.commands.docker
"""

from unittest.mock import Mock

from brewblox_ctl.commands import docker
from brewblox_ctl.testing import invoke

TESTED = docker.__name__


def test_up(m_sh: Mock):
    invoke(docker.up, '--quiet svc')
    m_sh.assert_called_once_with('SUDO docker compose up -d --quiet svc')

    m_sh.reset_mock()
    invoke(docker.up, '-d --quiet svc')
    m_sh.assert_called_once_with('SUDO docker compose up -d --quiet svc')


def test_down(m_sh: Mock):
    invoke(docker.down, '--quiet')
    m_sh.assert_called_once_with('SUDO docker compose down --quiet')


def test_restart(m_sh: Mock):
    invoke(docker.restart, '--quiet svc')
    m_sh.assert_called_once_with('SUDO docker compose up -d --force-recreate --quiet svc')


def test_follow(m_sh: Mock):
    invoke(docker.follow, 'spark-one spark-two')
    m_sh.assert_called_with('SUDO docker compose logs --follow spark-one spark-two')
    invoke(docker.follow)
    m_sh.assert_called_with('SUDO docker compose logs --follow ')


def test_kill(m_sh: Mock, m_command_exists: Mock):
    m_command_exists.add_existing_commands('docker', 'netstat')
    invoke(docker.kill)
    m_sh.assert_called_once_with('SUDO docker rm --force $(SUDO docker ps -aq)', check=False)

    m_sh.reset_mock()
    m_sh.return_value = ''
    invoke(docker.kill, '--zombies')
    assert m_sh.call_count == 2

    m_sh.reset_mock()
    m_sh.return_value = '\n'.join(
        [
            'Proto Recv-Q Send-Q Local Address  Foreign Address  State   PID/Program name',
            'tcp        0      0 0.0.0.0:80     0.0.0.0:*        LISTEN  5990/docker-proxy',
            'tcp        0      0 127.0.0.53:53  0.0.0.0:*        LISTEN  1632/systemd-resolv',
            'tcp        0      0 0.0.0.0:22     0.0.0.0:*        LISTEN  1787/sshd: /usr/sbi',
            'tcp        0      0 0.0.0.0:1883   0.0.0.0:*        LISTEN  138969/docker-proxy',
        ]
    )

    invoke(docker.kill, '--zombies')
    assert m_sh.call_count == 6

    m_sh.reset_mock()
    m_command_exists.clear_existing_commands()
    m_command_exists.add_existing_commands('docker')
    invoke(docker.kill, '--zombies')
    assert m_sh.call_count == 1
