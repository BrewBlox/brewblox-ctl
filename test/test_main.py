"""
Tests brewblox_ctl.__main__
"""

from tempfile import NamedTemporaryFile

import pytest

from brewblox_ctl import __main__ as main
from brewblox_ctl import utils

TESTED = main.__name__


@pytest.fixture(autouse=True)
def m_ensure_tty(mocker):
    return mocker.patch(TESTED + '.ensure_tty', autospec=True)


@pytest.fixture
def m_utils(mocker):
    return mocker.patch(TESTED + '.utils', autospec=True)


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
    m_utils.is_armv6.return_value = False
    m_utils.getenv.return_value = None
    m_utils.ContextOpts = utils.ContextOpts

    main.main(['--help'])

    with NamedTemporaryFile(mode='w+t') as f:
        f.write('REAL_KEY=value\n')
        f.flush()
        main.main(['dotenv', '-f', f'"{f.name}"', 'get', 'REAL_KEY'])

        with pytest.raises(SystemExit):
            main.main(['dotenv', '-f', f'"{f.name}"', 'get', 'DUMMY_KEY'])


def test_is_root(m_utils):
    m_utils.is_root.return_value = True
    m_utils.is_armv6.return_value = False
    with pytest.raises(SystemExit):
        main.main()


def test_is_armv6(m_utils, mocker):
    mock_cli = mocker.patch(TESTED + '.click_helpers.OrderedCommandCollection')
    m_utils.is_root.return_value = False
    m_utils.is_armv6.return_value = True
    m_utils.getenv.return_value = None

    with pytest.raises(SystemExit):
        main.main()

    m_utils.getenv.return_value = 'y'
    main.main()
    assert mock_cli.return_value.call_count == 1


def test_exception(m_utils, mocker):
    m_utils.is_root.return_value = False
    m_utils.is_armv6.return_value = False
    m_utils.getenv.return_value = None

    with pytest.raises(SystemExit):
        main.main(['pancakes'])


def test_supported(m_utils, mocker):
    m_utils.is_root.return_value = False
    m_utils.is_armv6.return_value = False
    m_utils.getenv.return_value = None

    # Neither should raise an error
    mocker.patch(TESTED + '.SUPPORTED_PYTHON_MINOR', 100)
    main.main(['--help'])

    mocker.patch(TESTED + '.SUPPORTED_PYTHON_MINOR', 1)
    main.main(['--help'])
