"""Shared article-text scraping, used by both the summary step
(fetch_and_notify.py) and the blog-post generator
(generate_blog_post.py) so there's one scrape implementation, not two."""

from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

FETCH_TIMEOUT = 15
USER_AGENT = "Mozilla/5.0 (compatible; securesein-pipeline/1.0)"


def fetch_article_text(url: str, max_chars: int) -> str:
    """Best-effort plain-text scrape. Returns "" on any failure so
    callers fall back to something else instead of crashing the run."""
    if not url:
        return ""
    try:
        response = requests.get(
            url,
            timeout=FETCH_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        )
        response.raise_for_status()
    except requests.RequestException:
        return ""

    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()[:max_chars]
