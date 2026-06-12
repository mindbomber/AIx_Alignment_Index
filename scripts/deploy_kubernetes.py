from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import tempfile

import yaml


def render(overlay: Path, api_image: str, web_image: str) -> list[dict]:
    output = subprocess.run(
        ["kubectl", "kustomize", str(overlay)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    documents = [document for document in yaml.safe_load_all(output) if document]
    for document in documents:
        pod_spec = None
        kind = document.get("kind")
        if kind == "Deployment":
            pod_spec = document["spec"]["template"]["spec"]
        elif kind == "Job":
            pod_spec = document["spec"]["template"]["spec"]
        if not pod_spec:
            continue
        for container in pod_spec.get("containers", []):
            if container["name"] in {"api", "worker", "migrate"}:
                container["image"] = api_image
            elif container["name"] == "web":
                container["image"] = web_image
    return documents


def write_documents(path: Path, documents: list[dict]) -> None:
    path.write_text(
        yaml.safe_dump_all(documents, sort_keys=False),
        encoding="utf-8",
    )


def kubectl(*arguments: str) -> None:
    subprocess.run(["kubectl", *arguments], check=True)


def ensure_namespace(namespace: str) -> None:
    result = subprocess.run(
        ["kubectl", "get", "namespace", namespace],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        kubectl("create", "namespace", namespace)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("environment", choices=("staging", "production"))
    parser.add_argument("--api-image", required=True)
    parser.add_argument("--web-image", required=True)
    parser.add_argument("--render-output", type=Path)
    parser.add_argument("--deploy", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    documents = render(
        root / "deploy" / "kubernetes" / args.environment,
        args.api_image,
        args.web_image,
    )
    if args.render_output:
        write_documents(args.render_output, documents)
    if not args.deploy:
        return 0

    namespace = f"aix-{args.environment}"
    migration = next(
        document
        for document in documents
        if document["kind"] == "Job"
        and document["metadata"]["name"].startswith("aix-migrate-")
    )
    migration_name = migration["metadata"]["name"]
    prerequisites = [
        document
        for document in documents
        if document["kind"] in {"ConfigMap", "ServiceAccount"}
        or document.get("metadata", {})
        .get("annotations", {})
        .get("aix.dev/deployment-phase")
        == "prerequisite"
    ]
    prerequisite_statefulsets = [
        document["metadata"]["name"]
        for document in prerequisites
        if document["kind"] == "StatefulSet"
    ]
    prerequisite_jobs = [
        document["metadata"]["name"]
        for document in prerequisites
        if document["kind"] == "Job"
    ]
    with tempfile.TemporaryDirectory() as directory:
        directory_path = Path(directory)
        prerequisite_file = directory_path / "prerequisites.yaml"
        migration_file = directory_path / "migration.yaml"
        all_file = directory_path / "all.yaml"
        write_documents(prerequisite_file, prerequisites)
        write_documents(migration_file, [migration])
        write_documents(all_file, documents)
        ensure_namespace(namespace)
        kubectl("apply", "-f", str(prerequisite_file))
        for statefulset in prerequisite_statefulsets:
            kubectl(
                "rollout",
                "status",
                f"statefulset/{statefulset}",
                "-n",
                namespace,
                "--timeout=10m",
            )
        for job in prerequisite_jobs:
            kubectl(
                "wait",
                "--for=condition=complete",
                f"job/{job}",
                "-n",
                namespace,
                "--timeout=10m",
            )
        kubectl(
            "delete",
            "job",
            migration_name,
            "-n",
            namespace,
            "--ignore-not-found",
        )
        kubectl("apply", "-f", str(migration_file))
        kubectl(
            "wait",
            "--for=condition=complete",
            f"job/{migration_name}",
            "-n",
            namespace,
            "--timeout=10m",
        )
        kubectl("apply", "-f", str(all_file))
        for deployment in ("aix-api", "aix-worker", "aix-web"):
            kubectl(
                "rollout",
                "status",
                f"deployment/{deployment}-{args.environment}",
                "-n",
                namespace,
                "--timeout=10m",
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
