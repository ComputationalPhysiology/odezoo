"""Find models by text and by filters"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from .schema import Model, normalize_keyword


def _as_set(value: str | Sequence[str] | None, normalize=str.lower) -> set[str] | None:
    if value is None:
        return None
    values = [value] if isinstance(value, str) else list(value)
    return {normalize(v) for v in values} or None


def _haystack(model: Model) -> str:
    parts = [
        model.id,
        model.name,
        model.family or "",
        model.paper.title,
        *model.paper.authors,
        *model.keywords,
        model.cell_type or "",
        model.species or "",
    ]
    return " ".join(parts).lower()


def search(
    models: Iterable[Model],
    text: str = "",
    *,
    category: str | Sequence[str] | None = None,
    keyword: str | Sequence[str] | None = None,
    species: str | Sequence[str] | None = None,
    format: str | None = None,
    reviewed: bool | None = None,
) -> list[Model]:
    """The models that match, sorted by id

    Every word of `text` must occur somewhere in the model's id, name, family, paper title and
    authors, keywords, cell type or species. Several values for one filter are alternatives;
    different filters must all hold.
    """
    words = text.lower().split()
    categories = _as_set(category, normalize=str)
    keywords = _as_set(keyword, normalize=normalize_keyword)
    species_set = _as_set(species)

    def matches(model: Model) -> bool:
        haystack = _haystack(model)
        return (
            all(word in haystack for word in words)
            and (categories is None or bool(categories & set(model.categories)))
            and (keywords is None or bool(keywords & set(model.keywords)))
            and (species_set is None or (model.species or "") in species_set)
            and (format is None or format in model.formats)
            and (reviewed is None or model.reviewed == reviewed)
        )

    return sorted((m for m in models if matches(m)), key=lambda m: m.id)
