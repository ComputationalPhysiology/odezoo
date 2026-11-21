// The search page: an anywidget whose model holds every model's details, as
// tools/generate_model_pages.py writes them into docs/search.md.
//
// Words are matched with MiniSearch (prefix and fuzzy), and the facets narrow the result as
// `odezoo search` does: values within a facet are alternatives, and facets must all hold. The
// pure functions are exported for `node --test docs/_static/`; MiniSearch is only loaded when
// the widget renders, so the tests need no network.

const MINISEARCH = "https://cdn.jsdelivr.net/npm/minisearch@7.2.0/+esm";

export const FACETS = ["categories", "species", "formats", "reviewed"];
const FACET_LABELS = {
  categories: "Category",
  species: "Species",
  formats: "Format",
  reviewed: "Reviewed",
};
const SEARCHED = ["name", "id", "authors", "keywords", "family", "cell_type", "species"];

// A model's values for a facet: none, one, or several
function valuesOf(model, facet) {
  const value = model[facet];
  if (facet === "reviewed") return [value ? "yes" : "no"];
  if (Array.isArray(value)) return value;
  return value ? [value] : [];
}

// Whether a model passes every facet's selection; `except` names a facet to leave out
export function matches(model, selected, except = null) {
  return FACETS.every((facet) => {
    const wanted = selected[facet];
    if (facet === except || !wanted || wanted.size === 0) return true;
    return valuesOf(model, facet).some((value) => wanted.has(value));
  });
}

// How many of the models that pass the other facets have each value of `facet`, most common
// first, then alphabetically
export function facetCounts(models, selected, facet) {
  const counts = new Map();
  for (const model of models) {
    if (!matches(model, selected, facet)) continue;
    for (const value of new Set(valuesOf(model, facet))) {
      counts.set(value, (counts.get(value) ?? 0) + 1);
    }
  }
  const byCount = (a, b) => b[1] - a[1] || a[0].localeCompare(b[0]);
  return new Map([...counts].sort(byCount));
}

const STYLE = `
.odezoo-search input[type="search"] { width: 100%; padding: 0.5em; font-size: 1em;
  box-sizing: border-box; border: 1px solid #8888; border-radius: 4px; }
.odezoo-search .facets { display: flex; flex-wrap: wrap; gap: 0.5em 2em; margin: 1em 0; }
.odezoo-search fieldset { border: none; padding: 0; margin: 0; }
.odezoo-search legend { font-weight: bold; padding: 0; }
.odezoo-search label { display: block; white-space: nowrap; }
.odezoo-search .count { opacity: 0.6; }
.odezoo-search ul { list-style: none; padding: 0; }
.odezoo-search li { margin: 0.4em 0; }
`;

function element(tag, properties = {}, ...children) {
  const node = document.createElement(tag);
  Object.assign(node, properties);
  node.append(...children);
  return node;
}

function render({ model, el }) {
  const models = model.get("models");
  const selected = Object.fromEntries(FACETS.map((facet) => [facet, new Set()]));
  const box = element("input", {
    type: "search",
    placeholder: "Name, author, keyword, family, cell type or species",
  });
  box.setAttribute("aria-label", "Search the models");
  const facets = element("div", { className: "facets" });
  const summary = element("p");
  const results = element("ul");
  el.append(
    element("style", { textContent: STYLE }),
    element("div", { className: "odezoo-search" }, box, facets, summary, results),
  );

  let index = null;
  import(MINISEARCH).then(({ default: MiniSearch }) => {
    index = new MiniSearch({
      fields: SEARCHED,
      extractField: (doc, field) => [doc[field] ?? ""].flat().join(" "),
    });
    index.addAll(models);
    update();
  });

  function found() {
    const text = box.value.trim();
    if (!text || index === null) return models;
    const byId = new Map(models.map((m) => [m.id, m]));
    const options = { prefix: true, fuzzy: 0.2, combineWith: "AND" };
    return index.search(text, options).map((hit) => byId.get(hit.id));
  }

  function drawFacets(matching) {
    facets.replaceChildren();
    for (const facet of FACETS) {
      const counts = facetCounts(matching, selected, facet);
      for (const value of selected[facet]) if (!counts.has(value)) counts.set(value, 0);
      if (counts.size === 0) continue;
      const group = element("fieldset", {}, element("legend", { textContent: FACET_LABELS[facet] }));
      for (const [value, count] of counts) {
        const box = element("input", { type: "checkbox", checked: selected[facet].has(value) });
        box.addEventListener("change", () => {
          box.checked ? selected[facet].add(value) : selected[facet].delete(value);
          update();
        });
        const name = value.replaceAll("_", " ");
        group.append(
          element("label", {}, box, ` ${name} `, element("span", { className: "count" }, `${count}`)),
        );
      }
      facets.append(group);
    }
  }

  function update() {
    const matching = found();
    const shown = matching.filter((m) => matches(m, selected));
    drawFacets(matching);
    summary.textContent =
      shown.length === 0 ? "No models match." : `${shown.length} of ${models.length} models`;
    results.replaceChildren(
      ...shown.map((m) =>
        element(
          "li",
          {},
          element("a", { href: m.url, textContent: m.name }),
          element("span", { className: "count", textContent: ` ${m.year} · ${m.formats.join(", ")} · ${m.id}` }),
        ),
      ),
    );
  }

  box.addEventListener("input", update);
  update();
}

export default { render };
