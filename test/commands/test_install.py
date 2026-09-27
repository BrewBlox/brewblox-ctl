"""
Tests brewblox_ctl.commands.install
"""

from typing import Callable, Dict, List
from unittest.mock import Mock

import pytest.__main__
from packaging.version import Version
from pytest_mock import MockerFixture

from brewblox_ctl import const, migration, testing, utils
from brewblox_ctl.commands import install
from brewblox_ctl.testing import invoke

TESTED = install.__name__
SNAPSHOT = install.snapshot.__name__


@pytest.fixture(autouse=True)
def m_sleep(mocker: MockerFixture):
    return mocker.patch(TESTED + '.sleep')


@pytest.fixture(autouse=True)
def m_input(mocker: MockerFixture):
    return mocker.patch(TESTED + '.input')


@pytest.fixture
def m_opts(mocker: MockerFixture):
    m = mocker.patch(TESTED + '.InstallOptions')
    m.return_value.user_info = ('username', 'password')
    m.return_value.move_legacy_history = False
    return m.return_value


@pytest.fixture
def m_actions(mocker: MockerFixture):
    return mocker.patch(TESTED + '.actions', autospec=True)


@pytest.fixture
def m_snapshot_actions(mocker: MockerFixture):
    return mocker.patch(SNAPSHOT + '.actions', autospec=True)


def test_check_compatibility(mocker: MockerFixture, m_confirm: Mock, m_is_armv6: Mock, m_docker_version: Mock):
    opts = install.InstallOptions()
    mocker.patch(TESTED + '.SystemExit', RuntimeError)

    m_is_armv6.return_value = True
    m_confirm.return_value = True
    opts.check_compatibility()

    m_confirm.return_value = False
    with pytest.raises(RuntimeError):
        opts.check_compatibility()

    m_is_armv6.return_value = False
    opts.check_compatibility()

    m_docker_version.return_value = Version('20.10.5')
    with pytest.raises(RuntimeError):
        opts.check_compatibility()


def test_check_confirm_opts(m_confirm: Mock):
    opts = install.InstallOptions()

    # use_defaults will be true, skip_confirm not asked
    m_confirm.return_value = True

    opts.check_confirm_opts()

    assert opts.use_defaults is True
    assert opts.skip_confirm is True
    assert m_confirm.call_count == 1

    # use_defaults False -> explicitly ask skip_confirm
    m_confirm.reset_mock()
    m_confirm.return_value = False

    opts.check_confirm_opts()

    assert opts.use_defaults is False
    assert opts.skip_confirm is False
    assert m_confirm.call_count == 2


def test_check_system_opts(m_confirm: Mock, m_command_exists: Mock):
    opts = install.InstallOptions()

    # no use defaults -> prompt
    m_command_exists.add_existing_commands('apt-get')
    m_confirm.return_value = True
    opts.check_system_opts()
    assert opts.apt_install is True
    assert m_confirm.call_count == 1

    # use defaults -> no prompt
    opts.use_defaults = True
    m_confirm.reset_mock()
    m_confirm.return_value = False
    opts.check_system_opts()
    assert opts.apt_install is True
    assert m_confirm.call_count == 0

    # apt not found -> no prompt
    opts.use_defaults = False
    m_confirm.reset_mock()
    m_confirm.return_value = True
    m_command_exists.clear_existing_commands()
    opts.check_system_opts()
    assert opts.apt_install is False
    assert m_confirm.call_count == 0


def test_check_docker_opts(m_confirm: Mock, m_command_exists: Mock, m_is_docker_user: Mock):
    opts = install.InstallOptions()

    # Clean env -> prompt to install, add, pull
    m_is_docker_user.return_value = False
    m_confirm.return_value = True
    opts.check_docker_opts()
    assert opts.docker_install is True
    assert opts.docker_group_add is True
    assert opts.docker_pull is True
    assert m_confirm.call_count == 3

    # use_defaults set -> no prompt
    opts.use_defaults = True
    m_confirm.reset_mock()
    m_is_docker_user.return_value = False
    m_confirm.return_value = True
    opts.check_docker_opts()
    assert opts.docker_install is True
    assert opts.docker_group_add is True
    assert opts.docker_pull is True
    assert m_confirm.call_count == 0

    # existing install -> only pull
    opts.use_defaults = False
    m_confirm.reset_mock()
    m_command_exists.add_existing_commands('docker')
    m_is_docker_user.return_value = True
    m_confirm.return_value = True
    opts.check_docker_opts()
    assert opts.docker_install is False
    assert opts.docker_group_add is False
    assert opts.docker_pull is True
    assert m_confirm.call_count == 1


def test_check_reboot_opts(m_confirm: Mock, m_is_docker_user: Mock):
    opts = install.InstallOptions()

    opts.docker_install = False
    opts.docker_group_add = False
    m_is_docker_user.return_value = False
    m_confirm.return_value = True

    opts.check_reboot_opts()
    assert opts.reboot_needed is False
    assert m_confirm.call_count == 0

    opts.docker_install = True
    opts.check_reboot_opts()
    assert opts.reboot_needed is True
    assert m_confirm.call_count == 1


def test_check_init_opts(m_confirm: Mock, m_file_exists: Mock):
    opts = install.InstallOptions()

    m_file_exists.add_existing_files(
        './docker-compose.yml', './auth/', './redis/', './victoria/', './traefik/', './mosquitto/', './spark/backup/'
    )
    m_confirm.return_value = True
    opts.check_init_opts()
    assert opts.init_compose is False
    assert opts.init_auth is False
    assert opts.init_datastore is False
    assert opts.init_history is False
    assert opts.init_gateway is False
    assert opts.init_eventbus is False
    assert opts.init_spark_backup is False
    # ./victoria without ./victoria-dense: history of before 0.12.0
    assert opts.move_legacy_history is True

    m_file_exists.clear_existing_files()
    opts.check_init_opts()
    assert opts.init_compose is True
    assert opts.init_auth is True
    assert opts.init_datastore is True
    assert opts.init_history is True
    assert opts.init_gateway is True
    assert opts.init_eventbus is True
    assert opts.init_spark_backup is True
    assert opts.move_legacy_history is False
    assert m_confirm.call_count == 7


@pytest.mark.parametrize(
    'dirs, moved',
    [
        (['./victoria/'], True),
        (['./victoria-dense/'], False),
        (['./victoria-legacy/'], False),
        (['./victoria/', './victoria-dense/'], False),
        (['./victoria/', './victoria-legacy/'], False),
        (['./victoria-dense/', './victoria-legacy/'], False),
        (['./victoria/', './victoria-dense/', './victoria-legacy/'], False),
    ],
)
def test_check_init_opts_history_dirs(m_confirm: Mock, m_file_exists: Mock, dirs: List[str], moved: bool):
    """One prompt covers all history directories"""
    opts = install.InstallOptions()
    m_file_exists.add_existing_files(*dirs)

    m_confirm.return_value = True
    opts.check_init_opts()
    m_confirm.assert_called_once_with(
        'This directory already contains Victoria history files. Do you want to keep them?'
    )
    assert opts.init_history is False
    assert opts.move_legacy_history is moved

    # Not kept: nothing to move
    m_confirm.reset_mock()
    m_confirm.return_value = False
    opts.check_init_opts()
    assert m_confirm.call_count == 1
    assert opts.init_history is True
    assert opts.move_legacy_history is False


def test_check_init_opts_legacy_not_movable(
    m_confirm: Mock, m_file_exists: Mock, m_is_mount: Mock, m_is_symlink: Mock, m_error: Mock
):
    opts = install.InstallOptions()
    m_file_exists.add_existing_files('./victoria/')

    # A mount point cannot be moved
    m_confirm.return_value = True
    m_is_mount.return_value = True
    with pytest.raises(SystemExit):
        opts.check_init_opts()
    assert m_error.call_count > 0

    # A symbolic link is moved as a link: the user decides
    m_is_mount.return_value = False
    m_is_symlink.return_value = True
    m_confirm.side_effect = prompt_answers({'continue': False})
    with pytest.raises(SystemExit):
        opts.check_init_opts()

    m_confirm.side_effect = prompt_answers({'continue': True})
    opts.check_init_opts()
    assert opts.move_legacy_history is True

    # Not kept: nothing is moved, and nothing is asked
    m_confirm.side_effect = prompt_answers({'continue': False, 'Victoria': False})
    opts.check_init_opts()
    assert opts.init_history is True
    assert opts.move_legacy_history is False


def test_install_basic(m_actions: Mock, m_input: Mock, m_sh: Mock, m_opts: Mock):
    invoke(install.install)
    assert m_sh.call_count == 15  # do everything
    assert m_input.call_count == 1  # prompt reboot

    m_sh.reset_mock()
    m_input.reset_mock()
    m_opts.prompt_reboot = False
    invoke(install.install)
    assert m_sh.call_count == 15  # do everything
    assert m_input.call_count == 0  # no reboot prompt


def test_install_minimal(m_actions: Mock, m_input: Mock, m_sh: Mock, m_opts: Mock, m_is_compose_up: Mock):
    m_is_compose_up.return_value = False
    m_opts.apt_install = False
    m_opts.docker_install = False
    m_opts.docker_group_add = False
    m_opts.docker_pull = False
    m_opts.reboot_needed = False
    m_opts.init_compose = False
    m_opts.init_auth = False
    m_opts.init_datastore = False
    m_opts.init_history = False
    m_opts.init_gateway = False
    m_opts.init_eventbus = False
    m_opts.init_spark_backup = False
    m_opts.user_info = None

    invoke(install.install)
    # The kept history directories are completed
    m_sh.assert_called_once_with('mkdir -p ./victoria/ ./victoria-dense/')


def test_install_snapshot(m_actions: Mock, m_input: Mock, m_sh: Mock, m_opts: Mock, m_snapshot_actions: Mock):
    utils.get_opts().dry_run = True
    invoke(install.install, '--snapshot brewblox.tar.gz')
    assert m_opts.check_init_opts.call_count == 0
    assert m_sh.call_count > 0


def test_makecert(m_actions: Mock):
    invoke(install.makecert)
    m_actions.make_tls_certificates.assert_called_once_with(True, (), None)


def prompt_answers(answers: Dict[str, bool], default: bool = True) -> Callable:
    """Answers confirm() prompts by a part of their text"""

    def confirm(msg: str, *args, **kwargs) -> bool:
        for key, value in answers.items():
            if key in msg:
                return value
        return default

    return confirm


@pytest.fixture(autouse=True)
def m_cfg_version(m_getenv: Mock):
    """The configuration version in the .env of the directory, from before the install"""
    m_getenv.side_effect = lambda key, default=None: '0.11.0' if key == const.ENV_KEY_CFG_VERSION else default
    return m_getenv


@pytest.fixture
def install_log(
    mocker: MockerFixture,
    m_actions: Mock,
    m_sh: Mock,
    m_command_exists: Mock,
    m_has_docker_rights: Mock,
) -> List[str]:
    """
    Runs the install with the real InstallOptions.
    Records its shell commands, generated files and checks in order.
    """
    log = []

    # Docker is installed and usable: no reboot
    m_command_exists.add_existing_commands('docker')
    m_has_docker_rights.return_value = True

    def sh(cmd, *args, **kwargs):
        log.append(cmd)
        return testing.check_sudo(cmd, *args, **kwargs)

    m_sh.side_effect = sh

    for name in ['make_brewblox_config', 'check_ports', 'make_dotenv', 'make_shared_compose', 'make_compose']:
        getattr(m_actions, name).side_effect = lambda *args, _name=name, **kwargs: log.append(_name)

    real_check = migration.check_legacy_movable

    def check_legacy_movable():
        log.append('check_legacy_movable')
        real_check()

    mocker.patch.object(migration, 'check_legacy_movable', side_effect=check_legacy_movable)
    return log


def history_cmds(log: List[str]) -> List[str]:
    return [cmd for cmd in log if 'victoria' in cmd]


def info_msgs(m_info: Mock) -> List[str]:
    return [str(c.args[0]) for c in m_info.call_args_list]


def assert_no_migrate_hint(m_info: Mock):
    assert not any(migration.MIGRATE_CMD in msg for msg in info_msgs(m_info))


def test_install_history_not_kept(install_log: List[str], m_confirm: Mock, m_file_exists: Mock, m_info: Mock):
    m_file_exists.add_existing_files('./victoria/', './victoria-dense/', './victoria-legacy/')
    m_confirm.side_effect = prompt_answers({'Victoria': False})

    invoke(install.install)

    # All three removed, the two databases created again
    cmds = history_cmds(install_log)
    assert len(cmds) == 1
    remove, create = cmds[0].split(';')
    assert remove.split()[:3] == ['sudo', 'rm', '-rf']
    assert {d.rstrip('/') for d in remove.split()[3:]} == {'./victoria', './victoria-dense', './victoria-legacy'}
    assert create.split()[0] == 'mkdir'
    assert {d.rstrip('/') for d in create.split()[1:]} == {'./victoria', './victoria-dense'}

    # After the services were stopped
    down = next(i for i, cmd in enumerate(install_log) if 'compose down' in cmd)
    assert down < install_log.index(cmds[0])

    assert 'check_legacy_movable' not in install_log
    assert install_log.count('make_shared_compose') == 1
    assert_no_migrate_hint(m_info)


def test_install_history_not_kept_legacy(
    install_log: List[str], m_confirm: Mock, m_file_exists: Mock, m_is_mount: Mock, m_info: Mock
):
    """Nothing is moved: a mount point does not stop the install"""
    m_file_exists.add_existing_files('./victoria/')
    m_is_mount.return_value = True
    m_confirm.side_effect = prompt_answers({'Victoria': False})

    invoke(install.install)

    assert not any(cmd.startswith('mv ') for cmd in install_log)
    assert 'check_legacy_movable' not in install_log
    assert len(history_cmds(install_log)) == 1
    assert_no_migrate_hint(m_info)


def test_install_keep_legacy(
    install_log: List[str], m_confirm: Mock, m_file_exists: Mock, m_setenv: Mock, m_info: Mock
):
    """Kept history of before 0.12.0 is moved to ./victoria-legacy, as the update does"""
    m_file_exists.add_existing_files('./docker-compose.yml', './redis/', './victoria/')
    m_confirm.return_value = True

    invoke(install.install)

    log = install_log
    # Checked before anything changes
    assert log.index('check_legacy_movable') < log.index('make_brewblox_config')
    assert log.count('check_legacy_movable') == 1

    # Moved once the services are stopped (check_ports), and before any configuration can open it
    move = log.index('mv ./victoria ./victoria-legacy')
    create = log.index('mkdir -p ./victoria/ ./victoria-dense/')
    assert log.index('check_ports') < move < log.index('make_dotenv') < log.index('make_shared_compose') < create
    assert history_cmds(log) == ['mv ./victoria ./victoria-legacy', 'mkdir -p ./victoria/ ./victoria-dense/']
    # One render, with the legacy database
    assert log.count('make_shared_compose') == 1

    m_setenv.assert_called_once_with(const.ENV_KEY_CFG_VERSION, const.CFG_VERSION)

    # The hint follows 'All done!'
    msgs = info_msgs(m_info)
    done = msgs.index('All done!')
    hint = next(i for i, msg in enumerate(msgs) if migration.MIGRATE_CMD in msg)
    assert done < hint
    assert any(const.VICTORIA_LEGACY_DIR in msg for msg in msgs[done:])
    # The kept datastore may hold an earlier migration
    assert f'    {migration.DISCARD_CMD}' in msgs[done:]


@pytest.mark.parametrize(
    'dirs',
    [
        ['./victoria/', './victoria-dense/'],
        ['./victoria/', './victoria-dense/', './victoria-legacy/'],
        ['./victoria-legacy/'],
        ['./victoria-dense/'],
    ],
)
def test_install_keep_dense_setup(
    install_log: List[str], m_confirm: Mock, m_file_exists: Mock, m_info: Mock, dirs: List[str]
):
    """Kept history of 0.12.0 stays where it is"""
    m_file_exists.add_existing_files(*dirs)
    m_confirm.return_value = True

    invoke(install.install)

    assert 'check_legacy_movable' not in install_log
    assert history_cmds(install_log) == ['mkdir -p ./victoria/ ./victoria-dense/']
    assert install_log.count('make_shared_compose') == 1
    assert_no_migrate_hint(m_info)


@pytest.mark.parametrize('mount, symlink', [(True, False), (False, True)])
def test_install_keep_legacy_not_movable(
    install_log: List[str],
    m_actions: Mock,
    m_confirm: Mock,
    m_file_exists: Mock,
    m_is_mount: Mock,
    m_is_symlink: Mock,
    m_setenv: Mock,
    mount: bool,
    symlink: bool,
):
    """The install stops before it changes anything"""
    m_file_exists.add_existing_files('./victoria/')
    m_is_mount.return_value = mount
    m_is_symlink.return_value = symlink
    # Keep the files, but do not continue with a symbolic link
    m_confirm.side_effect = prompt_answers({'continue': False})

    invoke(install.install, _err=SystemExit)

    assert install_log == ['check_legacy_movable']
    m_actions.make_brewblox_config.assert_not_called()
    m_setenv.assert_not_called()


def test_install_keep_legacy_symlink(install_log: List[str], m_confirm: Mock, m_file_exists: Mock, m_is_symlink):
    """The user may choose to move a symbolic link"""
    m_file_exists.add_existing_files('./victoria/')
    m_is_symlink.return_value = True
    m_confirm.return_value = True

    invoke(install.install)

    assert 'mv ./victoria ./victoria-legacy' in install_log


@pytest.mark.parametrize(
    'legacy, keep_redis, hint',
    [
        (True, True, True),
        (True, False, False),  # A new datastore holds no migration
        (False, True, False),  # No migration was unfinished without its legacy history
    ],
)
def test_install_wipe_history_keep_datastore(
    install_log: List[str], m_confirm: Mock, m_file_exists: Mock, m_info: Mock, legacy: bool, keep_redis: bool, hint
):
    """A kept datastore may hold a migration whose legacy history the install removes"""
    dirs = ['./redis/', './victoria/', './victoria-dense/'] + (['./victoria-legacy/'] if legacy else [])
    m_file_exists.add_existing_files(*dirs)
    m_confirm.side_effect = prompt_answers({'Victoria': False, 'Redis': keep_redis})

    invoke(install.install)

    msgs = info_msgs(m_info)
    assert (f'    {migration.DISCARD_CMD}' in msgs) is hint
    assert migration.MIGRATE_CMD not in ' '.join(m for m in msgs if 'discard' not in m)
