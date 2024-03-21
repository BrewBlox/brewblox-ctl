"""
Tests brewblox_ctl.__main__
"""

from tempfile import NamedTemporaryFile
from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from brewblox_ctl import __main__ as main
from brewblox_ctl import utils

TESTED = main.__name__


@pytest.fixture(autouse=True)
def m_ensure_tty(mocker: MockerFixture):
    return mocker.patch(TESTED + '.ensure_tty', autospec=True)


def test_escalate_debug():
    utils.get_config().debug = True
    with pytest.raises(RuntimeError):
        main.escalate(RuntimeError('Boo!'))


def test_escalate_production():
    utils.get_config().debug = False
    with pytest.raises(SystemExit):
        main.escalate(RuntimeError('Boo!'))


def test_main(m_is_root: Mock, m_getenv: Mock):
    m_is_root.return_value = False
    m_getenv.return_value = None

    main.main(['--help'])

    with NamedTemporaryFile(mode='w+t') as f:
        f.write('REAL_KEY=value\n')
        f.flush()
        main.main(['dotenv', '-f', f'"{f.name}"', 'get', 'REAL_KEY'])

        # with pytest.raises(SystemExit):
        #     main.main(['dotenv', '-f', f'"{f.name}"', 'get', 'DUMMY_KEY'])


def test_is_root(m_is_root: Mock):
    m_is_root.return_value = True
    with pytest.raises(SystemExit):
        main.main()


def test_exception(m_is_root: Mock):
    m_is_root.return_value = False
    utils.get_config().debug = False

    with pytest.raises(SystemExit):
        main.main(['pancakes'])
