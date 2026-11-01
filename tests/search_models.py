"""Three small models for the search and version-choice tests"""

from dataclasses import replace

from helpers import make_model

from odezoo.schema import Model, Paper

br = make_model()
_cellml = br.versions[0]
tt = replace(
    br,
    id="tentusscher_2006_epi",
    name="ten Tusscher–Panfilov 2006, epicardial",
    family="tentusscher_2006",
    categories=("electrophysiology", "calcium_dynamics"),
    keywords=("cardiac",),
    species="human",
    cell_type="ventricular myocyte, epicardial",
    reviewed=False,
    default_version=None,
    paper=Paper(
        title="Alternans and spiral breakup in a human ventricular tissue model",
        authors=("ten Tusscher KHWJ", "Panfilov AV"),
        journal="Am J Physiol Heart Circ Physiol",
        year=2006,
        pubmed=16565318,
    ),
    versions=(
        replace(_cellml, id="pmr-1", file="pmr-1.cellml"),
        replace(_cellml, id="v1", format="ode", file="v1.ode", source=None, derived_from="pmr-1"),
    ),
)
wk = replace(
    br,
    id="windkessel_2000",
    name="Three-element Windkessel",
    categories=("cardiovascular_circulation",),
    keywords=("circulation",),
    species=None,
    cell_type=None,
    default_version=None,
    versions=(replace(_cellml, id="v1", format="ode", file="v1.ode", source=None),),
)
ALL = [br, tt, wk]


def ids(models: list[Model]) -> list[str]:
    return [m.id for m in models]
