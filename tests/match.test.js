import { test } from "node:test";
import assert from "node:assert/strict";
import { parseVersion, parseConstraint, satisfies, resolveModule } from "../match.js";

test("parseVersion pads and strips v", () => {
  assert.deepEqual(parseVersion("5.12.0"), [5, 12, 0]);
  assert.deepEqual(parseVersion("v5.12.0"), [5, 12, 0]);
  assert.deepEqual(parseVersion("5.12"), [5, 12, 0]);
  assert.deepEqual(parseVersion("4"), [4, 0, 0]);
  assert.equal(parseVersion("5.0.0-beta1"), null);
  assert.equal(parseVersion("latest"), null);
  assert.equal(parseVersion(""), null);
});

test("Cegeka constraint styles", () => {
  assert.equal(satisfies("4.50.0", ">= 4.0.0, < 5.0.0"), true);
  assert.equal(satisfies("5.12.0", ">= 4.0.0, < 5.0.0"), false);
  assert.equal(satisfies("4.36.9", ">= 4.37.0, < 5.0.0"), false);
  assert.equal(satisfies("5.12.0", ">= 4.0.0, < 6.0.0"), true);
  assert.equal(satisfies("5.12.0", ">= 4.31.0, < 6.0.0"), true);
});

test("two-part versions in constraints", () => {
  assert.equal(satisfies("4.0.0", ">= 4.0, < 5.0"), true);
  assert.equal(satisfies("5.0.0", ">= 4.0, < 5.0"), false);
  assert.equal(satisfies("5.12.0", ">= 4.0, < 6.0"), true);
});

test("pessimistic operator", () => {
  assert.equal(satisfies("4.60.0", "~>4.52"), true);
  assert.equal(satisfies("4.51.0", "~>4.52"), false);
  assert.equal(satisfies("5.0.0", "~> 4.52"), false);
  assert.equal(satisfies("4.99.0", "~> 4.0"), true);
  assert.equal(satisfies("4.52.9", "~> 4.52.0"), true);
  assert.equal(satisfies("4.53.0", "~> 4.52.0"), false);
});

test("exact and not-equal", () => {
  assert.equal(satisfies("4.50.0", "4.50.0"), true);
  assert.equal(satisfies("4.50.0", "= 4.50.0"), true);
  assert.equal(satisfies("4.50.1", "= 4.50.0"), false);
  assert.equal(satisfies("4.51.0", ">= 4.0, != 4.51.0"), false);
});

test("unparseable gives null, never true", () => {
  assert.equal(parseConstraint("latest"), null);
  assert.equal(satisfies("5.12.0", ">= 4.0, < banana"), null);
  assert.equal(satisfies("junk", ">= 4.0"), null);
  assert.equal(satisfies("5.12.0", ""), null);
});

test("trailing empty clause is never compatible", () => {
  assert.equal(satisfies("5.12.0", ">= 4.0,"), null);
});

const rg = {
  "v0.0.1": { sha: "a", constraint: ">= 4.0, < 5.0" },
  "v1.0.0": { sha: "b", constraint: ">= 4.0, < 5.0" },
  "v1.1.0": { sha: "c", constraint: ">= 4.0, < 5.0" },
  "v1.2.0": { sha: "d", constraint: ">= 4.0, < 6.0" },
};
const logic = {
  "v1.0.0": { sha: "a", constraint: ">= 4.0, < 5.0" },
  "v1.0.2": { sha: "b", constraint: ">= 4.0, < 5.0" },
};

test("no-compatible reports newest tag with a constraint", () => {
  const tags = { "v1.0.0": { sha: "a", constraint: ">= 4.0, < 5.0" }, "v1.1.0": { sha: "b", constraint: null } };
  assert.deepEqual(resolveModule(tags, "5.12.0"), { status: "no-compatible", tag: "v1.0.0", constraint: ">= 4.0, < 5.0", newerUnknown: false });
});

test("spec expected results", () => {
  assert.deepEqual(resolveModule(rg, "5.12.0"), { status: "compatible", tag: "v1.2.0", constraint: ">= 4.0, < 6.0", newerUnknown: false });
  assert.deepEqual(resolveModule(rg, "4.50.0"), { status: "compatible", tag: "v1.2.0", constraint: ">= 4.0, < 6.0", newerUnknown: false });
  assert.deepEqual(resolveModule(logic, "5.12.0"), { status: "no-compatible", tag: "v1.0.2", constraint: ">= 4.0, < 5.0", newerUnknown: false });
  assert.deepEqual(resolveModule(logic, "4.50.0"), { status: "compatible", tag: "v1.0.2", constraint: ">= 4.0, < 5.0", newerUnknown: false });
});

test("semver ordering, not string ordering", () => {
  const t = { "v1.9.0": { sha: "a", constraint: ">= 4.0" }, "v1.10.0": { sha: "b", constraint: ">= 4.0" } };
  assert.equal(resolveModule(t, "4.1.0").tag, "v1.10.0");
});

test("other statuses", () => {
  assert.equal(resolveModule({}, "5.12.0").status, "no-releases");
  assert.equal(resolveModule({ "v1.0.0": { sha: "a", constraint: null } }, "5.12.0").status, "none-declared");
  assert.equal(resolveModule({ "v1.0.0": { sha: "a", constraint: "banana" }, "v0.9.0": { sha: "b", constraint: "< 5.0" } }, "5.12.0").status, "unknown");
});

test("newer release without constraint sets newerUnknown", () => {
  const t = { "v4.0.0": { sha: "a", constraint: ">= 4.0, < 6.0" }, "v4.1.0": { sha: "b", constraint: null } };
  assert.deepEqual(resolveModule(t, "5.12.0"), { status: "compatible", tag: "v4.0.0", constraint: ">= 4.0, < 6.0", newerUnknown: true });
});
