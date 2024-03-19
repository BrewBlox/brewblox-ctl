"""
Tools to manually generate and inspect managed configuration.
"""

import click
import yaml
from pydantic import BaseModel

from brewblox_ctl import actions, click_helpers, utils


@click.group(cls=click_helpers.OrderedGroup)
def cli():
    """Command collector"""


@cli.group()
def configuration():
    """Generate and inspect managed configuration."""


def format_model(model: BaseModel):
    schema = model.model_json_schema()
    props = schema['properties']
    for key, value in model.model_dump().items():
        model_value = getattr(model, key)
        if isinstance(model_value, BaseModel):
            props[key] = format_model(model_value)
        else:
            props[key]['value'] = value

    return props


@configuration.command()
def inspect():
    config = utils.get_config()
    click.secho(yaml.safe_dump(format_model(config)))


@configuration.command()
def generate():
    actions.generate_config_dirs()
    actions.edit_avahi_config()
    actions.generate_udev_config()
    actions.generate_tls_cert()
    actions.generate_traefik_config()
    actions.generate_compose_config()
