"""Command-line interface for freellmpool.

freellmpool ask "question"        one-shot completion (reads stdin too)
freellmpool providers            list configured / available providers
freellmpool quota                show today's per-provider usage
freellmpool proxy                run the OpenAI-compatible proxy server
"""

from __future__ import annotations

import argparse
import os
import sys

from . import __version__
from .config import configured_providers, load_catalog, resolve_alias, settings
from .errors import AllProvidersExhausted, NoProvidersConfigured
from .quota import QuotaStore
from .router import Pool
from .savings import format_saved


def _read_stdin() -> str:
    if sys.stdin is None or sys.stdin.isatty():
        return ""
    return sys.stdin.read()


def cmd_ask(args: argparse.Namespace) -> int:
    stdin = _read_stdin()
    prompt = args.prompt or ""
    if stdin:
        prompt = f"{stdin}\n\n{prompt}".strip() if prompt else stdin

    if not prompt.strip():
        print("freellmpool: no prompt provided (pass text or pipe stdin)", file=sys.stderr)
        return 3

    # Support `--model provider/model` as a shorthand for picking an exact
    # model on an exact provider (in addition to `--providers` + bare `--model`).
    # Common OpenAI/Anthropic names (gpt-4o-mini, ...) resolve to a free target.
    model_filter = resolve_alias(args.model) if args.model else None
    if model_filter == "auto":
        model_filter = None
    provider_filter = args.providers.split(",") if args.providers else None
    if model_filter and "/" in model_filter:
        prov, _, mdl = model_filter.partition("/")
        provider_filter = [prov]
        model_filter = mdl

    system = args.system
    if args.json:
        json_rule = "Respond with a single valid JSON value and nothing else — no prose, no markdown fences."
        system = f"{system}\n{json_rule}" if system else json_rule

    pool = Pool.from_default_config()
    try:
        reply = pool.ask(
            prompt,
            system=system,
            model=model_filter,
            providers=provider_filter,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
        )
    except NoProvidersConfigured as exc:
        print(f"freellmpool: {exc}", file=sys.stderr)
        return 3
    except AllProvidersExhausted as exc:
        print(f"freellmpool: {exc}", file=sys.stderr)
        return 4

    text = reply.text
    if args.json:
        text = _strip_fences(text)
    print(text)
    if args.verbose:
        saved = format_saved(reply.prompt_tokens, reply.completion_tokens)
        print(
            f"\n[served by {reply.provider_id}/{reply.model} · {saved}]",
            file=sys.stderr,
        )
    return 0


def _strip_fences(text: str) -> str:
    """Remove a leading ```json / ``` fence and trailing ``` if present."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


def cmd_providers(args: argparse.Namespace) -> int:
    catalog = load_catalog()
    configured = {p.id for p in configured_providers(catalog)}
    n_models = sum(1 for p in catalog for m in p.models if m.enabled)
    print(f"freellmpool catalog: {len(catalog)} providers, {n_models} models\n")
    for p in catalog:
        mark = "✓" if p.id in configured else "·"
        status = "configured" if p.id in configured else f"set {p.key_env}"
        on = sum(1 for m in p.models if m.enabled)
        off = len(p.models) - on
        count = f"{on} models" + (f" (+{off} off)" if off else "")
        print(f"  {mark} {p.id:<12} {p.label:<28} {count:<16} [{status}]")
    if not configured:
        print("\nNo providers configured yet. See .env.example for the env vars to set.")
    return 0


def cmd_providers_health(args: argparse.Namespace) -> int:
    from .healthcheck import render_health_table, run_healthcheck

    pool = Pool.from_default_config()
    provider_filter = args.providers.split(",") if args.providers else None
    rows = run_healthcheck(
        pool,
        model=args.model,
        providers=provider_filter,
        timeout=args.timeout,
    )
    print(render_health_table(rows))
    return 0


def cmd_models(args: argparse.Namespace) -> int:
    catalog = load_catalog()
    configured = {p.id for p in configured_providers(catalog)}
    only = set(args.providers.split(",")) if args.providers else None
    shown = 0
    for p in catalog:
        if only is not None and p.id not in only:
            continue
        if args.configured_only and p.id not in configured:
            continue
        mark = "✓" if p.id in configured else "·"
        keyless = "  (keyless)" if p.keyless and p.id in configured else ""
        print(f"\n{mark} {p.id}  —  {p.label}{keyless}")
        for m in p.models:
            if not m.enabled and not args.all:
                continue
            shown += 1
            tag = "  (off by default)" if not m.enabled else ""
            print(f"    {p.id}/{m.name}{tag}")
    if shown == 0:
        print("No models match. Try `freellmpool providers` to see configuration status.")
        return 0
    print(
        f"\nPass any id above to `--model`, e.g. "
        f'`freellmpool ask -m {catalog[0].id}/{catalog[0].models[0].name} "hi"`,'
    )
    print("or just `--model <model-name>` to use that model on any provider that has it.")
    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    from .benchmark import benchmark, render_table

    pool = Pool.from_default_config()
    if not pool.providers:
        print(
            "freellmpool: no providers configured; set at least one API key "
            "(see .env.example) before benchmarking.",
            file=sys.stderr,
        )
        return 3
    provider_filter = args.providers.split(",") if args.providers else None
    print(
        f"Benchmarking {len(pool.providers)} providers "
        f"(one model each{', pinned' if args.model else ''})...",
        file=sys.stderr,
    )
    rows = benchmark(
        pool,
        model=args.model,
        providers=provider_filter,
        timeout=args.timeout,
    )
    print(render_table(rows))
    return 0


def cmd_quota(args: argparse.Namespace) -> int:
    store = QuotaStore()
    snap = store.snapshot()
    if not snap:
        print("No usage recorded today (UTC).")
        return 0
    print("Today's usage (UTC):")
    for key, count in sorted(snap.items(), key=lambda kv: -kv[1]):
        print(f"  {count:>6}  {key}")
    return 0


def _format_capacity_row(row) -> str:
    quota = "?" if row.quota_hint <= 0 else str(row.quota_hint)
    key = "keyless" if row.keyless else (row.key_env or "-")
    expiry = f" expires={row.expires_at}" if row.expires_at else ""
    return (
        f"  {row.status:<11} {row.provider_id:<13} {row.label:<28} "
        f"used={row.used_today}/{quota:<5} models={row.enabled_models:<3} "
        f"key={key}{expiry}  {row.reason}"
    )


def cmd_keys_status(args: argparse.Namespace) -> int:
    from .capacity import build_capacity_report
    from .key_inventory import default_inventory_path, load_inventory

    inventory_path = default_inventory_path()
    inventory = load_inventory(inventory_path)
    report = build_capacity_report(target=args.target, inventory=inventory)
    print(f"Key inventory: {inventory_path}")
    print(f"Records: {len(inventory)}")
    print(f"Healthy providers: {report.healthy_count}/{args.target}\n")
    for row in report.providers:
        if args.all or row.status != "missing":
            print(_format_capacity_row(row))
    return 0


def cmd_keys_checklist(args: argparse.Namespace) -> int:
    from .capacity import build_capacity_report
    from .key_inventory import load_inventory

    report = build_capacity_report(target=args.target, inventory=load_inventory())
    todo = report.checklist()
    if not todo:
        print(f"Enough healthy providers: {report.healthy_count}/{args.target}.")
        return 0
    print(f"Manual key checklist to reach {args.target} healthy providers:")
    for row in todo:
        print(f"  - {row.provider_id}: create a key manually, then set {row.key_env}")
    return 0


def _choose_provider(catalog, provider_id: str | None):
    providers = [p for p in catalog if p.key_env]
    if provider_id:
        needle = provider_id.lower()
        matches = [p for p in providers if p.id.lower() == needle or p.label.lower() == needle]
        if not matches:
            raise SystemExit(
                f"provider is not configured in local providers.toml, or is keyless/external-only: {provider_id}"
            )
        return matches[0]

    print("Choose a provider to configure:")
    for i, provider in enumerate(providers, start=1):
        print(f"  {i}. {provider.id} ({provider.key_env})")

    while True:
        raw = input("Provider number or id: ").strip()
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(providers):
                return providers[idx - 1]

        for provider in providers:
            if provider.id == raw:
                return provider

        print("Invalid provider, try again.")


def _yes(raw: str) -> bool:
    return raw.strip().lower() in {"y", "yes"}


def _load_or_sync_external_catalog():
    from .catalog import load_external_catalog, sync_external_catalog

    external = load_external_catalog()
    if external:
        return external
    try:
        _, external = sync_external_catalog()
    except Exception:  # noqa: BLE001 - keys add can continue with manual creation
        return []
    return external


def _import_or_create_provider(provider_name: str, args: argparse.Namespace) -> str | None:
    from .catalog import (
        create_user_provider_stub,
        discover_openai_models,
        import_external_provider_to_user_catalog,
        suggest_external_provider,
    )

    external = _load_or_sync_external_catalog()
    suggestion = suggest_external_provider(provider_name, external)
    if suggestion:
        provider_slug = suggestion.provider.slug.replace("-", "_")
        query_slug = provider_name.lower().replace("_", "-")
        is_exact_provider = suggestion.exact and query_slug in {
            suggestion.provider.slug,
            provider_slug,
        }
        if is_exact_provider or (
            not args.yes
            and _yes(
                input(
                    f"Provider not found. Use external match "
                    f"{suggestion.provider.name} (matched {suggestion.matched})? [y/N] "
                )
            )
        ):
            local_id = import_external_provider_to_user_catalog(suggestion.provider.name)
            print(
                f"Imported external provider '{suggestion.provider.name}' as local provider '{local_id}'."
            )
            return local_id

    if args.yes and not args.base_url:
        print(
            "Provider not found. Pass --base-url to create it non-interactively.", file=sys.stderr
        )
        return None

    if not args.yes and not _yes(
        input(f"Provider '{provider_name}' not found. Create it manually? [y/N] ")
    ):
        return None

    base_url = args.base_url or input("OpenAI-compatible API base URL: ").strip()
    model = args.model or (
        "" if args.yes else input("Default model id (blank to autodiscover): ").strip()
    )
    if not model:
        api_key = getattr(args, "value", None)
        if not api_key and not args.yes:
            import getpass

            api_key = getpass.getpass("API key for model discovery (blank if not needed): ").strip()
            if api_key:
                args.value = api_key
        try:
            models = discover_openai_models(base_url, api_key=api_key or None)
        except ValueError as exc:
            print(f"Could not autodiscover models: {exc}", file=sys.stderr)
            models = []
        model = _choose_discovered_model(models, args)
        if not model and not args.yes:
            model = input("Default model id: ").strip()
    try:
        local_id = create_user_provider_stub(name=provider_name, base_url=base_url, model=model)
    except ValueError as exc:
        print(f"Could not create provider: {exc}", file=sys.stderr)
        return None
    print(f"Created local provider '{local_id}' in user providers.toml.")
    return local_id


def _choose_discovered_model(models: list[str], args: argparse.Namespace) -> str | None:
    if not models:
        return None
    if len(models) == 1 or args.yes:
        print(f"Discovered model: {models[0]}")
        return models[0]
    print("Discovered models:")
    for i, model in enumerate(models[:10], start=1):
        print(f"  {i}. {model}")
    raw = input("Model number or id: ").strip()
    if raw.isdigit():
        idx = int(raw)
        if 1 <= idx <= min(len(models), 10):
            return models[idx - 1]
    if raw in models:
        return raw
    return None


def cmd_keys_add(args: argparse.Namespace) -> int:
    import getpass
    from datetime import date

    from .config import load_catalog
    from .key_inventory import (
        KeyRecord,
        append_inventory_record,
        default_config_path,
        upsert_config_key,
    )

    if getattr(args, "provider_arg", None) and not args.provider:
        args.provider = args.provider_arg
    try:
        catalog = load_catalog()
    except FileNotFoundError:
        catalog = []
    try:
        provider = _choose_provider(catalog, args.provider)
    except SystemExit:
        if not args.provider:
            raise
        local_id = _import_or_create_provider(args.provider, args)
        if not local_id:
            return 3
        provider = _choose_provider(load_catalog(), local_id)

    value = getattr(args, "value", None)
    if not value:
        value = getpass.getpass(f"Paste {provider.key_env}: ").strip()

    if not value:
        print("No value provided.", file=sys.stderr)
        return 3

    if not args.yes:
        answer = input(f"Write {provider.key_env} to {default_config_path()}? [y/N] ")
        if answer.strip().lower() not in {"y", "yes"}:
            print("Cancelled.")
            return 1

    config_path = upsert_config_key(provider.key_env, value)

    inventory_path = append_inventory_record(
        KeyRecord(
            provider=provider.id,
            env_var=provider.key_env,
            label=args.label or "manual",
            created_at=date.today().isoformat(),
            commercial_allowed=args.commercial_allowed,
            notes=args.notes or "added with freellmpool keys add",
        )
    )

    print(f"Added {provider.id} key metadata.")
    print(f"Config: {config_path}")
    print(f"Inventory: {inventory_path}")
    print("Next command:")
    print("  python3 -m freellmpool providers health -p " + provider.id)
    return 0


def cmd_capacity_status(args: argparse.Namespace) -> int:
    from .capacity import build_capacity_report
    from .catalog import load_external_catalog, match_local_provider, sync_external_catalog
    from .key_inventory import load_inventory

    external = []
    cache_note = None
    if not args.no_catalog_sync:
        try:
            path, external = sync_external_catalog(timeout=args.catalog_timeout)
            cache_note = f"External catalog synced: {len(external)} providers ({path})"
        except Exception as exc:  # noqa: BLE001 - capacity must still work offline
            external = load_external_catalog()
            cache_note = f"External catalog sync failed ({type(exc).__name__}); using cache with {len(external)} providers"
    else:
        external = load_external_catalog()
        cache_note = f"External catalog cache: {len(external)} providers"

    local_catalog = load_catalog()
    linked = {match_local_provider(item, local_catalog) for item in external}
    linked.discard(None)
    external_only = [item for item in external if match_local_provider(item, local_catalog) is None]

    report = build_capacity_report(
        target=args.target, inventory=load_inventory(), catalog=local_catalog
    )
    print(f"LLM capacity: {report.healthy_count}/{args.target} healthy providers")
    print(cache_note)
    if external:
        print(f"Catalog links: {len(linked)} linked locally, {len(external_only)} external-only")
    if report.low_quota_count:
        print(f"Warning: {report.low_quota_count} provider(s) are near quota.")
    if report.needs_action:
        print(f"Action recommended: add {args.target - report.healthy_count} provider(s).")
    print()
    for row in report.providers:
        if args.all or row.status in {"healthy", "low_quota", "exhausted", "invalid_key"}:
            print(_format_capacity_row(row))
    if args.all and external_only:
        print()
        print("External-only catalog candidates, not in local providers.toml:")
        for item in external_only[: args.external_limit]:
            score = item.best_tpd or item.best_rpd or item.best_rpm
            print(
                f"  external    {item.name:<24} score={score:<8} models={item.model_count:<3} link={item.url or '-'}"
            )
    return 0


def cmd_catalog_sync(args: argparse.Namespace) -> int:
    from .catalog import sync_external_catalog

    path, providers = sync_external_catalog(timeout=args.timeout)
    print(f"Synced {len(providers)} external providers.")
    print(f"Cache: {path}")
    top = providers[:5]
    if top:
        print("Most generous external entries:")
        for provider in top:
            score = provider.best_tpd or provider.best_rpd or provider.best_rpm
            print(f"  {provider.name}: score={score} models={provider.model_count}")
    return 0


def cmd_catalog_status(args: argparse.Namespace) -> int:
    from .catalog import default_external_catalog_path, load_external_catalog

    path = default_external_catalog_path()
    providers = load_external_catalog(path)
    if not providers:
        print(f"No external catalog cache found at {path}.")
        print("Run: freellmpool catalog sync")
        return 1
    print(f"External catalog: {len(providers)} providers")
    print(f"Cache: {path}")
    for provider in providers[: args.limit]:
        score = provider.best_tpd or provider.best_rpd or provider.best_rpm
        print(
            f"  {provider.name:<28} score={score:<8} models={provider.model_count:<3} base={provider.base_url or '-'}"
        )
    return 0


def cmd_capability_sync(args: argparse.Namespace) -> int:
    from .capability import sync_capability_table

    aa_key = os.environ.get("FREELLMPOOL_AA_API_KEY")
    path, stats = sync_capability_table(timeout=args.timeout, aa_api_key=aa_key)
    by_source = ", ".join(f"{k}={v}" for k, v in sorted(stats["by_source"].items()))
    print(f"Synced capability scores → {path}")
    print(
        f"  benchmark models fetched: arena={stats['arena']}  "
        f"aider={stats['aider']}  aa={stats['aa']}"
    )
    print(f"  catalog models mapped: {stats['mapped']} ({by_source or 'none'})")
    if not aa_key:
        print(
            "  Artificial Analysis skipped — set FREELLMPOOL_AA_API_KEY for much broader "
            "coverage (its Intelligence Index covers most current/open models and wins)."
        )
    print("  Models not covered by a benchmark fall back to a name heuristic at runtime.")
    # Source attribution (required for Artificial Analysis; courtesy for the rest).
    sources = ["LMArena (https://lmarena.ai/)", "Aider (https://aider.chat/)"]
    if stats["aa"]:
        sources.append("Artificial Analysis (https://artificialanalysis.ai/)")
    print("  Scores via " + ", ".join(sources) + ".")
    return 0


def cmd_capability_status(args: argparse.Namespace) -> int:
    from .capability import capability_table, model_capability, user_capability_path
    from .config import load_catalog

    table = capability_table()
    user = user_capability_path()
    print(f"Capability scores: {len(table)} benchmark-scored models")
    print(f"  user cache: {user if user.exists() else '(none — using bundled snapshot)'}")
    names = sorted({m.name for p in load_catalog() for m in p.models})
    scored = sorted(((model_capability(n, table), n) for n in names), reverse=True)
    covered = sum(1 for n in names if _in_table(n, table))
    print(f"  catalog models with a benchmark score: {covered}/{len(names)} (rest use heuristic)")
    print(f"  top {args.limit} catalog models by capability:")
    for cap, name in scored[: args.limit]:
        print(f"    {cap:.3f}  {name}")
    return 0


def _in_table(name: str, table) -> bool:
    from .capability import normalize_model_name

    return normalize_model_name(name) in table


def cmd_proxy(args: argparse.Namespace) -> int:
    from .proxy import serve  # lazy: avoids http.server import on other paths

    pool = Pool.from_default_config()
    if not pool.providers:
        print(
            "freellmpool: no providers configured; set at least one API key "
            "(see .env.example) before starting the proxy.",
            file=sys.stderr,
        )
        return 3

    proxy_key = (
        args.api_key
        or os.environ.get("FREELLMPOOL_PROXY_KEY")
        or settings().get("proxy_key")
        or None
    )
    loopback = args.host in {"127.0.0.1", "localhost", "::1"}
    if not loopback and not proxy_key:
        print(
            f"freellmpool: WARNING — binding to {args.host} (not loopback) with NO proxy key "
            "exposes all your configured providers to the network. Set --api-key or "
            "FREELLMPOOL_PROXY_KEY, or bind to 127.0.0.1.",
            file=sys.stderr,
        )

    httpd = serve(pool, host=args.host, port=args.port, api_key=proxy_key)
    n_models = sum(len(p.models) for p in pool.providers)
    auth_note = "  auth: Bearer key required\n" if proxy_key else ""
    print(
        f"freellmpool proxy on http://{args.host}:{args.port}/v1  "
        f"({len(pool.providers)} providers, {n_models} models)\n"
        f"{auth_note}"
        f"  point your OpenAI client at:  OPENAI_BASE_URL=http://{args.host}:{args.port}/v1\n"
        f"  dashboard:  http://{args.host}:{args.port}/dashboard\n"
        "  press Ctrl-C to stop",
        file=sys.stderr,
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        s = pool.stats
        saved = format_saved(s["prompt_tokens"], s["completion_tokens"])
        print(
            f"\nfreellmpool: shutting down — served {s['requests']} requests · {saved}",
            file=sys.stderr,
        )
    finally:
        httpd.server_close()
    return 0


def cmd_code(args: argparse.Namespace) -> int:
    from .agents import list_agents, render

    if not args.agent:
        print(list_agents())
        return 0
    out = render(args.agent.lower())
    if out is None:
        print(f"freellmpool: unknown agent '{args.agent}'\n", file=sys.stderr)
        print(list_agents(), file=sys.stderr)
        return 3
    print(out)
    return 0


def cmd_mcp(args: argparse.Namespace) -> int:
    from .mcp_server import serve_stdio  # lazy import

    pool = Pool.from_default_config()
    print(
        f"freellmpool MCP server (stdio) — {len(pool.providers)} providers ready. "
        "Add to your MCP client config; see docs/MCP.md.",
        file=sys.stderr,
    )
    try:
        serve_stdio(pool, version=__version__)
    except (KeyboardInterrupt, BrokenPipeError):
        pass
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="freellmpool",
        description="Pool free-tier LLM APIs behind one OpenAI-compatible endpoint.",
    )
    parser.add_argument("--version", action="version", version=f"freellmpool {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ask = sub.add_parser("ask", help="one-shot completion")
    p_ask.add_argument("prompt", nargs="?", default="", help="prompt text (stdin is appended)")
    p_ask.add_argument("-s", "--system", help="system prompt")
    p_ask.add_argument(
        "-m", "--model", help="model name, or provider/model (e.g. groq/llama-3.3-70b-versatile)"
    )
    p_ask.add_argument("-p", "--providers", help="comma-separated provider ids to allow")
    p_ask.add_argument("--max-tokens", type=int, default=1024)
    p_ask.add_argument("--temperature", type=float, default=0.0)
    p_ask.add_argument(
        "--json", action="store_true", help="ask for JSON output and strip code fences"
    )
    p_ask.add_argument("-v", "--verbose", action="store_true", help="report which provider served")
    p_ask.set_defaults(func=cmd_ask)

    p_prov = sub.add_parser("providers", help="list providers and configuration status")
    prov_sub = p_prov.add_subparsers(dest="providers_command")
    p_prov_health = prov_sub.add_parser(
        "health", help="test configured providers with a tiny request"
    )
    p_prov_health.add_argument("-m", "--model", help="pin one model name to test on every provider")
    p_prov_health.add_argument("-p", "--providers", help="comma-separated provider ids to test")
    p_prov_health.add_argument(
        "--timeout", type=float, default=20.0, help="per-call timeout seconds"
    )
    p_prov_health.set_defaults(func=cmd_providers_health)
    p_prov.set_defaults(func=cmd_providers)

    p_models = sub.add_parser("models", help="list every available provider/model id")
    p_models.add_argument("-p", "--providers", help="comma-separated provider ids to filter")
    p_models.add_argument(
        "-c", "--configured-only", action="store_true", help="only show configured providers"
    )
    p_models.add_argument(
        "--all", action="store_true", help="include models that are off by default"
    )
    p_models.set_defaults(func=cmd_models)

    p_quota = sub.add_parser("quota", help="show today's per-provider usage")
    p_quota.set_defaults(func=cmd_quota)

    p_keys = sub.add_parser("keys", help="inspect manually configured provider keys")
    keys_sub = p_keys.add_subparsers(dest="keys_command", required=True)
    p_keys_status = keys_sub.add_parser("status", help="show key inventory and provider readiness")
    p_keys_status.add_argument(
        "--target", type=int, default=5, help="desired healthy provider count"
    )
    p_keys_status.add_argument("--all", action="store_true", help="include missing providers")
    p_keys_status.set_defaults(func=cmd_keys_status)
    p_keys_checklist = keys_sub.add_parser(
        "checklist", help="manual actions to reach target capacity"
    )
    p_keys_checklist.add_argument(
        "--target", type=int, default=5, help="desired healthy provider count"
    )
    p_keys_checklist.set_defaults(func=cmd_keys_checklist)
    p_keys_add = keys_sub.add_parser("add")
    p_keys_add.add_argument("provider_arg", nargs="?", help="provider id or external provider name")
    p_keys_add.add_argument("-p", "--provider")
    p_keys_add.add_argument("--value")
    p_keys_add.add_argument("--base-url", help="OpenAI-compatible base URL for a new provider")
    p_keys_add.add_argument("--model", help="default model id for a new provider")
    p_keys_add.add_argument("--label")
    p_keys_add.add_argument("--notes")
    p_keys_add.add_argument("--commercial-allowed", action="store_true")
    p_keys_add.add_argument("-y", "--yes", action="store_true")
    p_keys_add.set_defaults(func=cmd_keys_add)

    p_catalog = sub.add_parser(
        "catalog", help="sync and inspect advisory external provider metadata"
    )
    catalog_sub = p_catalog.add_subparsers(dest="catalog_command", required=True)
    p_catalog_sync = catalog_sub.add_parser(
        "sync", help="sync mnfst/awesome-free-llm-apis metadata into a local cache"
    )
    p_catalog_sync.add_argument(
        "--timeout", type=float, default=20.0, help="download timeout seconds"
    )
    p_catalog_sync.set_defaults(func=cmd_catalog_sync)
    p_catalog_status = catalog_sub.add_parser(
        "status", help="show cached external provider metadata"
    )
    p_catalog_status.add_argument(
        "--limit", type=int, default=10, help="number of providers to show"
    )
    p_catalog_status.set_defaults(func=cmd_catalog_status)

    p_capability = sub.add_parser(
        "capability", help="benchmark-scored model capability for quality routing"
    )
    capability_sub = p_capability.add_subparsers(dest="capability_command", required=True)
    p_cap_sync = capability_sub.add_parser(
        "sync", help="refresh capability scores from public benchmarks (Arena; AA with a key)"
    )
    p_cap_sync.add_argument("--timeout", type=float, default=20.0, help="download timeout seconds")
    p_cap_sync.set_defaults(func=cmd_capability_sync)
    p_cap_status = capability_sub.add_parser(
        "status", help="show capability-score coverage and the top-scoring models"
    )
    p_cap_status.add_argument("--limit", type=int, default=15, help="number of models to show")
    p_cap_status.set_defaults(func=cmd_capability_status)

    p_capacity = sub.add_parser("capacity", help="summarize legitimate LLM capacity")
    capacity_sub = p_capacity.add_subparsers(dest="capacity_command", required=True)
    p_capacity_status = capacity_sub.add_parser(
        "status", help="show provider capacity and quota hints"
    )
    p_capacity_status.add_argument(
        "--target", type=int, default=5, help="desired healthy provider count"
    )
    p_capacity_status.add_argument("--all", action="store_true", help="include missing providers")
    p_capacity_status.add_argument(
        "--no-catalog-sync",
        action="store_true",
        help="use external catalog cache without refreshing",
    )
    p_capacity_status.add_argument(
        "--catalog-timeout", type=float, default=8.0, help="external catalog sync timeout seconds"
    )
    p_capacity_status.add_argument(
        "--external-limit", type=int, default=8, help="external-only candidates to show with --all"
    )
    p_capacity_status.set_defaults(func=cmd_capacity_status)

    p_bench = sub.add_parser(
        "benchmark", help="time each configured provider and report latency / success"
    )
    p_bench.add_argument("-m", "--model", help="pin one model name to test on every provider")
    p_bench.add_argument("-p", "--providers", help="comma-separated provider ids to test")
    p_bench.add_argument("--timeout", type=float, default=30.0, help="per-call timeout seconds")
    p_bench.set_defaults(func=cmd_benchmark)

    p_proxy = sub.add_parser("proxy", help="run the OpenAI-compatible proxy server")
    p_proxy.add_argument("--host", default="127.0.0.1")
    p_proxy.add_argument("--port", type=int, default=8080)
    p_proxy.add_argument(
        "--api-key",
        default=None,
        help="require this Bearer token on requests (or set FREELLMPOOL_PROXY_KEY)",
    )
    p_proxy.set_defaults(func=cmd_proxy)

    p_mcp = sub.add_parser(
        "mcp", help="run an MCP server (stdio) so MCP clients can use free models"
    )
    p_mcp.set_defaults(func=cmd_mcp)

    p_code = sub.add_parser(
        "code", help="wire a coding agent (codex/aider/cline/...) to free models"
    )
    p_code.add_argument("agent", nargs="?", help="agent id (omit to list)")
    p_code.set_defaults(func=cmd_code)

    return parser


def main(argv: list[str] | None = None) -> int:
    from .observe import configure_logging_from_env

    configure_logging_from_env()  # honor FREELLMPOOL_LOG=<level> for the CLI/proxy
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (EOFError, KeyboardInterrupt):
        # No input on a non-TTY/piped stdin (or Ctrl-D/Ctrl-C at a prompt) —
        # exit cleanly instead of dumping a traceback.
        print("\nfreellmpool: cancelled (no input)", file=sys.stderr)
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
