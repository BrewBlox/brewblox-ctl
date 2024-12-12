"""
Prints data in tabular format
"""

from typing import Dict, List

import click


class Table:
    """Table string formatter, suitable for streamed data

    For every row, the values in `row[key] for key in keys` is printed.
    Header names and format strings can be optionally specified.
    Formatting is applied to row values only,
    and all rows are justified to the width of the header.
    """

    def __init__(
        self,
        keys: List[str],
        headers: Dict[str, str] = None,
        formatting: Dict[str, str] = None,
    ) -> None:
        self.keys = keys
        self.headers = headers or {}
        self.formatting = formatting or {}
        self.rows = []
        self.col_width = {}

    def print_headers(self):
        headers = []
        spacers = []

        for key in self.keys:
            header = self.headers.get(key, key)
            headers.append(header)
            spacers.append(''.ljust(len(header), '-'))
            self.col_width[key] = len(header)

        click.echo(' '.join(headers))
        click.echo(' '.join(spacers))

    def print_row(self, row: Dict[str, str]):
        line_values = [
            self.formatting.get(key, '{}').format(row.get(key, '')).ljust(self.col_width.get(key, 0))
            for key in self.keys
        ]
        click.echo(' '.join(line_values))
