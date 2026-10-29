import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from pyreview.linters.domain import LintIssue, LintRun
from pyreview.linters.infrastructure._process import run_linter

PYTHON_VERSION = f"{sys.version_info.major}.{sys.version_info.minor}"


def parse_ty(output: str) -> list[LintIssue]:
    issues = []
    for item in json.loads(output):
        begin = item["location"].get("positions", {}).get("begin", {"line": 1, "column": 1})
        code = item["check_name"]
        issues.append(
            LintIssue(
                tool="ty",
                line=begin["line"],
                column=begin["column"],
                code=code,
                message=item["description"].removeprefix(f"{code}: "),
            )
        )
    return issues


@dataclass(frozen=True, slots=True)
class TyLinter:
    timeout_seconds: float

    @property
    def name(self) -> str:
        return "ty"

    async def run(self, path: Path) -> LintRun:
        with tempfile.TemporaryDirectory(prefix="pyreview-ty-") as prefix:
            (Path(prefix) / "lib" / f"python{PYTHON_VERSION}" / "site-packages").mkdir(parents=True)
            args = ["check", "--config-file", "/dev/null", "--python", prefix]
            args += ["--python-version", PYTHON_VERSION, "--ignore", "unresolved-import"]
            args += ["--output-format", "gitlab", "--no-progress", "--color", "never"]
            env = {"XDG_CONFIG_HOME": prefix}
            return await run_linter(self.name, args, path, self.timeout_seconds, parse_ty, env)
