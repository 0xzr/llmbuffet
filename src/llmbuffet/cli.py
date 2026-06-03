"""Command-line interface for llmbuffet.

llmbuffet ask "question"        one-shot completion (reads stdin too)
llmbuffet providers            list configured / available providers
llmbuffet quota                show today's per-provider usage
llmbuffet proxy                run the OpenAI-compatible proxy server
"""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .config import configured_providers, load_catalog
from .errors import AllProvidersExhausted, NoProvidersConfigured
from .quota import QuotaStore
from .router import Buffet


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
        print("llmbuffet: no prompt provided (pass text or pipe stdin)", file=sys.stderr)
        return 3

    # Support `--model provider/model` as a shorthand for picking an exact
    # model on an exact provider (in addition to `--providers` + bare `--model`).
    model_filter = args.model
    provider_filter = args.providers.split(",") if args.providers else None
    if model_filter and "/" in model_filter:
        prov, _, mdl = model_filter.partition("/")
        provider_filter = [prov]
        model_filter = mdl

    buffet = Buffet.from_default_config()
    try:
        reply = buffet.ask(
            prompt,
            system=args.system,
            model=model_filter,
            providers=provider_filter,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
        )
    except NoProvidersConfigured as exc:
        print(f"llmbuffet: {exc}", file=sys.stderr)
        return 3
    except AllProvidersExhausted as exc:
        print(f"llmbuffet: {exc}", file=sys.stderr)
        return 4

    print(reply.text)
    if args.verbose:
        print(f"\n[served by {reply.provider_id}/{reply.model}]", file=sys.stderr)
    return 0


def cmd_providers(args: argparse.Namespace) -> int:
    catalog = load_catalog()
    configured = {p.id for p in configured_providers(catalog)}
    n_models = sum(len(p.models) for p in catalog)
    print(f"llmbuffet catalog: {len(catalog)} providers, {n_models} models\n")
    for p in catalog:
        mark = "✓" if p.id in configured else "·"
        status = "configured" if p.id in configured else f"set {p.key_env}"
        print(f"  {mark} {p.id:<12} {p.label:<28} {len(p.models):>2} models   [{status}]")
    if not configured:
        print("\nNo providers configured yet. See .env.example for the env vars to set.")
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
            shown += 1
            print(f"    {p.id}/{m.name}")
    if shown == 0:
        print("No models match. Try `llmbuffet providers` to see configuration status.")
        return 0
    print(
        f"\nPass any id above to `--model`, e.g. "
        f'`llmbuffet ask -m {catalog[0].id}/{catalog[0].models[0].name} "hi"`,'
    )
    print("or just `--model <model-name>` to use that model on any provider that has it.")
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


def cmd_proxy(args: argparse.Namespace) -> int:
    from .proxy import serve  # lazy: avoids http.server import on other paths

    buffet = Buffet.from_default_config()
    if not buffet.providers:
        print(
            "llmbuffet: no providers configured; set at least one API key "
            "(see .env.example) before starting the proxy.",
            file=sys.stderr,
        )
        return 3

    httpd = serve(buffet, host=args.host, port=args.port)
    n_models = sum(len(p.models) for p in buffet.providers)
    print(
        f"llmbuffet proxy on http://{args.host}:{args.port}/v1  "
        f"({len(buffet.providers)} providers, {n_models} models)\n"
        f"  point your OpenAI client at:  OPENAI_BASE_URL=http://{args.host}:{args.port}/v1\n"
        "  press Ctrl-C to stop",
        file=sys.stderr,
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nllmbuffet: shutting down", file=sys.stderr)
    finally:
        httpd.server_close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="llmbuffet",
        description="Pool free-tier LLM APIs behind one OpenAI-compatible endpoint.",
    )
    parser.add_argument("--version", action="version", version=f"llmbuffet {__version__}")
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
    p_ask.add_argument("-v", "--verbose", action="store_true", help="report which provider served")
    p_ask.set_defaults(func=cmd_ask)

    p_prov = sub.add_parser("providers", help="list providers and configuration status")
    p_prov.set_defaults(func=cmd_providers)

    p_models = sub.add_parser("models", help="list every available provider/model id")
    p_models.add_argument("-p", "--providers", help="comma-separated provider ids to filter")
    p_models.add_argument(
        "-c", "--configured-only", action="store_true", help="only show configured providers"
    )
    p_models.set_defaults(func=cmd_models)

    p_quota = sub.add_parser("quota", help="show today's per-provider usage")
    p_quota.set_defaults(func=cmd_quota)

    p_proxy = sub.add_parser("proxy", help="run the OpenAI-compatible proxy server")
    p_proxy.add_argument("--host", default="127.0.0.1")
    p_proxy.add_argument("--port", type=int, default=8080)
    p_proxy.set_defaults(func=cmd_proxy)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
