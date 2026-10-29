from pathlib import Path
from typing import Protocol

from pyreview.linters.domain import LintRun


class Linter(Protocol):
    @property
    def name(self) -> str: ...

    async def run(self, path: Path) -> LintRun: ...
