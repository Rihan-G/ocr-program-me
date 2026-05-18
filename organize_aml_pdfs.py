#!/usr/bin/env python3
"""
Organize AML (or other) PDF files from a source folder into person-specific
subfolders under a destination root (for example a OneDrive directory).

Typical OneDrive roots on Windows look like:
  C:\\Users\\<you>\\OneDrive
  C:\\Users\\<you>\\OneDrive - Contoso

Examples:
  # Copy each PDF into a subfolder named after the file stem (minus extension)
  python organize_aml_pdfs.py --source "D:\\Inbox\\AML" --dest-root "C:\\Users\\me\\OneDrive\\AML\\ByPerson"

  # Use the part before the first underscore as the person key (Doe_John_form.pdf -> Doe)
  python organize_aml_pdfs.py --source ./inbox --dest-root ~/OneDrive/AML --split-delimiter _ --person-part 0

  # Move files and use an explicit basename -> folder mapping
  python organize_aml_pdfs.py --source ./inbox --dest-root ~/OneDrive/AML --mapping mapping.json --move
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path


ILLEGAL_WIN_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_folder_name(name: str) -> str:
    """Make a string safe as a single path segment on Windows and Unix."""
    name = ILLEGAL_WIN_CHARS.sub("_", name)
    name = name.strip().rstrip(".")
    return name or "Unknown"


def load_mapping(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Mapping file must be a JSON object.")
    # Accept either {"file.pdf": "Folder"} or {"mappings": {...}}
    if "mappings" in data and isinstance(data["mappings"], dict):
        raw = data["mappings"]
    else:
        raw = data
    return {str(k): str(v) for k, v in raw.items()}


def person_folder_for_file(
    pdf: Path,
    mapping: dict[str, str] | None,
    delimiter: str | None,
    person_part: int,
) -> str:
    base = pdf.name
    if mapping is not None and base in mapping:
        return sanitize_folder_name(mapping[base])

    stem = pdf.stem
    if delimiter:
        parts = stem.split(delimiter)
        if person_part < 0 or person_part >= len(parts):
            raise ValueError(
                f"person-part {person_part} out of range for {pdf.name!r} "
                f"with delimiter {delimiter!r} (got {len(parts)} parts)."
            )
        key = parts[person_part].strip()
    else:
        key = stem.strip()

    return sanitize_folder_name(key)


def collect_pdfs(source: Path) -> list[Path]:
    if not source.is_dir():
        raise NotADirectoryError(f"Source is not a directory: {source}")
    return sorted(p for p in source.iterdir() if p.is_file() and p.suffix.lower() == ".pdf")


def run(
    source: Path,
    dest_root: Path,
    *,
    mapping: dict[str, str] | None,
    delimiter: str | None,
    person_part: int,
    move: bool,
    dry_run: bool,
) -> int:
    dest_root = dest_root.expanduser().resolve()
    source = source.expanduser().resolve()

    pdfs = collect_pdfs(source)
    if not pdfs:
        print(f"No PDF files found in {source}", file=sys.stderr)
        return 1

    verb = "Would move" if move and dry_run else ("Would copy" if dry_run else ("Move" if move else "Copy"))

    for pdf in pdfs:
        folder_name = person_folder_for_file(pdf, mapping, delimiter, person_part)
        target_dir = dest_root / folder_name
        target_path = target_dir / pdf.name

        print(f"{verb}: {pdf} -> {target_path}")

        if dry_run:
            continue

        target_dir.mkdir(parents=True, exist_ok=True)
        if target_path.exists():
            print(f"  Skip: destination already exists: {target_path}", file=sys.stderr)
            continue

        if move:
            shutil.move(str(pdf), str(target_path))
        else:
            shutil.copy2(str(pdf), str(target_path))

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Place each PDF from a source folder into a person subfolder under dest-root (e.g. OneDrive)."
    )
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Folder containing PDF files to distribute.",
    )
    parser.add_argument(
        "--dest-root",
        type=Path,
        required=True,
        help="Base folder (e.g. OneDrive path) where each person gets a subfolder.",
    )
    parser.add_argument(
        "--mapping",
        type=Path,
        default=None,
        help='Optional JSON file: {"SomeFile.pdf": "Last, First", ...} or {"mappings": {...}}.',
    )
    parser.add_argument(
        "--split-delimiter",
        default=None,
        metavar="STR",
        help="If set, split the filename stem on this string and take --person-part for the folder name.",
    )
    parser.add_argument(
        "--person-part",
        type=int,
        default=0,
        help="Index of the segment to use after splitting the stem (default 0). Ignored without --split-delimiter.",
    )
    parser.add_argument(
        "--move",
        action="store_true",
        help="Move files instead of copying (default is copy).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned actions without copying or moving.",
    )

    args = parser.parse_args()
    mapping = load_mapping(args.mapping) if args.mapping else None

    try:
        return run(
            args.source,
            args.dest_root,
            mapping=mapping,
            delimiter=args.split_delimiter,
            person_part=args.person_part,
            move=args.move,
            dry_run=args.dry_run,
        )
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
