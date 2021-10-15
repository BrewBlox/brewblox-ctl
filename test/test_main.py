"""
Tests brewblox_ctl.__main__
"""

import pytest
from brewblox_ctl import __main__ as main
from brewblox_ctl import utils

TESTED = main.__name__


@pytest.fixture
def m_utils(mocker):
    return mocker.patch(TESTED + '.utils')


def test_escalate_debug(m_utils):
    m_utils.getenv.return_value = True
    with pytest.raises(RuntimeError):
        main.escalate(RuntimeError('Boo!'))


def test_escalate_production(m_utils):
    m_utils.getenv.return_value = False
    with pytest.raises(SystemExit):
        main.escalate(RuntimeError('Boo!'))


def test_main(m_utils, mocker):
    m_utils.is_root.return_value = False
    m_utils.is_v6.return_value = False
    m_utils.getenv.return_value = None
    m_utils.ContextOpts = utils.ContextOpts

    main.main(['--help'])
    main.main(['env', 'get', 'USER'])


def test_is_root(m_utils):
    m_utils.is_root.return_value = True
    m_utils.is_v6.return_value = False
    with pytest.raises(SystemExit):
        main.main()


def test_is_v6(m_utils, mocker):
    mock_cli = mocker.patch(TESTED + '.click_helpers.OrderedCommandCollection')
    m_utils.is_root.return_value = False
    m_utils.is_v6.return_value = True

    m_utils.confirm.side_effect = [
        False,
        True,
    ]

    with pytest.raises(SystemExit):
        main.main()

    main.main()
    assert mock_cli.return_value.call_count == 1


def test_exception(m_utils, mocker):
    m_utils.is_root.return_value = False
    m_utils.is_v6.return_value = False
    m_utils.getenv.return_value = None

    with pytest.raises(SystemExit):
        main.main(['pancakes'])


def test_supported(m_utils, mocker):
    m_utils.is_root.return_value = False
    m_utils.is_v6.return_value = False
    m_utils.getenv.return_value = None

    # Neither should raise an error
    mocker.patch(TESTED + '.SUPPORTED_PYTHON_MINOR', 100)
    main.main(['--help'])

    mocker.patch(TESTED + '.SUPPORTED_PYTHON_MINOR', 1)
    main.main(['--help'])
