"""
Tests brewblox_ctl.commands
"""

import re

import pytest
from brewblox_ctl import commands
from brewblox_ctl.const import CFG_VERSION_KEY, RELEASE_KEY

TESTED = commands.__name__


@pytest.fixture
def mocked_run(mocker):
    return mocker.patch(TESTED + '.Command.run')


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
        'input'
    ]
    return {k: mocker.patch(TESTED + '.' + k) for k in mocked}


def check_optsudo(args):
    """Checks whether each call to docker/docker-compose is appropriately prefixed"""
    joined = ' '.join(args)
    assert len(re.findall('SUDO docker ', joined)) == len(re.findall('docker ', joined))
    assert len(re.findall('SUDO docker-compose ', joined)) == len(re.findall('docker-compose ', joined))


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
