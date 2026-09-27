"""
Tests brewblox_ctl.actions
"""

from socket import AF_INET, AF_INET6, SOCK_STREAM
from unittest.mock import Mock

import pytest
import yaml
from configobj import ConfigObj
from packaging.version import Version
from psutil import AccessDenied, _common
from pytest_mock import MockerFixture

from brewblox_ctl import actions, const
from brewblox_ctl.models import CtlConfig, HostProfile, VictoriaConfig
from brewblox_ctl.testing import matching
import contextlib

TESTED = actions.__name__

GIB = 2**30
SMALL = HostProfile(small=True, memory_allowed_bytes='96MB', max_concurrent_requests=2)
MEDIUM = HostProfile(small=False, memory_allowed_bytes='128MB', max_concurrent_requests=4)
LARGE = HostProfile(small=False, memory_allowed_bytes='256MB', max_concurrent_requests=4)
# Without it, the databases ignore their VM_ environment
VM_COMMAND = '--envflag.enable=true --envflag.prefix=VM_'


def test_make_dotenv(m_write_file: Mock):
    actions.make_dotenv('1.2.3')
    assert 'BREWBLOX_CFG_VERSION=1.2.3' in m_write_file.call_args_list[0][0][1]


def test_make_config_dirs(m_sh: Mock):
    actions.make_config_dirs()
    m_sh.assert_called_with(matching('mkdir -p ./traefik '))
    dirs = m_sh.call_args[0][0].split()
    assert './victoria' in dirs
    assert './victoria-dense' in dirs
    # The legacy directory is never created: its existence renders the legacy database
    assert './victoria-legacy' not in dirs


def test_make_tls_certificates(m_sh: Mock, m_file_exists: Mock):
    m_file_exists.add_existing_files('./traefik/brew.blox/cert.pem', './traefik/minica.der')

    actions.make_tls_certificates()
    assert m_sh.call_count == 1

    actions.make_tls_certificates(True)
    assert m_sh.call_count == 6


def test_make_traefik_config(m_write_file: Mock):
    actions.make_traefik_config()
    assert 'address: :1883/tcp' in m_write_file.call_args_list[0][0][1]
    assert 'accessControlAllowCredentials: true' in m_write_file.call_args_list[1][0][1]


@pytest.mark.parametrize(
    ('memory', 'armv7', 'x86', 'expected'),
    [
        # Small by memory
        (1 * GIB, False, False, SMALL),
        (1.5 * GIB - 1, False, False, SMALL),
        (512 * 2**20, False, False, SMALL),
        # Small by armv7, whatever the memory
        (8 * GIB, True, False, SMALL),
        (2 * GIB, True, False, SMALL),
        # Medium: 2 GB, aarch64
        (1.5 * GIB, False, False, MEDIUM),
        (2 * GIB, False, False, MEDIUM),
        (3 * GIB - 1, False, False, MEDIUM),
        # Large by memory
        (3 * GIB, False, False, LARGE),
        (4 * GIB, False, False, LARGE),
        (16 * GIB, False, False, LARGE),
        # Large by x86
        (2 * GIB, False, True, LARGE),
        (1.5 * GIB, False, True, LARGE),
        # x86 with too little memory is still small
        (1 * GIB, False, True, SMALL),
    ],
)
def test_host_profile(
    m_total_memory_bytes: Mock,
    m_is_armv7: Mock,
    m_is_x86: Mock,
    memory: float,
    armv7: bool,
    x86: bool,
    expected: HostProfile,
):
    m_total_memory_bytes.return_value = int(memory)
    m_is_armv7.return_value = armv7
    m_is_x86.return_value = x86
    assert actions.host_profile() == expected


def rendered_shared_compose(m_write_file: Mock) -> dict:
    path, content = m_write_file.call_args[0][:2]
    assert path == './docker-compose.shared.yml'
    return yaml.safe_load(content)


def env_of(service: dict) -> dict:
    """The service's `KEY=value` environment list as a dict"""
    return dict(v.split('=', 1) for v in service['environment'])


def test_make_shared_compose(m_write_file: Mock):
    actions.make_shared_compose()
    assert '127.0.0.1:9600:9600' in m_write_file.call_args_list[0][0][1]


@pytest.mark.parametrize('legacy_history', [True, False])
def test_make_shared_compose_legacy_override(m_write_file: Mock, m_file_exists: Mock, legacy_history: bool):
    # remove-legacy-history renders without the legacy database before it removes the directory
    m_file_exists.add_existing_files(const.VICTORIA_LEGACY_DIR)
    actions.make_shared_compose(legacy_history=legacy_history)
    assert ('victoria-legacy:' in m_write_file.call_args[0][1]) is legacy_history


def test_make_shared_compose_defaults(m_write_file: Mock, m_file_exists: Mock):
    # Default config, a large host (conftest: 4 GiB, not armv7), no legacy directory
    actions.make_shared_compose()
    m_file_exists.assert_any_call(const.VICTORIA_LEGACY_DIR)
    services = rendered_shared_compose(m_write_file)['services']

    victoria = services['victoria']
    assert victoria['image'] == 'victoriametrics/victoria-metrics:v1.152.0'
    assert victoria['restart'] == 'unless-stopped'
    assert victoria['stop_grace_period'] == '30s'
    assert victoria['command'] == VM_COMMAND
    assert victoria['labels'] == ['traefik.http.services.victoria.loadbalancer.server.port=8428']
    assert env_of(victoria) == {
        'VM_http_pathPrefix': '/victoria',
        'VM_influxMeasurementFieldSeparator': '/',
        'VM_retentionPeriod': '100y',
        'VM_search_latencyOffset': '1s',
        'VM_dedup_minScrapeInterval': '1ms',
        'VM_inmemoryDataFlushInterval': '10m',
        'VM_memory_allowedBytes': '256MB',
        'VM_search_maxConcurrentRequests': '4',
        'VM_search_maxWorkersPerQuery': '2',
        'VM_search_inmemoryBufSizeBytes': '4MB',
    }
    assert victoria['volumes'] == [{'type': 'bind', 'source': './victoria', 'target': '/victoria-metrics-data'}]

    dense = services['victoria-dense']
    assert dense['image'] == 'victoriametrics/victoria-metrics:v1.152.0'
    assert dense['restart'] == 'unless-stopped'
    assert dense['stop_grace_period'] == '30s'
    assert dense['command'] == VM_COMMAND
    assert dense['labels'] == ['traefik.http.services.victoria-dense.loadbalancer.server.port=8428']
    assert env_of(dense) == {
        'VM_http_pathPrefix': '/victoria-dense',
        'VM_influxMeasurementFieldSeparator': '/',
        'VM_retentionPeriod': '30d',
        'VM_search_latencyOffset': '1s',
        'VM_dedup_minScrapeInterval': '1ms',
        'VM_inmemoryDataFlushInterval': '5m',
        'VM_memory_allowedBytes': '256MB',
        'VM_search_maxConcurrentRequests': '4',
        'VM_search_maxWorkersPerQuery': '2',
        'VM_search_inmemoryBufSizeBytes': '4MB',
    }
    assert dense['volumes'] == [{'type': 'bind', 'source': './victoria-dense', 'target': '/victoria-metrics-data'}]

    assert 'victoria-legacy' not in services

    history = services['history']
    assert history['image'] == 'ghcr.io/brewblox/brewblox-history:${BREWBLOX_RELEASE}'
    # ctl renders only these settings of history
    assert env_of(history) == {
        'BREWBLOX_HISTORY_DENSE_ENABLED': 'True',
        'BREWBLOX_HISTORY_DENSE_RETENTION': '30d',
        'BREWBLOX_HISTORY_SPARSE_INTERVAL': '60s',
        'BREWBLOX_HISTORY_MINIMUM_STEP': '1s',
    }
    assert history['volumes'] == [
        {'type': 'bind', 'source': '/etc/localtime', 'target': '/etc/localtime', 'read_only': True}
    ]

    # The other shared services are still there
    assert {'eventbus', 'redis', 'auth', 'traefik', 'ui'} <= set(services)
    assert '127.0.0.1:9600:9600' in services['traefik']['ports']


def test_make_shared_compose_config(m_write_file: Mock, m_get_config: CtlConfig):
    m_get_config.victoria = VictoriaConfig(
        retention='10y',
        dense_retention='14d',
        sparse_interval='5m',
        minimum_step='10s',
        search_latency='2s',
    )
    actions.make_shared_compose()
    services = rendered_shared_compose(m_write_file)['services']

    victoria = env_of(services['victoria'])
    assert victoria['VM_retentionPeriod'] == '10y'
    assert victoria['VM_search_latencyOffset'] == '2s'

    dense = env_of(services['victoria-dense'])
    assert dense['VM_retentionPeriod'] == '14d'
    assert dense['VM_search_latencyOffset'] == '2s'

    assert env_of(services['history']) == {
        'BREWBLOX_HISTORY_DENSE_ENABLED': 'True',
        'BREWBLOX_HISTORY_DENSE_RETENTION': '14d',
        'BREWBLOX_HISTORY_SPARSE_INTERVAL': '5m',
        'BREWBLOX_HISTORY_MINIMUM_STEP': '10s',
    }


def test_make_shared_compose_dense_disabled(m_write_file: Mock, m_get_config: CtlConfig):
    m_get_config.victoria = VictoriaConfig(dense_enabled=False, retention='10y')
    actions.make_shared_compose()
    services = rendered_shared_compose(m_write_file)['services']

    assert 'victoria-dense' not in services
    assert 'victoria-legacy' not in services

    # The long-term database gets the raw samples
    victoria = services['victoria']
    assert victoria['image'] == 'victoriametrics/victoria-metrics:v1.152.0'
    assert env_of(victoria)['VM_retentionPeriod'] == '10y'
    assert env_of(victoria)['VM_influxMeasurementFieldSeparator'] == '/'

    # The settings are rendered either way
    assert env_of(services['history']) == {
        'BREWBLOX_HISTORY_DENSE_ENABLED': 'False',
        'BREWBLOX_HISTORY_DENSE_RETENTION': '30d',
        'BREWBLOX_HISTORY_SPARSE_INTERVAL': '60s',
        'BREWBLOX_HISTORY_MINIMUM_STEP': '1s',
    }


@pytest.mark.parametrize('dense_enabled', [True, False])
def test_make_shared_compose_legacy(
    m_write_file: Mock, m_file_exists: Mock, m_get_config: CtlConfig, dense_enabled: bool
):
    m_get_config.victoria = VictoriaConfig(dense_enabled=dense_enabled, retention='10y')
    m_file_exists.add_existing_files('./victoria-legacy')
    actions.make_shared_compose()
    services = rendered_shared_compose(m_write_file)['services']

    assert ('victoria-dense' in services) == dense_enabled

    legacy = services['victoria-legacy']
    # The version that last wrote the directory: a newer one migrates its index, with no way back
    assert legacy['image'] == 'victoriametrics/victoria-metrics:v1.129.1'
    assert legacy['restart'] == 'unless-stopped'
    assert legacy['stop_grace_period'] == '30s'
    assert legacy['command'] == VM_COMMAND
    assert sorted(legacy['labels']) == [
        'traefik.http.routers.victoria-legacy.entrypoints=admin',
        'traefik.http.services.victoria-legacy.loadbalancer.server.port=8428',
    ]
    env = env_of(legacy)
    assert env['VM_http_pathPrefix'] == '/victoria-legacy'
    # History reaches it at this address
    assert const.VICTORIA_LEGACY_URL.endswith(':8428' + env['VM_http_pathPrefix'])
    assert env['VM_influxMeasurementFieldSeparator'] == '/'
    # Not the configured retention: nothing may expire before it is migrated
    assert env['VM_retentionPeriod'] == '100y'
    assert env['VM_memory_allowedBytes'] == '256MB'
    assert env['VM_search_maxConcurrentRequests'] == '4'
    assert legacy['volumes'] == [{'type': 'bind', 'source': './victoria-legacy', 'target': '/victoria-metrics-data'}]

    # The long-term database is the fresh ./victoria
    assert services['victoria']['image'] == 'victoriametrics/victoria-metrics:v1.152.0'
    assert services['victoria']['volumes'][0]['source'] == './victoria'
    assert env_of(services['victoria'])['VM_retentionPeriod'] == '10y'


@pytest.mark.parametrize(
    ('memory', 'armv7', 'x86', 'allowed', 'requests'),
    [
        (1 * GIB, False, False, '96MB', '2'),
        (8 * GIB, True, False, '96MB', '2'),
        (2 * GIB, False, False, '128MB', '4'),
        (2 * GIB, False, True, '256MB', '4'),
        (4 * GIB, False, False, '256MB', '4'),
    ],
)
def test_make_shared_compose_profile(
    m_write_file: Mock,
    m_file_exists: Mock,
    m_total_memory_bytes: Mock,
    m_is_armv7: Mock,
    m_is_x86: Mock,
    memory: int,
    armv7: bool,
    x86: bool,
    allowed: str,
    requests: str,
):
    m_total_memory_bytes.return_value = memory
    m_is_armv7.return_value = armv7
    m_is_x86.return_value = x86
    m_file_exists.add_existing_files('./victoria-legacy')
    actions.make_shared_compose()
    services = rendered_shared_compose(m_write_file)['services']

    # The same caps on every database
    for name in ['victoria', 'victoria-dense', 'victoria-legacy']:
        env = env_of(services[name])
        assert env['VM_memory_allowedBytes'] == allowed, name
        assert env['VM_search_maxConcurrentRequests'] == requests, name


def test_make_compose(m_read_compose: Mock, m_write_compose: Mock):
    m_read_compose.side_effect = dict
    actions.make_compose()
    m_write_compose.assert_called_with({'services': {}})

    m_read_compose.side_effect = lambda: {'version': '3.7', 'services': {'spark': {}}}
    actions.make_compose()
    m_write_compose.assert_called_with({'services': {'spark': {}}})

    m_read_compose.side_effect = FileNotFoundError
    actions.make_compose()
    m_write_compose.assert_called_with({'services': {}})


def test_apt_upgrade(m_sh: Mock, m_command_exists: Mock):
    actions.apt_upgrade()
    assert m_sh.call_count == 0

    m_command_exists.add_existing_commands('apt-get')
    actions.apt_upgrade()
    assert m_sh.call_count > 0


def test_check_docker_version(m_docker_version: Mock, m_confirm: Mock):
    # Docker is not installed, or not running
    m_docker_version.return_value = None
    assert actions.check_docker_version()

    m_docker_version.return_value = Version('20.10.10')
    assert actions.check_docker_version()
    assert m_confirm.call_count == 0

    m_docker_version.return_value = Version('20.10.5')
    m_confirm.return_value = False
    assert not actions.check_docker_version()

    m_confirm.return_value = True
    assert actions.check_docker_version()


def test_make_udev_rules(m_sh: Mock, m_file_exists: Mock, m_command_exists: Mock):
    m_command_exists.add_existing_commands('udevadm')
    m_file_exists.add_existing_files('/etc/udev/rules.d/50-particle.rules', '/etc/udev/rules.d/50-espressif.rules')
    actions.make_udev_rules()
    assert m_sh.call_count == 0

    m_file_exists.clear_existing_files()
    actions.make_udev_rules()
    assert m_sh.call_count > 0


def test_install_compose_plugin(m_sh: Mock, m_check_ok: Mock, m_command_exists: Mock):
    m_check_ok.return_value = True
    actions.install_compose_plugin()
    assert m_sh.call_count == 0

    m_check_ok.return_value = False
    m_command_exists.add_existing_commands('apt-get')
    actions.install_compose_plugin()
    assert m_sh.call_count == 1

    m_check_ok.return_value = False
    m_command_exists.clear_existing_commands()
    with pytest.raises(SystemExit):
        actions.install_compose_plugin()


def test_check_ports(
    mocker: MockerFixture, m_confirm: Mock, m_getenv: Mock, m_file_exists: Mock, m_is_compose_up: Mock
):
    m_net_connections = mocker.patch(TESTED + '.psutil.net_connections', autospec=True)
    m_net_connections.return_value = []

    m_getenv.side_effect = lambda k, default: default
    actions.check_ports()

    actions.check_ports()

    m_is_compose_up.return_value = False
    actions.check_ports()

    # Find a mapped port
    m_net_connections.return_value = [
        _common.sconn(
            fd=0,
            family=AF_INET6,
            type=SOCK_STREAM,
            laddr=_common.addr('::', 1234),
            raddr=('::', 44444),
            status='ESTABLISHED',
            pid=None,
        ),
        _common.sconn(
            fd=0,
            family=AF_INET,
            type=SOCK_STREAM,
            laddr=_common.addr('0.0.0.0', 80),
            raddr=_common.addr('::', 44444),
            status='ESTABLISHED',
            pid=None,
        ),
        _common.sconn(
            fd=0,
            family=AF_INET6,
            type=SOCK_STREAM,
            laddr=_common.addr('::', 80),
            raddr=_common.addr('::', 44444),
            status='ESTABLISHED',
            pid=None,
        ),
    ]
    actions.check_ports()

    m_confirm.return_value = False
    with pytest.raises(SystemExit):
        actions.check_ports()

    # no mapped ports found -> no need for confirm
    m_net_connections.return_value = []
    actions.check_ports()

    # warn and continue on error
    m_net_connections.side_effect = AccessDenied
    actions.check_ports()


def test_install_ctl_package(
    m_sh: Mock, m_get_config: Mock, m_user_home_exists: Mock, m_file_exists: Mock, m_command_exists: Mock
):
    config = m_get_config

    m_user_home_exists.return_value = True
    m_command_exists.add_existing_commands('apt-get', 'uv', 'git')

    actions.install_ctl_package()
    m_sh.assert_called_with(
        'uv pip install --upgrade --force-reinstall --refresh --extra-index-url=https://www.piwheels.org/simple --index-strategy=unsafe-best-match "git+https://github.com/brewblox/brewblox-ctl@edge"'
    )

    m_sh.reset_mock()

    config.release = 'tag'
    actions.install_ctl_package()
    m_sh.assert_called_with(
        'uv pip install --upgrade --force-reinstall --refresh --extra-index-url=https://www.piwheels.org/simple --index-strategy=unsafe-best-match "git+https://github.com/brewblox/brewblox-ctl@tag"'
    )

    m_sh.reset_mock()

    uv_from_script = 'wget -qO- https://astral.sh/uv/install.sh | sh'
    uv_from_pip = 'pip install --upgrade uv'
    git_install = 'sudo apt-get update && sudo apt-get install -y git python3-dev'

    # test uv not installed yet
    m_sh.reset_mock()
    m_file_exists.clear_existing_files()
    m_command_exists.clear_existing_commands()
    m_command_exists.add_existing_commands('apt-get', 'git')
    with contextlib.suppress(SystemExit):
        actions.install_ctl_package()
    assert any(call[0][0] == uv_from_script for call in m_sh.call_args_list), 'Expected uv install from script'
    assert any(call[0][0] == uv_from_pip for call in m_sh.call_args_list), 'Expected uv install from pip'

    # test uv already installed, git not installed, but apt-get not available
    m_sh.reset_mock()
    m_command_exists.clear_existing_commands()
    m_command_exists.add_existing_commands('uv')
    with pytest.raises(SystemExit):
        actions.install_ctl_package()

    # test uv already installed, git not installed, apt-get available
    m_sh.reset_mock()
    m_command_exists.clear_existing_commands()
    m_command_exists.add_existing_commands('uv', 'apt-get')
    actions.install_ctl_package()
    assert any(call[0][0] == git_install for call in m_sh.call_args_list), 'Expected git + python3-dev install'

    # test uv, git already installed
    m_sh.reset_mock()
    m_command_exists.clear_existing_commands()
    m_command_exists.add_existing_commands('uv', 'git')
    config.ctl_release = 'ctl_tag'
    m_file_exists.add_existing_files('./brewblox-ctl.tar.gz')
    actions.install_ctl_package()
    m_sh.assert_any_call('rm -f ./brewblox-ctl.tar.gz')
    m_sh.assert_called_with(
        'uv pip install --upgrade --force-reinstall --refresh --extra-index-url=https://www.piwheels.org/simple --index-strategy=unsafe-best-match "git+https://github.com/brewblox/brewblox-ctl@ctl_tag"'
    )
    assert not any(call[0][0] == uv_from_script for call in m_sh.call_args_list), 'Unexpected uv install from script'
    assert not any(call[0][0] == uv_from_pip for call in m_sh.call_args_list), 'Unexpected uv install from pip'


def test_deploy_ctl_wrapper(m_sh: Mock, m_user_home_exists: Mock):
    m_user_home_exists.return_value = True
    actions.make_ctl_entrypoint()
    m_sh.assert_called_with(matching('mkdir -p'))
    m_user_home_exists.return_value = False
    actions.make_ctl_entrypoint()
    m_sh.assert_called_with(matching('sudo cp'))


def test_fix_ipv6(m_sh: Mock, m_is_wsl: Mock, m_command_exists: Mock, m_read_file_sudo: Mock):
    m_command_exists.add_existing_commands('service')
    m_is_wsl.return_value = False
    m_read_file_sudo.side_effect = [
        '{}',
        '',
        '{}',
        '{"fixed-cidr-v6": "2001:db8:1::/64"}',
    ]
    m_sh.side_effect = [
        # autodetect config
        """
        /usr/bin/dockerd -H fd:// --containerd=/run/containerd/containerd.sock
        grep --color=auto dockerd
        """,  # ps aux
        None,  # mkdir
        None,  # touch
        None,  # restart
        # with config provided, no restart
        None,  # mkdir
        None,  # touch
        # with config, service command not found
        None,  # mkdir
        None,  # touch
        # with config, config already set
        None,  # mkdir
        None,  # touch
    ]

    actions.fix_ipv6()
    assert m_sh.call_count == 4

    actions.fix_ipv6('/etc/file.json', False)
    assert m_sh.call_count == 4 + 2

    m_command_exists.clear_existing_commands()
    actions.fix_ipv6('/etc/file.json')
    assert m_sh.call_count == 4 + 2 + 2

    actions.fix_ipv6('/etc/file.json')
    assert m_sh.call_count == 4 + 2 + 2 + 2

    m_is_wsl.return_value = True
    actions.fix_ipv6('/etc/file.json')
    assert m_sh.call_count == 4 + 2 + 2 + 2


def test_edit_avahi_config(
    mocker: MockerFixture, m_sh: Mock, m_command_exists: Mock, m_file_exists: Mock, m_info: Mock, m_warn: Mock
):
    config = ConfigObj()
    m_config = mocker.patch(TESTED + '.ConfigObj')
    m_config.return_value = config

    m_command_exists.add_existing_commands('systemctl')

    # File not found
    actions.edit_avahi_config()
    assert m_config.call_count == 0
    assert m_info.call_count == 0
    assert m_warn.call_count == 0
    assert m_sh.call_count == 0

    # File is found for other tests
    m_file_exists.add_existing_files('/etc/avahi/avahi-daemon.conf')

    # Noop for empty config and default settings
    m_sh.reset_mock()
    m_warn.reset_mock()
    config.clear()
    actions.edit_avahi_config()
    assert m_sh.call_count == 0
    assert m_warn.call_count == 0

    # Change config if set
    m_sh.reset_mock()
    m_warn.reset_mock()
    config['server'] = {'use-ipv6': 'no'}
    config['publish'] = {'publish-aaaa-on-ipv4': 'no'}
    config['reflector'] = {'enable-reflector': 'yes'}
    actions.edit_avahi_config()
    assert m_sh.call_count == 1
    assert m_warn.call_count == 0
    assert config['reflector']['enable-reflector'] == 'no'

    # Abort if no changes were made
    m_sh.reset_mock()
    m_warn.reset_mock()
    config['server'] = {'use-ipv6': 'no'}
    config['publish'] = {'publish-aaaa-on-ipv4': 'no'}
    config['reflector'] = {'enable-reflector': 'no'}
    actions.edit_avahi_config()
    assert m_sh.call_count == 0
    assert m_warn.call_count == 0
    assert config['reflector']['enable-reflector'] == 'no'

    # systemctl command does not exist
    m_command_exists.clear_existing_commands()
    m_sh.reset_mock()
    m_warn.reset_mock()
    config.clear()
    config['reflector'] = {'enable-reflector': 'yes'}
    m_command_exists.clear_existing_commands()
    actions.edit_avahi_config()
    assert m_sh.call_count == 0
    assert m_warn.call_count == 1
    assert config['reflector']['enable-reflector'] == 'no'


def test_edit_sshd_config(m_sh: Mock, m_command_exists: Mock, m_file_exists: Mock, m_read_file_sudo: Mock):
    lines = '\n'.join(['# Allow client to pass locale environment variables', 'AcceptEnv LANG LC_*'])
    comment_lines = '\n'.join(['# Allow client to pass locale environment variables', '#AcceptEnv LANG LC_*'])

    m_command_exists.add_existing_commands('systemctl')

    # File not exists
    actions.edit_sshd_config()
    assert m_sh.call_count == 0

    # No change
    m_file_exists.add_existing_files('/etc/ssh/sshd_config')
    m_read_file_sudo.return_value = comment_lines
    actions.edit_sshd_config()
    assert m_sh.call_count == 0

    # Changed, but no service restart
    m_read_file_sudo.return_value = lines
    m_command_exists.clear_existing_commands()
    actions.edit_sshd_config()
    assert m_sh.call_count == 0

    # Changed, full change
    m_read_file_sudo.return_value = lines
    m_command_exists.add_existing_commands('systemctl')
    actions.edit_sshd_config()
    m_sh.assert_called_with(matching('sudo systemctl restart'))


def test_start_esptool(m_sh: Mock, m_command_exists: Mock):
    actions.start_esptool('--chip esp32', 'read_flash', 'coredump.bin')
    m_sh.assert_called_with('sudo -E env "PATH=$PATH" uv run esptool.py --chip esp32 read_flash coredump.bin')
    assert m_sh.call_count == 2

    m_sh.reset_mock()
    m_command_exists.add_existing_commands('esptool.py')
    actions.start_esptool()
    m_sh.assert_called_with('sudo -E env "PATH=$PATH" uv run esptool.py ')
    assert m_sh.call_count == 1
