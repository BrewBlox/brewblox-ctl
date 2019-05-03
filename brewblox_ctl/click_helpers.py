"""
Custom overrides for click
"""

import click


class OrderedGroup(click.Group):
    """
    Click group implementation that will list commands in order of insertion.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sorted_names = list(self.commands.keys())

    def add_command(self, cmd, name=None):
        super().add_command(cmd, name)
        self._sorted_names.append(name or cmd.name)

    def list_commands(self, ctx):
        return self._sorted_names.copy()


class OrderedCommandCollection(click.CommandCollection):
    """
    Click CommandCollection that will list commands in order of insertion.
    """

    def list_commands(self, ctx):
        rv = []
        for source in self.sources:
            rv += source.list_commands(ctx)
        return rv
