from __future__ import annotations

import argparse
import gzip
from io import BytesIO
import os
from pathlib import Path
import tarfile


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    epoch = int(os.environ.get("SOURCE_DATE_EPOCH", "0"))
    compressed = args.archive.read_bytes()
    source_tar = BytesIO(gzip.decompress(compressed))
    normalized_tar = BytesIO()
    with tarfile.open(fileobj=source_tar, mode="r:") as source:
        members = sorted(source.getmembers(), key=lambda member: member.name)
        with tarfile.open(
            fileobj=normalized_tar,
            mode="w:",
            format=tarfile.PAX_FORMAT,
        ) as destination:
            for member in members:
                member.mtime = epoch
                member.uid = 0
                member.gid = 0
                member.uname = ""
                member.gname = ""
                member.pax_headers = {}
                handle = source.extractfile(member) if member.isfile() else None
                destination.addfile(member, handle)
    with args.archive.open("wb") as destination:
        with gzip.GzipFile(
            filename="",
            mode="wb",
            fileobj=destination,
            mtime=epoch,
        ) as output:
            output.write(normalized_tar.getvalue())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
