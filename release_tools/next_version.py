#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


SEMVER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


@dataclass(frozen=True, order=True)
class Version:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, value: str) -> Version:
        match = SEMVER.fullmatch(value.strip())
        if not match:
            raise ValueError(f"Invalid semantic version: {value!r}")
        return cls(*(int(part) for part in match.groups()))

    def bump_patch(self) -> Version:
        return Version(self.major, self.minor, self.patch + 1)

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


def next_version(base: str, tags: list[str], head_tags: list[str]) -> Version:
    base_version = Version.parse(base)
    versions = [Version.parse(tag) for tag in tags if SEMVER.fullmatch(tag.strip())]
    current = [Version.parse(tag) for tag in head_tags if SEMVER.fullmatch(tag.strip())]
    if current:
        return max(current)
    if not versions:
        return base_version
    latest = max(versions)
    return base_version if latest < base_version else latest.bump_patch()


def git_tags(*arguments: str) -> list[str]:
    result = subprocess.run(
        ("git", "tag", *arguments),
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def main() -> None:
    base = Path("VERSION").read_text(encoding="utf-8").strip()
    version = next_version(base, git_tags("--list", "v*"), git_tags("--points-at", "HEAD", "v*"))
    values = f"version={version}\ntag=v{version}\n"
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8") as stream:
            stream.write(values)
    print(values, end="")


if __name__ == "__main__":
    main()
