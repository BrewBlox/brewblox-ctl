"""
Implementation of brewblox-ctl setup
"""

import re
from pathlib import Path

import click
from brewblox_ctl import click_helpers, sh
from brewblox_ctl import const, utils


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Command collector"""


def check_ports():
    if utils.path_exists('./docker-compose.yml'):
        utils.info('Stopping services...')
        sh(f'{utils.optsudo()}docker-compose down')

    ports = [
        utils.getenv(key, const.ENV_DEFAULTS[key]) for key in [
            const.HTTP_PORT_KEY,
            const.HTTPS_PORT_KEY,
            const.MQTT_PORT_KEY,
        ]]

    utils.info('Checking ports...')
    retv = sh('sudo netstat -tulpn', capture=True)
    lines = retv.split('\n')

    used_ports = []
    used_lines = []
    for port in ports:
        for line in lines:
            if re.match(r'.*(:::|0.0.0.0:){}\s.*'.format(port), line):
                used_ports.append(port)
                used_lines.append(line)
                break

    if used_ports:
        port_str = ', '.join(used_ports)
        utils.warn(f'Port(s) {port_str} already in use.')
        utils.warn('Run `brewblox-ctl service ports` to configure Brewblox ports.')
        for line in used_lines:
            utils.warn(line)
        if not utils.confirm('Do you want to continue?'):
            raise SystemExit(1)


@cli.command()
@click.option('--dir',
              default='./traefik',
              help='Target directory for generated certs.')
@click.option('--release',
              default=None,
              help='Brewblox release track.')
def makecert(dir, release):
    """Generate a self-signed SSL certificate.

    \b
    Steps:
        - Create directory if it does not exist.
        - Create brewblox.crt and brewblox.key files.
    """
    utils.confirm_mode()
    sudo = utils.optsudo()
    tag = utils.docker_tag(release)
    absdir = Path(dir).absolute()
    sh(f'mkdir -p "{absdir}"')
    sh(f'{sudo}docker run' +
        ' --rm --privileged' +
        ' --pull always' +
        f' -v "{absdir}":/certs/' +
        f' brewblox/omgwtfssl:{tag}')
    sh(f'sudo chmod 644 "{absdir}/brewblox.crt"')
    sh(f'sudo chmod 600 "{absdir}/brewblox.key"')


@cli.command()
@click.pass_context
@click.option('--port-check/--no-port-check',
              default=True,
              help='Check whether ports are already in use')
@click.option('--avahi-config/--no-avahi-config',
              default=True,
              help='Update Avahi config to enable mDNS discovery')
@click.option('--pull/--no-pull',
              default=True,
              help='Pull docker service images.')
def setup(ctx, avahi_config, pull, port_check):
    """Run first-time setup in Brewblox directory.

    Run after brewblox-ctl install, in the newly created Brewblox directory.
    This will create all required configuration files for your system.

    You can safely use this command to partially reset your system.
    Before making any changes, it will check for existing files,
    and prompt if any are found. It will do so separately for docker-compose,
    datastore, history, and gateway files.
    Choose to skip any, and the others will still be created and configured.

    \b
    Steps:
        - Check whether files already exist.
        - Set .env values.
        - Update avahi-daemon config.                (Optional)
        - Create docker-compose configuration files. (Optional)
        - Pull docker images.                        (Optional)
        - Create datastore (Redis) directory.        (Optional)
        - Create history (Victoria) directory.       (Optional)
        - Create gateway (Traefik) directory.        (Optional)
        - Create SSL certificates.                   (Optional)
        - Start and configure services.              (Optional)
        - Stop all services.
        - Set version number in .env.
    """
    utils.check_config()
    utils.confirm_mode()

    sudo = utils.optsudo()

    if port_check:
        check_ports()

    skip_compose = \
        utils.path_exists('./docker-compose.yml') \
        and utils.confirm('This directory already contains a docker-compose.yml file. ' +
                          'Do you want to keep it?')

    skip_datastore = \
        utils.path_exists('./redis/') \
        and utils.confirm('This directory already contains Redis datastore files. ' +
                          'Do you want to keep them?')

    skip_history = \
        utils.path_exists('./victoria/') \
        and utils.confirm('This directory already contains Victoria history files. ' +
                          'Do you want to keep them?')

    skip_gateway = \
        utils.path_exists('./traefik/') \
        and utils.confirm('This directory already contains Traefik gateway files. ' +
                          'Do you want to keep them?')

    skip_eventbus = \
        utils.path_exists('./mosquitto/') \
        and utils.confirm('This directory already contains Mosquitto config files. ' +
                          'Do you want to keep them?')

    utils.info('Setting .env values...')
    for key, default_val in const.ENV_DEFAULTS.items():
        utils.setenv(key, utils.getenv(key, default_val))

    if avahi_config:
        utils.update_avahi_config()

    utils.info('Copying docker-compose.shared.yml...')
    sh(f'cp -f {const.CONFIG_DIR}/docker-compose.shared.yml ./')

    if not skip_compose:
        utils.info('Copying docker-compose.yml...')
        sh(f'cp -f {const.CONFIG_DIR}/docker-compose.yml ./')

    # Stop and pull after we're sure we have a compose file
    utils.info('Stopping services...')
    sh(f'{sudo}docker-compose down')

    if pull:
        utils.info('Pulling docker images...')
        sh(f'{sudo}docker-compose pull')

    if not skip_datastore:
        utils.info('Creating datastore directory...')
        sh('sudo rm -rf ./redis/; mkdir ./redis/')

    if not skip_history:
        utils.info('Creating history directory...')
        sh('sudo rm -rf ./victoria/; mkdir ./victoria/')

    if not skip_gateway:
        utils.info('Creating gateway directory...')
        sh('sudo rm -rf ./traefik/; mkdir ./traefik/')

        utils.info('Creating SSL certificate...')
        ctx.invoke(makecert)

    if not skip_eventbus:
        utils.info('Creating mosquitto config directory...')
        sh('sudo rm -rf ./mosquitto/; mkdir ./mosquitto/')

    # Always copy cert config to traefik dir
    sh(f'cp -f {const.CONFIG_DIR}/traefik-cert.yaml ./traefik/')

    # Setup is complete and ok - now set CFG version
    utils.setenv(const.CFG_VERSION_KEY, const.CURRENT_VERSION)
    utils.info('All done!')
