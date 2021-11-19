"""
Logs system status and debugging info to file
"""

import math
import shlex
from pathlib import Path

import click
from brewblox_ctl import click_helpers, const, sh, utils

ENV_KEYS = [
    const.RELEASE_KEY,
    const.CFG_VERSION_KEY,
    const.HTTP_PORT_KEY,
    const.HTTPS_PORT_KEY,
    const.MQTT_PORT_KEY,
    const.COMPOSE_FILES_KEY,
    const.COMPOSE_PROJECT_KEY,
]


def create():
    sh('echo "BREWBLOX DIAGNOSTIC DUMP" > brewblox.log')


def append(s):
    sh(s + ' >> brewblox.log 2>&1', check=False)


def header(s):
    decorate_len = 120 - len(s)
    decorate_start = '+' * math.ceil(decorate_len / 2)
    decorate_end = '+' * math.floor(decorate_len / 2)
    append(f'echo "\\n{decorate_start} {s} {decorate_end}\\n"')


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Top-level commands"""


@cli.command()
@click.option('--add-compose/--no-add-compose',
              default=True,
              help='Include or omit docker-compose config files in the generated log.')
@click.option('--add-system/--no-add-system',
              default=True,
              help='Include or omit system diagnostics in the generated log.')
@click.option('--upload/--no-upload',
              default=True,
              help='Whether to upload the log file to termbin.com.')
def log(add_compose, add_system, upload):
    """Generate and share log file for bug reports.

    This command generates a comprehensive report on current system state and logs.
    When reporting bugs, a termbin blink to the output is often the first thing asked for.

    For best results, run when the services are still active.
    Service logs are discarded after `brewblox-ctl down`.

    Care is taken to prevent accidental leaks of confidential information.
    Only known variables are read from .env,
    and the `--no-add-compose` flag allows skipping compose configuration.
    The latter is useful if the configuration contains passwords or tokens.

    To review or edit the output, use the `--no-upload` flag.
    The output will include instructions on how to manually upload the file.

    \b
    Steps:
        - Create ./brewblox.log file.
        - Append Brewblox .env variables.
        - Append software version info.
        - Append service logs.
        - Append content of docker-compose.yml (optional).
        - Append content of docker-compose.shared.yml (optional).
        - Append blocks from Spark services.
        - Append system diagnostics.
        - Upload file to termbin.com for shareable link (optional).
    """
    utils.check_config()
    utils.confirm_mode()
    sudo = utils.optsudo()

    # Create log
    utils.info(f"Log file: {Path('./brewblox.log').resolve()}")
    create()
    append('date')

    # Add .env values
    utils.info('Writing Brewblox .env values...')
    header('.env')
    for key in ENV_KEYS:
        append(f'echo "{key}={utils.getenv(key)}"')

    # Add version info
    utils.info('Writing software version info...')
    header('Versions')
    append('uname -a')
    append('python3 --version')
    append(f'{sudo}docker --version')
    append(f'{sudo}docker-compose --version')

    # Add active containers
    utils.info('Writing active containers...')
    header('Containers')
    append(f'{sudo}docker-compose ps -a')

    # Add service logs
    try:
        config_names = list(utils.read_compose()['services'].keys())
        shared_names = list(utils.read_shared_compose()['services'].keys())
        names = [n for n in config_names if n not in shared_names] + shared_names
        for name in names:
            utils.info(f'Writing {name} service logs...')
            header(f'Service: {name}')
            append(f'{sudo}docker-compose logs --timestamps --no-color --tail 200 {name}')
    except Exception as ex:
        append('echo ' + shlex.quote(type(ex).__name__ + ': ' + str(ex)))

    # Add compose config
    if add_compose:
        utils.info('Writing docker-compose configuration...')
        header('docker-compose.yml')
        append('cat docker-compose.yml')
        header('docker-compose.shared.yml')
        append('cat docker-compose.shared.yml')
    else:
        utils.info('Skipping docker-compose configuration...')

    # Add blocks
    host_url = utils.host_url()
    services = utils.list_services('brewblox/brewblox-devcon-spark')
    for svc in services:
        utils.info(f'Writing {svc} blocks...')
        header(f'Blocks: {svc}')
        append(f'{const.CLI} http post --pretty {host_url}/{svc}/blocks/all/read')

    # Add system diagnostics
    if add_system:
        utils.info('Writing system diagnostics...')
        header('docker info')
        append(f'{sudo}docker info')
        header('disk usage')
        append('df -hl')
        header('/proc/net/dev')
        append('column -t /proc/net/dev')
        header('/var/log/syslog')
        append('sudo tail -n 500 /var/log/syslog')
        header('dmesg')
        append('dmesg -T')
    else:
        utils.info('Skipping system diagnostics...')

    # Upload
    if upload:
        click.echo(utils.file_netcat('termbin.com', 9999, Path('./brewblox.log')).decode())
    else:
        utils.info('Skipping upload. If you want to manually upload the log, run: ' +
                   click.style('brewblox-ctl termbin ./brewblox.log', fg='green'))


@cli.command()
@click.argument('file')
def termbin(file):
    click.echo(utils.file_netcat('termbin.com', 9999, Path(file)).decode())
