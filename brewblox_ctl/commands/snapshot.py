"""
Brewblox-ctl snapshot commands
"""

import re
from datetime import datetime
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


def validate_name(ctx, param, value):
    if not re.match(r'^[^<>:;,?"*|/]+$', value):
        raise click.BadParameter('Invalid file name')
    return value


@snapshot.command()
@click.option('--name',
              help='Snapshot name.',
              default='brewblox-snapshot',
              callback=validate_name)
@click.option('--timestamp/--no-timestamp',
              is_flag=True,
              help='Add timestamp to snapshot file name.',
              default=True)
@click.option('--output-dir',
              help='Output directory',
              default='..')
@click.option('--force',
              is_flag=True,
              help='Remove previous tarfile if it exists.')
@click.option('--history/--no-history',
              is_flag=True,
              help='Include history data. Snapshots without history are much smaller.',
              default=True)
def save(name, timestamp, output_dir, force, history):
    """Save Brewblox directory to snapshot.

    This can be used to move Brewblox installations between hosts.
    To load the snapshot, use `brewblox-ctl install --snapshot ARCHIVE`
    or `brewblox-ctl snapshot load --file ARCHIVE`
    """
    utils.check_config()
    utils.confirm_mode()
    cwd = Path('.').resolve()

    if timestamp:
        name += datetime.now().strftime('-%Y%m%d-%H%M')

    file = Path(output_dir) / f'{name}.tar.gz'
    file = file.resolve()

    if utils.path_exists(file):
        if force or utils.confirm(f'`{file}` already exists. ' +
                                  'Do you want to overwrite it?'):
            sh(f'rm -f {file}')
        else:
            return

    excluded = [
        # Installed Python packages are not portable between CPU platforms
        f'{cwd.name}/.venv',
        # Exclude obsolete database data
        f'{cwd.name}/influxdb*',
        f'{cwd.name}/couchdb*',
    ]

    if not history:
        excluded.append(f'{cwd.name}/victoria/*')

    exclude_args = ' '.join([f'--exclude {s}' for s in excluded])

    sh(f'sudo tar -C {cwd.parent} {exclude_args} -czf {file} {cwd.name}')
    click.echo(file)


@snapshot.command()
@click.argument('file', type=click.Path(exists=True, dir_okay=False, writable=False))
def load(file):
    """Create Brewblox directory from snapshot.

    This can be used to move Brewblox installations between hosts.
    To create a snapshot, use `brewblox-ctl snapshot save`
    """
    utils.check_config()
    utils.confirm_mode()
    dir = Path('./').resolve()

    with TemporaryDirectory() as tmpdir:
        utils.info(f'Extracting snapshot to {dir} directory...')
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
