# Brewblox CLI management tool

This is the primary tool for installing and managing Brewblox service hosts.

For user install instructions, see <https://www.brewblox.com/user/startup>.

## Context: footloose configuration

One of the core tenets of Brewblox is to keep the footprint on the service host strictly limited, and easily removed.
This is partially aspirational. For example, we rely on Docker to provide much of this isolation, but Docker itself is not a built-in tool on Debian-based operating systems.

There are three ways in which we promote isolation:

- Services are containerized using Docker.
- The `brewblox-ctl` management tooling is isolated using Python virtualenv.
- All Brewblox-specific configuration and data is contained in a single directory.

## The Brewblox directory

Located by default in `$HOME/brewblox`, the Brewblox installation directory includes:

- `.venv`: a Python virtualenv directory where brewblox-ctl is installed.
- `docker-compose.shared.yml`: default docker compose configuration. This file is overwritten during updates.
- `docker-compose.yml`: user-defined docker compose configuration. The contents of this file override `docker-compose.shared.yml`.
- Directories mounted in Docker containers to store persistent data:
  - `mosquitto/`
  - `traefik/`
  - `redis/`
  - `victoria/`
- `backup/`: contains zipped configuration backups.
- `brewblox-ctl.tar.gz`: the sdist tarball for the last installed brewblox-ctl package.

This is not an exhaustive list. Optional and third-party services may add their own configuration files here.

## Bootstrap installation

The `bootstrap-install.sh` script is hosted at `https://brewblox.com/install`, and the startup guide instructs users to download and execute it.

This script installs the minimum required dependencies,
and then starts the `brewblox-ctl install` command to handle everything else.

## The brewblox-ctl executable

One file that defies the convention of everything being placed in the Brewblox directory is the `brewblox-ctl` executable.
This script activates (or installs) the virtualenv, and then calls `uv run python3 -m brewblox_ctl ARGS`

For users to call this as a single command, it needs to be findable using `$PATH`.
It is deployed in `$HOME/.local/bin` if `$HOME` exists, otherwise in `/usr/local/bin`.

Because it potentially controls multiple Brewblox installations, it is intentionally kept generic.

## Development: using a local environment

If you wish to test new or changed `brewblox-ctl` commands in a configured environment, you can do so with a symlinked version of your development directory.

Install brewblox as normal, then (in your brewblox directory), run:

```sh
ln -s ${BREWBLOX_CTL_REPO_DIR}/brewblox_ctl ./brewblox_ctl
```

The `brewblox-ctl` script involves `uv run python3 -m brewblox_ctl`, which prefers `./brewblox_ctl` over the installed version.
