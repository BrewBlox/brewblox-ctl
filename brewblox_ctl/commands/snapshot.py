"""
Brewblox-ctl snapshot commands
"""

from pathlib import Path
from tempfile import TemporaryDirectory

import click

from brewblox_ctl import actions, click_helpers, utils
from brewblox_ctl.utils import sh


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
    sudo = utils.optsudo()
    dir = Path('./').resolve()

    if utils.path_exists(file):
        if force or utils.confirm(f'`{file}` already exists. ' +
                                  'Do you want to overwrite it?'):
            sh(f'rm -f {file}')
        else:
            return

    running = utils.has_running_containers()

    if running:
        sh(f'{sudo}docker compose stop')

    sh(f'sudo tar -C {dir.parent} --exclude .venv -czf {file} {dir.name}')
    click.echo(Path(file).resolve())

    if running:
        sh(f'{sudo}docker compose start')


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
        sh(f'tar -xzf {file} -C {tmpdir}')
        content = list(Path(tmpdir).iterdir())
        if utils.ctx_opts().dry_run:
            content = ['brewblox']
        if len(content) != 1:
            raise ValueError(f'Multiple files found in snapshot: {content}')
        sh('sudo rm -rf ./*')
        # We need to explicitly include dotfiles in the mv glob
        src = content[0]
        sh(f'mv {src}/.[!.]* {src}/* {dir}/')

    actions.install_ctl_package(download='missing')
