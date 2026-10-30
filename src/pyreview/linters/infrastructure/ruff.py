import json
from dataclasses import dataclass
from pathlib import Path

from pyreview.linters.domain import LintIssue, LintRun
from pyreview.linters.infrastructure._process import run_linter


def parse_ruff(output: str) -> list[LintIssue]:
    return [
        LintIssue(
            tool="ruff",
            line=item["location"]["row"],
            column=item["location"]["column"],
            code=item["code"] or "invalid-syntax",
            message=item["message"],
        )
        for item in json.loads(output)
    ]


@dataclass(frozen=True, slots=True)
class RuffLinter:
    select: tuple[str, ...]
    timeout_seconds: float

    @property
    def name(self) -> str:
        return "ruff"

    async def run(self, path: Path) -> LintRun:
        args = ["check", "--isolated", "--no-cache", "--output-format", "json"]
        args += ["--select", ",".join(self.select)]
        return await run_linter(self.name, args, path, self.timeout_seconds, parse_ruff)
