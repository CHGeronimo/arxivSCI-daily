from __future__ import annotations

import logging
import time
from typing import Generator, List, Set

import httpx

from backend.crawler.models import Paper

logger = logging.getLogger(__name__)

S2_AUTHOR_SEARCH = "https://api.semanticscholar.org/graph/v1/author/search"
S2_AUTHOR_PAPERS = "https://api.semanticscholar.org/graph/v1/author"
S2_PAPER_FIELDS = "title,abstract,authors,year,venue,citationCount,externalIds,publicationDate"


def search_authors(query: str, limit: int = 10) -> List[dict]:
    """Search S2 for authors matching query. Returns list of author dicts."""
    params = {"query": query, "limit": limit, "fields": "name,affiliations,paperCount,externalIds"}
    for attempt in range(3):
        try:
            resp = httpx.get(S2_AUTHOR_SEARCH, params=params, timeout=15)
            if resp.status_code == 429:
                logger.warning("S2 作者搜索被限流")
                time.sleep(2)
                continue
            resp.raise_for_status()
            return resp.json().get("data") or []
        except Exception as e:
            logger.warning(f"S2 作者搜索第 {attempt+1}/3 次尝试失败: {e}")
            if attempt < 2:
                time.sleep(1)
    return []


def get_author_papers(
    author_id: str,
    limit: int = 100,
    year_from: int = 2024,
) -> List[dict]:
    """Fetch papers by a specific S2 author."""
    url = f"{S2_AUTHOR_PAPERS}/{author_id}/papers"
    params = {
        "fields": S2_PAPER_FIELDS,
        "limit": min(limit, 100),
        "year": f"{year_from}-",
    }
    for attempt in range(3):
        try:
            resp = httpx.get(url, params=params, timeout=30)
            if resp.status_code == 429:
                logger.warning(f"S2 作者论文被限流: {author_id}")
                time.sleep(2)
                continue
            resp.raise_for_status()
            return resp.json().get("data") or []
        except Exception as e:
            logger.warning(f"S2 作者论文第 {attempt+1}/3 次尝试失败: {e}")
            if attempt < 2:
                time.sleep(1)
    return []


def _parse_paper(item: dict) -> Paper | None:
    paper_id = item.get("paperId") or ""
    title = item.get("title") or ""
    if not title:
        return None

    abstract = item.get("abstract") or ""
    authors: List[str] = [
        a["name"] for a in (item.get("authors") or []) if a.get("name")
    ]

    external_ids = item.get("externalIds") or {}
    doi = external_ids.get("DOI") or ""
    arxiv_id = external_ids.get("ArXiv") or ""
    paper_id_final = doi or paper_id

    url = f"https://www.semanticscholar.org/paper/{paper_id}" if paper_id else ""
    pdf = f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else ""

    venue = item.get("venue") or ""
    citation_count = item.get("citationCount") or 0
    pub_date = item.get("publicationDate") or ""
    year = item.get("year")
    if not pub_date and year is not None:
        pub_date = f"{year}-01-01"

    return Paper(
        id=paper_id_final,
        source="author_s2",
        title=title,
        summary=abstract,
        authors=authors,
        categories=[],
        doi=doi,
        published_date=pub_date,
        url=url,
        pdf=pdf,
        venue=venue,
        citation_count=citation_count if isinstance(citation_count, int) else 0,
    )


class AuthorCrawler:
    """Crawl papers from subscribed authors via S2 Author API."""

    def __init__(
        self,
        authors: List[dict],
        papers_per_author: int = 50,
        year_from: int = 2024,
    ):
        self.authors = authors
        self.papers_per_author = papers_per_author
        self.year_from = year_from

    def crawl_iter(self) -> Generator[Paper, None, None]:
        seen_ids: Set[str] = set()

        for author in self.authors:
            author_id = author.get("authorId", "")
            author_name = author.get("name", "")
            if not author_id:
                continue

            logger.info(f"获取作者论文: {author_name} ({author_id})")
            items = get_author_papers(
                author_id,
                limit=self.papers_per_author,
                year_from=self.year_from,
            )

            count = 0
            for item in items:
                paper = _parse_paper(item)
                if paper and paper.id not in seen_ids:
                    seen_ids.add(paper.id)
                    yield paper
                    count += 1

            logger.info(f"作者 {author_name}: {count} 篇论文")
            time.sleep(0.5)

    def crawl(self) -> List[Paper]:
        return list(self.crawl_iter())


def infer_author_domains(author_name: str, conn=None) -> list:
    """从论文库推断作者研究领域：分析其论文的 categories + venue + AI 关键词。

    返回最多 3 个领域标签（如 "cs.MA 多智能体"、"网络安全"）。
    """
    import json as _json
    if conn is None:
        from backend.db import get_conn
        conn = get_conn()

    # 在 papers 表的 authors JSON 数组中匹配
    rows = conn.execute("""
        SELECT p.categories, p.venue, p.source,
               a.tldr, a.method
        FROM papers p
        LEFT JOIN ai_results a ON p.id = a.paper_id
        WHERE p.authors LIKE ?
        ORDER BY p.created_at DESC LIMIT 20
    """, (f'%"{author_name}"%',)).fetchall()

    if not rows:
        return []

    # 统计 arXiv 分类
    cat_counter: dict = {}
    for r in rows:
        cats = r["categories"]
        if isinstance(cats, str):
            try:
                cats = _json.loads(cats)
            except (ValueError, TypeError):
                cats = []
        for c in (cats or []):
            if isinstance(c, str) and c.startswith("cs."):
                cat_counter[c] = cat_counter.get(c, 0) + 1

    # 常见领域中文映射
    CAT_LABELS = {
        "cs.MA": "多智能体", "cs.GT": "博弈论", "cs.LG": "机器学习",
        "cs.AI": "人工智能", "cs.CL": "自然语言", "cs.CV": "计算机视觉",
        "cs.CR": "网络安全", "cs.SY": "控制系统", "cs.RO": "机器人",
        "cs.DC": "分布式", "cs.NI": "网络", "cs.HC": "人机交互",
        "eess.SP": "信号处理", "eess.SY": "电子系统", "math.OC": "优化",
    }

    domains = []
    # 按出现频次取 top 3
    for cat, cnt in sorted(cat_counter.items, key=lambda x: -x[1])[:3] if hasattr(cat_counter, 'items') else sorted(cat_counter.items(), key=lambda x: -x[1])[:3]:
        label = CAT_LABELS.get(cat, cat)
        if label not in domains:
            domains.append(label)

    # 如果没有 arXiv 分类，从 venue 推断
    if not domains:
        venues = {r["venue"] or "" for r in rows}
        for v in venues:
            v_lower = v.lower()
            if "security" in v_lower and "网络安全" not in domains:
                domains.append("网络安全")
            elif "machine learn" in v_lower or "neural" in v_lower:
                if "机器学习" not in domains: domains.append("机器学习")
            elif "multi-agent" in v_lower or "distributed" in v_lower:
                if "多智能体" not in domains: domains.append("多智能体")
            if len(domains) >= 3:
                break

    return domains[:3]


def enrich_author_info(author_id: str, author_name: str) -> dict:
    """丰富作者信息：S2 详情 + 领域推断。返回补充的字段。"""
    extra = {"domains": [], "homepage": "", "affiliation": ""}

    # 1. S2 详情（affiliations 常为空但试一下）
    try:
        url = f"{S2_AUTHOR_PAPERS}/{author_id}"
        resp = httpx.get(url.replace("/papers", ""),
                        params={"fields": "name,affiliations,homepage"}, timeout=10)
        if resp.status_code == 200:
            d = resp.json()
            affs = d.get("affiliations") or []
            if affs:
                extra["affiliation"] = affs[0]
            extra["homepage"] = d.get("homepage") or ""
    except Exception:
        pass

    # 2. 从论文库推断领域
    extra["domains"] = infer_author_domains(author_name)

    return extra


def resolve_orcid_to_author(orcid_id: str) -> dict | None:
    """Resolve an ORCID ID to an S2 author via name lookup.

    Fetches name from ORCID public API, then searches S2 for matching author.
    Returns S2 author dict or None.
    """
    orcid_id = orcid_id.strip().replace("https://orcid.org/", "")
    try:
        resp = httpx.get(
            f"https://pub.orcid.org/v3.0/{orcid_id}",
            headers={"Accept": "application/json"},
            timeout=15,
        )
        if resp.status_code != 200:
            logger.warning(f"ORCID 查询失败: {orcid_id}: {resp.status_code}")
            return None
        data = resp.json()
        person = data.get("person", {}).get("name", {})
        given = person.get("given-names", {}).get("value", "")
        family = person.get("family-name", {}).get("value", "")
        full_name = f"{given} {family}".strip()
        if not full_name:
            return None

        # Search S2 with the name
        results = search_authors(full_name, limit=5)
        for r in results:
            ext = r.get("externalIds") or {}
            if ext.get("ORCID") == orcid_id:
                r["_orcid"] = orcid_id
                return r
            if ext.get("DBLP"):
                for dblp_name in ext["DBLP"]:
                    if dblp_name.lower() == full_name.lower():
                        r["_orcid"] = orcid_id
                        return r
        # Fallback: return first result if only one good match
        if results:
            best = results[0]
            best["_orcid"] = orcid_id
            return best
    except Exception as e:
        logger.warning(f"ORCID 解析失败: {e}")
    return None
