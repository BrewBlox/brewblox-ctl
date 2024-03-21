from typing import Dict, Optional

from pydantic import BaseModel, Field


class ComposeConfig(BaseModel):
    project: str = Field(default='brewblox',
                         title='Docker Compose project name',
                         description='If you run multiple Compose projects, they must have unique names.')
    file: str = Field(default='docker-compose.shared.yml:docker-compose.yml',
                      title='A `:`-separated list of files used by Compose to generate configuration. ' +
                      'If multiple files are found, they are merged.')


class PortConfig(BaseModel):
    http: int = Field(default=80,
                      title='External HTTP port',
                      description='HTTP is used by the UI and external REST API requests. ' +
                      'By default, all HTTP requests are redirected to HTTPS.')
    https: int = Field(default=443,
                       title='External HTTPS port',
                       description='HTTPS is HTTP + TLS encryption.')
    mqtt: int = Field(default=1883,
                      title='External MQTT port',
                      description='History data is published over MQTT')
    mqtts: int = Field(default=8883,
                       title='External MQTTS port',
                       description='MQTTS is MQTT + TLS encryption.')
    admin: int = Field(default=9600,
                       title='Admin HTTP port',
                       description='The admin port is only accessible from the server itself.')


class AvahiConfig(BaseModel):
    managed: bool = Field(default=True,
                          title='Enable/disable brewblox-ctl changing the host Avahi configuration')
    reflection: bool = Field(default=True,
                             title='Enable/disable mDNS reflection in host Avahi configuration')


class SystemConfig(BaseModel):
    apt_upgrade: bool = Field(default=True,
                              title='Enable/disable updating Apt packages during updates')


class AuthConfig(BaseModel):
    enabled: bool = Field(default=False,
                          title='Enable/disable the Authentication service',
                          description='When enabled, users need to login before using the UI.')


class TraefikConfig(BaseModel):
    tls: bool = Field(default=True,
                      title='Enable/disable TLS termination for the HTTPS/MQTTS ports',
                      description='This can be disabled when TLS termination is handled by another proxy.')
    static_config_file: str = Field(default='/config/traefik.yml',
                                    title='Path to the static Traefik configuration file',
                                    description='This is the path inside the `traefik` service. ' +
                                    'Change this setting to use custom configuration ' +
                                    'that will not be reset during updates.')
    dynamic_config_dir: str = Field(default='/config/dynamic',
                                    title='Path to the directory containing dynamic Traefik configuration files',
                                    description='This is the path inside the `traefik` service. ' +
                                    'Change this setting to stop using the default dynamic configuration.')


class VictoriaConfig(BaseModel):
    retention: str = Field(default='100y',
                           title='Retention period for history data in the Victoria Metrics database',
                           description='Data older than this value is gradually deleted.')
    search_latency: str = Field(default='10s',
                                title='Max duration before inserted history data is returned by queries',
                                description='Newly inserted data points must be indexed before they can be queried. '
                                'Every {search_latency}, all newly inserted points are indexed.' +
                                'This does not change the timestamp for inserted data.')


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
    ports: PortConfig = Field(default_factory=PortConfig)
    compose: ComposeConfig = Field(default_factory=ComposeConfig)
    avahi: AvahiConfig = Field(default_factory=AvahiConfig)
    system: SystemConfig = Field(default_factory=SystemConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    traefik: TraefikConfig = Field(default_factory=TraefikConfig)
    victoria: VictoriaConfig = Field(default_factory=VictoriaConfig)


class CtlOpts(BaseModel):
    dry_run: bool = False
    quiet: bool = False
    verbose: bool = False
    yes: bool = False
    color: bool = False
