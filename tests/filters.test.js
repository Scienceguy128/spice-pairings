const test = require("node:test");
const assert = require("node:assert");
const f = require("../web/filters.js");

test("threshold boundary at 9, 10 and 11 shared recipes", () => {
  const pairs = [9, 10, 11].map((n) => ({ a: "x", b: "y", shared: n, lift: 2 }));
  assert.deepStrictEqual(f.visibleEdges(pairs, 10).map((p) => p.shared), [10, 11]);
  assert.strictEqual(f.pairStatus(pairs[0], 10), "below-threshold");
  assert.strictEqual(f.visibleEdges(pairs, 9).length, 3);
});

test("non-positive and unobserved pairs are distinguished", () => {
  assert.strictEqual(f.pairStatus({ shared: 40, lift: 0.7 }, 10), "non-positive");
  assert.strictEqual(f.pairStatus({ shared: 40, lift: 1 }, 10), "non-positive");
  assert.strictEqual(f.pairStatus(undefined, 10), "unobserved");
});

test("edge width grows with lift and is bounded", () => {
  assert.strictEqual(f.edgeWidth(1, 8), 1);
  assert.ok(f.edgeWidth(2, 8) < f.edgeWidth(4, 8));
  assert.strictEqual(f.edgeWidth(100, 8), 10);
});

test("cuisine selection uses its own counts and pairs without changing all-cuisine data", () => {
  const allPairs = [{ a: "a", b: "b", shared: 10, lift: 2 }];
  const thaiPairs = [{ a: "a", b: "b", shared: 2, lift: 1.5, examples: [4] }];
  const data = {
    meta: { eligible_recipes: 100 },
    nodes: [{ id: "a", count: 40 }, { id: "b", count: 20 }, { id: "c", count: 5 }],
    pairs: allPairs,
    excluded_blends: { "curry powder": 5 },
    cuisines: {
      Thai: {
        eligible_recipes: 7,
        counts: { a: 3, b: 2 },
        pairs: thaiPairs,
        excluded_blends: {},
      },
    },
  };
  const thai = f.cuisineData(data, "Thai");
  assert.strictEqual(thai.eligible_recipes, 7);
  assert.deepStrictEqual(thai.nodes.map((node) => node.count), [3, 2, 0]);
  assert.deepStrictEqual(thai.pairs, thaiPairs);
  assert.deepStrictEqual(thai.excluded_blends, {});
  assert.strictEqual(f.cuisineData(data, "").pairs, allPairs);
  assert.deepStrictEqual(data.nodes.map((node) => node.count), [40, 20, 5]);
  assert.throws(() => f.cuisineData(data, "Unknown"), /Unknown cuisine/);
});

test("cuisine defaults reveal supported sparse evidence when it exists", () => {
  assert.strictEqual(f.cuisineDefaultMinShared([{ shared: 2, lift: 1.2 }]), 2);
  assert.strictEqual(f.cuisineDefaultMinShared([{ shared: 1, lift: 2 }, { shared: 2, lift: 1 }]), 1);
  assert.strictEqual(f.cuisineDefaultMinShared([]), 1);
});
