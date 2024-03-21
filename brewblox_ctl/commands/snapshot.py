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
@click.option('--file',
              help='Snapshot file',
              default='../brewblox-snapshot.tar.gz')
@click.option('--force',
              is_flag=True,
              help='Remove previous tarfile if it exists')
def save(file, force):
    """Save Brewblox directory to snapshot.

    This can be used to move Brewblox installations between hosts.
    To load the snapshot, use `brewblox-ctl install --snapshot ARCHIVE`
    or `brewblox-ctl snapshot load --file ARCHIVE`

    Block data stored on Spark controllers is not included in the snapshot.
    """
    utils.check_config()
    utils.confirm_mode()
    dir = Path('./').resolve()

    if utils.file_exists(file):
        if force or utils.confirm(f'`{file}` already exists. ' +
                                  'Do you want to overwrite it?'):
            utils.sh(f'rm -f {file}')
        else:
            return

    with utils.downed_services():
        utils.sh(f'sudo tar -C {dir.parent} --exclude .venv -czf {file} {dir.name}')
        click.echo(Path(file).resolve())


@snapshot.command()
@click.option('--file',
              help='Snapshot file',
              default='../brewblox-snapshot.tar.gz')
def load(file):
    """Create Brewblox directory from snapshot.

    This can be used to move Brewblox installations between hosts.
    To create a snapshot, use `brewblox-ctl snapshot save`
    """
    utils.check_config()
    utils.confirm_mode()
    dir = Path('./').resolve()

    with TemporaryDirectory() as tmpdir:
        utils.info(f'Extracting snapshot to {dir} directory ...')
        utils.sh(f'tar -xzf {file} -C {tmpdir}')
        content = list(Path(tmpdir).iterdir())
        if utils.get_opts().dry_run:
            content = ['brewblox']
        if len(content) != 1:
            raise ValueError(f'Multiple files found in snapshot: {content}')
        utils.sh('sudo rm -rf ./*')
        # We need to explicitly include dotfiles in the mv glob
        src = content[0]
        utils.sh(f'mv {src}/.[!.]* {src}/* {dir}/')
        utils.get_config.cache_clear()

    actions.install_ctl_package(download='missing')
