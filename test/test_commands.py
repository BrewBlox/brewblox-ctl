"""
Tests brewblox_ctl.commands
"""

from unittest.mock import call

import pytest
from click.testing import CliRunner

from brewblox_ctl import commands
from brewblox_ctl.const import CFG_VERSION_KEY, RELEASE_KEY, SKIP_CONFIRM_KEY

TESTED = commands.__name__


@pytest.fixture
def mocked_py(mocker):
    return mocker.patch(TESTED + '.PY', '/py')


@pytest.fixture
def mocked_utils(mocker):
    m = mocker.patch(TESTED + '.utils')
    m.optsudo.return_value = 'SUDO '
    return m


@pytest.fixture
def mocked_release_tag(mocker):
    m = mocker.patch(TESTED + '.release_tag')
    m.side_effect = lambda r: r or 'tag'
    return m


def test_release_tag(mocked_utils):
    mocked_utils.is_brewblox_cwd.return_value = False
    mocked_utils.docker_tag.side_effect = lambda r: r

    assert commands.release_tag('release') == 'release'
    with pytest.raises(SystemExit):
        commands.release_tag(None)


def test_down(mocked_utils):
    runner = CliRunner()
    result = runner.invoke(commands.down)
    assert result.exit_code == 0

    assert mocked_utils.run_all.call_args_list == [
        call([
            'SUDO docker-compose down --remove-orphans'
        ])
    ]


def test_up(mocked_utils):
    runner = CliRunner()
    result = runner.invoke(commands.up)
    assert result.exit_code == 0

    assert mocked_utils.run_all.call_args_list == [
        call([
            'SUDO docker-compose up -d --remove-orphans'
        ])
    ]


def test_install_simple(mocked_utils, mocked_py):
    mocked_utils.command_exists.side_effect = [
        True,  # check apt
        True,  # docker
        True,  # docker-compose
    ]
    mocked_utils.confirm.side_effect = [
        False,  # apt update
    ]
    mocked_utils.is_docker_user.side_effect = [
        True,  # optsudo check
        True,
    ]
    mocked_utils.getenv.side_effect = [
        'USEY',
    ]
    mocked_utils.select.side_effect = [
        './brewey//',  # target dir
    ]
    mocked_utils.path_exists.side_effect = [
        False,  # target dir
    ]

    runner = CliRunner()
    assert runner.invoke(commands.install).exit_code == 0

    assert mocked_utils.check_config.call_count == 0
    assert mocked_utils.run_all.call_args_list == [
        call([
            'mkdir -p ./brewey',
            'touch ./brewey/.env',
            '/py -m dotenv.cli --quote never -f ./brewey/.env set {} edge'.format(RELEASE_KEY),
            '/py -m dotenv.cli --quote never -f ./brewey/.env set {} 0.0.0'.format(CFG_VERSION_KEY),
        ])
    ]


def test_install_decline(mocked_utils, mocked_py):
    mocked_utils.command_exists.side_effect = [
        True,  # check apt
        False,  # docker
        False,  # docker-compose
    ]
    mocked_utils.confirm.side_effect = [
        False,  # apt update
        False,  # docker
        False,  # docker user
        False,  # docker-compose
    ]
    mocked_utils.is_docker_user.side_effect = [
        False,  # optsudo check
        False,
    ]
    mocked_utils.getenv.side_effect = [
        'USEY',
    ]
    mocked_utils.select.side_effect = [
        './brewey//',  # target dir
    ]
    mocked_utils.path_exists.side_effect = [
        False,  # target dir
    ]

    runner = CliRunner()
    assert runner.invoke(commands.install).exit_code == 0

    assert mocked_utils.check_config.call_count == 0
    assert mocked_utils.run_all.call_args_list == [
        call([
            'mkdir -p ./brewey',
            'touch ./brewey/.env',
            '/py -m dotenv.cli --quote never -f ./brewey/.env set {} edge'.format(RELEASE_KEY),
            '/py -m dotenv.cli --quote never -f ./brewey/.env set {} 0.0.0'.format(CFG_VERSION_KEY),
        ])
    ]


def test_install_cancel(mocked_utils, mocked_py):
    mocked_utils.command_exists.side_effect = [
        True,  # check apt
        True,  # docker
        True,  # docker-compose
    ]
    mocked_utils.confirm.side_effect = [
        False,  # apt update
        False,  # dir exists, don't continue
    ]
    mocked_utils.is_docker_user.side_effect = [
        True,  # optsudo check
        True,
    ]
    mocked_utils.getenv.side_effect = [
        'USEY',
    ]
    mocked_utils.select.side_effect = [
        './brewey//',  # target dir
    ]
    mocked_utils.path_exists.side_effect = [
        True,  # target dir
    ]

    runner = CliRunner()
    assert runner.invoke(commands.install).exit_code == 0

    assert mocked_utils.check_config.call_count == 0
    assert mocked_utils.run_all.call_count == 0


def test_install_all(mocked_utils, mocked_py):
    mocked_utils.command_exists.side_effect = [
        True,  # check apt
        False,  # docker
        False,  # docker-compose
    ]
    mocked_utils.confirm.side_effect = [
        True,  # apt update
        True,  # docker
        True,  # docker user
        True,  # docker-compose
        True,  # path exists
        True,  # reboot
    ]
    mocked_utils.is_docker_user.side_effect = [
        False,  # optsudo check
        False,
    ]
    mocked_utils.getenv.side_effect = [
        'USEY',
    ]
    mocked_utils.select.side_effect = [
        './brewey//',  # target dir
    ]
    mocked_utils.path_exists.side_effect = [
        True,  # target dir
    ]

    runner = CliRunner()
    assert runner.invoke(commands.install).exit_code == 0

    assert mocked_utils.check_config.call_count == 0
    assert mocked_utils.run_all.call_count == 1
    args = mocked_utils.run_all.call_args_list[0][0][0]

    assert args == [
        'sudo apt update',
        'sudo apt upgrade -y',
        'sudo apt install -y libssl-dev libffi-dev',
        "curl -sL get.docker.com | sh",
        'sudo usermod -aG docker $USER',
        'sudo /py -m pip install -U docker-compose',
        'mkdir -p ./brewey',
        'touch ./brewey/.env',
        '/py -m dotenv.cli --quote never -f ./brewey/.env set {} edge'.format(RELEASE_KEY),
        '/py -m dotenv.cli --quote never -f ./brewey/.env set {} 0.0.0'.format(CFG_VERSION_KEY),
        'sudo reboot',
    ]


def test_kill(mocked_utils):
    mocked_utils.confirm.side_effect = [
        False,
        True,
    ]

    runner = CliRunner()
    assert runner.invoke(commands.kill).exit_code == 0

    assert mocked_utils.run_all.call_count == 0

    assert runner.invoke(commands.kill).exit_code == 0
    assert mocked_utils.check_config.call_count == 0
    assert mocked_utils.run_all.call_count == 1
    args = mocked_utils.run_all.call_args_list[0][0][0]

    assert args == [
        'SUDO docker rm --force $(SUDO docker ps -aq) 2> /dev/null || echo "No containers found"',
    ]


def test_flash(mocked_utils, mocked_release_tag):
    mocked_utils.path_exists.side_effect = [
        True,
        False,
    ]

    runner = CliRunner()
    assert runner.invoke(commands.flash).exit_code == 0
    assert runner.invoke(commands.flash, '--release=taggart').exit_code == 0

    assert mocked_utils.check_config.call_count == 0
    assert mocked_utils.prompt_usb.call_count == 2
    assert mocked_utils.run_all.call_count == 2

    args1 = mocked_utils.run_all.call_args_list[0][0][0]
    args2 = mocked_utils.run_all.call_args_list[1][0][0]

    assert args1 == [
        'SUDO docker-compose down',
        'SUDO docker pull brewblox/firmware-flasher:tag',
        'SUDO docker run -it --rm --privileged brewblox/firmware-flasher:tag trigger-dfu',
        'SUDO docker run -it --rm --privileged brewblox/firmware-flasher:tag flash',
    ]

    assert args2 == [
        'SUDO docker pull brewblox/firmware-flasher:taggart',
        'SUDO docker run -it --rm --privileged brewblox/firmware-flasher:taggart trigger-dfu',
        'SUDO docker run -it --rm --privileged brewblox/firmware-flasher:taggart flash',
    ]


def test_bootloader(mocked_utils):
    mocked_utils.docker_tag.side_effect = [
        'tag',
        'tag',
    ]
    mocked_utils.path_exists.side_effect = [
        True,
        False,
    ]

    runner = CliRunner()
    assert runner.invoke(commands.bootloader).exit_code == 0
    assert runner.invoke(commands.bootloader).exit_code == 0

    assert mocked_utils.check_config.call_count == 0
    assert mocked_utils.prompt_usb.call_count == 2
    assert mocked_utils.run_all.call_count == 2

    args1 = mocked_utils.run_all.call_args_list[0][0][0]
    args2 = mocked_utils.run_all.call_args_list[1][0][0]

    assert args1 == [
        'SUDO docker-compose down',
        'SUDO docker pull brewblox/firmware-flasher:tag',
        'SUDO docker run -it --rm --privileged brewblox/firmware-flasher:tag flash-bootloader',
    ]

    assert args2 == args1[1:]


def test_wifi(mocked_utils):
    mocked_utils.docker_tag.side_effect = [
        'tag',
        'tag',
    ]
    mocked_utils.path_exists.side_effect = [
        True,
        False,
    ]

    runner = CliRunner()
    assert runner.invoke(commands.wifi).exit_code == 0
    assert runner.invoke(commands.wifi).exit_code == 0

    assert mocked_utils.check_config.call_count == 0
    assert mocked_utils.prompt_usb.call_count == 2
    assert mocked_utils.run_all.call_count == 2

    args1 = mocked_utils.run_all.call_args_list[0][0][0]
    args2 = mocked_utils.run_all.call_args_list[1][0][0]

    assert args1 == [
        'SUDO docker-compose down',
        'SUDO docker pull brewblox/firmware-flasher:tag',
        'SUDO docker run -it --rm --privileged brewblox/firmware-flasher:tag wifi',
    ]

    assert args2 == args1[1:]


def test_ctl_settings(mocked_utils, mocked_py):
    mocked_utils.confirm.side_effect = [
        True,
        False,
    ]
    runner = CliRunner()
    assert runner.invoke(commands.settings).exit_code == 0
    assert runner.invoke(commands.settings).exit_code == 0

    args1 = mocked_utils.run_all.call_args_list[0][0][0]
    args2 = mocked_utils.run_all.call_args_list[1][0][0]

    assert args1 == [
        '/py -m dotenv.cli --quote never -f .env set {} True'.format(SKIP_CONFIRM_KEY)
    ]

    assert args2 == [
        '/py -m dotenv.cli --quote never -f .env set {} False'.format(SKIP_CONFIRM_KEY)
    ]
