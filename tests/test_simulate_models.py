"""The model simulator for the site, `tools/simulate_models.py`"""

import importlib.util
import json
import math
import sys
import time
from datetime import date

import helpers
import pytest
from helpers import REPO

pytest.importorskip("gotranx", reason="the simulator loads models with gotranx")
pytest.importorskip("scipy", reason="the simulator integrates with scipy")
pytest.importorskip("matplotlib", reason="the simulator plots with matplotlib")
pytest.importorskip("crossbridge", reason="the calcium transients come from crossbridge")

import numpy as np  # noqa: E402

from odezoo.registry import build  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "simulate_models", REPO / "tools" / "simulate_models.py"
)
assert _spec is not None and _spec.loader is not None
sim = importlib.util.module_from_spec(_spec)
# Registered by name, so that the processes it starts can unpickle its jobs and workers.
sys.modules["simulate_models"] = sim
_spec.loader.exec_module(sim)

DATA = REPO / "tests" / "data" / "simulate"


def test_load_ode_file():
    ode, seconds_per_unit = sim.load(DATA / "decay.ode")
    assert seconds_per_unit == 1.0
    assert [s.name for s in ode.states] == ["x"]


def test_load_broken_file_is_a_load_failure():
    with pytest.raises(sim.SimulationError) as info:
        sim.load(DATA / "broken.ode")
    assert info.value.stage == "load"


def test_load_cellml_reads_the_time_unit():
    folder = REPO / "models" / "beeler_reuter_1977"
    (cellml,) = folder.glob("*.cellml")
    _, seconds_per_unit = sim.load(cellml)
    assert seconds_per_unit == 1e-3


def test_cellml_model_fires():
    (cellml,) = (REPO / "models" / "beeler_reuter_1977").glob("*.cellml")
    ode, seconds_per_unit = sim.load(cellml)
    trace = sim.simulate(ode, seconds_per_unit, duration=0.5)
    assert max(trace.values["V"]) > 0 > trace.values["V"][0]


def test_simulate_decay():
    ode, _ = sim.load(DATA / "decay.ode")
    trace = sim.simulate(ode, 1.0, duration=1.0)
    assert trace.t[-1] == pytest.approx(1.0)
    assert trace.values["x"][-1] == pytest.approx(math.exp(-1), rel=1e-4)


def test_stimulated_model_fires():
    # A 1 ms pulse at 100 ms: a solver free to take long steps would step over it.
    ode, _ = sim.load(DATA / "stimulated.ode")
    trace = sim.simulate(ode, 1e-3, duration=0.3)
    assert trace.t[-1] == pytest.approx(0.3)
    assert max(trace.values["v"]) > 10


def test_unnamed_short_pulse_fires():
    # O'Hara-Rudy 2011 names its 0.5 ms stimulus `amp` and `duration`.
    ode, _ = sim.load(DATA / "unnamed_pulse.ode")
    trace = sim.simulate(ode, 1e-3, duration=3.0)
    assert max(trace.values["v"]) > 5


def test_nan_is_a_failure():
    ode, _ = sim.load(DATA / "divides_by_zero.ode")
    with pytest.raises(sim.SimulationError) as info:
        sim.simulate(ode, 1.0, duration=1.0)
    assert info.value.stage == "simulate"


def test_calcium_drives_the_input():
    rice = sim.calcium("rice_2008")
    assert rice(np.array([0.0, 0.0417, 1.0417])) == pytest.approx([0.09, 1.45, 1.45], abs=1e-3)
    assert sim.calcium("beeler_reuter_1977") is None
    musgrave = sim.calcium("musgrave_2025")
    assert musgrave(np.array([0.2])) == pytest.approx(musgrave(np.array([1.2])))
    for model_id in sim.CALCIUM:
        ca = sim.calcium(model_id)(np.linspace(0, 3, 301))
        assert np.all(np.isfinite(ca)) and ca.min() > 0 and ca.max() > ca.min()


def test_calcium_sets_the_input_parameter():
    ode, _ = sim.load(REPO / "models" / "land_2017" / "github-6e5a5aa.ode")
    trace = sim.simulate(ode, 1.0, duration=1.0, calcium=sim.calcium("land_2017"))
    assert max(trace.values["Ta"]) > 10 * max(abs(trace.values["Ta"][0]), 1e-3)


def test_panels_pick_named_variables():
    t = np.linspace(0, 1, 5)
    trace = sim.Trace(t=t, values={"V": t, "Ca_i": t, "m": t})
    assert sim.panels(trace, "electrophysiology") == [
        ("Membrane voltage", ["V"]),
        ("Cytosolic Ca", ["Ca_i"]),
    ]


def test_panels_add_the_states_when_the_main_variable_is_missing():
    # A voltage under a name not looked for: the page must not show the calcium alone.
    t = np.linspace(0, 1, 5)
    trace = sim.Trace(t=t, values={"U": t, "Ca_i": t})
    assert sim.panels(trace, "electrophysiology") == [
        ("Cytosolic Ca", ["Ca_i"]),
        ("States", ["U", "Ca_i"]),
    ]


def test_panels_find_dokos_voltage():
    t = np.linspace(0, 1, 5)
    trace = sim.Trace(t=t, values={"Cai": t, "E": t})
    assert sim.panels(trace, "electrophysiology")[0] == ("Membrane voltage", ["E"])


def test_panels_fall_back_to_states():
    t = np.linspace(0, 1, 5)
    trace = sim.Trace(t=t, values={name: t for name in ("a", "b", "c", "d", "f")})
    assert sim.panels(trace, "electrophysiology") == [("States", ["a", "b", "c", "d"])]


def test_plot_writes_a_png(tmp_path):
    t = np.linspace(0, 1, 5)
    trace = sim.Trace(t=t, values={"V": t, "Ca_i": t})
    path = tmp_path / "model.png"
    sim.plot(trace, sim.panels(trace, "electrophysiology"), "A model", path)
    assert path.read_bytes().startswith(b"\x89PNG")


def job(tmp_path, name, category="electrophysiology"):
    return sim.Job(id=name, version="v1", path=DATA / f"{name}.ode", category=category, title=name)


def test_run_one_reports_a_load_failure(tmp_path):
    outcome = sim.run_one(job(tmp_path, "broken"), tmp_path)
    assert (outcome.status, outcome.stage, outcome.figure) == ("failed", "load", None)
    assert outcome.error


def test_run_one_reports_a_missing_file(tmp_path):
    missing = sim.Job(id="gone", version="v1", path=None, category="x", title="Gone")
    outcome = sim.run_one(missing, tmp_path)
    assert (outcome.status, outcome.stage) == ("failed", "load")


def test_run_one_ok_writes_a_figure(tmp_path):
    outcome = sim.run_one(job(tmp_path, "decay"), tmp_path)
    assert (outcome.status, outcome.figure) == ("ok", "decay.png")
    assert (tmp_path / "decay.png").exists()


def test_run_all_runs_every_job(tmp_path):
    outcomes = sim.run_all(
        [job(tmp_path, "decay"), job(tmp_path, "broken")], tmp_path, timeout=60, workers=2
    )
    assert {k: o.status for k, o in outcomes.items()} == {"decay": "ok", "broken": "failed"}


def test_run_all_times_out(tmp_path):
    started = time.monotonic()
    outcomes = sim.run_all(
        [job(tmp_path, "decay")], tmp_path, timeout=1, workers=1, worker=helpers.sleep_forever
    )
    assert outcomes["decay"].status == "timeout"
    assert time.monotonic() - started < 10


def test_run_all_reports_a_dead_process(tmp_path):
    outcomes = sim.run_all(
        [job(tmp_path, "decay")], tmp_path, timeout=30, workers=1, worker=helpers.exit_hard
    )
    assert outcomes["decay"].status == "failed"
    assert "3" in outcomes["decay"].error


def test_main_exits_0_when_models_fail(tmp_path):
    root = helpers.write_checkout(tmp_path / "checkout", [(helpers.make_model(), {
        "pmr-cb090c9.cellml": helpers.CELLML_BYTES})])  # fmt: skip
    registry_json = tmp_path / "registry.json"
    data = build(root, commit=None, built=date(2026, 11, 27))
    registry_json.write_text(json.dumps(data), encoding="utf-8")
    out = tmp_path / "out"
    code = sim.main([str(registry_json), str(root / "models"), str(out), "--workers", "1"])
    assert code == 0
    status = json.loads((out / "status.json").read_text(encoding="utf-8"))
    assert status["models"]["beeler_reuter_1977"]["status"] == "failed"
    assert status["models"]["beeler_reuter_1977"]["version"] == "pmr-cb090c9"


def test_main_usage_error(capsys):
    assert sim.main([]) == 2


def test_run_one_keeps_gotranx_quiet(tmp_path, capfd):
    # In a fresh process, where importing gotranx sets up its own logging.
    sim.run_all([job(tmp_path, "decay")], tmp_path, timeout=60, workers=1)
    out, err = capfd.readouterr()
    assert "Load ode" not in out + err


def test_run_all_stops_at_its_deadline(tmp_path):
    jobs = [job(tmp_path, "decay"), job(tmp_path, "broken"), job(tmp_path, "stimulated")]
    started = time.monotonic()
    outcomes = sim.run_all(
        jobs, tmp_path, timeout=60, workers=1, worker=helpers.sleep_forever, deadline=2
    )
    assert {o.status for o in outcomes.values()} == {"timeout"}
    assert sorted(outcomes) == ["broken", "decay", "stimulated"]
    assert time.monotonic() - started < 15


def test_run_all_writes_the_status_as_it_goes(tmp_path):
    status = tmp_path / "status.json"
    sim.run_all([job(tmp_path, "decay")], tmp_path, timeout=60, workers=1, status=status)
    data = json.loads(status.read_text(encoding="utf-8"))
    assert data["models"]["decay"]["status"] == "ok"
