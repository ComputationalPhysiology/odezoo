"""Simulate every model in the registry with gotranx, for the site

    odezoo --registry . registry build -o registry.json
    python tools/simulate_models.py registry.json models docs/simulations

Each model's default version is read from the checkout, byte for byte as recorded: CellML is
converted with gotranx through myokit, gotranx generates Python code for it, and scipy integrates
it for a few seconds of model time. Electrophysiology models run with their own stimulus; the
contraction models from crossbridge have their calcium input set from the transient crossbridge
drives them with; the circulation model runs on its defaults. Each model runs in its own process
under a time limit, and the outcome of every model goes to `status.json`, with a figure for each
model that got far enough. A model that fails is recorded, never raised: the site reports it.
"""

from __future__ import annotations

import argparse
import json
import logging
import multiprocessing
import os
import queue
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np

#: The panel that plots the left ventricle's pressure against its volume
PV_LOOP = "LV pressure–volume"

Calcium = Callable[[np.ndarray], np.ndarray]


class SimulationError(Exception):
    """A model failed at one stage of its simulation

    Parameters
    ----------
    stage : str
        `load`, `codegen`, `simulate` or `plot`
    message : str
        What went wrong
    """

    def __init__(self, stage: str, message: str) -> None:
        super().__init__(message)
        self.stage = stage


@dataclass
class Trace:
    """A simulation's result

    Parameters
    ----------
    t : np.ndarray
        Time, in seconds
    values : dict[str, np.ndarray]
        Every state and intermediate, and the calcium input when there is one, by name
    """

    t: np.ndarray
    values: dict[str, np.ndarray]


def _rdq20_mf_calcium(t: np.ndarray) -> np.ndarray:
    """Give the human calcium transient that drives RDQ20-MF, in µM

    A copy of `_calcium_human` in crossbridge's `demo/reproduce_figures_rdq20mf.py` (commit
    80cb6c2), which is not part of the crossbridge package: a bi-exponential approximation of the
    ToR-ORd calcium transient.

    Parameters
    ----------
    t : np.ndarray
        Time since the stimulus, in seconds

    Returns
    -------
    np.ndarray
        Calcium, in µM
    """
    c0, t_peak, cmax, tau1, tau2 = 0.1, 0.065, 0.80, 0.030, 0.180
    ratio = tau1 / tau2
    beta = ratio ** (-1 / (ratio - 1)) - ratio ** (-1 / (1 - tau2 / tau1))
    dt = np.maximum(t - t_peak, 0.0)
    pulse = c0 + (cmax - c0) / beta * (np.exp(-dt / tau1) - np.exp(-dt / tau2))
    return np.maximum(np.where(t >= t_peak, pulse, c0), c0)


def _transients() -> dict[str, tuple[float, Calcium]]:
    """Map each contraction model to its beat period and the calcium transient crossbridge uses

    Returns
    -------
    dict[str, tuple[float, Calcium]]
        Per model id: the period in seconds, and calcium in µM against time in the beat in seconds
    """
    from crossbridge.utils import calcium_trace, janssen_calcium, musgrave_calcium, rice_calcium

    def land(t: np.ndarray) -> np.ndarray:
        return calcium_trace(t, c0=0.15, cmax=0.6, tau1=0.02, tau2=0.11, t0=0.05)

    def lewalle(t: np.ndarray) -> np.ndarray:
        return calcium_trace(t, c0=0.1, cmax=5.0, tau1=0.02, tau2=0.15, t0=0.05)

    def janssen(t: np.ndarray) -> np.ndarray:
        return janssen_calcium(t, 2.0)

    return {
        "land_2017": (1.0, land),
        "lewalle_2024": (1.0, lewalle),
        "rice_2008": (1.0, rice_calcium),
        "tran_2010": (1.0, rice_calcium),
        "marzban_2020": (0.5, janssen),
        "tewari_2016": (0.5, janssen),
        "musgrave_2025": (1.0, musgrave_calcium),
        "rdq20_mf": (1.0, _rdq20_mf_calcium),
    }


#: The contraction models whose `Ca` input follows a transient, by id
CALCIUM = (
    "land_2017",
    "lewalle_2024",
    "rice_2008",
    "tran_2010",
    "marzban_2020",
    "tewari_2016",
    "musgrave_2025",
    "rdq20_mf",
)


def calcium(model_id: str) -> Calcium | None:
    """Give the calcium transient that drives a contraction model, repeated every beat

    Parameters
    ----------
    model_id : str
        The model's id

    Returns
    -------
    Calcium | None
        Calcium in µM against time in seconds, or `None` for a model not driven by calcium
    """
    if model_id not in CALCIUM:
        return None
    period, transient = _transients()[model_id]

    def periodic(t: np.ndarray) -> np.ndarray:
        phase = np.mod(np.atleast_1d(np.asarray(t, dtype=float)), period)
        return np.asarray(transient(phase), dtype=float)

    return periodic


def load(path: Path) -> tuple[Any, float]:
    """Load a model file with gotranx

    Parameters
    ----------
    path : Path
        A `.cellml` or `.ode` file

    Returns
    -------
    tuple[Any, float]
        The gotranx ODE, and the seconds in one of its time units (`.ode` files are in seconds)

    Raises
    ------
    SimulationError
        At stage `load`, if gotranx (or myokit) cannot read the file, or its time unit is neither
        seconds nor milliseconds
    """
    import gotranx

    try:
        if path.suffix == ".cellml":
            import myokit.formats.cellml
            from gotranx.myokit import myokit_to_gotran

            model = myokit.formats.cellml.CellMLImporter().model(str(path))
            unit = str(model.time().unit())
            seconds = {"[s]": 1.0, "[ms]": 1e-3}.get(unit)
            if seconds is None:
                raise SimulationError("load", f"time is in {unit}, neither seconds nor ms")
            # gotranx sorts a converted model's assignments only once it is read back from an
            # .ode file, as `gotranx cellml2ode` writes it.
            with tempfile.TemporaryDirectory() as folder:
                converted = Path(folder) / f"{path.stem}.ode"
                myokit_to_gotran(model).save(converted)
                return gotranx.load_ode(converted), seconds
        return gotranx.load_ode(path), 1.0
    except SimulationError:
        raise
    except Exception as e:
        raise SimulationError("load", _describe(e)) from e


def _describe(error: BaseException) -> str:
    """Describe an exception on one line

    Parameters
    ----------
    error : BaseException
        The exception

    Returns
    -------
    str
        Its type and the first line of its message, at most 500 characters
    """
    message = str(error).strip().splitlines()
    text = f"{type(error).__name__}: {message[0]}" if message else type(error).__name__
    return text[:500]


def _max_step(parameters: dict[str, float], end: float) -> float:
    """Choose the longest step the solver may take, so that it cannot step over a stimulus

    Parameters
    ----------
    parameters : dict[str, float]
        The model's parameters, by name
    end : float
        The end of the simulation, in the model's time unit

    Returns
    -------
    float
        Half the stimulus duration when a parameter names one, otherwise `end / 2000`
    """
    for name, value in parameters.items():
        lower = name.lower()
        if "stim" in lower and ("duration" in lower or "width" in lower) and value > 0:
            return min(value / 2, end / 2000)
    return end / 2000


def simulate(
    ode: Any, seconds_per_unit: float, *, duration: float = 3.0, calcium: Calcium | None = None
) -> Trace:
    """Integrate a model from its initial values

    Parameters
    ----------
    ode : Any
        A gotranx ODE
    seconds_per_unit : float
        The seconds in one of the model's time units
    duration : float, optional
        How long to simulate, in seconds, by default 3.0
    calcium : Calcium | None, optional
        Calcium in µM against time in seconds, set as the parameter `Ca` throughout, by default
        `None`, which leaves the parameters as they are

    Returns
    -------
    Trace
        The states and intermediates, about 1000 samples per second

    Raises
    ------
    SimulationError
        At stage `codegen` if gotranx cannot generate code for the model, and at `simulate` if
        the integration fails or gives a value that is not finite
    """
    from gotranx.cli.gotran2py import get_code
    from scipy.integrate import solve_ivp

    try:
        if ode.missing_variables:
            names = ", ".join(sorted(ode.missing_variables))
            raise SimulationError("codegen", f"the model has missing variables: {names}")
        namespace: dict[str, Any] = {}
        exec(compile(get_code(ode), f"<{ode.name}>", "exec"), namespace)
        y0 = np.asarray(namespace["init_state_values"](), dtype=float)
        p0 = np.asarray(namespace["init_parameter_values"](), dtype=float)
        parameter_index = namespace["parameter_index"]
        state_names = [s.name for s in ode.states]
        state_at = [namespace["state_index"](n) for n in state_names]
        monitor_names = [x.name for x in ode.intermediates]
        monitor_at = [namespace["monitor_index"](n) for n in monitor_names]
        parameters = {p.name: float(p0[parameter_index(p.name)]) for p in ode.parameters}
        ca_at = parameter_index("Ca") if calcium is not None else None
    except SimulationError:
        raise
    except Exception as e:
        raise SimulationError("codegen", _describe(e)) from e

    rhs, monitor_values = namespace["rhs"], namespace["monitor_values"]

    def with_calcium(t: float) -> np.ndarray:
        if ca_at is None or calcium is None:
            return p0
        p = p0.copy()
        p[ca_at] = calcium(np.array([t * seconds_per_unit]))[0]
        return p

    def f(t: float, y: np.ndarray) -> np.ndarray:
        return np.asarray(rhs(t, y, with_calcium(t)), dtype=float)

    end = duration / seconds_per_unit
    samples = max(int(round(duration * 1000)), 10) + 1
    t_eval = np.linspace(0.0, end, samples)
    try:
        with np.errstate(all="ignore"):
            solution = solve_ivp(
                f,
                (0.0, end),
                y0,
                method="BDF",
                t_eval=t_eval,
                rtol=1e-6,
                atol=1e-8,
                max_step=_max_step(parameters, end),
            )
            if not solution.success:
                raise SimulationError("simulate", f"the solver stopped: {solution.message}")
            if not np.all(np.isfinite(solution.y)):
                raise SimulationError("simulate", "a state became NaN or infinite")
            monitors = np.array(
                [
                    monitor_values(t, y, with_calcium(t))
                    for t, y in zip(solution.t, solution.y.T, strict=True)
                ]
            ).T
    except SimulationError:
        raise
    except Exception as e:
        raise SimulationError("simulate", _describe(e)) from e
    values = {name: solution.y[i] for name, i in zip(state_names, state_at, strict=True)}
    if monitor_names:
        values.update(
            {name: monitors[i] for name, i in zip(monitor_names, monitor_at, strict=True)}
        )
    t = solution.t * seconds_per_unit
    if calcium is not None:
        values["Ca"] = calcium(t)
    return Trace(t=t, values=values)


#: What to plot per category: panel title, and the names to look for, first match wins
_PANELS: dict[str, list[tuple[str, list[str]]]] = {
    "electrophysiology": [
        ("Membrane voltage", ["V", "Vm", "V_m"]),
        ("Cytosolic Ca", ["Ca_i", "Cai", "Ca_i_free", "Ca_myo"]),
    ],
    "myofilament_mechanics": [("Ca (input)", ["Ca"]), ("Active tension", ["Ta"])],
}


def panels(trace: Trace, category: str) -> list[tuple[str, list[str]]]:
    """Choose what to plot for a model

    Parameters
    ----------
    trace : Trace
        The simulation
    category : str
        The model's first category

    Returns
    -------
    list[tuple[str, list[str]]]
        Per panel, its title and the names it plots. A panel whose variables the model lacks is
        left out; when none is left, one panel of the first four states. The panel `PV_LOOP`
        plots its second name against its first.
    """
    lower = {name.lower(): name for name in trace.values}
    chosen: list[tuple[str, list[str]]] = []
    if category == "cardiovascular_circulation":
        if "v_lv" in lower and "p_lv" in lower:
            chosen.append((PV_LOOP, [lower["v_lv"], lower["p_lv"]]))
        pressures = sorted(n for n in trace.values if n.startswith("p_"))
        if pressures:
            chosen.append(("Pressures", pressures))
    for title, candidates in _PANELS.get(category, []):
        found = next((lower[c.lower()] for c in candidates if c.lower() in lower), None)
        if found is not None:
            chosen.append((title, [found]))
    return chosen or [("States", list(trace.values)[:4])]


def plot(trace: Trace, chosen: list[tuple[str, list[str]]], title: str, path: Path) -> None:
    """Plot a simulation to a PNG

    Parameters
    ----------
    trace : Trace
        The simulation
    chosen : list[tuple[str, list[str]]]
        The panels, as `panels` gives them
    title : str
        The figure's title
    path : Path
        Where to write the PNG
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(len(chosen), 1, figsize=(7, 2.4 * len(chosen)), squeeze=False)
    for ax, (panel, names) in zip(axes[:, 0], chosen, strict=True):
        if panel == PV_LOOP:
            ax.plot(trace.values[names[0]], trace.values[names[1]])
            ax.set_xlabel(names[0])
            ax.set_ylabel(names[1])
        else:
            for name in names:
                ax.plot(trace.t, trace.values[name], label=name)
            ax.set_xlabel("Time (s)")
            if len(names) > 1:
                ax.legend(fontsize="small", ncol=min(len(names), 4))
            else:
                ax.set_ylabel(names[0])
        ax.set_title(panel, fontsize="medium")
        ax.grid(alpha=0.3)
    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(path, dpi=100)
    plt.close(fig)


@dataclass
class Job:
    """A model to simulate

    Parameters
    ----------
    id : str
        The model's id
    version : str
        The id of the version simulated, the model's default
    path : Path | None
        The version's file in the checkout, or `None` when the checkout has no copy
    category : str
        The model's first category, which chooses the plots
    title : str
        The figure's title
    """

    id: str
    version: str
    path: Path | None
    category: str
    title: str


@dataclass
class Outcome:
    """How a model's simulation went

    Parameters
    ----------
    id : str
        The model's id
    version : str
        The version simulated
    status : Literal["ok", "failed", "timeout"]
        Whether it ran
    stage : str | None
        Where it failed: `load`, `codegen`, `simulate` or `plot`, or `None`
    error : str | None
        What went wrong, on one line
    seconds : float
        How long it took
    figure : str | None
        The PNG's file name in the output folder, when one was written
    """

    id: str
    version: str
    status: Literal["ok", "failed", "timeout"]
    stage: str | None
    error: str | None
    seconds: float
    figure: str | None


def jobs(registry: Any, models_dir: Path) -> list[Job]:
    """List the default version of every model, by id

    Parameters
    ----------
    registry : Registry
        The registry
    models_dir : Path
        The checkout's `models` folder

    Returns
    -------
    list[Job]
        One job per model, sorted by id
    """
    from odezoo.resolve import choose_version

    result = []
    for model_id in sorted(registry.models):
        model = registry.models[model_id]
        version = choose_version(model)
        path = models_dir / model_id / version.file if version.file else None
        result.append(Job(model_id, version.id, path, model.categories[0], model.name))
    return result


def run_one(job: Job, out_dir: Path) -> Outcome:
    """Simulate one model and plot it, recording any failure rather than raising it

    Parameters
    ----------
    job : Job
        The model
    out_dir : Path
        Where to write the figure, `<id>.png`

    Returns
    -------
    Outcome
        How it went
    """
    import gotranx  # noqa: F401
    import structlog

    # gotranx reports every step of loading a model; only its errors matter here. It sets up its
    # logging when imported, so this comes after the import.
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.ERROR))
    started = time.monotonic()

    def outcome(status: Any, stage: str | None, error: str | None, figure: str | None) -> Outcome:
        seconds = round(time.monotonic() - started, 2)
        return Outcome(job.id, job.version, status, stage, error, seconds, figure)

    try:
        if job.path is None or not job.path.is_file():
            raise SimulationError("load", "the checkout has no copy of this version")
        ode, seconds_per_unit = load(job.path)
        trace = simulate(ode, seconds_per_unit, calcium=calcium(job.id))
        figure = f"{job.id}.png"
        try:
            plot(trace, panels(trace, job.category), job.title, out_dir / figure)
        except Exception as e:
            raise SimulationError("plot", _describe(e)) from e
    except SimulationError as e:
        return outcome("failed", e.stage, str(e), None)
    except Exception as e:
        return outcome("failed", None, _describe(e), None)
    return outcome("ok", None, None, figure)


def _child(worker: Callable[[Job, Path], Outcome], job: Job, out_dir: Path, results: Any) -> None:
    """Run one job in a child process and send back its outcome

    Parameters
    ----------
    worker : Callable[[Job, Path], Outcome]
        What runs the job
    job : Job
        The job
    out_dir : Path
        The output folder
    results : multiprocessing.Queue
        Where the outcome goes, as `(id, dict)`
    """
    results.put((job.id, asdict(worker(job, out_dir))))


def run_all(
    jobs: list[Job],
    out_dir: Path,
    *,
    timeout: float,
    workers: int,
    worker: Callable[[Job, Path], Outcome] = run_one,
) -> dict[str, Outcome]:
    """Run every job, each in its own process, at most `workers` at a time

    Parameters
    ----------
    jobs : list[Job]
        The models
    out_dir : Path
        Where the figures go
    timeout : float
        Seconds a job may take before its process is stopped and it is recorded as `timeout`
    workers : int
        How many processes run at once
    worker : Callable[[Job, Path], Outcome], optional
        What runs a job in its process, by default `run_one`

    Returns
    -------
    dict[str, Outcome]
        Every job's outcome, by model id
    """
    # The children import this module by name, wherever it was loaded from.
    here = str(Path(__file__).resolve().parent)
    if here not in sys.path:
        sys.path.insert(0, here)
    context = multiprocessing.get_context("spawn")
    results = context.Queue()
    pending = list(jobs)
    running: dict[str, tuple[Any, Job, float]] = {}
    outcomes: dict[str, Outcome] = {}

    def drain(wait: float) -> None:
        try:
            while True:
                model_id, data = results.get(timeout=wait)
                outcomes[model_id] = Outcome(**data)
                wait = 0.0
        except queue.Empty:
            pass

    def failed(job: Job, status: Any, error: str, started: float) -> Outcome:
        seconds = round(time.monotonic() - started, 2)
        return Outcome(job.id, job.version, status, None, error, seconds, None)

    while pending or running:
        while pending and len(running) < max(workers, 1):
            job = pending.pop(0)
            process = context.Process(target=_child, args=(worker, job, out_dir, results))
            process.start()
            running[job.id] = (process, job, time.monotonic())
        drain(0.1)
        for model_id, (process, job, started) in list(running.items()):
            if model_id in outcomes:
                process.join(5)
            elif not process.is_alive():
                drain(0.5)
                if model_id not in outcomes:
                    error = f"the process exited with code {process.exitcode}"
                    outcomes[model_id] = failed(job, "failed", error, started)
            elif time.monotonic() - started > timeout:
                process.terminate()
                process.join(5)
                if process.is_alive():
                    process.kill()
                    process.join()
                error = f"stopped after {timeout:g} s"
                outcomes[model_id] = failed(job, "timeout", error, started)
            else:
                continue
            del running[model_id]
    return outcomes


def write_status(outcomes: dict[str, Outcome], path: Path) -> None:
    """Write every model's outcome as JSON, `{"models": {id: outcome}}`

    Parameters
    ----------
    outcomes : dict[str, Outcome]
        The outcomes, by model id
    path : Path
        The file to write
    """
    data = {"models": {k: asdict(outcomes[k]) for k in sorted(outcomes)}}
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    """Simulate the models and write `status.json` and the figures

    Parameters
    ----------
    argv : Sequence[str], optional
        The arguments, by default `sys.argv[1:]`

    Returns
    -------
    int
        0 whatever the models did, or 2 for a usage error
    """
    parser = argparse.ArgumentParser(prog=Path(__file__).name, description=__doc__.splitlines()[0])
    parser.add_argument("registry_json", type=Path, help="a registry.json, as `registry build`")
    parser.add_argument("models_dir", type=Path, help="the checkout's models folder")
    parser.add_argument("out_dir", type=Path, help="where status.json and the figures go")
    parser.add_argument("--timeout", type=float, default=300.0, help="seconds per model")
    parser.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    parser.add_argument("--only", nargs="+", metavar="ID", help="simulate only these models")
    try:
        args = parser.parse_args(sys.argv[1:] if argv is None else list(argv))
    except SystemExit as e:
        return 0 if e.code == 0 else 2

    from odezoo.registry import from_json

    registry = from_json(json.loads(args.registry_json.read_text(encoding="utf-8")))
    todo = [j for j in jobs(registry, args.models_dir) if not args.only or j.id in args.only]
    args.out_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    outcomes = run_all(todo, args.out_dir, timeout=args.timeout, workers=args.workers)
    write_status(outcomes, args.out_dir / "status.json")
    for model_id in sorted(outcomes):
        o = outcomes[model_id]
        where = f" at {o.stage}" if o.stage else ""
        error = f"{where}: {o.error}" if o.error else ""
        print(f"{o.status:<8}{model_id:<28}{o.seconds:7.1f} s{error}")
    counts = {s: sum(o.status == s for o in outcomes.values()) for s in ("ok", "failed", "timeout")}
    total = time.monotonic() - started
    print(", ".join(f"{n} {s}" for s, n in counts.items()) + f", in {total:.0f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
