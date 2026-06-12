from __future__ import annotations

import argparse
import asyncio
from statistics import quantiles
from time import perf_counter

import httpx


async def run_requests(
    base_url: str, token: str, requests: int, concurrency: int
) -> list[tuple[int, float]]:
    semaphore = asyncio.Semaphore(concurrency)
    limits = httpx.Limits(
        max_connections=concurrency,
        max_keepalive_connections=concurrency,
    )
    async with httpx.AsyncClient(
        base_url=base_url.rstrip("/"),
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
        limits=limits,
    ) as client:
        async def request() -> tuple[int, float]:
            async with semaphore:
                started = perf_counter()
                response = await client.get("/v1/systems")
                return response.status_code, (perf_counter() - started) * 1000

        return await asyncio.gather(*(request() for _ in range(requests)))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--token", required=True)
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--max-error-rate", type=float, default=0.01)
    parser.add_argument("--max-p95-ms", type=float, default=1000)
    args = parser.parse_args()

    results = asyncio.run(
        run_requests(args.base_url, args.token, args.requests, args.concurrency)
    )
    errors = sum(status >= 400 for status, _ in results)
    latencies = [latency for _, latency in results]
    p95 = quantiles(latencies, n=20)[18] if len(latencies) >= 20 else max(latencies)
    error_rate = errors / len(results)
    print(
        f"requests={len(results)} errors={errors} "
        f"error_rate={error_rate:.3f} p95_ms={p95:.1f}"
    )
    return int(
        error_rate > args.max_error_rate or p95 > args.max_p95_ms
    )


if __name__ == "__main__":
    raise SystemExit(main())
