from __future__ import annotations

import uvicorn

from .app import create_app


app = create_app()


def run() -> None:
    # The packaged server is intended to listen inside a container/network namespace.
    uvicorn.run(
        "aix_platform.main:app",
        host="0.0.0.0",  # nosec B104
        port=8000,
    )
