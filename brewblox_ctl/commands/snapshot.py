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
        raise ValueError('`{}` is not a Brewblox directory'.format(dir))

    if utils.path_exists(file):
        if force or utils.confirm('`{}` already exists. '.format(file) +
                                  'Do you want to overwrite it?'):
            sh('rm -f {}'.format(file))
        else:
            return

    basedir = path.basename(dir)
    parent = dir + '/..'
    sh('sudo tar -C {} -czf {} {}'.format(parent, file, basedir))
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
            raise FileExistsError('`{}` is not a Brewblox directory.'.format(dir))
        if force or utils.confirm('`{}` already exists. '.format(dir) +
                                  'Do you want to continue and erase its content?'):
            # we'll do the actual rm after unpacking files
            utils.info('Contents of `{}` will be removed'.format(dir))
        else:
            return

    with TemporaryDirectory() as tmpdir:
        utils.info('Extracting snapshot to {} directory...'.format(dir))
        sh('tar -xzf {} -C {}'.format(file, tmpdir))
        content = listdir(tmpdir)
        if utils.ctx_opts().dry_run:
            content = ['brewblox']
        if len(content) != 1:
            raise ValueError('Multiple files found in snapshot: {}'.format(content))
        sh('mkdir -p {}'.format(dir))
        sh('sudo rm -rf {}/*'.format(dir))
        # We need to explicitly include dotfiles in the mv glob
        src = '{}/{}'.format(tmpdir, content[0])
        sh('mv {}/.[!.]* {}/* {}/'.format(src, src, dir))
