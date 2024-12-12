import re
from getpass import getpass
from typing import Optional, Tuple

import click
from passlib.hash import pbkdf2_sha512

from . import const, utils


def read_users() -> dict:
    content = ''

    if utils.file_exists(const.PASSWD_FILE):
        content = utils.read_file_sudo(const.PASSWD_FILE)

    return {
        name: hashed for (name, hashed) in [line.strip().split(':', 1) for line in content.split('\n') if ':' in line]
    }


def write_users(users: dict):
    content = ''.join([f'{k}:{v}\n' for k, v in users.items()])
    utils.write_file_sudo(const.PASSWD_FILE, content, secret=True)
    utils.sh(f'sudo chown root:root "{const.PASSWD_FILE}"')


def prompt_user_info(username: Optional[str], password: Optional[str]) -> Tuple[str, str]:
    if username is None:
        username = click.prompt('Auth user name')
    while not re.fullmatch(r'\w+', username):
        utils.warn('Names can only contain letters, numbers, - or _')
        username = click.prompt('Auth user name')
    if password is None:
        password = getpass(prompt='Auth password: ')
    return (username, password)


def add_user(username: Optional[str], password: Optional[str]):
    username, password = prompt_user_info(username, password)
    users = read_users()
    users[username] = pbkdf2_sha512.hash(password)
    write_users(users)


def remove_user(username: str):
    users = read_users()
    try:
        del users[username]
        write_users(users)
    except KeyError:
        pass
