"""Tests for hybrid RAG retrieval."""

from __future__ import annotations

import pytest

from investment_agent.agents.narrative.ingest import NewsArticle
from investment_agent.agents.narrative.rag import (
    _rrf_fuse,
    retrieve_articles,
)


def _article(article_id: str, title: str, summary: str = "") -> NewsArticle:
    return NewsArticle(
        id=article_id,
        title=title,
        summary=summary or title,
        url=f"https://example.com/{article_id}",
        source="test",
    )


def test_rrf_fuse_combines_two_rankings() -> None:
    a = _article("a", "rates fed inflation")
    b = _article("b", "ai semiconductor earnings")
    c = _article("c", "oil energy geopolitics")
    fused = _rrf_fuse(
        [
            [a, b, c],
            [c, b, a],
        ],
        k=60,
        top_k=3,
    )
    assert [x.id for x in fused] == ["a", "c", "b"]
    top2 = _rrf_fuse([[a, b, c], [c, b, a]], k=60, top_k=2)
    assert len(top2) == 2
    assert top2[0].id != top2[1].id


def test_retrieve_lexical_only_when_hybrid_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RAG_HYBRID", "0")
    articles = [
        _article("1", "Fed raises rates", "inflation policy"),
        _article("2", "Tech earnings beat", "ai cloud software"),
    ]
    out = retrieve_articles(articles, "fed inflation rates", top_k=1)
    assert len(out) == 1
    assert out[0].id == "1"


def test_retrieve_hybrid_uses_rrf_when_embeddings_mocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RAG_HYBRID", "1")

    articles = [
        _article("lex", "fed ecb rates inflation", "policy"),
        _article("emb", "sports weather travel", "leisure"),
        _article("both", "fed ai rates semiconductor", "mixed"),
    ]

    def fake_embedding_scores(arts, query, *, model_name: str):
        return [(1.0, arts[1]), (0.5, arts[2]), (0.1, arts[0])]

    monkeypatch.setattr(
        "investment_agent.agents.narrative.rag._embedding_scores",
        fake_embedding_scores,
    )

    out = retrieve_articles(articles, "fed inflation rates", top_k=2)
    assert len(out) == 2
    ids = {a.id for a in out}
    assert "emb" in ids or "both" in ids


def test_retrieve_falls_back_to_lexical_on_embedding_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RAG_HYBRID", "1")

    articles = [
        _article("1", "Fed inflation", "rates"),
        _article("2", "Cricket scores", "sports"),
    ]

    def boom(*args, **kwargs):
        raise RuntimeError("no model")

    monkeypatch.setattr(
        "investment_agent.agents.narrative.rag._embedding_scores",
        boom,
    )

    out = retrieve_articles(articles, "fed inflation", top_k=1)
    assert out[0].id == "1"
