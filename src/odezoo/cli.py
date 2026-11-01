"""The `odezoo` command line

The parser and the handlers live here; what the output looks like is `render.py`, imported only
by the handlers that print with rich.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from contextlib import nullcontext
from pathlib import Path
from typing import Any

from odezoo import __version__, api
from odezoo.cache import Cache, cache_dir
from odezoo.errors import OdezooError
from odezoo.schema import CATEGORIES, FORMATS, model_to_dict

Handler = Callable[[argparse.Namespace], int]

# Python 3.14 suggests the right subcommand or choice for a typo.
PARSER_OPTIONS: dict[str, Any] = {"suggest_on_error": True} if sys.version_info >= (3, 14) else {}


def _global_options(parser: argparse.ArgumentParser, *, suppress: bool) -> None:
    """--registry and --cache-dir, accepted before and after the command

    On the subcommands the default is SUPPRESS, so a value given before the command is kept.
    """
    default = argparse.SUPPRESS if suppress else None
    group = parser.add_argument_group("global options")
    group.add_argument(
        "--registry",
        metavar="PATH",
        default=default,
        help="use the registry checkout at PATH instead of the bundled one (env ODEZOO_REGISTRY)",
    )
    group.add_argument(
        "--cache-dir",
        metavar="PATH",
        default=default,
        help="keep downloads in PATH (env ODEZOO_CACHE_DIR)",
    )


def _command(commands: Any, name: str, help: str, handler: Handler) -> argparse.ArgumentParser:
    parser = commands.add_parser(name, help=help, description=help, **PARSER_OPTIONS)
    _global_options(parser, suppress=True)
    parser.set_defaults(handler=handler)
    return parser


def _search(args: argparse.Namespace) -> int:
    found = api.search(
        " ".join(args.text),
        category=args.category,
        keyword=args.keyword,
        species=args.species,
        format=args.format,
        reviewed=args.reviewed,
        registry=args.registry,
    )
    if args.ids:
        for m in found:
            print(m.id)
        return 0
    if args.json:
        print(json.dumps([model_to_dict(m) for m in found], indent=2))
        return 0
    from odezoo import render

    if not found:
        render.console(stderr=True).print("No models match.")
        return 0
    render.print_models(found, render.console())
    return 0


def _info(args: argparse.Namespace) -> int:
    model = api.model(args.id, registry=args.registry)
    if args.json:
        print(json.dumps(model_to_dict(model), indent=2))
        return 0
    from odezoo import render

    render.print_model(model, render.console())
    return 0


def _fetch(args: argparse.Namespace) -> int:
    ids = list(dict.fromkeys(args.ids))
    if args.version is not None and len(ids) > 1:
        args.command_parser.error("--version can only be used with one model id")
    output = Path(args.output)
    if output.exists() and not output.is_dir():
        raise OdezooError(f"{output} is not a folder")
    output.mkdir(parents=True, exist_ok=True)
    from rich.progress import Progress

    from odezoo import render

    out, err = render.console(), render.console(stderr=True)
    failed = 0
    progress = Progress(console=out, transient=True) if len(ids) > 1 and out.is_terminal else None
    with progress or nullcontext():
        task = progress.add_task("Fetching", total=len(ids)) if progress else None
        for id in ids:
            try:
                path = api.get(
                    id,
                    version=args.version,
                    format=args.format,
                    dest=output,
                    cache=not args.no_cache,
                    cache_dir=args.cache_dir,
                    registry=args.registry,
                    force=args.force,
                )
            except OdezooError as e:
                render.print_error(e, err, prefix=f"{id}: ")
                failed += 1
            else:
                render.print_fetched(id, path, out)
            if progress is not None and task is not None:
                progress.advance(task)
    return 1 if failed else 0


def _cache_dir(args: argparse.Namespace) -> int:
    print(cache_dir(args.cache_dir))
    return 0


def _cache_clear(args: argparse.Namespace) -> int:
    directory = cache_dir(args.cache_dir)
    removed = Cache(directory).clear()
    print(f"Removed {removed} file{'' if removed == 1 else 's'} from {directory}")
    return 0


def _group(commands: Any, name: str, help: str) -> tuple[argparse.ArgumentParser, Any]:
    """A command that only holds subcommands; on its own it prints its help (exit 2)"""
    parser = commands.add_parser(name, help=help, description=help, **PARSER_OPTIONS)

    def usage(args: argparse.Namespace) -> int:
        parser.print_help(sys.stderr)
        return 2

    parser.set_defaults(handler=usage)
    return parser, parser.add_subparsers(metavar="COMMAND")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="odezoo",
        description="Search the odezoo registry of ODE models and fetch their files.",
        **PARSER_OPTIONS,
    )
    parser.add_argument("--version", action="version", version=f"odezoo {__version__}")
    _global_options(parser, suppress=False)
    commands = parser.add_subparsers(dest="command", metavar="COMMAND")

    search = _command(commands, "search", "find models by text and filters", _search)
    search.add_argument("text", nargs="*", help="words that must all occur in a model's details")
    search.add_argument(
        "--category", action="append", choices=CATEGORIES, help="repeat for any of several"
    )
    search.add_argument("--keyword", action="append", help="repeat for any of several")
    search.add_argument("--species", action="append", help="repeat for any of several")
    search.add_argument("--format", choices=list(FORMATS))
    reviewed = search.add_mutually_exclusive_group()
    reviewed.add_argument("--reviewed", dest="reviewed", action="store_const", const=True)
    reviewed.add_argument("--unreviewed", dest="reviewed", action="store_const", const=False)
    output = search.add_mutually_exclusive_group()
    output.add_argument("--ids", action="store_true", help="print only the ids, one per line")
    output.add_argument("--json", action="store_true", help="print the models as JSON")

    info = _command(commands, "info", "show a model's paper, versions and sources", _info)
    info.add_argument("id")
    info.add_argument("--json", action="store_true", help="print the model as JSON")

    fetch = _command(commands, "fetch", "download models' files, verified by sha256", _fetch)
    fetch.set_defaults(command_parser=fetch)
    fetch.add_argument("ids", nargs="+", metavar="ID")
    fetch.add_argument("--version", help="the version to fetch (one model id only)")
    fetch.add_argument("--format", choices=list(FORMATS), help="the newest version in FORMAT")
    fetch.add_argument(
        "-o", "--output", default=".", metavar="DIR", help="folder to write <id>.<ext> into"
    )
    fetch.add_argument("--force", action="store_true", help="overwrite a different file")
    fetch.add_argument(
        "--no-cache", action="store_true", help="download again; do not read or write the cache"
    )

    _, cache = _group(commands, "cache", "show or empty the download cache")
    _command(cache, "dir", "print the cache folder", _cache_dir)
    _command(cache, "clear", "delete everything odezoo cached", _cache_clear)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler: Handler | None = getattr(args, "handler", None)
    if handler is None:
        parser.print_help(sys.stderr)
        return 2
    try:
        return handler(args)
    except OdezooError as e:
        from odezoo import render

        render.print_error(e, render.console(stderr=True))
        return 1
    except KeyboardInterrupt:
        return 130
