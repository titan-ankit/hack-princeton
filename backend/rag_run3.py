# rag_run.py
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

# Load backend/.env if present
load_dotenv()

# Import your project's Storage (which provides .rag)
from load import Storage


# ----------------------------
# Configuration
# ----------------------------
ABSOLUTE_DEFAULT = "/Users/ankitwalishetti/Desktop/Ankit Programming/hack-princeton/backend/faiss_index"
FAISS_PATH = os.getenv("FAISS_INDEX_PATH") or ABSOLUTE_DEFAULT

# 5 categories from your UI (no "Other")
CATEGORIES: List[Dict[str, str]] = [
    {
        "name": "Housing & Development",
        "query": (
            "Recent state actions on housing supply, zoning reform, tenant protections, "
            "permitting streamlining, ADUs, and homelessness interventions in the last 6–12 months."
        ),
    },
    {
        "name": "Education Funding & Property Tax",
        "query": (
            "School finance reforms, property tax changes, equalization formulas, "
            "categorical aid shifts, accountability funding, and teacher pay proposals this year."
        ),
    },
    {
        "name": "Environment & Climate",
        "query": (
            "State-level climate bills, decarbonization plans, resilience funding, "
            "emissions standards, wildfire mitigation, and environmental justice actions this quarter."
        ),
    },
    {
        "name": "Infrastructure & Energy",
        "query": (
            "Grid modernization, transmission siting, broadband expansion, transportation funding, "
            "EV charging buildout, and utility regulation changes in the last 90–180 days."
        ),
    },
    {
        "name": "Civic & Electoral Reform",
        "query": (
            "AI in elections, deepfake disclosures, voting access, mail-in voting processes, "
            "election security, redistricting oversight, and public transparency measures recently."
        ),
    },
]

CITATIONS_PER_ARTICLE = 5
DOC_SLICE_SIZE = 8  # how many top docs to consider when building an article
OPENAI_MODEL_DEFAULT = os.getenv("RAG_MODEL") or "gpt-4o-mini"


# ----------------------------
# Metadata helpers
# ----------------------------
META_URL_KEYS = [
    "source_url", "url", "document_url", "page_url", "permalink", "href", "link",
    "web_url", "bill_url", "pdf_url", "html_url", "source"
]
META_TITLE_KEYS = [
    "title", "doc_title", "heading", "name", "filename", "file_name", "document_title", "id", "slug"
]
META_DATE_KEYS = ["journal_date", "date", "published", "pub_date", "created", "updated_at"]


def _first(meta: Dict[str, Any], keys: List[str]) -> Optional[str]:
    for k in keys:
        v = meta.get(k)
        if v not in (None, ""):
            return str(v)
    return None


def _fmt_date(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    # tolerate ISO-ish
    try:
        return s[:10]
    except Exception:
        return s


def _slug_title(meta: Dict[str, Any], fallback: str) -> str:
    # Prefer explicit titles
    t = _first(meta, META_TITLE_KEYS)
    if t:
        return t

    # Derive from filename-like fields
    fn = meta.get("file_name") or meta.get("filename") or meta.get("source") or ""
    if fn:
        base = os.path.basename(str(fn))
        base = re.sub(r"\.[A-Za-z0-9]+$", "", base)
        pretty = base.replace("_", " ").strip()
        pretty = re.sub(r"(\d{4}-\d{2}-\d{2})[_-](\d{2})[-:](\d{2})", r"\1 \2:\3", pretty)
        return pretty or fallback

    return fallback


def _ensure_index(path: str) -> None:
    p = Path(path)
    if not p.exists() or not p.is_dir():
        raise FileNotFoundError(f"FAISS_INDEX_PATH not a directory: {path}")
    need = ["index.faiss", "index.pkl"]
    missing = [n for n in need if not (p / n).exists()]
    if missing:
        raise FileNotFoundError(f"FAISS index missing files in {path}: {missing}")


# ----------------------------
# Retrieval helpers (use Storage.rag first)
# ----------------------------
def _retrieve_with_rag(
    storage: Storage,
    query: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> List[Any]:
    date_range = [start_date or "", end_date or ""] if (start_date or end_date) else None
    try:
        result = storage.rag(question=query, schema=None, date_range=date_range)
        docs = result.get("documents", []) if isinstance(result, dict) else getattr(result, "documents", [])
        return docs or []
    except Exception:
        return []


def _fallback_vector_retrieve(storage: Storage, query: str, k: int = 50) -> List[Any]:
    vs = getattr(storage, "vector_store", None)
    if not vs:
        return []
    # Prefer MMR if available
    if hasattr(vs, "max_marginal_relevance_search"):
        try:
            return vs.max_marginal_relevance_search(query, k=min(k, 120), fetch_k=4 * k, lambda_mult=0.6)
        except Exception:
            pass
    if hasattr(vs, "similarity_search"):
        try:
            return vs.similarity_search(query, k=k)
        except Exception:
            pass
    return []


def _get_docs(storage: Storage, query: str, k: int = 50, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Any]:
    docs = _retrieve_with_rag(storage, query, start_date, end_date)
    if not docs:
        docs = _fallback_vector_retrieve(storage, query, k=k)
    # De-duplicate by (title,url)
    seen = set()
    uniq = []
    for d in docs:
        meta = getattr(d, "metadata", {}) or {}
        title = _slug_title(meta, "Doc")
        url = _first(meta, META_URL_KEYS) or _first(meta, ["source", "file_path", "path"]) or ""
        key = (title.strip(), str(url).strip())
        if key in seen:
            continue
        seen.add(key)
        uniq.append(d)
        if len(uniq) >= k:
            break
    return uniq


# ----------------------------
# Article building
# ----------------------------
def _summarize_text(text: str, max_chars: int = 450) -> str:
    if not text:
        return "No summary available."
    t = re.sub(r"\s+", " ", text).strip()
    if len(t) <= max_chars:
        return t
    return t[:max_chars].rstrip() + "…"


def _make_citations(docs: List[Any], cap: int) -> List[Dict[str, str]]:
    cites = []
    for i, d in enumerate(docs[:cap], start=1):
        meta = getattr(d, "metadata", {}) or {}
        title = _slug_title(meta, f"Doc {i}")
        date = _fmt_date(_first(meta, META_DATE_KEYS))
        url = _first(meta, META_URL_KEYS) or ""
        label = f"{title} ({date})" if date else title
        cites.append({"S": f"S{i}", "title": label, "url": url})
    return cites


def _snip(s: str, lines: int = 6) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    parts = s.splitlines()
    return "\n".join(parts[:lines])


def _llm_article(prompt: str, summary: str, docs: List[Any], citations: List[Dict[str, str]]) -> Optional[str]:
    """Optional: craft content with an LLM if OPENAI_API_KEY is set. Returns None on failure."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        snippets = []
        for i, d in enumerate(docs[:len(citations)], start=1):
            text = getattr(d, "page_content", None) or getattr(d, "content", None) or ""
            snippets.append({
                "sref": f"S{i}",
                "snippet": _snip(text, 12),
                "source": citations[i - 1]["title"],
                "url": citations[i - 1]["url"],
            })
        system = (
            "You write concise, non-markdown briefs for a civic news feed. "
            "Use ONLY the provided summary and snippets. Insert inline citations like [S1], [S2] "
            "whenever claims come from snippets. End with 3–5 short key takeaways."
        )
        user = {
            "task": prompt,
            "retrieval_summary": summary,
            "snippets": snippets,
            "sources": citations,
        }
        res = client.chat.completions.create(
            model=OPENAI_MODEL_DEFAULT,
            temperature=0.3,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
        )
        return (res.choices[0].message.content or "").strip()
    except Exception:
        return None


def _fallback_article(prompt: str, summary: str, docs: List[Any], citations: List[Dict[str, str]]) -> str:
    # Build a plain-text (non-markdown) article that is still readable and cites [S#]
    lines = []
    lines.append(summary if summary and summary != "No summary available." else f"Brief: {prompt}")
    # weave 3–4 mini paragraphs with snippets and citations
    for i, d in enumerate(docs[:4], start=1):
        txt = getattr(d, "page_content", None) or getattr(d, "content", None) or ""
        snip = _snip(txt, 5)
        if snip:
            lines.append(f"[S{i}] {snip}")
    lines.append("Key takeaways:")
    lines.append("- See sources for legislative specifics and dates.")
    content = "\n\n".join(lines).strip()
    return content


def _build_article_for_category(storage: Storage, category_name: str, base_query: str) -> Dict[str, Any]:
    # Category-specific query to diversify content
    seed_query = f"{category_name}: {base_query}"

    docs = _get_docs(storage, seed_query, k=DOC_SLICE_SIZE)
    # Compose a lightweight summary from the top doc text
    top_text = ""
    if docs:
        top_text = getattr(docs[0], "page_content", None) or getattr(docs[0], "content", None) or ""
    summary = _summarize_text(top_text)

    # Citations
    citations = _make_citations(docs, cap=CITATIONS_PER_ARTICLE)

    # Title tailored per category (avoid repeated generic phrasing)
    title = {
        "Housing & Development": "Zoning, Supply, and Permitting Updates",
        "Education Funding & Property Tax": "School Finance and Property Tax Changes",
        "Environment & Climate": "Decarbonization, Resilience, and EJ Actions",
        "Infrastructure & Energy": "Grid, Broadband, and Transport Funding Moves",
        "Civic & Electoral Reform": "Election Integrity, AI Disclosures, and Access",
    }.get(category_name, f"{category_name} — Recent Legislative Activity")

    # Try LLM; fallback to stitcher
    content = _llm_article(seed_query, summary, docs, citations) or _fallback_article(seed_query, summary, docs, citations)

    return {
        "title": title,
        "summary": summary,
        "content": content,
        "references": citations,
    }


# ----------------------------
# Orchestrator
# ----------------------------
def generate_feed() -> Dict[str, Any]:
    _ensure_index(FAISS_PATH)
    storage = Storage(path=FAISS_PATH, from_path=True)

    items = []
    used_categories = set()
    for cat in CATEGORIES:
        name = cat["name"]
        if name in used_categories:
            continue
        article = _build_article_for_category(storage, name, cat["query"])
        items.append({
            "category": name,
            "articles": [article],
        })
        used_categories.add(name)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "faiss_path": FAISS_PATH,
        "per_category": 1,
        "doc_slice_size": DOC_SLICE_SIZE,
        "citations_per_article": CITATIONS_PER_ARTICLE,
        "categories": items,
    }


# ----------------------------
# Main
# ----------------------------
if __name__ == "__main__":
    payload = generate_feed()
    print(json.dumps(payload, indent=2, ensure_ascii=False))