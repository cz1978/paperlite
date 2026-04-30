from __future__ import annotations

import argparse
import sys
from pathlib import Path

check_endpoint_health = None
check_selected_endpoint_health = None
format_health_markdown = None
run_source_audit = None
format_source_audit_markdown = None
summarize_audit_results = None
run_doctor = None
format_doctor_markdown = None
format_doctor_json = None
paper_rag_index = None
paper_ask = None


def _write_or_print(body: str, output: str | None) -> None:
    if output:
        Path(output).write_text(body, encoding="utf-8")
    else:
        try:
            print(body)
        except UnicodeEncodeError:
            sys.stdout.buffer.write(body.encode("utf-8"))
            sys.stdout.buffer.write(b"\n")


def _format_rag_index_markdown(payload: dict) -> str:
    warnings = payload.get("warnings") or []
    lines = [
        "# PaperLite RAG index",
        "",
        f"- configured: {bool(payload.get('configured'))}",
        f"- embedding_model: {payload.get('embedding_model') or ''}",
        f"- date: {payload.get('date_from') or ''} to {payload.get('date_to') or ''}",
        f"- discipline: {payload.get('discipline') or 'all'}",
        f"- source: {payload.get('source') or 'all'}",
        f"- q: {payload.get('q') or 'all'}",
        f"- limit_per_source: {payload.get('limit_per_source') or ''}",
        f"- candidates: {payload.get('candidates') or 0}",
        f"- indexed: {payload.get('indexed') or 0}",
        f"- skipped: {payload.get('skipped') or 0}",
    ]
    if warnings:
        lines.append(f"- warnings: {', '.join(str(item) for item in warnings)}")
    return "\n".join(lines)


def _format_rag_ask_markdown(payload: dict) -> str:
    warnings = payload.get("warnings") or []
    retrieval = payload.get("retrieval") or {}
    citations = payload.get("citations") or []
    lines = [
        "# PaperLite RAG answer",
        "",
        payload.get("answer") or "_No answer returned._",
        "",
        f"- configured: {bool(payload.get('configured'))}",
        f"- model: {payload.get('model') or ''}",
        f"- embedding_model: {payload.get('embedding_model') or ''}",
        f"- retrieval: candidates {retrieval.get('candidates') or 0}, indexed {retrieval.get('indexed') or 0}, stale {retrieval.get('stale') or 0}, matches {retrieval.get('matches') or 0}",
        f"- q: {retrieval.get('q') or 'all'}",
    ]
    if warnings:
        lines.append(f"- warnings: {', '.join(str(item) for item in warnings)}")
    if citations:
        lines.extend(["", "## Citations"])
        for citation in citations:
            paper = citation.get("paper") or {}
            index = citation.get("index") or ""
            score = citation.get("score")
            score_text = f" score={score:.3f}" if isinstance(score, (int, float)) else ""
            lines.append(f"{index}. {paper.get('title') or 'Untitled'}{score_text}")
            meta = " · ".join(str(item) for item in [paper.get("source"), paper.get("published_at"), paper.get("doi")] if item)
            if meta:
                lines.append(f"   {meta}")
            if paper.get("url"):
                lines.append(f"   {paper.get('url')}")
    return "\n".join(lines)


def _format_sources_markdown(items: list[dict]) -> str:
    lines = ["# PaperLite Sources", ""]
    for item in items:
        disciplines = ", ".join(str(value) for value in item.get("canonical_disciplines") or item.get("disciplines") or [])
        access_modes = ", ".join(str(value) for value in item.get("access_modes") or [])
        parts = [
            f"group={item.get('group') or ''}",
            f"kind={item.get('source_kind_key') or item.get('catalog_kind') or item.get('source_type') or ''}",
            f"health={item.get('health_status') or ''}",
        ]
        if disciplines:
            parts.append(f"disciplines={disciplines}")
        if access_modes:
            parts.append(f"access={access_modes}")
        if item.get("primary_endpoint"):
            parts.append(f"endpoint={item.get('primary_endpoint')}")
        name = item.get("display_name") or item.get("journal") or item.get("name") or "Unknown"
        lines.append(f"- {item.get('name')}: {name} ({'; '.join(parts)})")
    return "\n".join(lines)


def _rag_scope_kwargs(args) -> dict:
    return {
        "date_value": args.date,
        "date_from": args.date_from,
        "date_to": args.date_to,
        "discipline": args.discipline,
        "source": args.source,
        "q": args.q,
        "limit_per_source": args.limit_per_source,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="paperlite")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="Inspect runtime dependencies, config, SQLite, LLM, Zotero, and ops state")
    doctor.add_argument("--format", default="markdown", choices=["markdown", "md", "json"])
    doctor.add_argument("--output", default=None)

    catalog = sub.add_parser("catalog", help="Validate and maintain source catalog files")
    catalog_sub = catalog.add_subparsers(dest="catalog_action", required=True)
    catalog_validate = catalog_sub.add_parser("validate", help="Validate sources/endpoints/taxonomy YAML")
    catalog_validate.add_argument("--format", default="markdown", choices=["json", "markdown", "md"])
    catalog_coverage = catalog_sub.add_parser("coverage", help="Report catalog coverage by discipline")
    catalog_coverage.add_argument("--format", default="markdown", choices=["json", "markdown", "md"])
    catalog_add = catalog_sub.add_parser("add-source", help="Add an ordinary RSS/Atom/feed source")
    catalog_add.add_argument("--key", required=True)
    catalog_add.add_argument("--name", required=True)
    catalog_add.add_argument("--kind", required=True, help="Source kind, e.g. journal, preprint, news")
    catalog_add.add_argument("--discipline", required=True, help="Discipline name/key/alias; comma-separated is accepted")
    catalog_add.add_argument("--url", required=True)
    catalog_add.add_argument("--publisher", default=None)
    catalog_add.add_argument("--homepage", default=None)
    catalog_add.add_argument("--status", default="active", choices=["active", "candidate", "temporarily_unavailable"])
    catalog_add.add_argument("--origin", default="manual")
    catalog_add.add_argument("--mode", default="rss", choices=["rss", "atom", "feed"])
    catalog_add.add_argument("--write", action="store_true", help="Append to YAML files; default is dry-run")
    catalog_add.add_argument("--format", default="markdown", choices=["json", "markdown", "md"])

    endpoints = sub.add_parser("endpoints", help="List source retrieval endpoints")
    endpoints.add_argument("endpoint_action", nargs="?", choices=["list", "health", "audit"], default="list")
    endpoints.add_argument("--format", default="json", choices=["json", "markdown", "md"])
    endpoints.add_argument("--mode", default=None, help="Filter by endpoint mode, e.g. rss, atom, api, manual")
    endpoints.add_argument("--status", default=None, help="Filter by endpoint catalog status")
    endpoints.add_argument("--discipline", default=None, help="Filter health/audit endpoints by canonical discipline")
    endpoints.add_argument("--source", default=None, help="Filter health/audit endpoints by source key, comma-separated")
    endpoints.add_argument("--limit", type=int, default=None, help="Endpoint action limit")
    endpoints.add_argument("--offset", type=int, default=0, help="Audit batch offset")
    endpoints.add_argument("--sample-size", type=int, default=3, help="Audit metadata samples per endpoint")
    endpoints.add_argument("--timeout", type=float, default=5.0, help="Health check timeout in seconds")
    endpoints.add_argument("--output", default=None, help="Write listing or health report to a file")
    endpoints.add_argument("--write-snapshot", action="store_true", help="Write audit results to the runtime source audit snapshot")
    endpoints.add_argument("--all", action="store_true", help="Run audit batches until all selected endpoints are checked")
    endpoints.add_argument(
        "--request-profile",
        default="paperlite",
        choices=["paperlite", "browser_compat"],
        help="Health check request headers profile",
    )

    sources = sub.add_parser("sources", help="List source catalog records")
    sources.add_argument("--format", default="json", choices=["json", "markdown", "md"])
    sources.add_argument("--discipline", default=None, help="Filter by canonical discipline name/key/alias")
    sources.add_argument("--area", default=None, help="Filter by taxonomy area key")
    sources.add_argument("--kind", default=None, help="Filter by source kind key, e.g. journal or preprint")
    sources.add_argument("--core", default=None, choices=["true", "false", "1", "0", "yes", "no", "on", "off"])
    sources.add_argument("--health", default=None, help="Filter by source health status")
    sources.add_argument("--output", default=None)

    rag = sub.add_parser("rag", help="Index and ask over cached PaperLite metadata")
    rag_sub = rag.add_subparsers(dest="rag_action", required=True)
    rag_index = rag_sub.add_parser("index", help="Build or refresh embeddings for cached paper metadata")
    rag_index.add_argument("--date", default=None, help="Single cache date, YYYY-MM-DD")
    rag_index.add_argument("--date-from", default=None, help="Start cache date, YYYY-MM-DD")
    rag_index.add_argument("--date-to", default=None, help="End cache date, YYYY-MM-DD")
    rag_index.add_argument("--discipline", default=None, help="Canonical discipline key")
    rag_index.add_argument("--source", default=None, help="Source key or comma-separated source keys")
    rag_index.add_argument("--q", default=None, help="Filter cached metadata by the same query text used in /daily")
    rag_index.add_argument("--limit-per-source", type=int, default=100)
    rag_index.add_argument("--format", default="markdown", choices=["json", "markdown", "md"])
    rag_index.add_argument("--output", default=None)
    rag_ask = rag_sub.add_parser("ask", help="Ask a question using already indexed cached paper metadata")
    rag_ask.add_argument("question", nargs="*", help="Question to ask")
    rag_ask.add_argument("--question", dest="question_option", default=None, help="Question to ask")
    rag_ask.add_argument("--date", default=None, help="Single cache date, YYYY-MM-DD")
    rag_ask.add_argument("--date-from", default=None, help="Start cache date, YYYY-MM-DD")
    rag_ask.add_argument("--date-to", default=None, help="End cache date, YYYY-MM-DD")
    rag_ask.add_argument("--discipline", default=None, help="Canonical discipline key")
    rag_ask.add_argument("--source", default=None, help="Source key or comma-separated source keys")
    rag_ask.add_argument("--q", default=None, help="Filter cached metadata by the same query text used in /daily")
    rag_ask.add_argument("--top-k", type=int, default=8)
    rag_ask.add_argument("--limit-per-source", type=int, default=100)
    rag_ask.add_argument("--format", default="markdown", choices=["json", "markdown", "md"])
    rag_ask.add_argument("--output", default=None)

    serve = sub.add_parser("serve", help="Run REST API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)

    mcp = sub.add_parser("mcp", help="Run MCP server")
    mcp.add_argument("--transport", default=None)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "doctor":
        run_fn = run_doctor
        markdown_fn = format_doctor_markdown
        json_fn = format_doctor_json
        if run_fn is None or markdown_fn is None or json_fn is None:
            from paperlite.doctor import (
                format_doctor_json as json_fn,
                format_doctor_markdown as markdown_fn,
                run_doctor as run_fn,
            )

        payload = run_fn()
        body = json_fn(payload) if args.format == "json" else markdown_fn(payload)
        _write_or_print(body, args.output)
        if payload.get("overall") == "fail":
            raise SystemExit(1)
        return

    if args.command == "catalog":
        if args.catalog_action == "validate":
            from paperlite.catalog_maintenance import validate_catalog

            result = validate_catalog()
            if args.format in {"markdown", "md"}:
                _write_or_print(result.to_markdown(), None)
            else:
                import json

                _write_or_print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), None)
            if not result.ok:
                raise SystemExit(1)
            return
        if args.catalog_action == "coverage":
            from paperlite.catalog_quality import build_catalog_coverage, format_catalog_coverage_markdown

            coverage = build_catalog_coverage()
            if args.format in {"markdown", "md"}:
                _write_or_print(format_catalog_coverage_markdown(coverage), None)
            else:
                import json

                _write_or_print(json.dumps(coverage, ensure_ascii=False, indent=2), None)
            return
        if args.catalog_action == "add-source":
            from paperlite.catalog_maintenance import add_feed_source

            try:
                result = add_feed_source(
                    key=args.key,
                    name=args.name,
                    kind=args.kind,
                    discipline=args.discipline,
                    url=args.url,
                    publisher=args.publisher,
                    homepage=args.homepage,
                    status=args.status,
                    origin=args.origin,
                    mode=args.mode,
                    write=args.write,
                )
            except ValueError as exc:
                parser.error(str(exc))
            if args.format in {"markdown", "md"}:
                _write_or_print(result.to_markdown(), None)
            else:
                import json

                _write_or_print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), None)
            if not result.validation.ok:
                raise SystemExit(1)
            return

    if args.command == "sources":
        from paperlite.registry import list_sources

        try:
            items = list_sources(
                discipline=args.discipline,
                area=args.area,
                kind=args.kind,
                core=args.core,
                health=args.health,
            )
        except KeyError as exc:
            parser.error(str(exc))
        if args.format in {"markdown", "md"}:
            _write_or_print(_format_sources_markdown(items), args.output)
        else:
            import json

            _write_or_print(json.dumps(items, ensure_ascii=False, indent=2), args.output)
        return

    if args.command == "rag":
        if args.rag_action == "index":
            run_index = paper_rag_index
            if run_index is None:
                from paperlite.agent import paper_rag_index as run_index
            payload = run_index(**_rag_scope_kwargs(args))
            if args.format in {"markdown", "md"}:
                _write_or_print(_format_rag_index_markdown(payload), args.output)
            else:
                import json

                _write_or_print(json.dumps(payload, ensure_ascii=False, indent=2), args.output)
            return
        if args.rag_action == "ask":
            run_ask = paper_ask
            if run_ask is None:
                from paperlite.agent import paper_ask as run_ask
            question = (args.question_option or " ".join(args.question)).strip()
            if not question:
                parser.error("rag ask requires a question")
            payload = run_ask(question=question, top_k=args.top_k, **_rag_scope_kwargs(args))
            if args.format in {"markdown", "md"}:
                _write_or_print(_format_rag_ask_markdown(payload), args.output)
            else:
                import json

                _write_or_print(json.dumps(payload, ensure_ascii=False, indent=2), args.output)
            return

    if args.command == "endpoints":
        if args.endpoint_action == "audit":
            audit_fn = run_source_audit
            markdown_fn = format_source_audit_markdown
            summary_fn = summarize_audit_results
            if audit_fn is None or markdown_fn is None or summary_fn is None:
                from paperlite.source_audit import (
                    DEFAULT_AUDIT_BATCH_LIMIT,
                    format_source_audit_markdown as markdown_fn,
                    replace_source_audit_snapshot,
                    run_source_audit as audit_fn,
                    summarize_audit_results as summary_fn,
                )
            else:
                DEFAULT_AUDIT_BATCH_LIMIT = 100
                replace_source_audit_snapshot = None

            batch_limit = args.limit or DEFAULT_AUDIT_BATCH_LIMIT
            try:
                if args.all:
                    offset = max(0, int(args.offset or 0))
                    all_results = []
                    last_payload = {}
                    while True:
                        payload = audit_fn(
                            discipline=args.discipline,
                            source=args.source,
                            mode=args.mode,
                            limit=batch_limit,
                            offset=offset,
                            sample_size=args.sample_size,
                            timeout_seconds=args.timeout,
                            request_profile=args.request_profile,
                            write_snapshot=False,
                        )
                        last_payload = payload
                        all_results.extend(payload.get("results") or [])
                        if payload.get("next_offset") is None:
                            break
                        offset = int(payload["next_offset"])
                    payload = dict(last_payload)
                    payload["checked"] = len(all_results)
                    payload["results"] = all_results
                    payload["summary"] = summary_fn(all_results)
                    payload["next_offset"] = None
                    if args.write_snapshot:
                        if replace_source_audit_snapshot is None:
                            from paperlite.source_audit import replace_source_audit_snapshot
                        payload["snapshot"] = replace_source_audit_snapshot(
                            all_results,
                            params=payload.get("params") if isinstance(payload.get("params"), dict) else {},
                        )
                else:
                    payload = audit_fn(
                        discipline=args.discipline,
                        source=args.source,
                        mode=args.mode,
                        limit=batch_limit,
                        offset=args.offset,
                        sample_size=args.sample_size,
                        timeout_seconds=args.timeout,
                        request_profile=args.request_profile,
                        write_snapshot=args.write_snapshot,
                    )
            except ValueError as exc:
                parser.error(str(exc))
            if args.format in {"markdown", "md"}:
                _write_or_print(markdown_fn(payload), args.output)
            else:
                import json

                _write_or_print(json.dumps(payload, ensure_ascii=False, indent=2), args.output)
            return

        if args.endpoint_action == "health":
            selected_check_fn = check_selected_endpoint_health
            check_fn = check_endpoint_health
            markdown_fn = format_health_markdown
            if args.discipline or args.source:
                if selected_check_fn is None:
                    from paperlite.endpoint_health import check_selected_endpoint_health as selected_check_fn
            elif check_fn is None:
                from paperlite.endpoint_health import check_endpoint_health as check_fn
            if markdown_fn is None:
                from paperlite.endpoint_health import format_health_markdown as markdown_fn

            try:
                if args.discipline or args.source:
                    results = selected_check_fn(
                        discipline=args.discipline,
                        source=args.source,
                        mode=args.mode or "rss",
                        limit=args.limit or 50,
                        timeout_seconds=args.timeout,
                        request_profile=args.request_profile,
                    )
                else:
                    results = check_fn(
                        mode=args.mode or "rss",
                        limit=args.limit or 50,
                        timeout_seconds=args.timeout,
                        request_profile=args.request_profile,
                    )
            except ValueError as exc:
                parser.error(str(exc))
            if args.format in {"markdown", "md"}:
                _write_or_print(markdown_fn(results), args.output)
            else:
                import json

                _write_or_print(json.dumps({"health": [result.to_dict() for result in results]}, ensure_ascii=False, indent=2), args.output)
            return

        from paperlite.sources import list_endpoints

        try:
            items = list_endpoints(mode=args.mode, status=args.status)
        except ValueError as exc:
            parser.error(str(exc))
        if args.format in {"markdown", "md"}:
            _write_or_print(
                "\n".join(
                    f"- {x['key']} -> {x['source_key']} ({x['mode']}/{x.get('status')}): {x.get('url') or x.get('provider') or ''}"
                    for x in items
                ),
                args.output,
            )
        else:
            import json

            _write_or_print(json.dumps(items, ensure_ascii=False, indent=2), args.output)
        return

    if args.command == "serve":
        import uvicorn

        uvicorn.run("paperlite.api:app", host=args.host, port=args.port)
        return

    if args.command == "mcp":
        from paperlite.mcp_server import run

        run()
        return


if __name__ == "__main__":
    main()
