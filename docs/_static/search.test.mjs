// The search page's filtering and counting: node --test docs/_static/
import { test } from "node:test";
import assert from "node:assert/strict";

import { FACETS, facetCounts, matches } from "./search.mjs";

// Three models like tests/search_models.py
const br = {
  id: "beeler_reuter_1977", categories: ["electrophysiology"], species: "canine",
  formats: ["cellml"], reviewed: true,
};
const tt = {
  id: "tentusscher_2006_epi", categories: ["electrophysiology", "calcium_dynamics"],
  species: "human", formats: ["cellml", "ode"], reviewed: false,
};
const wk = {
  id: "windkessel_2000", categories: ["cardiovascular_circulation"], species: null,
  formats: ["ode"], reviewed: true,
};
const ALL = [br, tt, wk];
const ids = (models) => models.map((m) => m.id);

test("the facets are those the command line filters by", () => {
  assert.deepEqual(FACETS, ["categories", "species", "formats", "reviewed"]);
});

test("with nothing selected every model matches", () => {
  assert.deepEqual(ids(ALL.filter((m) => matches(m, {}))), ids(ALL));
});

test("values of one facet are alternatives", () => {
  const selected = { categories: new Set(["calcium_dynamics", "cardiovascular_circulation"]) };
  assert.deepEqual(ids(ALL.filter((m) => matches(m, selected))), [tt.id, wk.id]);
});

test("different facets must all hold", () => {
  const selected = { categories: new Set(["electrophysiology"]), species: new Set(["human"]) };
  assert.deepEqual(ids(ALL.filter((m) => matches(m, selected))), [tt.id]);
});

test("an empty selection for a facet does not filter", () => {
  assert.equal(ALL.filter((m) => matches(m, { species: new Set() })).length, 3);
});

test("a facet's counts ignore its own selection but apply the others", () => {
  const selected = { categories: new Set(["electrophysiology"]), species: new Set(["human"]) };
  assert.deepEqual([...facetCounts(ALL, selected, "species")], [["canine", 1], ["human", 1]]);
});

test("counts are most common first, and models without a value are left out", () => {
  assert.deepEqual([...facetCounts(ALL, {}, "formats")], [["cellml", 2], ["ode", 2]]);
  assert.deepEqual([...facetCounts(ALL, {}, "species")], [["canine", 1], ["human", 1]]);
});

test("review status counts as yes and no", () => {
  assert.deepEqual([...facetCounts(ALL, {}, "reviewed")], [["yes", 2], ["no", 1]]);
  assert.deepEqual(ids(ALL.filter((m) => matches(m, { reviewed: new Set(["no"]) }))), [tt.id]);
});
