from __future__ import annotations

import argparse
import sys

import httpx


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run live AIx API security probes.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--organization", default="aix-research")
    parser.add_argument("--email", default="owner@example.com")
    parser.add_argument("--password", required=True)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    with httpx.Client(base_url=base, timeout=10) as client:
        unauthenticated = client.get("/v1/systems")
        require(unauthenticated.status_code == 401, "Unauthenticated read was accepted")
        require(
            unauthenticated.headers.get("x-content-type-options") == "nosniff",
            "Security headers are missing",
        )
        require(
            client.get(
                "/v1/systems",
                headers={"Authorization": "Bearer ' OR 1=1 --"},
            ).status_code
            == 401,
            "Bearer-token injection was accepted",
        )
        login = client.post(
            "/v1/auth/login",
            json={
                "organization_slug": args.organization,
                "email": args.email,
                "password": args.password,
            },
        )
        require(login.status_code == 200, f"Probe login failed: {login.text}")
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        require(
            client.get("/v1/evidence/..%2F..%2Fetc%2Fpasswd/content", headers=headers)
            .status_code
            in {404, 422},
            "Path traversal probe escaped evidence routing",
        )
        require(
            client.post(
                "/v1/webhooks",
                headers=headers,
                json={"url": "http://169.254.169.254/latest/meta-data", "events": ["*"]},
            ).status_code
            == 422,
            "Cloud metadata SSRF target was accepted",
        )
        require(
            client.get(
                "/scim/v2/Users",
                headers=headers,
                params={"filter": 'userName eq "x" or userName pr'},
            ).status_code
            == 403,
            "Ordinary session accessed SCIM provisioning",
        )
        require(
            client.request("TRACE", "/v1/me", headers=headers).status_code == 405,
            "TRACE method was accepted",
        )
    print("AIx live security probes passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, httpx.HTTPError) as exc:
        print(f"security probe failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
