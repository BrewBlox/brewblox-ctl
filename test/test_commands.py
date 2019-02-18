"""
Tests brewblox_ctl.commands
"""

from subprocess import STDOUT
from unittest.mock import call

import pytest

from brewblox_ctl import commands
from brewblox_ctl.const import CFG_VERSION_KEY, RELEASE_KEY

TESTED = commands.__name__


class DummyCommand(commands.Command):
    def __init__(self):
        super().__init__('dummy command', 'dummy')

    def action(self):
        """noop"""


@pytest.fixture
def mocked_run(mocker):
    return mocker.patch(TESTED + '.Command.run')


@pytest.fixture
def mocked_announce(mocker):
    return mocker.patch(TESTED + '.Command.announce')


@pytest.fixture
def mocked_run_all(mocker):
    return mocker.patch(TESTED + '.Command.run_all')


@pytest.fixture
def mocked_py(mocker):
    return mocker.patch(TESTED + '.PY', '/py')


@pytest.fixture
def mocked_utils(mocker):
    mocked = [
        'check_config',
        'command_exists',
        'confirm',
        'ctl_lib_tag',
        'docker_tag',
        'getenv',
        'is_docker_user',
        'path_exists',
        'select',
        'input',
        'check_call',
    ]
    return {k: mocker.patch(TESTED + '.' + k) for k in mocked}


def test_command_str():
    cmd = DummyCommand()
    assert str(cmd) == 'dummy           dummy command'


def test_command_announce(mocked_utils):
    cmd = DummyCommand()
    cmd.announce(['cmd1', 'cmd2'])
    assert mocked_utils['input'].call_count == 1


def test_command_run(mocked_utils):
    cmd = DummyCommand()
    cmd.run('cmd')
    assert mocked_utils['check_call'].call_args_list == [
        call('cmd', shell=True, stderr=STDOUT)
    ]


def test_command_run_all(mocked_announce, mocked_run):
    cmd = DummyCommand()
    cmd.run_all(['cmd1', 'cmd2'])
    assert mocked_announce.call_args_list == [
        call(['cmd1', 'cmd2'])
    ]
    assert mocked_run.call_args_list == [
        call('cmd1'),
        call('cmd2')
    ]


def test_command_run_all_silent(mocked_announce, mocked_run):
    cmd = DummyCommand()
    cmd.run_all(['cmd1', 'cmd2'], announce=False)
    assert mocked_announce.call_count == 0
    assert mocked_run.call_args_list == [
        call('cmd1'),
        call('cmd2')
    ]


def test_command_lib_commands(mocked_utils):
    mocked_utils['ctl_lib_tag'].side_effect = [
        'lib_tag',
    ]

    cmd = DummyCommand()
    cmd.optsudo = 'SUDO '

    assert cmd.lib_commands() == [
        'SUDO docker rm ctl-lib || echo "you can ignore this error"',
        'SUDO docker pull brewblox/brewblox-ctl-lib:lib_tag || true',
        'SUDO docker create --name ctl-lib brewblox/brewblox-ctl-lib:lib_tag',
        'rm -rf ./brewblox_ctl_lib || echo "you can ignore this error"',
        'SUDO docker cp ctl-lib:/brewblox_ctl_lib ./',
        'SUDO docker rm ctl-lib',
        'sudo chown -R $USER ./brewblox_ctl_lib/',
    ]


def test_compose_down(mocked_run_all, mocked_utils):
    cmd = commands.ComposeDownCommand()
    cmd.optsudo = 'SUDO '
    cmd.action()

    assert mocked_utils['check_config'].call_count == 1
    args = mocked_run_all.call_args_list[0][0][0]

    assert args == [
        'SUDO docker-compose down',
    ]


def test_compose_up(mocked_run_all, mocked_utils):
    cmd = commands.ComposeUpCommand()
    cmd.optsudo = 'SUDO '
    cmd.action()

    assert mocked_utils['check_config'].call_count == 1
    assert mocked_run_all.call_count == 1
    args = mocked_run_all.call_args_list[0][0][0]

    assert args == [
        'SUDO docker-compose up -d',
    ]


def test_install_simple(mocked_run_all, mocked_utils, mocked_py):
    mocked_utils['command_exists'].side_effect = [
        True,  # check apt
        True,  # docker
        True,  # docker-compose
    ]
    mocked_utils['confirm'].side_effect = [
        False,  # apt update
    ]
    mocked_utils['is_docker_user'].side_effect = [
        True,  # optsudo check
        True,
    ]
    mocked_utils['getenv'].side_effect = [
        'USEY',
    ]
    mocked_utils['select'].side_effect = [
        './brewey//',  # target dir
    ]
    mocked_utils['path_exists'].side_effect = [
        False,  # target dir
    ]

    cmd = commands.InstallCommand()
    cmd.optsudo = 'SUDO '
    cmd.action()

    assert mocked_utils['check_config'].call_count == 0
    assert mocked_run_all.call_count == 1
    args = mocked_run_all.call_args_list[0][0][0]

    assert args == [
        'mkdir -p ./brewey',
        'touch ./brewey/.env',
        '/py -m dotenv.cli --quote never -f ./brewey/.env set {} edge'.format(RELEASE_KEY),
        '/py -m dotenv.cli --quote never -f ./brewey/.env set {} 0.0.0'.format(CFG_VERSION_KEY),
    ]


def test_install_decline(mocked_run_all, mocked_utils, mocked_py):
    mocked_utils['command_exists'].side_effect = [
        True,  # check apt
        False,  # docker
        False,  # docker-compose
    ]
    mocked_utils['confirm'].side_effect = [
        False,  # apt update
        False,  # docker
        False,  # docker user
        False,  # docker-compose
    ]
    mocked_utils['is_docker_user'].side_effect = [
        False,  # optsudo check
        False,
    ]
    mocked_utils['getenv'].side_effect = [
        'USEY',
    ]
    mocked_utils['select'].side_effect = [
        './brewey//',  # target dir
    ]
    mocked_utils['path_exists'].side_effect = [
        False,  # target dir
    ]

    cmd = commands.InstallCommand()
    cmd.optsudo = 'SUDO '
    cmd.action()

    assert mocked_utils['check_config'].call_count == 0
    assert mocked_run_all.call_count == 1
    args = mocked_run_all.call_args_list[0][0][0]

    assert args == [
        'mkdir -p ./brewey',
        'touch ./brewey/.env',
        '/py -m dotenv.cli --quote never -f ./brewey/.env set {} edge'.format(RELEASE_KEY),
        '/py -m dotenv.cli --quote never -f ./brewey/.env set {} 0.0.0'.format(CFG_VERSION_KEY),
    ]


def test_install_cancel(mocked_run_all, mocked_utils, mocked_py):
    mocked_utils['command_exists'].side_effect = [
        True,  # check apt
        True,  # docker
        True,  # docker-compose
    ]
    mocked_utils['confirm'].side_effect = [
        False,  # apt update
        False,  # dir exists, don't continue
    ]
    mocked_utils['is_docker_user'].side_effect = [
        True,  # optsudo check
        True,
    ]
    mocked_utils['getenv'].side_effect = [
        'USEY',
    ]
    mocked_utils['select'].side_effect = [
        './brewey//',  # target dir
    ]
    mocked_utils['path_exists'].side_effect = [
        True,  # target dir
    ]

    cmd = commands.InstallCommand()
    cmd.optsudo = 'SUDO '
    cmd.action()

    assert mocked_utils['check_config'].call_count == 0
    assert mocked_run_all.call_count == 0


def test_install_all(mocked_run_all, mocked_utils, mocked_py):
    mocked_utils['command_exists'].side_effect = [
        True,  # check apt
        False,  # docker
        False,  # docker-compose
    ]
    mocked_utils['confirm'].side_effect = [
        True,  # apt update
        True,  # docker
        True,  # docker user
        True,  # docker-compose
        True,  # path exists
        True,  # reboot
    ]
    mocked_utils['is_docker_user'].side_effect = [
        False,  # optsudo check
        False,
    ]
    mocked_utils['getenv'].side_effect = [
        'USEY',
    ]
    mocked_utils['select'].side_effect = [
        './brewey//',  # target dir
    ]
    mocked_utils['path_exists'].side_effect = [
        True,  # target dir
    ]

    cmd = commands.InstallCommand()
    cmd.optsudo = 'SUDO '
    cmd.action()

    assert mocked_utils['check_config'].call_count == 0
    assert mocked_run_all.call_count == 1
    args = mocked_run_all.call_args_list[0][0][0]

    assert args == [
        'sudo apt update',
        'sudo apt upgrade -y',
        'curl -sSL https://get.docker.com | sh',
        'sudo usermod -aG docker $USER',
        'sudo /py -m pip install -U docker-compose',
        'mkdir -p ./brewey',
        'touch ./brewey/.env',
        '/py -m dotenv.cli --quote never -f ./brewey/.env set {} edge'.format(RELEASE_KEY),
        '/py -m dotenv.cli --quote never -f ./brewey/.env set {} 0.0.0'.format(CFG_VERSION_KEY),
        'sudo reboot',
    ]


def test_kill(mocked_utils, mocked_run_all):
    mocked_utils['confirm'].side_effect = [
        False,
        True,
    ]

    cmd = commands.KillCommand()
    cmd.optsudo = 'SUDO '
    cmd.action()

    assert mocked_run_all.call_count == 0

    cmd.action()
    assert mocked_utils['check_config'].call_count == 0
    assert mocked_run_all.call_count == 1
    args = mocked_run_all.call_args_list[0][0][0]

    assert args == [
        'SUDO docker rm --force $(SUDO docker ps -aq) 2> /dev/null || echo "No containers found"',
    ]


def test_flash(mocked_run_all, mocked_utils):
    mocked_utils['docker_tag'].side_effect = [
        'tag',
        'tag',
    ]
    mocked_utils['path_exists'].side_effect = [
        True,
        False,
    ]

    cmd = commands.FirmwareFlashCommand()
    cmd.optsudo = 'SUDO '
    cmd.action()
    cmd.action()

    assert mocked_utils['check_config'].call_count == 0
    assert mocked_utils['input'].call_count == 2
    assert mocked_run_all.call_count == 2

    args1 = mocked_run_all.call_args_list[0][0][0]
    args2 = mocked_run_all.call_args_list[1][0][0]

    assert args1 == [
        'SUDO docker-compose down',
        'SUDO docker pull brewblox/firmware-flasher:tag',
        'SUDO docker run -it --rm --privileged brewblox/firmware-flasher:tag trigger-dfu',
        'SUDO docker run -it --rm --privileged brewblox/firmware-flasher:tag flash',
    ]

    assert args2 == args1[1:]


def test_bootloader(mocked_run_all, mocked_utils):
    mocked_utils['docker_tag'].side_effect = [
        'tag',
        'tag',
    ]
    mocked_utils['path_exists'].side_effect = [
        True,
        False,
    ]

    cmd = commands.BootloaderCommand()
    cmd.optsudo = 'SUDO '
    cmd.action()
    cmd.action()

    assert mocked_utils['check_config'].call_count == 0
    assert mocked_utils['input'].call_count == 2
    assert mocked_run_all.call_count == 2

    args1 = mocked_run_all.call_args_list[0][0][0]
    args2 = mocked_run_all.call_args_list[1][0][0]

    assert args1 == [
        'SUDO docker-compose down',
        'SUDO docker pull brewblox/firmware-flasher:tag',
        'SUDO docker run -it --rm --privileged brewblox/firmware-flasher:tag flash-bootloader',
    ]

    assert args2 == args1[1:]


def test_wifi(mocked_run_all, mocked_utils):
    mocked_utils['docker_tag'].side_effect = [
        'tag',
        'tag',
    ]
    mocked_utils['path_exists'].side_effect = [
        True,
        False,
    ]

    cmd = commands.WiFiCommand()
    cmd.optsudo = 'SUDO '
    cmd.action()
    cmd.action()

    assert mocked_utils['check_config'].call_count == 0
    assert mocked_utils['input'].call_count == 2
    assert mocked_run_all.call_count == 2

    args1 = mocked_run_all.call_args_list[0][0][0]
    args2 = mocked_run_all.call_args_list[1][0][0]

    assert args1 == [
        'SUDO docker-compose down',
        'SUDO docker pull brewblox/firmware-flasher:tag',
        'SUDO docker run -it --rm --privileged brewblox/firmware-flasher:tag wifi',
    ]

    assert args2 == args1[1:]
