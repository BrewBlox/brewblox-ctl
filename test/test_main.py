"""
Tests brewblox_ctl.__main__
"""

import pytest
from click.exceptions import UsageError

from brewblox_ctl import __main__ as main
from brewblox_ctl import utils

TESTED = main.__name__


@pytest.fixture(autouse=True)
def mocked_local_commands(mocker):
    m = mocker.patch(TESTED + '.local_commands')
    m.return_value = []
    return m


@pytest.fixture
def mocked_utils(mocker):
    return mocker.patch(TESTED + '.utils')


def test_check_lib(mocked_utils):
    mocked_utils.is_brewblox_cwd.side_effect = [
        True,  # run 1
        True,  # run 2
        True,  # run 3
        False,  # run 4
    ]
    mocked_utils.path_exists.side_effect = [
        False,  # run 1
        False,  # run 2
        True,  # run 3
    ]
    mocked_utils.confirm.side_effect = [
        True,  # run 1
        False,  # run 2
    ]

    main.check_lib()  # ok
    main.check_lib()  # user nok
    main.check_lib()  # files exist
    main.check_lib()  # not a brewblox cwd

    assert mocked_utils.load_ctl_lib.call_count == 1


def test_main(mocked_utils, mocker):
    mocked_utils.is_root.return_value = False
    mocked_utils.is_v6.return_value = False
    mocked_utils.getenv.return_value = None
    mocked_utils.ContextOpts = utils.ContextOpts

    main.main(['--help'])
    main.main(['env', 'get', 'USER'])


def test_is_root(mocked_utils):
    mocked_utils.is_root.return_value = True
    mocked_utils.is_v6.return_value = False
    with pytest.raises(SystemExit):
        main.main()


def test_is_v6(mocked_utils, mocker):
    mock_cli = mocker.patch(TESTED + '.click_helpers.OrderedCommandCollection')
    mocked_utils.is_root.return_value = False
    mocked_utils.is_v6.return_value = True

    mocked_utils.confirm.side_effect = [
        False,
        True,
    ]

    with pytest.raises(SystemExit):
        main.main()

    main.main()
    assert mock_cli.return_value.call_count == 1


def test_exception(mocked_utils, mocker):
    mocked_utils.is_root.return_value = False
    mocked_utils.is_v6.return_value = False
    mocked_utils.getenv.return_value = None

    with pytest.raises(SystemExit):
        main.main(['pancakes'])


def test_usage_hint(mocker, mocked_utils):
    mocked_utils.is_brewblox_cwd.return_value = True

    main.usage_hint(UsageError(''))
    assert mocked_utils.is_brewblox_cwd.call_count == 0

    main.usage_hint(UsageError('No such command'))
    assert mocked_utils.is_brewblox_cwd.call_count == 1

    mocked_utils.is_brewblox_cwd.return_value = False
    mocked_utils.path_exists.return_value = False

    main.usage_hint(UsageError('No such command'))

    mocked_utils.path_exists.return_value = True

    main.usage_hint(UsageError('No such command'))

    mock_cli = mocker.patch(TESTED + '.click_helpers.OrderedCommandCollection')
    mock_cli.return_value.side_effect = main.UsageError('No such command')
    mocked_utils.is_root.return_value = False
    mocked_utils.is_v6.return_value = False

    # call to getenv(BREWBLOX_DEBUG)
    mocked_utils.getenv.side_effect = [
        'true',
        None,
    ]

    with pytest.raises(UsageError):
        main.main(['nope'])

    with pytest.raises(SystemExit):
        main.main(['nope'])
