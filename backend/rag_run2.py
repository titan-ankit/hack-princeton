# rag_run.py
from __future__ import annotations

import json
import os
import re
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
load_dotenv()

from load import Storage

# ============================
# Config
# ============================
ABSOLUTE_DEFAULT = "/Users/ankitwalishetti/Desktop/Ankit Programming/hack-princeton/backend/faiss_index"
FAISS_PATH = os.getenv("FAISS_INDEX_PATH") or ABSOLUTE_DEFAULT

PER_CATEGORY_DEFAULT = int(os.getenv("PER_CATEGORY_COUNT", "5"))
DOCS_PER_ARTICLE = int(os.getenv("DOCS_PER_ARTICLE", "8"))
CITATIONS_PER_ARTICLE = int(os.getenv("CITATIONS_PER_ARTICLE", "5"))

FEED_SHUFFLE = os.getenv("FEED_SHUFFLE", "1").lower() in ("1", "true", "yes")
seed_env = os.getenv("FEED_SEED")
if seed_env:
    try:
        random.seed(int(seed_env))
    except Exception:
        random.seed(seed_env)

# Default categories for your UI (no "Other")
DEFAULT_FEED_CATEGORIES = [
    "Housing & Development",
    "Education Funding & Property Tax",
    "Taxes & Economic Policy",
    "Environment & Climate",
    "Workforce & Labor",
    "Healthcare & Mental Health",
    "Public Safety & Justice",
    "Infrastructure & Energy",
    "Civic & Electoral Reform",
]

# Extraction keys
META_URL_KEYS = [
    "source_url", "url", "document_url", "page_url", "permalink", "href", "link",
    "web_url", "bill_url", "pdf_url", "html_url", "source"
]
META_DATE_KEYS = ["journal_date", "date", "published", "pub_date", "created", "updated_at"]
META_TITLE_FALLBACK_KEYS = ["title", "doc_title", "filename", "name", "heading", "document_title", "id", "doc_id", "slug"]
META_BUCKET_KEYS = ["committee", "committee_name", "chamber", "body", "agency", "department", "subject", "topic", "category"]

# ============================
# Helpers
# ============================
def _ensure_index(path: str) -> None:
    p = Path(path)
    if not p.exists() or not p.is_dir():
        raise FileNotFoundError(f"FAISS_INDEX_PATH not a directory: {path}")
    missing = [name for name in ("index.faiss", "index.pkl") if not (p / name).exists()]
    if missing:
        raise FileNotFoundError(f"Missing files in {path}: {missing}")

def _first_meta(meta: Dict[str, Any], keys: List[str]) -> Optional[str]:
    for k in keys:
        v = meta.get(k)
        if v not in (None, ""):
            return str(v)
    return None

def _format_date(d: Optional[str]) -> Optional[str]:
    if not d: return None
    try:
        return datetime.fromisoformat(d[:10]).date().isoformat()
    except Exception:
        return d

def _slug_to_title(s: str) -> str:
    base = Path(str(s)).name
    base = re.sub(r"\.[A-Za-z0-9]+$", "", base)
    pretty = base.replace("_", " ").strip()
    # Only fix HH-MM to HH:MM (keep YYYY-MM-DD intact)
    pretty = re.sub(r"(?<=\b)(\d{2})-(\d{2})(?=\b)", r"\1:\2", pretty)
    pretty = re.sub(r"(\d{4}-\d{2}-\d{2})\s+(\d{2})-(\d{2})", r"\1 \2:\3", pretty)
    return pretty or "Untitled"

def _compose_title(meta: Dict[str, Any], i: int) -> str:
    fn = meta.get("file_name")
    if fn: return _slug_to_title(str(fn))
    chamber = meta.get("chamber"); bill = meta.get("bill_number")
    if chamber or bill:
        return " — ".join([p for p in [chamber, bill] if p])
    summary = meta.get("act_summary")
    if summary:
        s = str(summary).strip()
        return s if len(s) <= 80 else s[:77] + "…"
    fb = _first_meta(meta, META_TITLE_FALLBACK_KEYS)
    return fb or f"Doc {i}"

def _file_uri_if_path(s: str) -> str:
    try:
        p = Path(s)
        return p.resolve().as_uri() if p.exists() else s
    except Exception:
        return s

def _url_host(meta: Dict[str, Any]) -> str:
    url = _first_meta(meta, META_URL_KEYS) or ""
    m = re.match(r"^https?://([^/]+)/", url)
    return m.group(1).lower() if m else ""

def _mmr_retrieve(
    storage: Storage,
    query: str,
    k: int = 120,
    fetch_k: int = 400,
    lambda_mult: float = 0.6,
    date_range: Optional[List[str]] = None,
) -> List[Any]:
    """
    Primary: use Storage.rag(...) from load.py to fetch retrieved documents, so we stay
    consistent with the project's built-in RAG pipeline (date filtering, prompt context, etc.).

    Fallback: if rag() returns nothing or errors, fall back to the vector store's MMR/similarity.
    """
    # --- Primary path: your built-in RAG ---
    try:
        result = storage.rag(question=query, schema=None, date_range=date_range)
        docs = result.get("documents", []) if isinstance(result, dict) else getattr(result, "documents", [])
        if docs:
            # Keep at most k for downstream steps
            return list(docs[:k]) if k else docs
    except Exception:
        pass  # fall back below

    # --- Fallback path: use the vector store directly ---
    vs = getattr(storage, "vector_store", None)
    if vs and hasattr(vs, "max_marginal_relevance_search"):
        try:
            return vs.max_marginal_relevance_search(query, k=k, fetch_k=fetch_k, lambda_mult=lambda_mult)
        except Exception:
            pass
    if vs and hasattr(vs, "similarity_search"):
        try:
            return vs.similarity_search(query, k=k)
        except Exception:
            pass

    return []

def _dedupe_docs(docs: List[Any]) -> List[Any]:
    seen: set[Tuple[str, str]] = set()
    out: List[Any] = []
    for d in docs:
        meta = getattr(d, "metadata", {}) or {}
        urlish = (
            meta.get("source_url") or meta.get("url") or meta.get("document_url") or
            meta.get("page_url") or meta.get("source") or meta.get("file_path") or
            meta.get("filepath") or meta.get("path") or ""
        )
        date = str(meta.get("journal_date") or meta.get("date") or "")
        key = (str(urlish), date)
        if key in seen: continue
        seen.add(key)
        out.append(d)
    return out

def _select_diverse_slice(docs: List[Any], max_items: int, host_cap: int = 2) -> List[Any]:
    chosen = []
    per_host: Dict[str, int] = defaultdict(int)
    seen_urls: set[str] = set()
    for d in docs:
        meta = getattr(d, "metadata", {}) or {}
        url = _first_meta(meta, META_URL_KEYS) or ""
        host = _url_host(meta)
        key = url.strip() or (meta.get("source") or meta.get("file_path") or "")
        if key in seen_urls: continue
        if host and per_host[host] >= host_cap: continue
        chosen.append(d)
        seen_urls.add(key)
        if host: per_host[host] += 1
        if len(chosen) >= max_items: break
    return chosen

# ============================
# Bucketing & themes
# ============================
def _url_host_and_section(meta: Dict[str, Any]) -> Tuple[str, str]:
    url = _first_meta(meta, META_URL_KEYS) or ""
    host = section = ""
    try:
        m = re.match(r"^https?://([^/]+)/([^/?#]+)", url)
        if m:
            host = m.group(1)
            section = m.group(2)
            section = re.sub(r"[_-]?\d{4}-\d{2}-\d{2}.*$", "", section)
    except Exception:
        pass
    return host, section

def _bill_prefix(meta: Dict[str, Any]) -> Optional[str]:
    bill = (meta.get("bill_number") or "").strip()
    if not bill: return None
    m = re.match(r"^([A-Za-z]+)", bill.replace(" ", ""))
    return m.group(1).upper() if m else None

def _subtopic_key_and_label(meta: Dict[str, Any]) -> Tuple[str, str]:
    for k in META_BUCKET_KEYS:
        val = meta.get(k)
        if val:
            return (f"meta:{k}:{val}", str(val))
    bp = _bill_prefix(meta)
    if bp: return (f"billprefix:{bp}", f"{bp} Bills")
    host, section = _url_host_and_section(meta)
    if host and section: return (f"url:{host}:{section}", f"{section} ({host})")
    if host: return (f"url:{host}", host)
    return ("general", "General")

def _build_buckets(docs: List[Any]) -> List[Tuple[str, str, List[Any]]]:
    buckets: Dict[str, Dict[str, Any]] = {}
    for d in docs:
        meta = getattr(d, "metadata", {}) or {}
        key, label = _subtopic_key_and_label(meta)
        buckets.setdefault(key, {"label": label, "docs": []})["docs"].append(d)
    items = [(k, v["label"], v["docs"]) for k, v in buckets.items()]
    items.sort(key=lambda t: len(t[2]), reverse=True)
    return items

_THEME_MAP = [
    ("AI in Elections", r"election|ballot|campaign|candidate|synthetic media|deep ?fake|FEC|disclosure.*election"),
    ("Education & Schools", r"\bschool|student|district|teacher|curriculum|K-12|university|board of education"),
    ("Healthcare & Telehealth", r"health|hospital|medicaid|insurance|patient|clinical|telehealth"),
    ("Government Use & Procurement", r"procure|vendor|RFP|inventory|governance framework|agency use|model policy|policy act"),
    ("Public Safety & Justice", r"police|criminal|justice|court|sheriff|attorney|fraud|forensic"),
    ("Workforce & Labor", r"workforce|labor|jobs|unemployment|hiring|training"),
    ("Privacy & Data Governance", r"privacy|biometric|face|facial|dataset|surveillance|data governance|watermark"),
    ("Cybersecurity", r"cyber|ransom|threat|breach|intrusion|attack"),
    ("AI Oversight Bodies", r"task force|commission|council|committee|office of artificial intelligence|study committee"),
    ("Consumer Protection & Transparency", r"disclosure|label|watermark|deceptive|impersonation|notice"),
]

def _infer_theme_label(docs_slice: List[Any], fallback_label: str) -> str:
    text = " ".join(
        (getattr(d, "page_content", None) or getattr(d, "content", None) or "")
        for d in docs_slice[:DOCS_PER_ARTICLE]
    ).lower()
    for theme, pattern in _THEME_MAP:
        if re.search(pattern, text):
            return theme
    return re.sub(r"\s*\([^)]*\)\s*$", "", fallback_label).strip() or "General"

# ============================
# Content (plain text, JSON-friendly)
# ============================
def _make_summary(text: str, max_chars: int = 400) -> str:
    if not text:
        return "No summary returned."
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    s = " ".join(parts[:3]) or text.strip()
    if len(s) > max_chars:
        s = s[:max_chars].rstrip() + "..."
    return s

def _build_cited_sources(docs_slice: List[Any], max_citations: int) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for i, d in enumerate(docs_slice[:max_citations], start=1):
        meta = getattr(d, "metadata", {}) or {}
        url = _first_meta(meta, META_URL_KEYS)
        if not url:
            path_like = _first_meta(meta, ["source", "file_path", "filepath", "path", "pdf_path"])
            if path_like:
                url = _file_uri_if_path(path_like)
        title = _compose_title(meta, i)
        date  = _format_date(_first_meta(meta, META_DATE_KEYS))
        label = f"{title} ({date})" if date else title
        out.append({"S": f"S{i}", "title": label, "url": url or ""})
    return out

def _stitch_plain_text(topic: str, theme: str, docs_slice: List[Any], summary: str, max_citations: int) -> str:
    parts: List[str] = []
    parts.append(f"Theme: {theme}")
    parts.append(f"Category: {topic}")
    parts.append(f"Summary: {summary}")
    parts.append("Synthesis: Focused findings for this theme based on retrieved materials.")
    for i, d in enumerate(docs_slice[:max_citations], start=1):
        text = (getattr(d, "page_content", None) or getattr(d, "content", None) or "").strip()
        if not text: continue
        excerpt = " ".join(text.split())
        if len(excerpt) > 420: excerpt = excerpt[:420].rstrip() + "..."
        parts.append(f"[S{i}] {excerpt}")
    parts.append("Key Takeaways:")
    parts.append("- This article emphasizes the selected theme; see references for context.")
    parts.append("- Inline markers [S#] map to the numbered items in references.")
    return "\n".join(parts)

def _article_with_citations_plain(topic: str, theme: str, summary: str, docs_slice: List[Any],
                                  cited_sources: List[Dict[str, str]], model_hint: Optional[str]) -> Optional[str]:
    try:
        from openai import OpenAI
    except Exception:
        return None
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return None
    snippets = []
    for i, d in enumerate(docs_slice[:len(cited_sources)], start=1):
        meta = getattr(d, "metadata", {}) or {}
        title = _compose_title(meta, i)
        url = cited_sources[i-1]["url"] if i - 1 < len(cited_sources) else ""
        text = (getattr(d, "page_content", None) or getattr(d, "content", None) or "")[:1500]
        snippets.append({"sref": f"S{i}", "title": title, "url": url, "snippet": text})
    system = (
        "Write a clear, plain-text briefing (no markdown). "
        "Focus tightly on the provided THEME within the given CATEGORY. "
        "Use ONLY the provided summary and snippets. "
        "Insert inline citations like [S1], [S2] tied to snippets. "
        "If unsupported by snippets, say you don't know. "
        "End with 'Key Takeaways:' lines."
    )
    user = {
        "category": topic,
        "theme": theme,
        "retrieval_summary": summary,
        "snippets": snippets,
        "sources": cited_sources,
    }
    try:
        client = OpenAI(api_key=key)
        model = model_hint or os.getenv("RAG_MODEL") or "gpt-4o-mini"
        res = client.chat.completions.create(
            model=model,
            temperature=0.25,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user)},
            ],
        )
        return res.choices[0].message.content.strip()
    except Exception:
        return None

def _article_json_from_slice(base_category: str, bucket_label: str, docs_slice: List[Any],
                             seed_summary: str, use_llm: bool, model_hint: Optional[str]) -> Dict[str, Any]:
    theme = _infer_theme_label(docs_slice, bucket_label)
    cited_sources = _build_cited_sources(docs_slice, max_citations=CITATIONS_PER_ARTICLE)
    slice_text = " ".join(
        (getattr(d, "page_content", None) or getattr(d, "content", None) or "")
        for d in docs_slice[:CITATIONS_PER_ARTICLE]
    )
    local_summary = _make_summary(slice_text) if slice_text.strip() else _make_summary(seed_summary)
    content = None
    if use_llm:
        content = _article_with_citations_plain(base_category, theme, local_summary, docs_slice, cited_sources, model_hint)
    if not content:
        content = _stitch_plain_text(base_category, theme, docs_slice, local_summary, CITATIONS_PER_ARTICLE)
    return {
        "title": theme,              # theme becomes the article title (unique & readable)
        "summary": local_summary,
        "content": content,
        "references": cited_sources,
    }

# ============================
# Category runner
# ============================
def _build_buckets(docs: List[Any]) -> List[Tuple[str, str, List[Any]]]:
    buckets: Dict[str, Dict[str, Any]] = {}
    for d in docs:
        meta = getattr(d, "metadata", {}) or {}
        key, label = _subtopic_key_and_label(meta)
        buckets.setdefault(key, {"label": label, "docs": []})["docs"].append(d)
    items = [(k, v["label"], v["docs"]) for k, v in buckets.items()]
    items.sort(key=lambda t: len(t[2]), reverse=True)
    return items

def run_category(base_category: str, per_category: int, start_date: Optional[str],
                 end_date: Optional[str], use_llm: bool, model_hint: Optional[str]) -> Dict[str, Any]:
    _ensure_index(FAISS_PATH)
    storage = Storage(path=FAISS_PATH, from_path=True)

    # Broader query phrasing to steer retrieval toward state policy in that category
    query = f"{base_category} — recent state policy proposals, hearings, bills, and agency actions"
    pool = _mmr_retrieve(storage, query, k=200, fetch_k=600, lambda_mult=0.6)
    if not pool:
        date_range = [start_date or "", end_date or ""] if (start_date or end_date) else None
        result = storage.rag(question=query, schema=None, date_range=date_range)
        pool = result.get("documents", [])

    if not pool:
        return {"category": base_category, "articles": []}

    pool = _dedupe_docs(pool)
    buckets = _build_buckets(pool)
    if FEED_SHUFFLE:
        random.shuffle(buckets)
    picked = buckets[:per_category]

    seed_docs: List[Any] = []
    for _, _, docs_in_bucket in picked:
        seed_docs.extend(docs_in_bucket[: max(2, DOCS_PER_ARTICLE)])
    seed_text = " ".join(
        (getattr(d, "page_content", None) or getattr(d, "content", None) or "")
        for d in seed_docs
    )
    seed_summary = _make_summary(seed_text)

    articles: List[Dict[str, Any]] = []
    for key, bucket_label, docs_in_bucket in picked:
        if not docs_in_bucket:
            continue
        subquery = f"{base_category} — {bucket_label} — state bills, hearings, oversight, implementation details"
        sub_pool = _mmr_retrieve(storage, subquery, k=120, fetch_k=400, lambda_mult=0.6) or list(docs_in_bucket)
        sub_pool = _dedupe_docs(sub_pool)

        def _score(d):
            txt = (getattr(d, "page_content", None) or getattr(d, "content", None) or "").lower()
            return 0 if bucket_label.lower() in txt else 1
        sub_pool.sort(key=_score)

        slice_docs = _select_diverse_slice(sub_pool, DOCS_PER_ARTICLE, host_cap=2)
        if len(slice_docs) < DOCS_PER_ARTICLE:
            extra = _select_diverse_slice(docs_in_bucket, DOCS_PER_ARTICLE - len(slice_docs), host_cap=2)
            existing_ids = {id(x) for x in slice_docs}
            for d in extra:
                if id(d) not in existing_ids and len(slice_docs) < DOCS_PER_ARTICLE:
                    slice_docs.append(d)

        art = _article_json_from_slice(base_category, bucket_label, slice_docs, seed_summary, use_llm, model_hint)
        articles.append(art)

    # Ensure unique titles in a category
    seen = set()
    for a in articles:
        t = a["title"]; i = 2
        while t in seen:
            t = f"{a['title']} (Part {i})"; i += 1
        a["title"] = t; seen.add(t)

    return {"category": base_category, "articles": articles}

# ============================
# Feed runner
# ============================
def run_feed(categories: List[str], per_category: int, start_date: Optional[str], end_date: Optional[str],
             use_llm: bool, model_hint: Optional[str]) -> Dict[str, Any]:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "faiss_path": FAISS_PATH,
        "per_category": per_category,
        "doc_slice_size": DOCS_PER_ARTICLE,
        "citations_per_article": CITATIONS_PER_ARTICLE,
        "categories": [],
    }
    for cat in categories:
        payload["categories"].append(
            run_category(cat.strip(), per_category, start_date, end_date, use_llm, model_hint)
        )
    return payload

# ============================
# Script entry
# ============================
if __name__ == "__main__":
    # If FEED_CATEGORIES is set, use it (semicolon-separated). Otherwise default to your UI list.
    raw = os.getenv("FEED_CATEGORIES", "")
    if raw.strip():
        categories = [c for c in raw.split(";") if c.strip()]
    else:
        categories = list(DEFAULT_FEED_CATEGORIES)

    per_cat = int(os.getenv("PER_CATEGORY_COUNT", str(PER_CATEGORY_DEFAULT)))
    start = os.getenv("FEED_START_DATE")
    end   = os.getenv("FEED_END_DATE")
    use_llm = os.getenv("FEED_USE_LLM", "true").lower() in ("1", "true", "yes")
    model_hint = os.getenv("RAG_MODEL")

    feed = run_feed(categories, per_cat, start, end, use_llm, model_hint)
    print(json.dumps(feed, ensure_ascii=False, indent=2))