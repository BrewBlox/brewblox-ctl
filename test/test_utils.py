"""
Tests brewblox_ctl.utils
"""

import os

import pytest

from brewblox_ctl import utils

# The real function: conftest replaces it in every test
loadenv = utils.loadenv


def test_loadenv(monkeypatch: pytest.MonkeyPatch):
    # Values loaded from the previous .env at startup.
    # monkeypatch restores both after the test.
    monkeypatch.setenv('BREWBLOX_RELEASE', 'edge')
    monkeypatch.setenv('COMPOSE_FILE', 'docker-compose.yml')

    loadenv('BREWBLOX_RELEASE=develop\nCOMPOSE_FILE=docker-compose.shared.yml:docker-compose.yml\nNO_VALUE\n')
    assert os.environ['BREWBLOX_RELEASE'] == 'develop'
    assert os.environ['COMPOSE_FILE'] == 'docker-compose.shared.yml:docker-compose.yml'
    assert 'NO_VALUE' not in os.environ
