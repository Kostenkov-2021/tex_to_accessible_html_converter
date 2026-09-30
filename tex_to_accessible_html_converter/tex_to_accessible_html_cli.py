"""Command-line interface for TeX to Accessible HTML Converter."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from converter import ConversionError, convert_tex_to_accessible_html, output_file_for

RETENTION = {
    "html": (False, False),
    "logs": (True, False),
    "temporary": (False, True),
    "all": (True, True),
}


def collect_tex_files(inputs: list[str], recursive: bool = False) -> list[Path]:
    """Expand files and directories into an ordered, duplicate-free file list."""
    result: list[Path] = []
    seen: set[Path] = set()
    for raw_input in inputs:
        path = Path(raw_input).expanduser()
        candidates = (
            path.rglob("*")
            if path.is_dir() and recursive
            else (path.iterdir() if path.is_dir() else [path])
        )
        for candidate in sorted(candidates, key=lambda item: str(item).casefold()):
            if candidate.is_file() and candidate.suffix.casefold() == ".tex":
                resolved = candidate.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    result.append(candidate)
    return result


def build_parser() -> argparse.ArgumentParser:
    """Build and return the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Convert TeX files to accessible HTML with MathML.",
    )
    parser.add_argument("inputs", nargs="+", help="TeX files or directories")
    parser.add_argument("-o", "--output-dir", type=Path, help="HTML output directory")
    parser.add_argument(
        "--recursive", action="store_true", help="search directories recursively"
    )
    parser.add_argument(
        "--engine", choices=("latex", "lualatex", "xelatex"), default="lualatex"
    )
    parser.add_argument("--mode", choices=("default", "draft"), default="default")
    parser.add_argument(
        "--tex-distribution", choices=("auto", "texlive", "miktex"), default="auto"
    )
    parser.add_argument(
        "--timeout", type=float, default=300, help="timeout per file in seconds"
    )
    parser.add_argument(
        "--keep",
        choices=tuple(RETENTION),
        default="html",
        help="artifacts to keep in addition to HTML",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run command-line conversion and return a process exit status."""
    args = build_parser().parse_args(argv)
    files = collect_tex_files(args.inputs, args.recursive)
    if not files:
        print("No .tex files were found.", file=sys.stderr)
        return 2

    if args.timeout <= 0:
        print("--timeout must be greater than zero.", file=sys.stderr)
        return 2

    keep_logs, keep_temporary_files = RETENTION[args.keep]
    failures = 0
    for tex_file in files:
        output_file = output_file_for(tex_file, args.output_dir)
        try:
            result = convert_tex_to_accessible_html(
                tex_file=tex_file,
                output_file=output_file,
                engine=args.engine,
                mode=args.mode,
                tex_distribution=args.tex_distribution,
                timeout=args.timeout,
                keep_logs=keep_logs,
                keep_temporary_files=keep_temporary_files,
            )
        except (ConversionError, OSError) as error:
            failures += 1
            print(f"ERROR: {tex_file}\n{error}", file=sys.stderr)
        else:
            print(result)

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
