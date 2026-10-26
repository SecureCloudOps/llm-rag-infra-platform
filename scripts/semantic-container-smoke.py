#!/usr/bin/env python3
"""Validate an isolated API container on an existing Compose Qdrant network."""

import argparse
import json
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import httpx


def docker(*args):
    return subprocess.check_output(
        ["docker", *args], text=True, stderr=subprocess.STDOUT
    ).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="rag-api:semantic")
    parser.add_argument("--network", default="llm-rag-infra-platform_default")
    parser.add_argument("--port", type=int, default=8003)
    parser.add_argument(
        "--mock", action="store_true", help="Explicit mock-only plumbing validation"
    )
    parser.add_argument("--ca-bundle", type=Path)
    parser.add_argument(
        "--model-cache", type=Path,
        help="Pre-populated Hugging Face hub cache to mount read-only at /models",
    )
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.offline and not args.model_cache:
        parser.error("--offline requires --model-cache with the pinned snapshot")
    name = "semantic-smoke-" + uuid4().hex
    collection = name + ("-mock" if args.mock else "-real")
    report = {
        "provider": "mock" if args.mock else "sentence_transformers",
        "collection": collection,
        "image": args.image,
    }
    command = [
        "run",
        "-d",
        "--name",
        name,
        "--network",
        args.network,
        "-p",
        f"127.0.0.1:{args.port}:8000",
        "-e",
        "QDRANT_URL=http://qdrant:6333",
        "-e",
        f"COLLECTION_NAME={collection}",
        "-e",
        "LLM_PROVIDER=mock",
        "-e",
        "NO_PROXY=qdrant,localhost,127.0.0.1",
        "-e",
        "no_proxy=qdrant,localhost,127.0.0.1",
        "-e",
        "HF_HUB_ETAG_TIMEOUT=3",
        "-e",
        "HF_HUB_DOWNLOAD_TIMEOUT=3",
    ]
    if args.model_cache:
        if not args.model_cache.is_dir():
            parser.error("--model-cache must be an existing hub cache directory")
        command += [
            "--mount", f"type=bind,src={args.model_cache.resolve()},dst=/models,readonly",
            "-e", "HF_HOME=/tmp/huggingface",
        ]
    else:
        command += ["-v", "semantic-task-model-cache:/models"]
    if args.offline:
        command += ["-e", "HF_HUB_OFFLINE=1", "-e", "TRANSFORMERS_OFFLINE=1"]
    report["offline"] = args.offline
    report["cache_provisioning"] = "read-only bind mount" if args.model_cache else "named volume"
    if args.mock:
        command += ["-e", "EMBEDDING_PROVIDER=mock", "-e", "EMBEDDING_DIMENSIONS=8"]
    if args.ca_bundle:
        command += [
            "--mount",
            f"type=bind,src={args.ca_bundle.resolve()},dst=/run/proxy-ca.pem,readonly",
            "-e",
            "REQUESTS_CA_BUNDLE=/run/proxy-ca.pem",
            "-e",
            "SSL_CERT_FILE=/run/proxy-ca.pem",
        ]
    report["image_id"] = docker("image", "inspect", args.image, "-f", "{{.Id}}")
    created = False
    try:
        docker(*command, args.image)
        created = True
        with httpx.Client(
            base_url=f"http://127.0.0.1:{args.port}", timeout=10, trust_env=False
        ) as client:

            def wait_ready():
                deadline = time.monotonic() + 120
                while time.monotonic() < deadline:
                    if docker("inspect", "-f", "{{.State.Running}}", name) != "true":
                        raise RuntimeError(
                            "Container exited before readiness: "
                            + docker("logs", name)[-4000:]
                        )
                    try:
                        if client.get("/ready").status_code == 200:
                            return
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.25)
                raise RuntimeError("Readiness timeout after 120 seconds")

            wait_ready()
            report["ready"] = True
            cpu = docker(
                "exec",
                name,
                "python",
                "-c",
                "import torch; assert torch.version.cuda is None; print(torch.__version__)",
            )
            report["torch_cpu_version"] = cpu
            if args.offline and not args.mock:
                # No network interface and an audit hook prove real cached inference
                # works without even attempting an external connection.
                output = docker(
                    "run", "--rm", "--network", "none",
                    "--mount", f"type=bind,src={args.model_cache.resolve()},dst=/models,readonly",
                    "-e", "HF_HOME=/tmp/huggingface",
                    "-e", "HF_HUB_OFFLINE=1", "-e", "TRANSFORMERS_OFFLINE=1",
                    "--entrypoint", "python", args.image, "-c",
                    "import sys, json, math\n"
                    "attempts = []\n"
                    "def block(event, args):\n"
                    "    if event in ('socket.connect', 'socket.getaddrinfo', 'socket.sendto'):\n"
                    "        attempts.append(event)\n"
                    "        raise AssertionError('Unexpected network attempt: ' + event)\n"
                    "sys.addaudithook(block)\n"
                    "from app.embeddings import SentenceTransformerEmbeddingProvider\n"
                    "p = SentenceTransformerEmbeddingProvider(cache_folder='/models')\n"
                    "v = p.embed('Kubernetes workload scheduling')\n"
                    "assert len(v) == 384 and all(math.isfinite(x) for x in v)\n"
                    "assert str(p._model.device) == 'cpu'\n"
                    "assert not attempts, attempts\n"
                    "print(json.dumps({'dimensions': len(v), 'device': 'cpu', 'network_attempts': len(attempts)}))\n",
                )
                report["disconnected_inference"] = json.loads(output.splitlines()[-1])
            text = "Place databases in private subnets without public IP addresses to prevent internet access."
            response = client.post(
                "/documents/upload", files={"file": ("network.txt", text)}
            )
            response.raise_for_status()
            report["upload"] = response.json()
            assert report["upload"]["embedding_count"] == 1
            stats = client.get("/documents")
            stats.raise_for_status()
            report["documents_before_restart"] = stats.json()
            assert stats.json() == {"total_documents": 1, "total_chunks": 1}
            response = client.post(
                "/search",
                json={"query": "How do I keep a data store off the public internet?"},
            )
            response.raise_for_status()
            report["search"] = response.json()
            assert response.json()["results"][0]["filename"] == "network.txt"
            response = client.post(
                "/ask",
                json={
                    "question": "How do I keep a data store off the public internet?"
                },
            )
            response.raise_for_status()
            report["ask"] = response.json()
            assert response.json()["sources"][0]["filename"] == "network.txt"
            docker("restart", name)
            wait_ready()
            response = client.get("/documents")
            response.raise_for_status()
            report["documents_after_restart"] = response.json()
            assert response.json() == report["documents_before_restart"]
            response = client.post(
                "/search", json={"query": "How do I keep a database private?"}
            )
            response.raise_for_status()
            assert response.json()["results"][0]["filename"] == "network.txt"
            report["search_after_restart"] = response.json()
            report["status"] = "passed"
    except Exception as exc:
        report.update(status="blocked" if not args.mock else "failed", error=str(exc))
    finally:
        if created:
            docker("rm", "-f", name)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
