const CLAUSE = /^(=|!=|>=|<=|>|<|~>)?\s*v?(\d+(?:\.\d+){0,2})$/;

export function parseVersion(s) {
  const m = /^v?(\d+(?:\.\d+){0,2})$/.exec(String(s).trim());
  if (!m) return null;
  const p = m[1].split(".").map(Number);
  while (p.length < 3) p.push(0);
  return p;
}

export function compareVersions(a, b) {
  for (let i = 0; i < 3; i++) {
    if (a[i] !== b[i]) return a[i] < b[i] ? -1 : 1;
  }
  return 0;
}

export function parseConstraint(s) {
  const clauses = String(s).split(",").map((c) => c.trim());
  const out = [];
  for (const c of clauses) {
    const m = CLAUSE.exec(c);
    if (!m) return null;
    out.push({ op: m[1] || "=", v: parseVersion(m[2]), parts: m[2].split(".").length });
  }
  return out;
}

function ok(version, { op, v, parts }) {
  const c = compareVersions(version, v);
  switch (op) {
    case "=": return c === 0;
    case "!=": return c !== 0;
    case ">=": return c >= 0;
    case "<=": return c <= 0;
    case ">": return c > 0;
    case "<": return c < 0;
    case "~>": {
      const upper = parts === 3 ? [v[0], v[1] + 1, 0] : [v[0] + 1, 0, 0];
      return c >= 0 && compareVersions(version, upper) < 0;
    }
  }
}

export function satisfies(version, constraint) {
  const v = parseVersion(version);
  const cs = parseConstraint(constraint);
  if (!v || !cs) return null;
  return cs.every((c) => ok(v, c));
}

export function resolveModule(tags, version) {
  const sorted = Object.entries(tags)
    .map(([tag, { constraint }]) => ({ tag, constraint, v: parseVersion(tag) }))
    .filter((t) => t.v)
    .sort((a, b) => compareVersions(b.v, a.v));
  const res = (status, t, newerUnknown = false) => ({ status, tag: t ? t.tag : null, constraint: t ? t.constraint : null, newerUnknown });
  if (!sorted.length) return res("no-releases");
  if (sorted.every((t) => t.constraint === null)) return res("none-declared");
  let newerUnknown = false;
  let anyUnparseable = false;
  for (const t of sorted) {
    const r = t.constraint === null ? null : satisfies(version, t.constraint);
    if (r === true) return res("compatible", t, newerUnknown);
    if (r === null) {
      newerUnknown = true;
      if (t.constraint !== null) anyUnparseable = true;
    }
  }
  return anyUnparseable ? res("unknown") : res("no-compatible", sorted.find((t) => t.constraint !== null) || sorted[0]);
}
