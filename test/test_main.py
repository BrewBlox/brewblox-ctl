"""
Tests brewblox_ctl.__main__
"""

import pytest
from brewblox_ctl import __main__ as main
from brewblox_ctl import utils

TESTED = main.__name__


@pytest.fixture
def mocked_utils(mocker):
    return mocker.patch(TESTED + '.utils')


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


def test_supported(mocked_utils, mocker):
    mocked_utils.is_root.return_value = False
    mocked_utils.is_v6.return_value = False
    mocked_utils.getenv.return_value = None

    # Neither should raise an error
    mocker.patch(TESTED + '.SUPPORTED_PYTHON_MINOR', 100)
    main.main(['--help'])

    mocker.patch(TESTED + '.SUPPORTED_PYTHON_MINOR', 1)
    main.main(['--help'])
