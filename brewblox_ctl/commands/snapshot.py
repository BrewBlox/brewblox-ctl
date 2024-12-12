"""
Brewblox-ctl snapshot commands
"""

from pathlib import Path
from tempfile import TemporaryDirectory

import click

from brewblox_ctl import actions, click_helpers, utils


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Command collector"""


@cli.group()
def snapshot():
    """Save or load snapshots."""


@snapshot.command()
@click.option('--file', help='Snapshot file', default='../brewblox-snapshot.tar.gz')
@click.option('--force', is_flag=True, help='Remove previous tarfile if it exists')
def save(file, force):
    """Save Brewblox directory to snapshot.

    This can be used to move Brewblox installations between hosts.
    To load the snapshot, use `brewblox-ctl install --snapshot ARCHIVE`
    or `brewblox-ctl snapshot load --file ARCHIVE`

    Block data stored on Spark controllers is not included in the snapshot.
    """
    utils.check_config()
    utils.confirm_mode()
    brewblox_dir = Path('./').resolve()

    if utils.file_exists(file):
        if force or utils.confirm(f'`{file}` already exists. ' + 'Do you want to overwrite it?'):
            utils.sh(f'rm -f {file}')
        else:
            return

    with utils.downed_services():
        utils.info(f'Creating snapshot of {brewblox_dir} directory ...')
        utils.info('Generating requirements.txt for snapshot, to restore Python packages at the same version')
        utils.sh(f'uv pip freeze > {brewblox_dir}/requirements.txt')
        utils.info('Creating snapshot tarball')
        utils.sh(f'sudo tar -C {brewblox_dir.parent} --exclude .venv -czf {file} {brewblox_dir.name}')
        utils.sh(f'rm -f {brewblox_dir}/requirements.txt')
        click.echo(Path(file).resolve())


@snapshot.command()
@click.option('--file', help='Snapshot file', default='../brewblox-snapshot.tar.gz')
def load(file):
    """Create Brewblox directory from snapshot.

    This can be used to move Brewblox installations between hosts.
    To create a snapshot, use `brewblox-ctl snapshot save`
    """
    utils.check_config()
    utils.confirm_mode()
    brewblox_dir = Path('./').resolve()

    utils.info(f'Extracting snapshot to {brewblox_dir} directory ...')
    # check that the target directory is empty
    if any(brewblox_dir.iterdir()) and not utils.confirm(
        f'Target directory `{brewblox_dir}` is not empty. Existing files will be deleted. Do you want to continue?'
    ):
        return

    with TemporaryDirectory() as tmpdir:
        utils.sh(f'tar -xzf {file} -C {tmpdir}')
        content = list(Path(tmpdir).iterdir())
        if utils.get_opts().dry_run:
            content = ['brewblox']
        if len(content) != 1:
            err = f'Multiple files found in snapshot: {content}'
            raise ValueError(err)

        utils.sh(f'sudo rm -rf {brewblox_dir}/*')
        # We need to explicitly include dotfiles in the mv glob
        src = content[0]
        utils.sh(f'mv {src}/.[!.]* {src}/* {brewblox_dir}/')

    utils.get_config.cache_clear()
    utils.info('Recreating Python virtual environment')
    utils.sh('uv venv')
    if utils.file_exists('requirements.txt'):
        utils.info('Restoring Python packages from requirements.txt')
        utils.sh('uv pip install -r requirements.txt')
        utils.sh('rm requirements.txt')
    elif utils.file_exists('brewblox-ctl.tar.gz'):
        utils.info('Restoring Python packages from brewlox-ctl.tar.gz')
        utils.sh('uv pip install pip')  # for backwards compaitibility with older brewblox-ctl versions from snapshot
        utils.sh('uv pip install brewblox-ctl.tar.gz')
        utils.sh('rm brewblox-ctl.tar.gz')
    else:
        utils.info(
            'No requirements.txt or brewblox-ctl.tar.gz in snapshot. ' 'Installing default version of brewblox-ctl'
        )
        actions.install_ctl_package()
