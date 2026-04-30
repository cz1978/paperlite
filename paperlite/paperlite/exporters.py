from __future__ import annotations

import json
import re
from html import escape

from paperlite.models import Paper


def to_json(papers: list[Paper]) -> str:
    return json.dumps([paper.to_dict() for paper in papers], ensure_ascii=False, indent=2)


def to_jsonl(papers: list[Paper]) -> str:
    return "\n".join(json.dumps(paper.to_dict(), ensure_ascii=False) for paper in papers)


def to_markdown(papers: list[Paper]) -> str:
    lines = ["# Papers", ""]
    for paper in papers:
        date = paper.published_at.date().isoformat() if paper.published_at else "unknown date"
        source = paper.journal or paper.source
        lines.append(f"## {paper.title}")
        lines.append("")
        lines.append(f"- Source: {source}")
        lines.append(f"- Date: {date}")
        if paper.doi:
            lines.append(f"- DOI: {paper.doi}")
        lines.append(f"- URL: {paper.url}")
        if paper.abstract:
            lines.append("")
            lines.append(paper.abstract)
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def to_rss(papers: list[Paper], title: str = "PaperLite Feed") -> str:
    items: list[str] = []
    for paper in papers:
        pub_date = paper.published_at.strftime("%a, %d %b %Y %H:%M:%S GMT") if paper.published_at else ""
        items.append(
            "    <item>\n"
            f"      <title>{escape(paper.title)}</title>\n"
            f"      <link>{escape(paper.url)}</link>\n"
            f"      <guid>{escape(paper.id)}</guid>\n"
            f"      <description>{escape(paper.abstract)}</description>\n"
            f"      <pubDate>{escape(pub_date)}</pubDate>\n"
            "    </item>"
        )
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<rss version=\"2.0\">\n"
        "  <channel>\n"
        f"    <title>{escape(title)}</title>\n"
        "    <link>https://github.com/</link>\n"
        "    <description>Lightweight paper aggregation feed</description>\n"
        + "\n".join(items)
        + "\n  </channel>\n</rss>\n"
    )


def _clean_line(value: object | None) -> str:
    return " ".join(str(value or "").split())


def _ris_type(paper: Paper) -> str:
    if paper.source_type == "journal" or paper.journal or paper.venue:
        return "JOUR"
    if paper.source_type == "preprint":
        return "RPRT"
    return "GEN"


def _ris_date(paper: Paper) -> str:
    return paper.published_at.strftime("%Y/%m/%d") if paper.published_at else ""


def _note_lines(paper: Paper) -> list[str]:
    notes = [f"PaperLite ID: {paper.id}", f"PaperLite source: {paper.source}"]
    if paper.pmid:
        notes.append(f"PMID: {paper.pmid}")
    if paper.pmcid:
        notes.append(f"PMCID: {paper.pmcid}")
    if paper.openalex_id:
        notes.append(f"OpenAlex: {paper.openalex_id}")
    if paper.pdf_url:
        notes.append(f"External PDF URL: {paper.pdf_url}")
    return notes


def to_ris(papers: list[Paper]) -> str:
    records: list[str] = []
    for paper in papers:
        lines = [f"TY  - {_ris_type(paper)}", f"TI  - {_clean_line(paper.title)}"]
        for author in paper.authors:
            lines.append(f"AU  - {_clean_line(author)}")
        if paper.abstract:
            lines.append(f"AB  - {_clean_line(paper.abstract)}")
        if paper.published_at:
            lines.append(f"PY  - {paper.published_at.year}")
            lines.append(f"DA  - {_ris_date(paper)}")
        venue = paper.journal or paper.venue
        if venue:
            lines.append(f"JO  - {_clean_line(venue)}")
        if paper.publisher:
            lines.append(f"PB  - {_clean_line(paper.publisher)}")
        if paper.doi:
            lines.append(f"DO  - {_clean_line(paper.doi)}")
        lines.append(f"UR  - {_clean_line(paper.url)}")
        for tag in [*paper.categories, *paper.concepts]:
            lines.append(f"KW  - {_clean_line(tag)}")
        for note in _note_lines(paper):
            lines.append(f"N1  - {_clean_line(note)}")
        lines.append("ER  -")
        records.append("\n".join(lines))
    return "\n\n".join(records).strip() + ("\n" if records else "")


def _bibtex_type(paper: Paper) -> str:
    if paper.source_type == "journal" or paper.journal or paper.venue:
        return "article"
    return "misc"


def _bibtex_key(paper: Paper) -> str:
    key = re.sub(r"[^A-Za-z0-9]+", "_", paper.id).strip("_")
    return key or "paperlite"


def _bibtex_escape(value: object | None) -> str:
    text = _clean_line(value)
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def _bibtex_field(name: str, value: object | None) -> str:
    return f"  {name} = {{{_bibtex_escape(value)}}},"


def to_bibtex(papers: list[Paper]) -> str:
    entries: list[str] = []
    for paper in papers:
        fields = [
            _bibtex_field("title", paper.title),
            _bibtex_field("author", " and ".join(paper.authors)),
        ]
        if paper.published_at:
            fields.append(_bibtex_field("year", paper.published_at.year))
            fields.append(_bibtex_field("date", paper.published_at.date().isoformat()))
        venue = paper.journal or paper.venue
        if venue:
            fields.append(_bibtex_field("journal", venue))
        if paper.publisher:
            fields.append(_bibtex_field("publisher", paper.publisher))
        if paper.doi:
            fields.append(_bibtex_field("doi", paper.doi))
        fields.append(_bibtex_field("url", paper.url))
        if paper.abstract:
            fields.append(_bibtex_field("abstract", paper.abstract))
        tags = [*paper.categories, *paper.concepts]
        if tags:
            fields.append(_bibtex_field("keywords", ", ".join(str(tag) for tag in tags)))
        fields.append(_bibtex_field("note", "; ".join(_note_lines(paper))))
        entries.append(f"@{_bibtex_type(paper)}{{{_bibtex_key(paper)},\n" + "\n".join(fields) + "\n}")
    return "\n\n".join(entries).strip() + ("\n" if entries else "")


def export_papers(papers: list[Paper], format: str = "json") -> str:
    fmt = format.lower()
    if fmt == "json":
        return to_json(papers)
    if fmt == "jsonl":
        return to_jsonl(papers)
    if fmt == "rss":
        return to_rss(papers)
    if fmt in {"md", "markdown"}:
        return to_markdown(papers)
    if fmt == "ris":
        return to_ris(papers)
    if fmt in {"bib", "bibtex"}:
        return to_bibtex(papers)
    raise ValueError(f"unsupported export format: {format}")
