"""
Tools to manually generate and inspect managed configuration.
"""

from typing import Any, Dict, Tuple

import click
from pydantic import BaseModel

from brewblox_ctl import actions, click_helpers, const, utils

PROP_ORDER = [
    'title',
    'description',
    'type',
    'items',
    'anyOf',
    'value',
    'default',
]


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Command collector"""


@cli.group(name='config')
def configuration():
    """Generate and inspect managed configuration."""


def sort_prop(item: Tuple[str, Any]):
    try:
        return PROP_ORDER.index(item[0])
    except ValueError:
        return len(PROP_ORDER)


def format_model(model: BaseModel) -> Dict[str, Any]:
    schema = model.model_json_schema()
    props = schema['properties']
    for key, value in model.model_dump().items():
        model_value = getattr(model, key)

        # Recurse if property is a nested model
        if isinstance(model_value, BaseModel):
            props[key] = format_model(model_value)
        else:
            props[key]['value'] = value

        # Sort fields in each prop to improve output readability
        props[key] = dict(sorted(props[key].items(), key=sort_prop))

    return props


def print_formatted(data: dict, depth: int = 0):
    opts = utils.get_opts()
    prefix = ' ' * depth
    for key, value in data.items():
        # skipped fields
        if key in ('additionalProperties',):
            continue

        # nested fields
        if isinstance(value, dict):
            if key == 'value':
                click.secho(f'{prefix}{key}', fg='blue', color=opts.color)
            else:
                click.secho(f'{prefix}{key}', fg='cyan', bold=True, color=opts.color)
            print_formatted(value, depth + 4)
            click.secho('')

        # special case for union types
        elif key == 'anyOf':
            click.secho(f'{prefix}type: ', nl=False, fg='blue', color=opts.color)
            types = [obj.get('type') for obj in value]
            click.secho(' | '.join(types))

        elif key in ('title', 'description'):
            click.secho(f'{prefix}{value}', fg='bright_black', color=opts.color)

        # value type
        else:
            click.secho(f'{prefix}{key}: ', nl=False, fg='blue', color=opts.color)

            if value is None:
                click.secho('null')
            elif key in ('value', 'default') and isinstance(value, str):
                click.secho(f'"{value}"')
            else:
                click.secho(f'{value}')


@configuration.command()
def inspect():
    """
    Print all available settings for brewblox.yml.
    """
    utils.check_config()

    config = utils.get_config()
    data = format_model(config)
    print_formatted(data)
    # click.secho(utils.dump_yaml(format_model(config)))


@configuration.command()
def apply():
    """
    Use brewblox.yml to generate configuration files.
    """
    utils.check_config()
    utils.confirm_mode()

    with utils.downed_services():
        if not utils.file_exists(const.CONFIG_FILE):
            actions.make_brewblox_config(utils.get_config())

        version = utils.getenv(const.ENV_KEY_CFG_VERSION, const.CFG_VERSION)
        actions.make_dotenv(version)
        actions.make_config_dirs()
        actions.make_tls_certificates()
        actions.make_traefik_config()
        actions.make_shared_compose()
        actions.make_compose()
        actions.make_udev_rules()
        actions.make_ctl_entrypoint()
        actions.edit_avahi_config()
