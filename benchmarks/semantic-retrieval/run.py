"""Real Qdrant HTTP benchmark. Never deletes collections; each run uses fresh names."""

import argparse
import hashlib
import json
import platform
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import numpy as np

from app.chunking import chunk_text
from app.embeddings import MockEmbeddingProvider, create_embedding_provider
from app.config import get_settings
from app.vector_store import QdrantVectorStore, VectorStoreChunk

ROOT = Path(__file__).resolve().parent


def distribution(values):
    return {
        "p50_ms": float(np.percentile(values, 50)),
        "p95_ms": float(np.percentile(values, 95)),
    }


def evaluate(provider, corpus, questions, url, repeats):
    name = f"benchmark-{provider.identity['provider']}-{uuid4().hex}"
    store = QdrantVectorStore(url, name, embedding_identity=provider.identity)
    store.ensure_collection(provider.dimensions)
    chunks = [
        (doc, i, text)
        for doc in corpus
        for i, text in enumerate(chunk_text(doc["text"]))
    ]
    start = perf_counter()
    vectors = provider.embed_batch([text for _, _, text in chunks])
    store.add_chunks(
        [
            VectorStoreChunk(
                text,
                vector,
                {
                    "document_id": doc["id"],
                    "filename": doc["id"] + ".txt",
                    "chunk_index": i,
                    "chunk_text": text,
                },
            )
            for (doc, i, text), vector in zip(chunks, vectors, strict=True)
        ]
    )
    ingestion_ms = (perf_counter() - start) * 1000
    # Warm up both paths. Cold initialization and ingestion are reported separately.
    store.search(provider.embed(questions[0]["question"]), len(chunks))
    embedding, search, total, rows = [], [], [], []
    for repeat in range(repeats):
        for question in questions:
            start = perf_counter()
            vector = provider.embed(question["question"])
            embedded = perf_counter()
            hits = store.search(vector, len(chunks))
            end = perf_counter()
            embedding.append((embedded - start) * 1000)
            search.append((end - embedded) * 1000)
            total.append((end - start) * 1000)
            if repeat == 0:
                ranked = list(dict.fromkeys(hit.document_id for hit in hits))
                relevant = set(question["relevant_document_ids"])
                rank = next(
                    (i for i, doc in enumerate(ranked, 1) if doc in relevant), None
                )
                rows.append(
                    {
                        "question_id": question["id"],
                        "ranked_document_ids": ranked,
                        "recall_at_1": len(relevant.intersection(ranked[:1]))
                        / len(relevant),
                        "recall_at_3": len(relevant.intersection(ranked[:3]))
                        / len(relevant),
                        "reciprocal_rank": 1 / rank if rank else 0,
                    }
                )
    store.client.close()
    return {
        "status": "ok",
        "collection": name,
        "identity": provider.identity,
        "dimensions": provider.dimensions,
        "questions": len(questions),
        "repeats": repeats,
        "ingestion_ms": ingestion_ms,
        "recall_at_1": float(np.mean([r["recall_at_1"] for r in rows])),
        "recall_at_3": float(np.mean([r["recall_at_3"] for r in rows])),
        "mrr": float(np.mean([r["reciprocal_rank"] for r in rows])),
        "embedding_latency": distribution(embedding),
        "vector_search_latency": distribution(search),
        "end_to_end_latency": distribution(total),
        "relevance_failures_at_1": [
            r["question_id"] for r in rows if r["recall_at_1"] < 1
        ],
        "results": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qdrant-url", default="http://localhost:6333")
    parser.add_argument("--output", type=Path, default=ROOT / "results.json")
    parser.add_argument(
        "--provider", choices=["both", "mock", "sentence_transformers"], default="both"
    )
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    corpus = json.loads((ROOT / "corpus.json").read_text())
    questions = json.loads((ROOT / "questions.json").read_text())
    assert len(questions) >= 30
    assert all(
        set(q["relevant_document_ids"]) <= {d["id"] for d in corpus} for q in questions
    )
    report = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "corpus_sha256": hashlib.sha256(
            (ROOT / "corpus.json").read_bytes()
        ).hexdigest(),
        "questions_sha256": hashlib.sha256(
            (ROOT / "questions.json").read_bytes()
        ).hexdigest(),
        "providers": {},
    }
    failed = False
    for name in ["mock", "sentence_transformers"]:
        if args.provider not in ["both", name]:
            continue
        start = perf_counter()
        try:
            provider = (
                MockEmbeddingProvider()
                if name == "mock"
                else create_embedding_provider(get_settings())
            )
            if (
                name == "sentence_transformers"
                and provider.identity["provider"] != name
            ):
                raise ValueError(
                    "Real benchmark requires EMBEDDING_PROVIDER=sentence_transformers"
                )
            initialization_ms = (perf_counter() - start) * 1000
            result = evaluate(
                provider, corpus, questions, args.qdrant_url, args.repeats
            )
            result["initialization_ms"] = initialization_ms
        except Exception as exc:
            failed = True
            result = {"status": "blocked", "error": str(exc)}
        report["providers"][name] = result
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(name, json.dumps({k: v for k, v in result.items() if k != "results"}))
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
