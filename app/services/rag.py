import json
import math
import os
import re
from collections.abc import Iterable
from datetime import date, datetime, time, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Article, ArticleChunk

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
AI_ENABLED = bool(GEMINI_API_KEY or GROQ_API_KEY)
TOKEN_RE = re.compile(r"[a-z0-9_+.-]+", re.IGNORECASE)
STOP_WORDS = {
    "a", "about", "after", "all", "an", "and", "any", "are", "as", "at", "be", "been",
    "but", "by", "can", "could", "did", "do", "does", "for", "from", "have", "help", "how",
    "i", "in", "into", "is", "it", "me", "matching", "my", "no", "not", "of", "on", "or",
    "our", "please", "problem", "solution", "support", "system", "technical", "the", "their",
    "there", "this", "to", "what", "when", "where", "which", "why", "with", "would", "you",
    "your", "document", "exists",
}


def tokens(text: str) -> set[str]:
    return {token.lower() for token in TOKEN_RE.findall(text) if len(token) > 1} - STOP_WORDS


def lexical_score(query: str, article: Article) -> float:
    query_terms = tokens(query)
    if not query_terms:
        return 0.0
    title_terms = tokens(article.title)
    content_terms = tokens(f"{article.summary} {article.content} {article.tags} {article.error_code} {article.technology} {article.product}")
    title_match = len(query_terms & title_terms) / len(query_terms)
    body_match = len(query_terms & content_terms) / len(query_terms)
    exact_error = bool(article.error_code and article.error_code.lower() in query.lower())
    matched_terms = query_terms & content_terms
    if not exact_error and (
        (len(query_terms) > 1 and len(matched_terms) < 2)
        or (len(query_terms) == 1 and not query_terms & title_terms)
    ):
        return 0.0
    return min(1.0, body_match * 0.72 + title_match * 0.28 + (0.35 if exact_error else 0.0))


async def embed_text(text: str) -> list[float] | None:
    if not GEMINI_API_KEY:
        return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key={GEMINI_API_KEY}"
    payload = {"model": "models/gemini-embedding-001", "content": {"parts": [{"text": text[:12000]}]}}
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return response.json()["embedding"]["values"]
    except (httpx.HTTPError, KeyError, ValueError):
        return None


def cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        return 0.0
    denominator = math.sqrt(sum(value * value for value in left)) * math.sqrt(sum(value * value for value in right))
    return sum(a * b for a, b in zip(left, right)) / denominator if denominator else 0.0


def split_into_chunks(text: str, limit: int = 1100) -> list[str]:
    chunks = []
    current = ""
    for paragraph in text.splitlines():
        for word in paragraph.split():
            if current and len(current) + len(word) + 1 > limit:
                chunks.append(current)
                current = ""
            current = f"{current} {word}".strip()
    if current:
        chunks.append(current)
    return chunks


async def index_article(db: Session, article: Article) -> None:
    db.flush()
    article.chunks.clear()
    chunks = split_into_chunks(f"{article.title}\n{article.summary}\n{article.content}")
    article.chunks.extend(
        ArticleChunk(chunk_index=index, content=content)
        for index, content in enumerate(chunks)
    )
    db.flush()
    if not GEMINI_API_KEY or not chunks:
        return
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:batchEmbedContents?key={GEMINI_API_KEY}"
    requests = [
        {"model": "models/gemini-embedding-001", "content": {"parts": [{"text": text}]}}
        for text in chunks
    ]
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json={"requests": requests})
            response.raise_for_status()
            embeddings = response.json().get("embeddings", [])
        for chunk, result in zip(article.chunks, embeddings):
            chunk.embedding = json.dumps(result["values"])
    except (httpx.HTTPError, KeyError, ValueError):
        return


async def retrieve(
    db: Session,
    query: str,
    *,
    category: str | None = None,
    technology: str | None = None,
    product: str | None = None,
    error_code: str | None = None,
    difficulty: str | None = None,
    tag: str | None = None,
    date_after: str | None = None,
) -> list[tuple[Article, float]]:
    statement = select(Article)
    for field, value in (("category", category), ("technology", technology), ("product", product), ("difficulty", difficulty)):
        if value:
            statement = statement.where(getattr(Article, field).ilike(f"%{value}%"))
    if error_code:
        statement = statement.where(Article.error_code.ilike(f"%{error_code}%"))
    if tag:
        statement = statement.where(Article.tags.ilike(f"%{tag}%"))
    if date_after:
        try:
            since = datetime.combine(date.fromisoformat(date_after), time.min, tzinfo=timezone.utc)
        except ValueError:
            raise ValueError("date_after must use YYYY-MM-DD format") from None
        statement = statement.where(Article.created_at >= since)
    articles = db.scalars(statement).all()
    article_ids = [article.id for article in articles]
    chunks = db.scalars(select(ArticleChunk).where(ArticleChunk.article_id.in_(article_ids))).all() if article_ids else []
    chunks_by_article: dict[int, list[ArticleChunk]] = {}
    for chunk in chunks:
        chunks_by_article.setdefault(chunk.article_id, []).append(chunk)
    query_vector = await embed_text(query)
    ranked = []
    for article in articles:
        lexical = lexical_score(query, article)
        semantic = 0.0
        if query_vector:
            for chunk in chunks_by_article.get(article.id, []):
                if not chunk.embedding:
                    continue
                try:
                    semantic = max(semantic, cosine(query_vector, json.loads(chunk.embedding)))
                except (ValueError, TypeError):
                    continue
        score = (0.58 * semantic + 0.42 * lexical) if query_vector else lexical
        if score >= 0.055:
            ranked.append((article, score))
    return sorted(ranked, key=lambda item: item[1], reverse=True)[:6]


async def generate_answer(query: str, results: Iterable[tuple[Article, float]]) -> str:
    sources = list(results)
    if not sources:
        return "I couldn't find a reliable match in the knowledge base. Try adding an error code or product name, or open a support ticket so an agent can investigate."
    context = "\n\n".join(
        f"SOURCE {index}: {article.title}\n{article.content[:3500]}"
        for index, (article, _) in enumerate(sources, start=1)
    )
    prompt = (
        "Answer the user's technical question using only the provided sources. "
        "If they do not contain a reliable answer, say so. Use plain language and numbered steps. "
        "Do not invent commands or claim actions were performed. Cite source numbers like [1].\n\n"
        f"QUESTION: {query}\n\nSOURCES:\n{context}"
    )
    if GROQ_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=25) as client:
                response = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                    json={
                        "model": GROQ_MODEL,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.2,
                    },
                )
                response.raise_for_status()
                return response.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError, ValueError):
            pass
    if GEMINI_API_KEY:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
        try:
            async with httpx.AsyncClient(timeout=25) as client:
                response = await client.post(url, json={"contents": [{"parts": [{"text": prompt}]}]})
                response.raise_for_status()
                return response.json()["candidates"][0]["content"]["parts"][0]["text"]
        except (httpx.HTTPError, KeyError, IndexError, ValueError):
            pass
    article = sources[0][0]
    steps = [
        re.sub(r"^\d+[.)]\s*", "", line.strip(" -*\t"))
        for line in article.content.splitlines()
        if line.strip()
    ]
    context = [step for step in steps if step.lower().startswith("why it happens:")]
    actions = [step for step in steps if step not in context]
    answer = f"{article.summary or article.title}\n\n"
    if context:
        answer += "\n".join(context) + "\n\n"
    answer += "\n".join(f"{index}. {step}" for index, step in enumerate(actions[:6], start=1))
    return answer + "\n\nAnswer assembled from the matching knowledge article; add a Gemini API key for generated answers."
