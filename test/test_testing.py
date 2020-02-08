"""
Tests brewblox_ctl.testing
"""

from unittest.mock import Mock

import pytest

from brewblox_ctl import testing

TESTED = testing.__name__


def test_invoke(mocker):
    m_result = mocker.patch(TESTED + '.CliRunner').return_value.invoke.return_value
    m_result.exception = None
    assert testing.invoke('arg1', 'arg2', other='kwarg1') == m_result

    with pytest.raises(AssertionError):
        testing.invoke(_err=RuntimeError)

    m_result.exception = RuntimeError()
    assert testing.invoke(_err=RuntimeError) == m_result
    with pytest.raises(RuntimeError):
        testing.invoke()


def test_matching():
    obj = testing.matching(r'.art')
    assert obj == 'cart'
    assert obj == 'part'

    mock = Mock()
    mock('fart')
    mock.assert_called_with(obj)


def test_check_sudo():
    testing.check_sudo('something else')
    testing.check_sudo(v for v in 'xyz')
    testing.check_sudo('sudo docker run')
    testing.check_sudo('SUDO docker-compose up -d')


@pytest.mark.parametrize('cmd', [
    'docker run',
    '   docker run',
    '\n\ndocker-compose kill',
    'fluffy bunnies; docker-compose down',
    'pretty kitties&&docker',
    'pretty kitties&&     docker',
    'cuddly puppies||docker-compose',
    'cuddly puppies||\tdocker-compose',
    'cuddly puppies||\ndocker-compose',
])
def test_check_sudo_caught(cmd):
    with pytest.raises(AssertionError):
        testing.check_sudo(cmd)
