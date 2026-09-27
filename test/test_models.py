"""
Tests brewblox_ctl.models
"""

from datetime import timedelta

import pytest
from pydantic import ValidationError

from brewblox_ctl import models
from brewblox_ctl.models import CtlConfig, VictoriaConfig


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        # The table of brewblox-history's test_parse_retention, as strings: brewblox.yml gives strings
        ('30d', timedelta(days=30)),
        ('30D', timedelta(days=30)),
        ('4w', timedelta(weeks=4)),
        ('100y', timedelta(days=36500)),
        ('1d12h', timedelta(hours=36)),
        ('2d-5h', timedelta(hours=43)),  # parts after a negative one are negative too
        ('10ms', timedelta(milliseconds=10)),
        # Months of 31 days, as a bare number or with `M`
        ('1', timedelta(days=31)),
        ('1.5M', timedelta(days=46.5)),
        ('3', timedelta(days=93)),
        (3, timedelta(days=93)),
        # More combinations
        ('1M', timedelta(days=31)),
        ('1m30s', timedelta(seconds=90)),
        ('-1', timedelta(days=-31)),
        ('0', timedelta()),
    ],
)
def test_parse_retention(value, expected: timedelta):
    # Read as VictoriaMetrics reads -retentionPeriod, and as the history service reads it
    assert models.parse_retention(value) == expected


@pytest.mark.parametrize(
    'value',
    [
        # The table of brewblox-history's test_parse_retention_invalid
        '30m',
        '1h30m',
        '1i',
        'x',
        '',
        'inf',
        'nan',
        '1e400',
        '99999999999999999999y',
        # More
        'M',
        '30 d',
        'd',
    ],
)
def test_parse_retention_invalid(value: str):
    with pytest.raises(ValueError, match='Invalid retention period'):
        models.parse_retention(value)


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        ('60s', 60),
        ('1m', 60),
        ('1h', 3600),
        ('0s', 0),
        ('10s', 10),
        ('90m', 5400),
        ('2h', 7200),
    ],
)
def test_parse_interval(value: str, expected: int):
    assert models.parse_interval(value) == expected


@pytest.mark.parametrize(
    'value',
    [
        '1.5s',
        '1min',
        '60',
        '',
        '1d',
        '-1s',
        'PT1M',
        '1m30s',
        ' 60s',
        's',
        # Beyond what the history service reads as a timedelta
        '99999999999999999h',
    ],
)
def test_parse_interval_invalid(value: str):
    # Only whole seconds, minutes or hours: history reads these the same way
    with pytest.raises(ValueError, match='Invalid interval'):
        models.parse_interval(value)


def test_victoria_defaults():
    config = VictoriaConfig()
    assert config.dense_enabled is True
    assert config.dense_retention == '30d'
    assert config.sparse_interval == '60s'
    assert config.minimum_step == '1s'
    assert config.search_latency == '1s'
    assert config.retention == '100y'

    # A brewblox.yml of before 0.12.0 gets the new fields from the defaults
    config = CtlConfig.model_validate({'victoria': {'retention': '10y'}})
    assert config.victoria.retention == '10y'
    assert config.victoria.dense_enabled is True
    assert config.victoria.dense_retention == '30d'
    assert config.victoria.sparse_interval == '60s'
    assert config.victoria.minimum_step == '1s'


@pytest.mark.parametrize(
    'values',
    [
        {'sparse_interval': '10s'},  # the smallest sparse_interval
        {'sparse_interval': '1m', 'minimum_step': '1s'},
        {'sparse_interval': '1h', 'minimum_step': '1m'},
        {'sparse_interval': '60s', 'minimum_step': '60s'},
        {'sparse_interval': '30s', 'minimum_step': '10s'},
        {'sparse_interval': '5m', 'minimum_step': '15s'},
        {'dense_retention': '1d'},  # the database minimum
        {'dense_retention': '24h'},
        {'dense_retention': '1'},
        {'dense_retention': '2w'},
        {'dense_retention': '1d12h'},
        {'retention': '1d'},
        {'retention': '1'},
        {'retention': '1.5M'},
        {'retention': '10y'},
        {'retention': '1d12h'},
    ],
)
def test_victoria_valid(values: dict):
    config = VictoriaConfig.model_validate({'dense_enabled': True, **values})
    for key, value in values.items():
        assert getattr(config, key) == value


@pytest.mark.parametrize('dense_enabled', [True, False])
@pytest.mark.parametrize(
    ('retention', 'match'),
    [
        ('x', "Invalid retention period: 'x'"),
        ('', 'Invalid retention period'),
        ('30m', 'Invalid retention period'),
        ('1h30m', 'Invalid retention period'),
        ('inf', 'Invalid retention period'),
        ('23h', 'The retention period must be at least 1d'),
        ('86399s', 'The retention period must be at least 1d'),
        ('1h', 'The retention period must be at least 1d'),
        ('0', 'The retention period must be at least 1d'),
        ('0d', 'The retention period must be at least 1d'),
        ('-1', 'The retention period must be at least 1d'),
    ],
)
def test_victoria_retention_invalid(dense_enabled: bool, retention: str, match: str):
    # The long-term retention is checked with or without the dense database
    with pytest.raises(ValidationError, match=match) as exc_info:
        VictoriaConfig(dense_enabled=dense_enabled, retention=retention)
    assert exc_info.value.errors()[0]['loc'] == ('retention',)


@pytest.mark.parametrize('retention', ['100y', '1200', '1200M', '102y'])
def test_victoria_retention_max(retention: str):
    # VictoriaMetrics accepts up to 1200 months of 31 days
    assert VictoriaConfig(retention=retention).retention == retention


@pytest.mark.parametrize(
    'values',
    [
        {'retention': '200y'},
        {'retention': '1000y'},
        {'retention': '1201'},
        {'retention': '1300M'},
        {'dense_enabled': True, 'dense_retention': '200y'},
    ],
)
def test_victoria_retention_above_max(values: dict):
    with pytest.raises(ValidationError):
        VictoriaConfig.model_validate(values)


@pytest.mark.parametrize(
    ('values', 'match'),
    [
        # Formats
        ({'minimum_step': '1.5s'}, "Invalid interval: '1.5s'"),
        ({'sparse_interval': '60.5s'}, "Invalid interval: '60.5s'"),
        ({'sparse_interval': '1min'}, 'Invalid interval'),
        ({'sparse_interval': '60'}, 'Invalid interval'),
        ({'sparse_interval': 'PT1M'}, 'Invalid interval'),
        ({'sparse_interval': '1d'}, 'Invalid interval'),
        ({'minimum_step': ''}, 'Invalid interval'),
        ({'minimum_step': '-1s'}, 'Invalid interval'),
        # Zero
        ({'minimum_step': '0s'}, 'minimum_step and sparse_interval must be positive'),
        ({'sparse_interval': '0s'}, 'minimum_step and sparse_interval must be positive'),
        ({'sparse_interval': '0m', 'minimum_step': '0h'}, 'minimum_step and sparse_interval must be positive'),
        # Not a multiple of minimum_step
        ({'minimum_step': '45s'}, 'sparse_interval must be a multiple of minimum_step'),
        ({'minimum_step': '120s'}, 'sparse_interval must be a multiple of minimum_step'),
        ({'sparse_interval': '15s', 'minimum_step': '10s'}, 'sparse_interval must be a multiple of minimum_step'),
        ({'sparse_interval': '1h', 'minimum_step': '7m'}, 'sparse_interval must be a multiple of minimum_step'),
        # Below history's follow_up_step_max
        ({'sparse_interval': '5s', 'minimum_step': '1s'}, 'sparse_interval must be at least 10s'),
        ({'sparse_interval': '9s'}, 'sparse_interval must be at least 10s'),
        ({'sparse_interval': '1s'}, 'sparse_interval must be at least 10s'),
        # The dense retention
        ({'dense_retention': '23h'}, 'dense_retention must be at least 1d'),
        ({'dense_retention': '86399s'}, 'dense_retention must be at least 1d'),
        ({'dense_retention': '0'}, 'dense_retention must be at least 1d'),
        ({'dense_retention': '-1'}, 'dense_retention must be at least 1d'),
        ({'dense_retention': '30m'}, "Invalid retention period: '30m'"),
        ({'dense_retention': 'x'}, 'Invalid retention period'),
        ({'dense_retention': ''}, 'Invalid retention period'),
    ],
)
def test_victoria_dense_invalid(values: dict, match: str):
    with pytest.raises(ValidationError, match=match):
        VictoriaConfig.model_validate({'dense_enabled': True, **values})

    # utils.get_config() reads brewblox.yml as CtlConfig
    with pytest.raises(ValidationError, match=match) as exc_info:
        CtlConfig.model_validate({'victoria': values})
    assert exc_info.value.errors()[0]['loc'][0] == 'victoria'


@pytest.mark.parametrize(
    'values',
    [
        {'minimum_step': '0s'},
        {'sparse_interval': '0s'},
        {'minimum_step': '45s'},
        {'minimum_step': '120s'},
        {'sparse_interval': '15s', 'minimum_step': '10s'},
        {'sparse_interval': '5s', 'minimum_step': '1s'},
        {'sparse_interval': '9s'},
        {'dense_retention': '23h'},
        {'dense_retention': '0'},
        {'dense_retention': '-1'},
    ],
)
def test_victoria_dense_disabled(values: dict):
    # History checks these only with the dense database, and must start whatever they are
    config = VictoriaConfig.model_validate({'dense_enabled': False, **values})
    assert config.dense_enabled is False
    for key, value in values.items():
        assert getattr(config, key) == value


@pytest.mark.parametrize(
    'values',
    [
        {'sparse_interval': 'abc'},
        {'minimum_step': 'x'},
        {'sparse_interval': ''},
        {'dense_retention': '30m'},
        {'dense_retention': 'x'},
    ],
)
def test_victoria_dense_disabled_unreadable(values: dict):
    # History reads the formats with or without the dense database
    with pytest.raises(ValidationError):
        VictoriaConfig.model_validate({'dense_enabled': False, **values})


@pytest.mark.parametrize('value', ['1s', '10s', '500ms', '1m30s', '0', '1.5s'])
def test_victoria_search_latency(value: str):
    # Victoria Metrics reads it as a Go duration
    assert VictoriaConfig(search_latency=value).search_latency == value


@pytest.mark.parametrize('value', ['10 s', '1d', 'x', '', '10'])
def test_victoria_search_latency_invalid(value: str):
    with pytest.raises(ValidationError, match='Invalid duration'):
        VictoriaConfig(search_latency=value)
