import hashlib
import logging
import os
from typing import Optional

from duckduckgo_search import DDGS

logger = logging.getLogger("prepq.retrieval")

CACHE_TTL_SECONDS = 3600  # 1 hour

SEARCH_QUERIES = [
    "{company} {role} interview experience 2025",
    "{company} {role} interview questions technical round India",
]


def _cache_key(company: str, role: str) -> str:
    raw = f"{company.lower().strip()}:{role.lower().strip()}"
    return f"ddg:{hashlib.sha256(raw.encode()).hexdigest()[:16]}"


async def _get_cached(key: str) -> Optional[str]:
    """Try to fetch cached search result from Upstash Redis."""
    try:
        from redis import asyncio as aioredis

        url = os.environ.get("UPSTASH_REDIS_URL", "")
        token = os.environ.get("UPSTASH_REDIS_TOKEN", "")
        if not url:
            return None

        if "upstash.io" in url and not url.startswith("redis"):
            host = url.replace("https://", "").replace("http://", "")
            redis_url = f"rediss://:{token}@{host}:6379"
        else:
            redis_url = url

        redis = aioredis.from_url(redis_url, decode_responses=True)
        result = await redis.get(key)
        await redis.aclose()
        return result
    except Exception as exc:
        logger.warning(f"Redis cache GET failed: {exc}")
        return None


async def _set_cached(key: str, value: str) -> None:
    """Cache search result in Upstash Redis with TTL."""
    try:
        from redis import asyncio as aioredis

        url = os.environ.get("UPSTASH_REDIS_URL", "")
        token = os.environ.get("UPSTASH_REDIS_TOKEN", "")
        if not url:
            return

        if "upstash.io" in url and not url.startswith("redis"):
            host = url.replace("https://", "").replace("http://", "")
            redis_url = f"rediss://:{token}@{host}:6379"
        else:
            redis_url = url

        redis = aioredis.from_url(redis_url, decode_responses=True)
        await redis.setex(key, CACHE_TTL_SECONDS, value)
        await redis.aclose()
    except Exception as exc:
        logger.warning(f"Redis cache SET failed: {exc}")


def _ddg_search(query: str, max_results: int = 5) -> list[dict]:
    """
    Runs a DuckDuckGo text search synchronously.
    Returns a list of result dicts with keys: title, href, body.
    """
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        return results
    except Exception as exc:
        logger.warning(f"DuckDuckGo search failed for '{query}': {exc}")
        return []


def _format_results(all_results: list[dict]) -> str:
    """Format DuckDuckGo results into a context block for the system prompt."""
    if not all_results:
        return ""

    lines = ["=== COMPANY INTERVIEW INTELLIGENCE ===\n"]
    seen_urls: set[str] = set()
    count = 0

    for result in all_results:
        url = result.get("href", "")
        title = result.get("title", "Unknown Source")
        body = result.get("body", "").strip()

        if not body or url in seen_urls:
            continue

        seen_urls.add(url)
        count += 1
        lines.append(f"[Source {count}] {title}")
        lines.append(f"URL: {url}")
        lines.append(f"\n{body[:800]}")  # Cap per-source at 800 chars
        lines.append("\n" + "─" * 60 + "\n")

        if count >= 5:
            break

    return "\n".join(lines) if count > 0 else ""


async def fetch_company_intel(company: str, role: str) -> str:
    """
    Fetches real interview data for a company+role combination via DuckDuckGo.
    No API key required. Results are cached in Redis for 1 hour.

    Returns a formatted string ready for injection into the system prompt.
    Returns empty string on any failure (graceful degradation).
    """
    cache_key = _cache_key(company, role)

    # Check cache first
    cached = await _get_cached(cache_key)
    if cached:
        logger.info(f"DDG cache hit for {company} {role}")
        return cached

    # Run searches (DDG is synchronous — run in thread pool to avoid blocking)
    import asyncio

    all_results: list[dict] = []

    for query_template in SEARCH_QUERIES:
        query = query_template.format(company=company, role=role)
        try:
            results = await asyncio.get_event_loop().run_in_executor(
                None, _ddg_search, query, 5
            )
            all_results.extend(results)
            logger.info(f"DDG returned {len(results)} results for: {query}")
        except Exception as exc:
            logger.error(f"DDG executor error: {exc}")

    if not all_results:
        return ""

    formatted = _format_results(all_results)

    if formatted:
        await _set_cached(cache_key, formatted)

    return formatted
