"""The `odezoo` command line

The parser and the handlers live here; what the output looks like is `render.py`, imported only
by the handlers that print with rich.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Sequence
from contextlib import nullcontext
from datetime import date
from pathlib import Path
from typing import Any

from . import __version__, api
from .cache import Cache, cache_dir
from .errors import OdezooError, RegistryError
from .registry import ENV_VAR as REGISTRY_ENV_VAR
from .registry import build, resolve_commit
from .schema import CATEGORIES, FORMATS, model_to_dict

Handler = Callable[[argparse.Namespace], int]

# Python 3.14 suggests the right subcommand or choice for a typo.
PARSER_OPTIONS: dict[str, Any] = {"suggest_on_error": True} if sys.version_info >= (3, 14) else {}


def _global_options(parser: argparse.ArgumentParser, *, suppress: bool) -> None:
    """Add --registry and --cache-dir, which are accepted before and after the command

    On the subcommands the default is SUPPRESS, so a value given before the command is kept.

    Parameters
    ----------
    parser : argparse.ArgumentParser
        The top-level parser, or a subcommand's parser
    suppress : bool
        Whether to leave the options out of the namespace when they are not given, as the
        subcommands must
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
    """Add a subcommand that runs `handler`

    Parameters
    ----------
    commands : Any
        The subparsers action to add it to
    name : str
        The subcommand's name
    help : str
        One line about it, for its own help and the help of the command above it
    handler : Handler
        The function that runs it

    Returns
    -------
    argparse.ArgumentParser
        The subcommand's parser, for adding its arguments
    """
    parser = commands.add_parser(name, help=help, description=help, **PARSER_OPTIONS)
    _global_options(parser, suppress=True)
    parser.set_defaults(handler=handler)
    return parser


def _search(args: argparse.Namespace) -> int:
    """Run `odezoo search`: print the matching models as a table, as ids, or as JSON

    Parameters
    ----------
    args : argparse.Namespace
        The parsed command line

    Returns
    -------
    int
        The exit code, 0
    """
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
    from . import render

    if not found:
        render.console(stderr=True).print("No models match.")
        return 0
    render.print_models(found, render.console())
    return 0


def _info(args: argparse.Namespace) -> int:
    """Run `odezoo info`: print one model's details, or its JSON

    Parameters
    ----------
    args : argparse.Namespace
        The parsed command line

    Returns
    -------
    int
        The exit code, 0
    """
    model = api.model(args.id, registry=args.registry)
    if args.json:
        print(json.dumps(model_to_dict(model), indent=2))
        return 0
    from . import render

    render.print_model(model, render.console())
    return 0


def _fetch(args: argparse.Namespace) -> int:
    """Run `odezoo fetch`: write each model's file into the output folder

    A model that fails is reported, and the others are still fetched. With more than one id and
    output to a terminal, a progress bar shows.

    Parameters
    ----------
    args : argparse.Namespace
        The parsed command line

    Returns
    -------
    int
        The exit code: 0 if every file was fetched, else 1

    Raises
    ------
    OdezooError
        If the output folder is a file or cannot be made
    """
    ids = list(dict.fromkeys(args.ids))
    if args.version is not None and len(ids) > 1:
        args.command_parser.error("--version can only be used with one model id")
    output = Path(args.output)
    if output.exists() and not output.is_dir():
        raise OdezooError(f"{output} is not a folder")
    try:
        output.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise OdezooError(f"cannot use {output} as the output folder ({e})") from None
    from rich.progress import Progress

    from . import render

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
            except (OdezooError, OSError) as e:
                render.print_error(e, err, prefix=f"{id}: ")
                failed += 1
            else:
                render.print_fetched(id, path, out)
            if progress is not None and task is not None:
                progress.advance(task)
    return 1 if failed else 0


def _cache_dir(args: argparse.Namespace) -> int:
    """Run `odezoo cache dir`: print the cache folder

    Parameters
    ----------
    args : argparse.Namespace
        The parsed command line

    Returns
    -------
    int
        The exit code, 0
    """
    print(cache_dir(args.cache_dir))
    return 0


def _cache_clear(args: argparse.Namespace) -> int:
    """Run `odezoo cache clear`: delete the cached files, and say how many there were

    Parameters
    ----------
    args : argparse.Namespace
        The parsed command line

    Returns
    -------
    int
        The exit code, 0
    """
    directory = cache_dir(args.cache_dir)
    removed = Cache(directory).clear()
    print(f"Removed {removed} file{'' if removed == 1 else 's'} from {directory}")
    return 0


def _registry_root(args: argparse.Namespace) -> Path:
    """Find the checkout the maintainer commands work on: --registry, $ODEZOO_REGISTRY, or here

    Parameters
    ----------
    args : argparse.Namespace
        The parsed command line

    Returns
    -------
    Path
        The checkout

    Raises
    ------
    RegistryError
        If that folder has no `models/` folder
    """
    root = Path(args.registry or os.environ.get(REGISTRY_ENV_VAR) or ".")
    if not (root / "models").is_dir():
        raise RegistryError(
            f"{root.resolve()} has no models/ folder; "
            "run this in a registry checkout or pass --registry PATH"
        )
    return root


def _registry_check(args: argparse.Namespace) -> int:
    """Run `odezoo registry check`: check the checkout's models and print what is wrong

    Parameters
    ----------
    args : argparse.Namespace
        The parsed command line

    Returns
    -------
    int
        The exit code: 0 if there are no errors (warnings are allowed), else 1
    """
    from . import render
    from .maintain.check import check

    report = check(_registry_root(args), args.ids or None)
    render.print_report(report, render.console())
    return 0 if report.ok else 1


def _registry_build(args: argparse.Namespace) -> int:
    """Run `odezoo registry build`: write the checkout's `registry.json`

    The mirror URLs are pinned to $ODEZOO_REGISTRY_COMMIT, else to the checkout's commit.

    Parameters
    ----------
    args : argparse.Namespace
        The parsed command line

    Returns
    -------
    int
        The exit code, 0
    """
    root = _registry_root(args)
    commit = os.environ.get("ODEZOO_REGISTRY_COMMIT") or resolve_commit(root)
    data = build(root, commit=commit, built=date.today())
    output = Path(args.output)
    output.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(output)
    return 0


def _registry_add_version(args: argparse.Namespace) -> int:
    """Run `odezoo registry add version`: add an edited file as a new version of a model

    Parameters
    ----------
    args : argparse.Namespace
        The parsed command line

    Returns
    -------
    int
        The exit code, 0
    """
    from .maintain.version import add_version

    version = add_version(
        _registry_root(args),
        args.id,
        Path(args.file),
        derived_from=args.derived_from,
        license=args.license,
        notes=args.notes,
    )
    print(f"Added {args.id} {version.id} ({version.format})")
    return 0


def _group(commands: Any, name: str, help: str) -> tuple[argparse.ArgumentParser, Any]:
    """Add a command that only holds subcommands; on its own it prints its help (exit 2)

    Parameters
    ----------
    commands : Any
        The subparsers action to add it to
    name : str
        The command's name
    help : str
        One line about it

    Returns
    -------
    tuple[argparse.ArgumentParser, Any]
        The command's parser, and the subparsers action to add its subcommands to
    """
    parser = commands.add_parser(name, help=help, description=help, **PARSER_OPTIONS)

    def usage(args: argparse.Namespace) -> int:
        """Print the command's help, as it was run without a subcommand

        Parameters
        ----------
        args : argparse.Namespace
            The parsed command line, which is not used

        Returns
        -------
        int
            The exit code of a usage error, 2
        """
        parser.print_help(sys.stderr)
        return 2

    parser.set_defaults(handler=usage)
    return parser, parser.add_subparsers(metavar="COMMAND")


def build_parser() -> argparse.ArgumentParser:
    """Build the parser for the `odezoo` command line

    Returns
    -------
    argparse.ArgumentParser
        The parser; each command sets `handler` in the namespace to the function that runs it
    """
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

    _, registry = _group(commands, "registry", "maintain a registry checkout")
    check = _command(registry, "check", "check models and their files", _registry_check)
    check.add_argument("ids", nargs="*", metavar="ID", help="only these models")
    build_command = _command(registry, "build", "write registry.json", _registry_build)
    build_command.add_argument("-o", "--output", default="registry.json", metavar="PATH")
    _, add = _group(registry, "add", "add models or versions to the checkout")
    version = _command(add, "version", "add our own file as a new version", _registry_add_version)
    version.add_argument("id", metavar="ID")
    version.add_argument("file", metavar="FILE", help="a .cellml or .ode file")
    version.add_argument("--derived-from", required=True, metavar="V", help="the version it edits")
    version.add_argument("--license", metavar="SPDX", help="default: that of --derived-from")
    version.add_argument("--notes", metavar="TEXT", help="what was changed, and why")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the `odezoo` command line

    Errors odezoo raises on purpose, and files or folders that cannot be read or written, are
    printed without a traceback.

    Parameters
    ----------
    argv : Sequence[str], optional
        The arguments, by default `sys.argv[1:]`

    Returns
    -------
    int
        The exit code: 0 on success, 1 on an error, 2 when a command is missing, and 130 when
        interrupted. A malformed command line exits with 2 from argparse itself.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    handler: Handler | None = getattr(args, "handler", None)
    if handler is None:
        parser.print_help(sys.stderr)
        return 2
    try:
        return handler(args)
    except (OdezooError, OSError) as e:  # OSError: a folder that cannot be read or written
        from . import render

        render.print_error(e, render.console(stderr=True))
        return 1
    except KeyboardInterrupt:
        return 130
