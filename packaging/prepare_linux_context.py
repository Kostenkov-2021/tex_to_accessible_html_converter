"""Stage only build inputs; avoid traversing restricted Windows cache folders."""

from pathlib import Path
import shutil


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    destination = root / "build" / "linux-docker-context"
    files = [
        root / "pytest.ini", root / "LICENSE", root / ".dockerignore",
        root / "tex_to_accessible_html_converter/pyproject.toml",
        root / "docs/README.html", root / "docs/README_RU.html",
        root / "docs/LINUX.md", root / "scripts/check_tex_integration.py",
        root / "tests/fixtures/integration.tex",
        root / "packaging/Dockerfile.linux",
    ]
    for folder, pattern in (
        ("tex_to_accessible_html_converter", "*.py"),
        ("tex_to_accessible_html_converter/tests", "*.py"),
        ("packaging", "*.py"), ("packaging", "*.sh"), ("packaging", "*.spec"),
        ("tex_to_accessible_html_converter/locales", "**/*.po"),
        ("tex_to_accessible_html_converter/locales", "**/*.mo"),
    ):
        files.extend((root / folder).glob(pattern))
    for source in files:
        target = destination / source.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    print(destination)


if __name__ == "__main__":
    main()
