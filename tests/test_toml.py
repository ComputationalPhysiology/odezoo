import tomllib
from dataclasses import replace

from helpers import make_model

from odezoo.maintain.toml import dump_dict, dump_model, version_block
from odezoo.schema import model_to_dict, parse_model


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
        sha256="0" * 64,
        file="v1.ode",
        source=None,
        derived_from="pmr-cb090c9",
        notes="Units in ms",
    )
    text = dump_model(m) + "\n" + version_block(v)
    assert parse_model(tomllib.loads(text), where="x").versions[-1] == v


def test_dump_dict_matches_dump_model():
    m = make_model()
    assert dump_dict(model_to_dict(m)) == dump_model(m)


def test_dump_dict_writes_a_model_still_to_fill_in():
    text = dump_dict({"id": "m", "name": "m", "categories": [], "reviewed": False})
    assert text == 'id = "m"\nname = "m"\ncategories = []\nreviewed = false\n'
