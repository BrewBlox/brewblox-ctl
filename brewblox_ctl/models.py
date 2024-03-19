from typing import Dict, Optional

from pydantic import BaseModel, Field


class ComposeConfig(BaseModel):
    version: str = '3.7'
    project: str = 'brewblox'
    file: str = 'docker-compose.shared.yml:docker-compose.yml'


class PortConfig(BaseModel):
    http: int = 80
    https: int = 443
    mqtt: int = 1883
    mqtts: int = 8883
    admin: int = 9600


class AvahiConfig(BaseModel):
    enabled: bool = True
    reflection: bool = True


class SystemConfig(BaseModel):
    apt_upgrade: bool = True


class AuthConfig(BaseModel):
    enabled: bool = False


class TraefikConfig(BaseModel):
    tls: bool = True
    static_config_file: str = '/config/traefik.yml'
    dynamic_config_dir: str = '/config/dynamic'


class VictoriaConfig(BaseModel):
    retention: str = '100y'
    search_latency: str = '10s'


class CtlConfig(BaseModel):
    release: str = Field(default='edge',
                         title='Brewblox release track',
                         description='This determines download tags for Docker and brewblox-ctl')

    ctl_release: Optional[str] = Field(default=None,
                                       title='brewblox-ctl release track',
                                       description='The release track for brewblox-ctl itself. ' +
                                       'If not set, `release` is used.')

    skip_confirm: bool = Field(default=False,
                               title='Automatically skip confirmation prompts',
                               description='brewblox-ctl prompts whenever a command makes a persistent change, '
                               'unless the `-y` option is used, or `skip_confirm` is true.')

    debug: bool = Field(default=False,
                        title='Run brewblox-ctl in debug mode',
                        description='Show stack traces on error, and print additional information in commands.')

    environment: Dict[str, str] = Field(default_factory=dict,
                                        title='Custom environment settings',
                                        description='They will be inserted in the .env file')

    # Nested configuration

    ports: PortConfig = Field(default_factory=PortConfig,
                              title='Network ports exposed by the Traefik reverse proxy',
                              description='Ports can be remapped if they conflict with other applications.')

    compose: ComposeConfig = Field(default_factory=ComposeConfig,
                                   title='Configuration options for Docker Compose')

    avahi: AvahiConfig = Field(default_factory=AvahiConfig,
                               title='Configuration options for the Avahi daemon',
                               description='Avahi is used for mDNS discovery')

    system: SystemConfig = Field(default_factory=SystemConfig,
                                 title='Generic system options')

    auth: AuthConfig = Field(default_factory=AuthConfig,
                             title='Configuration options for the authentication service',
                             description='When enabled, all incoming HTTP request must carry an authentication token')

    traefik: TraefikConfig = Field(default_factory=TraefikConfig,
                                   title='Configuration options for the Traefik reverse proxy',
                                   description='Traefik forwards incoming HTTP requests to the relevant service')

    victoria: VictoriaConfig = Field(default_factory=VictoriaConfig,
                                     title='Configuration options for the Victoria Metrics time-series database',
                                     description='History data for graphs is stored here.')


class CtlOpts(BaseModel):
    dry_run: bool = False
    quiet: bool = False
    verbose: bool = False
    yes: bool = False
    color: bool = False
