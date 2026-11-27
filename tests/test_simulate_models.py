"""The model simulator for the site, `tools/simulate_models.py`"""

import importlib.util
import math

import pytest
from helpers import REPO

pytest.importorskip("gotranx", reason="the simulator loads models with gotranx")
pytest.importorskip("scipy", reason="the simulator integrates with scipy")
pytest.importorskip("matplotlib", reason="the simulator plots with matplotlib")
pytest.importorskip("crossbridge", reason="the calcium transients come from crossbridge")

import numpy as np  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "simulate_models", REPO / "tools" / "simulate_models.py"
)
assert _spec is not None and _spec.loader is not None
sim = importlib.util.module_from_spec(_spec)
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


def test_panels_fall_back_to_states():
    t = np.linspace(0, 1, 5)
    trace = sim.Trace(t=t, values={name: t for name in "abcde"})
    assert sim.panels(trace, "electrophysiology") == [("States", ["a", "b", "c", "d"])]


def test_plot_writes_a_png(tmp_path):
    t = np.linspace(0, 1, 5)
    trace = sim.Trace(t=t, values={"V": t, "Ca_i": t})
    path = tmp_path / "model.png"
    sim.plot(trace, sim.panels(trace, "electrophysiology"), "A model", path)
    assert path.read_bytes().startswith(b"\x89PNG")
