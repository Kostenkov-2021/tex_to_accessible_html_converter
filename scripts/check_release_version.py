"""Reject release tags that do not match the application and installer."""

import os
from pathlib import Path
import re
import subprocess
import tomllib

root = Path(__file__).resolve().parents[1]
tag = os.environ["RELEASE_TAG"]
version = tomllib.loads(
    (root / "tex_to_accessible_html_converter/pyproject.toml").read_text(encoding="utf-8")
)["project"]["version"]
installer = (root / "packaging/installer.iss").read_text(encoding="utf-8")
match = re.search(r'^#define AppVersion "([^"]+)"$', installer, re.MULTILINE)
if tag != f"v{version}" or not match or match[1] != version:
    raise SystemExit("Tag, pyproject.toml and installer.iss must have the same version.")
revision = subprocess.check_output(
    ["git", "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}"],
    cwd=root, text=True,
).strip()
head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
if head != revision:
    raise SystemExit("Checkout does not match the requested tag.")
with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
    output.write(f"tag={tag}\nrevision={revision}\n")
