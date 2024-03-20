from unittest.mock import Mock

import pytest

from brewblox_ctl import utils
from brewblox_ctl.models import CtlConfig, CtlOpts


@pytest.fixture(autouse=True)
def m_get_config(monkeypatch: pytest.MonkeyPatch):
    cfg = CtlConfig()
    monkeypatch.setattr(utils, 'get_config', lambda: cfg)
    yield cfg


@pytest.fixture(autouse=True)
def m_get_opts(monkeypatch: pytest.MonkeyPatch):
    opts = CtlOpts()
    monkeypatch.setattr(utils, 'get_opts', lambda: opts)
    yield opts


@pytest.fixture(autouse=True)
def m_confirm(monkeypatch: pytest.MonkeyPatch):
    m = Mock(spec=utils.confirm)
    monkeypatch.setattr(utils, 'confirm', m)
    yield m


@pytest.fixture(autouse=True)
def m_select(monkeypatch: pytest.MonkeyPatch):
    m = Mock(spec=utils.select)
    monkeypatch.setattr(utils, 'select', m)
    yield m


@pytest.fixture(autouse=True)
def m_confirm_usb(monkeypatch: pytest.MonkeyPatch):
    m = Mock(spec=utils.confirm_usb)
    monkeypatch.setattr(utils, 'confirm_usb', m)
    yield m
