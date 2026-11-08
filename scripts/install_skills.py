#!/usr/bin/env python3
"""Install the AI Teacher skill into an explicitly selected project, never globally."""
import argparse
from pathlib import Path
import shutil
import sys

NAMES = ("ai-teacher",)


def install(project, bundle, dry_run=False):
    project = Path(project).resolve(strict=True)
    if not project.is_dir():
        raise ValueError("project must be an existing directory")
    source = Path(bundle) / "plugins" / "ai-teacher" / "skills"
    agents = project / ".agents"
    target = agents / "skills"
    for directory in (agents, target):
        if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
            raise ValueError("refusing symlink or nondirectory install location")
    for name in NAMES:
        src = source / name
        dst = target / name
        if not (src / "SKILL.md").is_file() or src.is_symlink():
            raise ValueError(f"missing or invalid source skill: {name}")
        if any(p.is_symlink() for p in src.rglob("*")):
            raise ValueError(f"source skill contains symlinks: {name}")
        if dst.exists() or dst.is_symlink():
            raise ValueError(f"refusing to overwrite existing skill: {dst}")
    destinations = [target / name for name in NAMES]
    if dry_run:
        return destinations
    created = []
    agents_existed, target_existed = agents.exists(), target.exists()
    try:
        target.mkdir(parents=True, exist_ok=True)
        for name, dst in zip(NAMES, destinations):
            # Reserve the destination so a concurrent installation cannot be overwritten.
            dst.mkdir()
            created.append(dst)
            shutil.copytree(source / name, dst, dirs_exist_ok=True)
    except Exception:
        for dst in reversed(created):
            shutil.rmtree(dst)
        for directory, existed in ((target, target_existed), (agents, agents_existed)):
            if not existed and directory.exists():
                try:
                    directory.rmdir()
                except OSError:
                    pass
        raise
    return destinations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        bundle = Path(__file__).resolve().parent.parent
        destinations = install(args.project, bundle, args.dry_run)
        print("Dry run; no files written." if args.dry_run else "Installed project-local skills:")
        for dst in destinations:
            print(dst)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"installation failed: {exc}\n")


if __name__ == "__main__":
    main()
