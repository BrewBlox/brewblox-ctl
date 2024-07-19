"""
Logs system status and debugging info to file
"""

import math
import shlex
from pathlib import Path

import click

from brewblox_ctl import actions, click_helpers, const, discovery, utils


def create():
    utils.sh('echo "BREWBLOX DIAGNOSTIC DUMP" > brewblox.log')


def append(s):
    utils.sh(s + ' >> brewblox.log 2>&1', check=False)


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
              help='Include or omit docker compose config files in the generated log.')
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
        - Append software version info.
        - Append user config.
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

    # Add version info
    utils.info('Writing software version info ...')
    header('Versions')
    append('uname -a')
    append('python3 --version')
    append(f'{sudo}docker --version')
    append(f'{sudo}docker compose version')

    # Add config
    # Exclude potentially sensitive fields
    utils.info('Writing config ...')
    header('Config')
    content = utils.get_config().model_dump_json(indent=2,
                                                 exclude={'environment'},
                                                 exclude_defaults=True)
    append(f"echo '{content}'")

    # Add active containers
    utils.info('Writing active containers ...')
    header('Containers')
    append(f'{sudo}docker compose ps -a')

    # Add service logs
    try:
        config_names = list(utils.read_compose()['services'].keys())
        shared_names = list(utils.read_shared_compose()['services'].keys())
        names = [n for n in config_names if n not in shared_names] + shared_names
        for name in names:
            utils.info(f'Writing {name} service logs ...')
            header(f'Service: {name}')
            append(f'{sudo}docker compose logs --timestamps --no-color --tail 200 {name}')
    except Exception as ex:
        append('echo ' + shlex.quote(type(ex).__name__ + ': ' + str(ex)))

    # Add compose config
    if add_compose:
        utils.info('Writing docker compose configuration ...')
        header('docker-compose.yml')
        append('cat docker-compose.yml')
        header('docker-compose.shared.yml')
        append('cat docker-compose.shared.yml')
    else:
        utils.info('Skipping docker compose configuration ...')

    # Add blocks
    host_url = utils.host_url()
    services = utils.list_services('ghcr.io/brewblox/brewblox-devcon-spark')
    for svc in services:
        utils.info(f'Writing {svc} blocks ...')
        header(f'Blocks: {svc}')
        append(f'{const.CURL} -X POST {host_url}/{svc}/blocks/all/read | python3 -m json.tool')

    # Add system diagnostics
    if add_system:
        utils.info('Writing system diagnostics ...')
        header('docker info')
        append(f'{sudo}docker info')
        header('journalctl -u docker')
        append('sudo journalctl -u docker | tail -100')
        header('journalctl -u avahi-daemon')
        append('sudo journalctl -u avahi-daemon | tail -100')
        header('disk usage')
        append('df -hl')
        header('/var/log/syslog')
        append('sudo tail -n 500 /var/log/syslog')
        header('dmesg')
        append('dmesg -T')
    else:
        utils.info('Skipping system diagnostics ...')

    # Upload
    if upload:
        click.echo(actions.file_netcat('termbin.com', 9999, Path('./brewblox.log')).decode())
    else:
        utils.info('Skipping upload. If you want to manually upload the log, run: ' +
                   click.style('brewblox-ctl termbin ./brewblox.log', fg='green'))


@cli.command()
@click.option('--upload/--no-upload',
              default=True,
              help='Whether to upload the core dump file to termbin.com.')
def coredump(upload):
    """Read and upload a core dump file for the Spark 4.

    This requires the Spark to be connected over USB.
    Not compatible with the Spark 2 or 3.

    If the Spark 4 crashes, it stores what it was doing at the time of the crash.
    This command exports and uploads this data.

    The `esptool` python package is required, and will be installed if not found.
    """
    actions.start_esptool('--chip esp32',
                          '--baud 115200',
                          'read_flash 0xA10000 81920',
                          'coredump.bin')
    utils.sh('base64 coredump.bin > coredump.b64')

    if upload:
        click.echo(actions.file_netcat('termbin.com', 9999, Path('./coredump.b64')).decode())
    else:
        utils.info('Skipping upload. If you want to manually upload the file, run: ' +
                   click.style('brewblox-ctl termbin ./coredump.b64', fg='green'))


@cli.command()
def monitor():
    """Connect to a Spark 4, and monitor its logs.

    This requires the Spark to be connected over USB.
    Not compatible with the Spark 2 or 3.
    """
    dev_tty = next(discovery.discover_esp_spark_tty(), None)

    if not dev_tty:
        utils.warn('No Spark 4 detected')
        return

    utils.info(f'Connecting to {dev_tty} ...')
    utils.sh(f'sudo -E env "PATH=$PATH" pyserial-miniterm --raw {dev_tty} 115200')


@cli.command()
@click.argument('file')
def termbin(file):
    """Upload text file to termbin, and get a shareable URL.

    Files are available for limited duration on termbin.com,
    and anyone with the link can view them.
    """
    click.echo(actions.file_netcat('termbin.com', 9999, Path(file)).decode())
