"""
Tests brewblox_ctl.__main__
"""

from subprocess import CalledProcessError
from unittest.mock import ANY

import pytest
from brewblox_ctl import __main__ as main

TESTED = main.__name__


class DummyCommand(main.commands.Command):
    def __init__(self):
        super().__init__('dummy command', 'dummy')
        self.call_count = 0

    def action(self):
        self.call_count += 1


class ErrorCommand(main.commands.Command):
    def __init__(self):
        super().__init__('error command', 'error')
        self.call_count = 0

    def action(self):
        self.call_count += 1
        raise CalledProcessError(1, 'error command error')


@pytest.fixture
def mocked_run(mocker):
    return mocker.patch(TESTED + '.commands.Command.run')


@pytest.fixture
def mocked_run_all(mocker):
    return mocker.patch(TESTED + '.commands.Command.run_all')


@pytest.fixture
def mocked_run_commands(mocker):
    return mocker.patch(TESTED + '.run_commands')


@pytest.fixture
def mocked_utils(mocker):
    mocked = [
        'confirm',
        'getcwd',
        'is_brewblox_cwd',
        'is_root',
        'path_exists',
        'input',
        'find_dotenv',
        'load_dotenv',
        'local_commands',
    ]
    return {k: mocker.patch(TESTED + '.' + k) for k in mocked}


def test_check_lib(mocked_utils, mocked_run_all):
    mocked_utils['is_brewblox_cwd'].side_effect = [
        True,  # run 1
        True,  # run 2
        True,  # run 3
        False,  # run 4
    ]
    mocked_utils['path_exists'].side_effect = [
        False,  # run 1
        False,  # run 2
        True,  # run 3
    ]
    mocked_utils['confirm'].side_effect = [
        True,  # run 1
        False,  # run 2
    ]

    cmd = main.CheckLibCommand()
    cmd.action()  # ok
    cmd.action()  # user nok
    cmd.action()  # files exist
    cmd.action()  # not a brewblox cwd

    assert mocked_run_all.call_count == 1


def test_exit():
    cmd = main.ExitCommand()
    with pytest.raises(SystemExit):
        cmd.action()


def test_run_commands(mocked_utils, mocked_run_all):
    mocked_utils['input'].side_effect = [
        '',
        KeyboardInterrupt()
    ]
    main.run_commands([], [])
    assert mocked_run_all.call_count == 0
    assert mocked_utils['input'].call_count == 2

    dummy_cmd = DummyCommand()
    err_cmd = ErrorCommand()
    mocked_utils['input'].reset_mock()

    main.run_commands(['dummy'], [dummy_cmd, err_cmd])
    assert dummy_cmd.call_count == 1
    assert err_cmd.call_count == 0
    assert mocked_utils['input'].call_count == 0

    main.run_commands(['dummy', 'error'], [dummy_cmd, err_cmd])
    assert dummy_cmd.call_count == 2
    assert err_cmd.call_count == 1
    assert mocked_utils['input'].call_count == 0


def test_main(mocked_utils, mocked_run_commands):
    cmd = DummyCommand()
    mocked_utils['local_commands'].return_value = [cmd]
    mocked_utils['is_root'].side_effect = [
        False,
        True,
    ]

    main.main(['cmd1', 'cmd2'])
    mocked_run_commands.assert_called_once_with(
        ['cmd1', 'cmd2'],
        [*main.commands.ALL_COMMANDS, cmd, ANY])

    with pytest.raises(SystemExit):
        # is_root is True
        main.main(['cmd1'])
