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
