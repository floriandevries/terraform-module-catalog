import { parseVersion, resolveModule, matchesQuery } from "./match.js";

const LABELS = {
  "compatible": "Compatible",
  "no-compatible": "No compatible release",
  "none-declared": "No constraint declared",
  "unknown": "Unknown",
  "no-releases": "No releases",
};

const HIDDEN_TOPICS = ["terraform", "azurerm", "azure"];

const $ = (id) => document.getElementById(id);

function el(tag, text, cls) {
  const e = document.createElement(tag);
  if (text !== undefined) e.textContent = text;
  if (cls) e.className = cls;
  return e;
}

function link(href, text) {
  const a = el("a", text);
  a.href = href;
  return a;
}

function copyButton(text) {
  const b = el("button", "Copy");
  b.type = "button";
  b.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(text);
      b.textContent = "Copied";
      setTimeout(() => { b.textContent = "Copy"; }, 1500);
    } catch {
    }
  });
  return b;
}

function row(name, mod, r) {
  const tr = document.createElement("tr");
  const tdName = el("td");
  tdName.append(link(mod.url, name));
  const shown = (mod.topics || []).filter((t) => !HIDDEN_TOPICS.includes(t));
  if (shown.length) {
    const box = el("div", undefined, "topics");
    for (const t of shown) box.append(el("span", t, "topic"));
    tdName.append(box);
  }
  let status = LABELS[r.status];
  if (r.newerUnknown) status += " (newer releases with unknown support exist)";
  const tdRelease = el("td");
  const tdConstraint = el("td", r.constraint || "");
  const tdSource = el("td");
  if (r.status === "compatible") {
    tdRelease.append(link(`${mod.url}/tree/${r.tag}`, r.tag));
    const src = `git::${mod.url}.git?ref=${r.tag}`;
    tdSource.append(el("code", src), copyButton(src));
  } else if (r.status === "no-compatible") {
    tdRelease.textContent = r.tag;
  }
  tr.append(tdName, el("td", status, r.status), tdRelease, tdConstraint, tdSource);
  return tr;
}

function render(catalog) {
  const version = $("version").value;
  const query = $("query").value.trim();
  const valid = parseVersion(version) !== null;
  $("hint").hidden = valid;
  $("results").hidden = !valid;
  const status = $("status");
  status.hidden = true;
  const rows = $("rows");
  rows.replaceChildren();
  if (!valid) return;
  let n = 0;
  for (const name of Object.keys(catalog.modules).sort()) {
    const mod = catalog.modules[name];
    const r = resolveModule(mod.tags, version);
    if (!matchesQuery(name, mod.topics || [], query)) continue;
    if (!query && r.status !== "compatible") continue;
    rows.append(row(name, mod, r));
    n++;
  }
  status.hidden = false;
  if (query) {
    status.textContent = n ? "" : `No modules match '${query}'`;
    status.hidden = n > 0;
  } else if (n) {
    status.textContent = `Showing ${n} compatible modules. Search to include modules without a compatible release.`;
  } else {
    status.textContent = `No compatible modules for azurerm ${version}`;
  }
}

async function main() {
  let catalog;
  try {
    const res = await fetch("catalog.json");
    if (!res.ok) throw new Error(res.status);
    catalog = await res.json();
  } catch {
    $("error").hidden = false;
    return;
  }
  const list = $("versions");
  for (const v of catalog.azurerm_versions) {
    const o = document.createElement("option");
    o.value = v;
    list.append(o);
  }
  $("version").value = catalog.azurerm_versions[0] || "";
  $("footer").textContent = `Data last changed: ${catalog.updated_at} · Owner: ${catalog.owner}`;
  $("version").addEventListener("input", () => render(catalog));
  $("query").addEventListener("input", () => render(catalog));
  render(catalog);
}

main();
