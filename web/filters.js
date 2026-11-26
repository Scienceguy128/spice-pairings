// Pure helpers shared by the browser app and the Node tests.
(function (root) {
  const DEFAULT_MIN_SHARED = 10;

  // Why a pair is or is not drawn. Pairs never seen together have no record at all.
  function pairStatus(pair, minShared) {
    if (!pair || pair.shared === 0) return "unobserved";
    if (pair.shared < minShared) return "below-threshold";
    if (!(pair.lift > 1)) return "non-positive";
    return "shown";
  }

  function visibleEdges(pairs, minShared) {
    return pairs.filter((p) => pairStatus(p, minShared) === "shown");
  }

  function isSparse(pair) {
    return pair.shared < DEFAULT_MIN_SHARED;
  }

  // Log-lift keeps a few extreme (often rare) pairs from dominating the drawing.
  function edgeWidth(lift, maxLift) {
    const top = Math.log(Math.max(maxLift, 1.0001));
    const t = Math.min(Math.log(Math.max(lift, 1)) / top, 1);
    return 1 + 9 * t;
  }

  const api = { DEFAULT_MIN_SHARED, pairStatus, visibleEdges, isSparse, edgeWidth };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.PairingFilters = api;
})(this);
