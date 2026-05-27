"""阶段 2.C：VectorStore Adapter（底层 primitive）测试。"""

from __future__ import annotations

import pytest
from app.vectorstores import InMemoryVectorStore, SQLiteVectorStore, VectorRecord


def _rec(chunk_id: str, task_id: str, emb: list[float], source_id: str = "s1") -> VectorRecord:
    return VectorRecord(
        chunk_id=chunk_id,
        source_id=source_id,
        task_id=task_id,
        embedding=emb,
        metadata={"m": chunk_id},
    )


def test_add_embeddings_and_similarity_top_k() -> None:
    store = InMemoryVectorStore()
    n = store.add_embeddings(
        [
            _rec("c1", "t1", [1.0, 0.0, 0.0]),
            _rec("c2", "t1", [0.9, 0.1, 0.0]),
            _rec("c3", "t1", [0.0, 1.0, 0.0]),
        ]
    )
    assert n == 3
    out = store.similarity_search([1.0, 0.0, 0.0], top_k=2)
    assert len(out) == 2
    assert out[0].chunk_id == "c1"
    assert out[0].score >= out[1].score


def test_result_fields_complete() -> None:
    store = InMemoryVectorStore()
    store.add_embeddings([_rec("c1", "t1", [1.0, 0.0])])
    out = store.similarity_search([1.0, 0.0], top_k=1)
    r = out[0]
    assert r.chunk_id == "c1"
    assert r.source_id == "s1"
    assert r.task_id == "t1"
    assert isinstance(r.score, float)
    assert r.metadata == {"m": "c1"}


def test_task_id_filter_isolation() -> None:
    store = InMemoryVectorStore()
    store.add_embeddings(
        [
            _rec("c1", "task_A", [1.0, 0.0]),
            _rec("c2", "task_B", [1.0, 0.0]),
        ]
    )
    out_a = store.similarity_search([1.0, 0.0], top_k=10, task_id="task_A")
    assert [x.chunk_id for x in out_a] == ["c1"]


def test_empty_store_returns_empty() -> None:
    store = InMemoryVectorStore()
    assert store.similarity_search([1.0, 0.0], top_k=3) == []


def test_top_k_non_positive_returns_empty() -> None:
    store = InMemoryVectorStore()
    store.add_embeddings([_rec("c1", "t", [1.0, 0.0])])
    assert store.similarity_search([1.0, 0.0], top_k=0) == []
    assert store.similarity_search([1.0, 0.0], top_k=-2) == []


def test_top_k_greater_than_candidates_returns_all() -> None:
    store = InMemoryVectorStore()
    store.add_embeddings([_rec("c1", "t", [1.0, 0.0]), _rec("c2", "t", [0.0, 1.0])])
    out = store.similarity_search([1.0, 0.0], top_k=99)
    assert len(out) == 2


def test_query_embedding_empty_raises() -> None:
    store = InMemoryVectorStore()
    store.add_embeddings([_rec("c1", "t", [1.0, 0.0])])
    with pytest.raises(ValueError, match="query embedding 不能为空"):
        store.similarity_search([], top_k=3)


def test_query_embedding_dimension_mismatch_raises() -> None:
    store = InMemoryVectorStore()
    store.add_embeddings([_rec("c1", "t", [1.0, 0.0])])
    with pytest.raises(ValueError, match="query embedding 维度不一致"):
        store.similarity_search([1.0, 0.0, 0.0], top_k=3)


def test_record_embedding_empty_raises() -> None:
    store = InMemoryVectorStore()
    with pytest.raises(ValueError, match="record embedding 不能为空"):
        store.add_embeddings([_rec("c1", "t", [])])


def test_record_embedding_dimension_mismatch_raises() -> None:
    store = InMemoryVectorStore()
    store.add_embeddings([_rec("c1", "t", [1.0, 0.0])])
    with pytest.raises(ValueError, match="record embedding 维度不一致"):
        store.add_embeddings([_rec("c2", "t", [1.0, 0.0, 0.0])])


def test_zero_vector_safe_no_divide_by_zero() -> None:
    store = InMemoryVectorStore()
    store.add_embeddings([_rec("c1", "t", [0.0, 0.0]), _rec("c2", "t", [1.0, 0.0])])
    out = store.similarity_search([0.0, 0.0], top_k=2)
    assert len(out) == 2
    assert all(x.score == 0.0 for x in out)


def test_duplicate_chunk_id_overwrites() -> None:
    store = InMemoryVectorStore()
    store.add_embeddings([_rec("same", "t", [1.0, 0.0], source_id="s1")])
    store.add_embeddings([_rec("same", "t", [0.0, 1.0], source_id="s2")])
    out = store.similarity_search([0.0, 1.0], top_k=5)
    assert len(out) == 1
    assert out[0].chunk_id == "same"
    assert out[0].source_id == "s2"


def test_delete_behavior() -> None:
    store = InMemoryVectorStore()
    store.add_embeddings([_rec("c1", "t", [1.0, 0.0]), _rec("c2", "t", [0.0, 1.0])])
    d = store.delete(["c1", "nope"])
    assert d == 1
    out = store.similarity_search([1.0, 0.0], top_k=5)
    assert [x.chunk_id for x in out] == ["c2"]


def test_delete_task_behavior() -> None:
    store = InMemoryVectorStore()
    store.add_embeddings([_rec("c1", "t1", [1.0, 0.0]), _rec("c2", "t2", [1.0, 0.0])])

    assert store.delete_task("t1") == 1
    out = store.similarity_search([1.0, 0.0], top_k=5)

    assert [x.chunk_id for x in out] == ["c2"]


def test_clear_behavior() -> None:
    store = InMemoryVectorStore()
    store.add_embeddings([_rec("c1", "t", [1.0, 0.0])])
    assert store.dimension == 2
    store.clear()
    assert store.dimension is None
    assert store.similarity_search([1.0, 0.0], top_k=3) == []


def test_sqlite_vector_store_persists_and_filters_by_task(tmp_path) -> None:
    path = tmp_path / "vectors.sqlite"
    store = SQLiteVectorStore(str(path))
    store.add_embeddings(
        [
            _rec("c1", "task_A", [1.0, 0.0], source_id="s1"),
            _rec("c2", "task_B", [0.0, 1.0], source_id="s2"),
        ]
    )

    reopened = SQLiteVectorStore(str(path))
    out = reopened.similarity_search([1.0, 0.0], top_k=5, task_id="task_A")

    assert reopened.dimension == 2
    assert [item.chunk_id for item in out] == ["c1"]
    assert out[0].metadata == {"m": "c1"}


def test_sqlite_vector_store_delete_task(tmp_path) -> None:
    store = SQLiteVectorStore(str(tmp_path / "vectors.sqlite"))
    store.add_embeddings([_rec("c1", "t1", [1.0, 0.0]), _rec("c2", "t2", [1.0, 0.0])])

    assert store.delete_task("t1") == 1

    assert store.similarity_search([1.0, 0.0], top_k=5, task_id="t1") == []
    assert [item.chunk_id for item in store.similarity_search([1.0, 0.0], top_k=5)] == ["c2"]


def test_sqlite_vector_store_rejects_dimension_mismatch_against_existing_store(tmp_path) -> None:
    store = SQLiteVectorStore(str(tmp_path / "vectors.sqlite"))
    store.add_embeddings([_rec("c1", "t1", [1.0, 0.0])])

    with pytest.raises(ValueError, match="record embedding 维度不一致"):
        store.add_embeddings([_rec("c2", "t1", [1.0, 0.0, 0.0])])
