import tomllib
from dataclasses import replace

from helpers import make_model

from odezoo.maintain.toml import dump_model, version_block
from odezoo.schema import parse_model


def test_dump_model_round_trips():
    m = make_model()
    assert parse_model(tomllib.loads(dump_model(m)), where="x") == m


def test_dump_model_escapes_strings():
    m = make_model(name='Quote " and \\ backslash – en dash')
    assert parse_model(tomllib.loads(dump_model(m)), where="x").name == m.name


def test_version_block_appends_a_version():
    m = make_model()
    v = replace(
        m.versions[0],
        id="v1",
        format="ode",
        file="v1.ode",
        source=None,
        derived_from="pmr-cb090c9",
        notes="Units in ms",
    )
    text = dump_model(m) + "\n" + version_block(v)
    assert parse_model(tomllib.loads(text), where="x").versions[-1] == v
