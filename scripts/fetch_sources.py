#!/usr/bin/env python3
"""Download pinned source snapshots used to build core-en."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path


SOURCES = (
    {
        "name": "oewn-2025",
        "url": (
            "https://github.com/globalwordnet/english-wordnet/archive/"
            "refs/tags/2025-edition.tar.gz"
        ),
        "sha256": "0af7ec077ecda0f61d4e33371cf31c3ac0a8c667150f25894787a0da9e2f3dea",
    },
    {
        "name": "omw-data",
        "url": (
            "https://github.com/omwn/omw-data/archive/"
            "406bf83b3c507a3d1f26e88252d5d66893fd36bf.tar.gz"
        ),
        "sha256": "01ef22a0a9ae0856975cf0edbfda124b6844f81ec307ffaf49cd0f09e243b44d",
    },
    {
        "name": "pwn30",
        "url": "https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/corpora/wordnet.zip",
        "sha256": "cbda5ea6eef7f36a97a43d4a75f85e07fccbb4f23657d27b4ccbc93e2646ab59",
        "archive": "zip",
    },
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "core-en-builder/1"})
    with urllib.request.urlopen(request) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)


def fetch_source(source: dict[str, str], cache_dir: Path) -> Path:
    destination = cache_dir / source["name"]
    marker = destination / ".source-sha256"
    if marker.exists() and marker.read_text().strip() == source["sha256"]:
        return destination
    if destination.exists():
        raise RuntimeError(
            f"{destination} exists but is incomplete or from another version; remove it"
        )

    cache_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=cache_dir) as temp_name:
        temp_dir = Path(temp_name)
        archive = temp_dir / "source.tar.gz"
        print(f"Downloading {source['name']}...")
        download(source["url"], archive)
        actual_hash = file_sha256(archive)
        if actual_hash != source["sha256"]:
            raise RuntimeError(
                f"SHA-256 mismatch for {source['name']}: {actual_hash}"
            )

        extracted = temp_dir / "extracted"
        extracted.mkdir()
        if source.get("archive", "tar.gz") == "zip":
            with zipfile.ZipFile(archive) as zipped:
                zipped.extractall(extracted)
        else:
            with tarfile.open(archive, "r:gz") as tar:
                tar.extractall(extracted, filter="data")
        roots = [path for path in extracted.iterdir() if path.is_dir()]
        if len(roots) != 1:
            raise RuntimeError(f"Unexpected archive layout for {source['name']}")
        roots[0].rename(destination)
        marker.write_text(source["sha256"] + "\n")
    return destination


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path(".cache/sources"),
        help="Directory for extracted source snapshots",
    )
    args = parser.parse_args()
    for source in SOURCES:
        path = fetch_source(source, args.cache_dir)
        print(path)


if __name__ == "__main__":
    main()
