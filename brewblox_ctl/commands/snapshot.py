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
              default='./brewblox',
              help='Brewblox directory')
@click.option('--file',
              default='./brewblox.tar.gz',
              help='Snapshot file')
@click.option('--force',
              is_flag=True,
              help='Remove previous tarfile if it exists')
def save(dir, file, force):
    """Save Brewblox directory to snapshot

    This can be used to move Brewblox installations between hosts.
    To load the snapshot, use `brewblox-ctl install --snapshot ARCHIVE`
    or `brewblox-ctl snapshot load --file ARCHIVE`

    Block data stored on Spark controllers is not included in the snapshot.
    """

    if utils.is_brewblox_cwd():
        raise RuntimeError('Please run this command outside a Brewblox directory')

    if not utils.path_exists('{}/docker-compose.yml'.format(dir)):
        raise ValueError('`{}` is not a Brewblox dir'.format(dir))

    if utils.path_exists(file):
        if force:
            sh('rm -f {}'.format(file))
        else:
            raise FileExistsError('The `{}` snapshot already exists'.format(file))

    sh('sudo tar -czf {} {}'.format(file, dir))
    click.echo(path.abspath(path.expanduser(file)))


@snapshot.command()
@click.option('--dir',
              default='./brewblox',
              help='Brewblox directory')
@click.option('--file',
              default='./brewblox.tar.gz',
              help='Snapshot file')
@click.option('--force',
              is_flag=True,
              help='Remove directory if it exists')
def load(dir, file, force):
    """Create Brewblox directory from snapshot.

    This can be used to move Brewblox installations between hosts.
    To create a snapshot, use `brewblox-ctl snapshot save`
    """
    if utils.is_brewblox_cwd():
        raise RuntimeError('Please run this command outside a Brewblox directory')

    if utils.path_exists(dir) and not force:
        raise FileExistsError('The `{}` directory already exists. '.format(dir) +
                              'Please remove it before loading a snapshot, or use the --force option.')

    with TemporaryDirectory() as tmpdir:
        utils.info('Extracting snapshot to {} directory...'.format(dir))
        sh('tar -xzf {} -C {}'.format(file, tmpdir))
        content = listdir(tmpdir)
        if utils.ctx_opts().dry_run:
            content = ['brewblox']
        if len(content) != 1:
            raise ValueError('Multiple files found in snapshot: {}'.format(content))
        sh('rm -rf {}'.format(dir))
        sh('mv {}/{} {}'.format(tmpdir, content[0], dir))
