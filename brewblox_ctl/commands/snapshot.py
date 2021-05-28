"""
Brewblox-ctl snapshot commands
"""

from os import listdir, path
from tempfile import TemporaryDirectory

import click
from brewblox_ctl import click_helpers, utils
from brewblox_ctl.utils import sh


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Command collector"""


@cli.group()
def snapshot():
    """Save or load snapshots."""


@snapshot.command()
@click.option('--dir',
              help='Brewblox directory')
@click.option('--file',
              help='Snapshot file')
@click.option('--force',
              is_flag=True,
              help='Remove previous tarfile if it exists')
def save(dir, file, force):
    """Save Brewblox directory to snapshot.

    This can be used to move Brewblox installations between hosts.
    To load the snapshot, use `brewblox-ctl install --snapshot ARCHIVE`
    or `brewblox-ctl snapshot load --file ARCHIVE`

    Block data stored on Spark controllers is not included in the snapshot.
    """
    utils.confirm_mode()

    if utils.is_brewblox_cwd():
        dir = dir or '.'
        file = file or '../brewblox.tar.gz'
    else:
        dir = dir or './brewblox'
        file = file or './brewblox.tar.gz'

    dir = path.abspath(dir)

    if not utils.is_brewblox_dir(dir):
        raise ValueError(f'`{dir}` is not a Brewblox directory')

    if utils.path_exists(file):
        if force or utils.confirm(f'`{file}` already exists. ' +
                                  'Do you want to overwrite it?'):
            sh(f'rm -f {file}')
        else:
            return

    basedir = path.basename(dir)
    parent = dir + '/..'
    sh(f'sudo tar -C {parent} -czf {file} {basedir}')
    click.echo(path.abspath(path.expanduser(file)))


@snapshot.command()
@click.option('--dir',
              help='Brewblox directory')
@click.option('--file',
              help='Snapshot file')
@click.option('--force',
              is_flag=True,
              help='Remove directory if it exists')
def load(dir, file, force):
    """Create Brewblox directory from snapshot.

    This can be used to move Brewblox installations between hosts.
    To create a snapshot, use `brewblox-ctl snapshot save`
    """
    utils.confirm_mode()

    if utils.is_brewblox_cwd():
        dir = dir or '.'
        file = file or '../brewblox.tar.gz'
    else:
        dir = dir or './brewblox'
        file = file or './brewblox.tar.gz'

    dir = path.abspath(dir)

    if utils.path_exists(dir) and not utils.is_empty_dir(dir):
        if not utils.is_brewblox_dir(dir):
            raise FileExistsError(f'`{dir}` is not a Brewblox directory.')
        if force or utils.confirm(f'`{dir}` already exists. ' +
                                  'Do you want to continue and erase its content?'):
            # we'll do the actual rm after unpacking files
            utils.info(f'Contents of `{dir}` will be removed')
        else:
            return

    with TemporaryDirectory() as tmpdir:
        utils.info(f'Extracting snapshot to {dir} directory...')
        sh(f'tar -xzf {file} -C {tmpdir}')
        content = listdir(tmpdir)
        if utils.ctx_opts().dry_run:
            content = ['brewblox']
        if len(content) != 1:
            raise ValueError(f'Multiple files found in snapshot: {content}')
        sh(f'mkdir -p {dir}')
        sh(f'sudo rm -rf {dir}/*')
        # We need to explicitly include dotfiles in the mv glob
        src = f'{tmpdir}/{content[0]}'
        sh(f'mv {src}/.[!.]* {src}/* {dir}/')
