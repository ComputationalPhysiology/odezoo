"""The `odezoo` command line

The parser and the handlers live here; what the output looks like is `render.py`, imported only
by the handlers that print with rich.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from typing import Any

from odezoo import __version__, api
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
