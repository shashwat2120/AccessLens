"""Assemble the folder that is pushed to a Hugging Face Space.

A Space is its own git repository whose root holds the Dockerfile, so this copies just what the
single-container image needs (source, UI, lock file, Streamlit config) plus the Space files in
this directory. Usage: ``python deploy/huggingface/build_space.py [out_dir]`` (default
``build/space``). Standard library only; secrets are never copied.
"""

import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FROM_ROOT = ("pyproject.toml", "uv.lock", "LICENSE")
DIRS_FROM_ROOT = ("src", "ui", ".streamlit")
FROM_HERE = ("Dockerfile", "start.sh", "README.md")
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".env", ".env.*")


def build(out: Path) -> Path:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for name in FROM_ROOT:
        shutil.copy2(ROOT / name, out / name)
    for name in DIRS_FROM_ROOT:
        shutil.copytree(ROOT / name, out / name, ignore=IGNORE)
    for name in FROM_HERE:
        shutil.copy2(HERE / name, out / name)
    script = out / "start.sh"  # bash inside the container fails on Windows line endings
    script.write_bytes(script.read_bytes().replace(b"\r\n", b"\n"))
    return out


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "build" / "space"
    build(out)
    print(f"Space folder ready at {out}")


if __name__ == "__main__":
    main()
