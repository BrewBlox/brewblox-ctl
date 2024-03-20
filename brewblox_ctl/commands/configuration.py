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


@configuration.command()
def inspect():
    utils.check_config()

    config = utils.get_config()
    click.secho(utils.dump_yaml(format_model(config)))


@configuration.command()
def generate():
    utils.check_config()
    utils.confirm_mode()

    with utils.downed_services():
        version = utils.getenv(const.ENV_KEY_CFG_VERSION, const.CFG_VERSION)
        actions.make_dotenv(version)
        actions.make_config_dirs()
        actions.make_tls_certificates()
        actions.make_traefik_config()
        actions.make_shared_compose()
        actions.make_compose()
        actions.make_udev_rules()
        actions.make_ctl_wrapper()
        actions.edit_avahi_config()
