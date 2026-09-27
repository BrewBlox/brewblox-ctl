import math
import re
from datetime import timedelta
from glob import glob
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

# One part of a metricsql duration, as in `1d12h`
_RETENTION_PART = re.compile(r'(-?)(\d+(?:\.\d+)?)(ms|s|m|h|d|w|y)')
_RETENTION_UNITS = {
    'ms': timedelta(milliseconds=1),
    's': timedelta(seconds=1),
    'm': timedelta(minutes=1),
    'h': timedelta(hours=1),
    'd': timedelta(days=1),
    'w': timedelta(weeks=1),
    'y': timedelta(days=365),
}

_INTERVAL = re.compile(r'(\d+)(s|m|h)')
_INTERVAL_UNITS = {'s': 1, 'm': 60, 'h': 3600}

# A Go duration, as Victoria Metrics reads -search.latencyOffset
_GO_DURATION = re.compile(r'[-+]?(?:0|(?:(?:\d+\.?\d*|\.\d+)(?:ns|us|µs|μs|ms|s|m|h))+)')

# The history service's default `follow_up_step_max`, which must not exceed `sparse_interval`
MIN_SPARSE_INTERVAL = 10

# Victoria Metrics refuses a -retentionPeriod below a day, or above 1200 months of 31 days
MIN_RETENTION = timedelta(days=1)
MAX_RETENTION_MONTHS = 1200


def parse_retention(value: str) -> timedelta:
    """Parses a retention period the way Victoria Metrics reads `-retentionPeriod`.

    The history service reads it the same way.
    A bare number or an `M` suffix counts months of 31 days.
    Otherwise the value is a metricsql duration, whose parts can be combined (`1d12h`),
    except that it must not end in `m`: the database refuses that as ambiguous.
    """
    text = str(value)
    try:
        return timedelta(days=31 * float(text[:-1] if text.endswith('M') else text))
    except (ValueError, OverflowError):  # not a number, or beyond timedelta
        pass

    text = text.lower()
    if text.endswith('m') or not re.fullmatch(f'(?:{_RETENTION_PART.pattern})+', text):
        raise ValueError(f'Invalid retention period: {value!r}')

    retention = timedelta()
    negative = False  # As in metricsql: once a part is negative, the parts after it are too
    try:
        for sign, number, unit in _RETENTION_PART.findall(text):
            negative = negative or sign == '-'
            part = float(number) * _RETENTION_UNITS[unit]
            retention += -part if negative else part
    except OverflowError as ex:
        raise ValueError(f'Invalid retention period: {value!r}') from ex
    return retention


def parse_interval(value: str) -> int:
    """Parses an interval of whole seconds, minutes or hours (`60s`, `1m`, `1h`) as seconds.

    The history service reads these formats the same way.
    """
    match = _INTERVAL.fullmatch(str(value))
    if not match:
        raise ValueError(f'Invalid interval: {value!r}. Use a whole number of s, m or h, as in 60s')
    seconds = int(match[1]) * _INTERVAL_UNITS[match[2]]
    try:
        timedelta(seconds=seconds)  # The history service reads it as a timedelta
    except OverflowError as ex:
        raise ValueError(f'Invalid interval: {value!r}') from ex
    return seconds


def physical_interfaces() -> List[str]:
    """Infers list of network interfaces connected to a physical component.

    All network interfaces are listed in /sys/class/net/.
    We want to exclude the loopback interface, and all virtual interfaces created by Docker.
    We do this by only selecting the network interfaces that are linked to a device.
    """
    return [v.split('/')[4] for v in glob('/sys/class/net/*/device')]


class ComposeConfig(BaseModel):
    project: str = Field(
        default='brewblox',
        title='Docker Compose project name',
        description='If you run multiple Compose projects, they must have unique names.',
    )
    files: List[str] = Field(
        default=['docker-compose.shared.yml', 'docker-compose.yml'],
        title='A list of files used by Compose to generate configuration. '
        + 'If multiple files are found, they are merged.',
    )


class PortConfig(BaseModel):
    http: int = Field(
        default=80,
        title='External HTTP port',
        description='HTTP is used by the UI and external REST API requests. '
        + 'By default, all HTTP requests are redirected to HTTPS.',
    )
    https: int = Field(default=443, title='External HTTPS port', description='HTTPS is HTTP + TLS encryption.')
    mqtt: int = Field(default=1883, title='External MQTT port', description='History data is published over MQTT.')
    mqtts: int = Field(default=8883, title='External MQTTS port', description='MQTTS is MQTT + TLS encryption.')
    admin: int = Field(
        default=9600, title='Admin HTTP port', description='The admin port is only accessible from the server itself.'
    )


class AvahiConfig(BaseModel):
    managed: bool = Field(default=True, title='Enable/disable brewblox-ctl changing the host Avahi configuration')
    reflection: bool = Field(default=False, title='Enable/disable mDNS reflection in host Avahi configuration')


class ReflectorConfig(BaseModel):
    enabled: bool = Field(
        default=True,
        title='Generate mDNS reflector services',
        description='Should not be combined with Avahi reflection.',
    )
    interfaces: List[str] = Field(
        default_factory=physical_interfaces,
        title='Reflected host network interfaces',
        description='A service will be generated for each interface.',
    )


class UsbProxyConfig(BaseModel):
    enabled: bool = Field(
        default=False,
        title='Enable USB proxy service for Spark 2/3',
        description='The Spark service will query the proxy service during discovery.',
    )


class SystemConfig(BaseModel):
    apt_upgrade: bool = Field(default=True, title='Enable/disable updating Apt packages during updates')


class AuthConfig(BaseModel):
    enabled: bool = Field(
        default=False,
        title='Enable/disable UI authentication',
        description='When enabled, users need to login when using the UI.',
    )


class TraefikConfig(BaseModel):
    tls: bool = Field(
        default=True,
        title='Enable/disable TLS termination for the HTTPS port',
        description='This can be disabled when TLS termination is handled by another proxy.',
    )
    redirect_http: bool = Field(
        default=True,
        title='Redirect HTTP requests to HTTPS and the HTTPS port',
        description='This option should not be disabled while authentication is enabled.',
    )
    static_config_file: str = Field(
        default='/config/traefik.yml',
        title='Path to the static Traefik configuration file',
        description='This is the path inside the `traefik` service. '
        + 'Change this setting to use custom configuration '
        + 'that will not be reset during updates.',
    )
    dynamic_config_dir: str = Field(
        default='/config/dynamic',
        title='Path to the directory containing dynamic Traefik configuration files',
        description='This is the path inside the `traefik` service. '
        + 'Change this setting to stop using the default dynamic configuration.',
    )


class VictoriaConfig(BaseModel):
    retention: str = Field(
        default='100y',
        title='Retention period for history data in the long-term Victoria Metrics database',
        description='Data older than this value is gradually deleted. '
        'With `dense_enabled`, the long-term database keeps averages of every `sparse_interval`.',
    )
    dense_enabled: bool = Field(
        default=True,
        title='Keep raw history data in a separate dense database',
        description='The dense database keeps every raw sample for `dense_retention`, '
        'and the long-term database keeps averages of every `sparse_interval`. '
        'If disabled, the long-term database keeps the raw samples.',
    )
    dense_retention: str = Field(
        default='30d',
        title='Retention period for raw history data in the dense database',
        description='It must be at least 1d.',
    )
    sparse_interval: str = Field(
        default='60s',
        title='Interval of the averages in the long-term database',
        description='Choose it before migrating history: a history migration stops when it changes, '
        'until it is set back or the migration is discarded. '
        'Averages keep the interval they were written with. '
        'It must be a multiple of `minimum_step`, and at least 10s.',
    )
    minimum_step: str = Field(
        default='1s',
        title='Smallest interval between the points of a history query',
        description='This is the finest resolution of graphs.',
    )
    search_latency: str = Field(
        default='1s',
        title='Max duration before inserted history data is returned by queries',
        description='Newly inserted data points must be indexed before they can be queried. '
        'Every {search_latency}, all newly inserted points are indexed.',
    )

    # The history service reads its settings at startup, and fails on a value it refuses.
    # It also serves the datastore, so values are checked here first.

    @field_validator('retention', 'dense_retention')
    @classmethod
    def _check_retention(cls, value: str) -> str:
        months = parse_retention(value) / timedelta(days=31)
        if not re.fullmatch(r'[\d.]+M?', value):  # A duration counts whole months
            months = math.floor(months)
        if months > MAX_RETENTION_MONTHS:
            raise ValueError('The retention period must be at most 1200 months, the database maximum')
        return value

    @field_validator('retention')
    @classmethod
    def _check_min_retention(cls, value: str) -> str:
        if parse_retention(value) < MIN_RETENTION:
            raise ValueError('The retention period must be at least 1d, the database minimum')
        return value

    @field_validator('minimum_step', 'sparse_interval')
    @classmethod
    def _check_interval(cls, value: str) -> str:
        parse_interval(value)
        return value

    @field_validator('search_latency')
    @classmethod
    def _check_search_latency(cls, value: str) -> str:
        if not _GO_DURATION.fullmatch(str(value)):
            raise ValueError(f'Invalid duration: {value!r}. Use a duration such as 1s, 500ms or 1m30s')
        return value

    @model_validator(mode='after')
    def _check_dense(self) -> 'VictoriaConfig':
        # The history service only checks these with the dense database
        if not self.dense_enabled:
            return self
        minimum_step = parse_interval(self.minimum_step)
        sparse_interval = parse_interval(self.sparse_interval)
        if minimum_step <= 0 or sparse_interval <= 0:
            raise ValueError('minimum_step and sparse_interval must be positive')
        if sparse_interval % minimum_step:
            raise ValueError('sparse_interval must be a multiple of minimum_step')
        if sparse_interval < MIN_SPARSE_INTERVAL:
            raise ValueError(f'sparse_interval must be at least {MIN_SPARSE_INTERVAL}s')
        if parse_retention(self.dense_retention) < MIN_RETENTION:
            raise ValueError('dense_retention must be at least 1d, the database minimum')
        return self


class CtlConfig(BaseModel):
    release: str = Field(
        default='edge',
        title='Brewblox release tag',
        description='This determines the software version used for services and firmware.',
    )
    ctl_release: Optional[str] = Field(
        default=None,
        title='brewblox-ctl release tag',
        description='The release tag for brewblox-ctl itself. ' + 'If not set, the value of `release` is used.',
    )
    skip_confirm: bool = Field(
        default=False,
        title='Automatically skip confirmation prompts',
        description='brewblox-ctl prompts whenever a command makes a persistent change, '
        'unless the `-y` option is used, or `skip_confirm` is true.',
    )
    debug: bool = Field(
        default=False,
        title='Run brewblox-ctl in debug mode',
        description='Show stack traces on error, and print additional information in commands.',
    )
    environment: Dict[str, str] = Field(
        default={},
        title='Custom environment settings',
        description='They will be inserted in the .env file. '
        + 'You can reference them in your docker-compose.yml configuration.',
    )

    # Nested configuration
    ports: PortConfig = Field(default_factory=PortConfig)
    compose: ComposeConfig = Field(default_factory=ComposeConfig)
    avahi: AvahiConfig = Field(default_factory=AvahiConfig)
    reflector: ReflectorConfig = Field(default_factory=ReflectorConfig)
    usb_proxy: UsbProxyConfig = Field(default_factory=UsbProxyConfig)
    system: SystemConfig = Field(default_factory=SystemConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    traefik: TraefikConfig = Field(default_factory=TraefikConfig)
    victoria: VictoriaConfig = Field(default_factory=VictoriaConfig)


class HostProfile(BaseModel):
    """Settings of the history databases that depend on the host"""

    small: bool
    # Each database sizes its caches from this, and not from a share of the host's memory
    memory_allowed_bytes: str
    # Bounds the memory used to unpack raw samples for queries
    max_concurrent_requests: int


class CtlOpts(BaseModel):
    dry_run: bool = False
    quiet: bool = False
    verbose: bool = False
    yes: bool = False
    color: bool = False
