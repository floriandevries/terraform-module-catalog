import { parseVersion, resolveModule } from "./match.js";

const LABELS = {
  "compatible": "Compatible",
  "no-compatible": "No compatible release",
  "none-declared": "No constraint declared",
  "unknown": "Unknown",
  "no-releases": "No releases",
};

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

function row(name, mod, version) {
  const r = resolveModule(mod.tags, version);
  const tr = document.createElement("tr");
  const tdName = el("td");
  tdName.append(link(mod.url, name));
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
  const valid = parseVersion(version) !== null;
  $("hint").hidden = valid;
  $("results").hidden = !valid;
  const rows = $("rows");
  rows.replaceChildren();
  if (!valid) return;
  for (const name of Object.keys(catalog.modules).sort()) {
    rows.append(row(name, catalog.modules[name], version));
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
  render(catalog);
}

main();
