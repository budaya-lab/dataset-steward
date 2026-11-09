"use strict";

const state = {
  datasets: [],
  folder: null,
  tab: "view",
  detail: null,
  pkg: null,      // working copy of datapackage.json for the Edit tab
  raw: "",        // working copy for the JSON tab
  dirty: false,
};

const DEFAULT_SCHEMA = "https://datapackage.org/profiles/2.0/datapackage.json";
const CREATED_RE = /^(\d{4}-\d{2}-\d{2})T\d{2}:\d{2}:\d{2}Z$/;
const REQUIRED_PREFIXES = ["task", "project", "stage"];

const $ = (selector) => document.querySelector(selector);

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "class") node.className = value;
    else if (key === "on") {
      for (const [event, handler] of Object.entries(value)) node.addEventListener(event, handler);
    } else if (key in node && key !== "list") node[key] = value;
    else node.setAttribute(key, value);
  }
  node.append(...children.filter((child) => child !== null && child !== undefined));
  return node;
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || `Request failed (${response.status})`);
  return body;
}

let toastTimer;
function toast(message) {
  const node = $("#toast");
  node.textContent = message;
  node.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { node.hidden = true; }, 5000);
}

const plural = (count, word) => `${count} ${word}${count === 1 ? "" : "s"}`;

/* ------------------------------------------------------- dataset list */

function renderList() {
  const passing = state.datasets.filter((d) => d.ok).length;
  $("#summary").textContent = `${passing} of ${state.datasets.length} pass`;
  const list = $("#dataset-list");
  list.replaceChildren(...state.datasets.map((dataset) => {
    const status = el("span", { class: "dataset-status" });
    status.append(dataset.ok
      ? el("span", { class: "status-ok" }, "✓ Pass")
      : el("span", { class: "status-bad" }, `✕ ${plural(dataset.errors, "error")}`));
    if (dataset.warnings) {
      status.append(" · ", el("span", { class: "status-warn" }, `⚠ ${plural(dataset.warnings, "warning")}`));
    }
    const button = el("button", {
      type: "button",
      on: { click: () => selectDataset(dataset.folder) },
    }, el("span", { class: "dataset-name" }, dataset.folder), status);
    if (dataset.folder === state.folder) button.setAttribute("aria-current", "true");
    return el("li", {}, button);
  }));
}

async function refreshList() {
  state.datasets = await api("/api/datasets");
  renderList();
}

function confirmDiscard() {
  return !state.dirty || window.confirm("Discard unsaved changes?");
}

async function selectDataset(folder, tab = null) {
  if (folder !== state.folder && !confirmDiscard()) return;
  state.folder = folder;
  state.tab = tab || state.tab;
  await loadDetail();
}

function applyDetail(detail) {
  state.detail = detail;
  state.raw = detail.raw;
  state.pkg = detail.package
    ? JSON.parse(JSON.stringify(detail.package))
    : (detail.raw ? null : { $schema: DEFAULT_SCHEMA, name: detail.folder, resources: [] });
  state.dirty = false;
}

async function loadDetail() {
  try {
    applyDetail(await api(`/api/datasets/${encodeURIComponent(state.folder)}`));
  } catch (error) {
    toast(error.message);
    return;
  }
  history.replaceState(null, "", `#${encodeURIComponent(state.folder)}/${state.tab}`);
  renderList();
  renderMain();
}

/* --------------------------------------------------------------- main */

function renderMain() {
  const detail = state.detail;
  const tabs = el("div", { class: "tabs", role: "tablist" }, ...[["view", "README"], ["edit", "Edit"], ["json", "JSON"]].map(([id, label]) => {
    const button = el("button", { type: "button", role: "tab", on: { click: () => switchTab(id) } }, label);
    button.setAttribute("aria-selected", String(state.tab === id));
    return button;
  }));
  const content = state.tab === "view" ? renderView() : state.tab === "edit" ? renderEdit() : renderJson();
  $("#main").replaceChildren(el("div", { class: "main-inner" },
    el("h1", {}, detail.folder), tabs, renderIssues(detail.report), content));
  if (state.tab === "view") renderCharts();
}

function switchTab(tab) {
  if (tab === state.tab) return;
  if (state.tab === "json" && tab === "edit") {
    let parsed;
    try {
      parsed = JSON.parse(state.raw);
    } catch (error) {
      toast(`Fix the JSON first: ${error.message}`);
      return;
    }
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      toast("Fix the JSON first: it must be an object");
      return;
    }
    state.pkg = parsed;
  } else if (state.tab === "edit" && tab === "json" && state.dirty && state.pkg) {
    state.raw = JSON.stringify(state.pkg, null, 2) + "\n";
  } else if (tab === "view" && !confirmDiscard()) {
    return;
  } else if (tab === "view" && state.dirty) {
    applyDetail(state.detail);
  }
  state.tab = tab;
  history.replaceState(null, "", `#${encodeURIComponent(state.folder)}/${tab}`);
  renderMain();
}

function renderIssues(report) {
  const blocks = [];
  if (report.errors.length) {
    blocks.push(el("div", { class: "issues issues-error" },
      el("h3", {}, `✕ ${plural(report.errors.length, "error")}`),
      el("ul", {}, ...report.errors.map((message) => el("li", {}, message)))));
  }
  if (report.warnings.length) {
    blocks.push(el("div", { class: "issues issues-warn" },
      el("h3", {}, `⚠ ${plural(report.warnings.length, "warning")}`),
      el("ul", {}, ...report.warnings.map((message) => el("li", {}, message)))));
  }
  if (!blocks.length) blocks.push(el("div", { class: "issues issues-ok" }, "✓ Passes all checks"));
  return el("div", {}, ...blocks);
}

/* --------------------------------------------------------------- view */

function renderView() {
  const detail = state.detail;
  let banner;
  if (!detail.report.ok) {
    banner = `Preview. ${detail.readme_name} is only written once the errors are fixed.`;
  } else if (!detail.readme_current) {
    banner = `${detail.readme_name} is out of date. Press Re-validate to update it.`;
  } else {
    banner = `Showing ${detail.readme_name}.`;
  }
  const readme = el("article", { class: "readme" });
  readme.innerHTML = detail.readme_html; // rendered by the server with raw HTML escaped
  readme.querySelectorAll("a").forEach((link) => {
    link.target = "_blank";
    link.rel = "noopener noreferrer";
  });
  return el("div", {}, el("p", { class: "banner" }, banner), readme);
}

function positionTooltip(event) {
  const tip = $("#tooltip");
  const x = Math.min(event.clientX + 12, window.innerWidth - tip.offsetWidth - 8);
  tip.style.left = `${Math.max(x, 8)}px`;
  tip.style.top = `${event.clientY + 14}px`;
}

function renderCharts() {
  const holder = $("#buckets-chart");
  if (!holder) return;
  const detail = state.detail;
  if (!detail.buckets_present) {
    holder.append(el("p", { class: "muted" }, "buckets.csv is missing."));
    return;
  }
  for (const chart of detail.charts) {
    const peak = Math.max(...chart.points.map((point) => Math.abs(point.value)), 0);
    const rows = chart.points.map((point) => {
      const bar = el("div", { class: "chart-bar" });
      // Reserves room at the tip so the longest value label still fits.
      bar.style.width = peak ? `calc((100% - 5rem) * ${Math.abs(point.value) / peak})` : "2px";
      const row = el("div", {
        class: "chart-row",
        on: {
          mouseenter: (event) => {
            const tip = $("#tooltip");
            tip.textContent = `${chart.label_column}: ${point.label} · ${chart.column}: ${point.display}`;
            tip.hidden = false;
            positionTooltip(event);
          },
          mousemove: positionTooltip,
          mouseleave: () => { $("#tooltip").hidden = true; },
        },
      },
      el("div", { class: "chart-label" }, point.label),
      el("div", { class: "chart-track" }, bar, el("span", { class: "chart-value" }, point.display)));
      return row;
    });
    holder.append(el("figure", { class: "chart" },
      el("figcaption", { class: "chart-title" }, `${chart.column} by ${chart.label_column}`),
      ...rows));
  }
  const table = detail.bucket_table;
  if (table.headers.length) {
    const details = el("details", { class: "chart-table" },
      el("summary", {}, "Show as table"),
      el("table", {},
        el("thead", {}, el("tr", {}, ...table.headers.map((header) => el("th", {}, header)))),
        el("tbody", {}, ...table.rows.map((row) => el("tr", {}, ...row.map((cell) => el("td", {}, cell)))))));
    if (!detail.charts.length) details.open = true;
    holder.append(details);
  }
}

/* --------------------------------------------------------------- edit */

function markDirty() {
  state.dirty = true;
}

function textInput(value, onInput, attrs = {}) {
  return el("input", {
    type: "text",
    value: value ?? "",
    autocomplete: "off",
    spellcheck: false,
    on: { input: (event) => { onInput(event.target.value); markDirty(); } },
    ...attrs,
  });
}

function field(label, control) {
  return el("label", { class: "field" }, el("span", {}, label), control);
}

function keywordParts(pkg) {
  const keywords = Array.isArray(pkg.keywords) ? pkg.keywords.filter((k) => typeof k === "string") : [];
  const required = {};
  const others = [];
  for (const keyword of keywords) {
    const prefix = REQUIRED_PREFIXES.find((p) => keyword.startsWith(`${p}:`));
    if (prefix && !(prefix in required)) required[prefix] = keyword.slice(prefix.length + 1);
    else others.push(keyword);
  }
  return { required, others };
}

function setKeywords(required, others) {
  const keywords = REQUIRED_PREFIXES.filter((prefix) => required[prefix])
    .map((prefix) => `${prefix}:${required[prefix]}`);
  state.pkg.keywords = keywords.concat(others);
}

function renderKeywords() {
  const { required, others } = keywordParts(state.pkg);
  const update = () => setKeywords(required, others);
  const stages = [...state.detail.stages];
  // Keep an unrecognized stage visible, so opening the form never changes it silently.
  if (required.stage && !stages.includes(required.stage)) stages.push(required.stage);
  const stage = el("select", {
    on: { change: (event) => { required.stage = event.target.value; update(); markDirty(); } },
  }, el("option", { value: "" }, "Choose a stage"), ...stages.map((name) => el("option", { value: name }, name)));
  stage.value = required.stage || "";
  return el("section", { class: "form-section" },
    el("h2", {}, "Keywords"),
    el("div", { class: "field-grid" },
      field("task", textInput(required.task, (value) => { required.task = value.trim(); update(); })),
      field("project", textInput(required.project, (value) => { required.project = value.trim(); update(); })),
      field("stage", stage)),
    // Shown only so that keywords which aren't allowed can be removed, never to add new ones.
    others.length ? field("Not allowed: clear this field to remove them", textInput(others.join(", "), (value) => {
      others.splice(0, others.length, ...value.split(",").map((k) => k.trim()).filter(Boolean));
      update();
    })) : null);
}

function renderCreated() {
  const current = typeof state.pkg.created === "string" ? state.pkg.created : "";
  const match = CREATED_RE.exec(current);
  const output = el("code", {}, current || "not set");
  const picker = el("input", {
    type: "date",
    value: match ? match[1] : "",
    on: {
      change: (event) => {
        if (event.target.value) state.pkg.created = `${event.target.value}T00:00:00Z`;
        else delete state.pkg.created;
        output.textContent = state.pkg.created || "not set";
        markDirty();
      },
    },
  });
  return el("section", { class: "form-section" },
    el("h2", {}, "Created"),
    el("div", { class: "date-row" }, picker, el("span", { class: "muted" }, "Stored as "), output));
}

function ensureList(key) {
  if (!Array.isArray(state.pkg[key])) state.pkg[key] = [];
  return state.pkg[key];
}

function rowSection({ key, title, hint, rowClass, headers, cells, blank, extraActions }) {
  const section = el("section", { class: "form-section" });
  const draw = () => {
    const items = ensureList(key);
    const rows = items.map((item, index) => {
      if (!item || typeof item !== "object") {
        items[index] = {};
        item = items[index];
      }
      return el("div", { class: `row ${rowClass}` },
        ...cells(item),
        el("button", {
          type: "button",
          class: "link",
          title: "Remove",
          "aria-label": `Remove ${title} row ${index + 1}`,
          on: { click: () => { items.splice(index, 1); markDirty(); draw(); } },
        }, "✕"));
    });
    const head = items.length ? el("div", { class: `row ${rowClass} row-head` }, ...headers.map((h) => el("span", {}, h)), el("span", {})) : null;
    section.replaceChildren(
      el("h2", {}, title),
      hint ? el("p", { class: "hint" }, hint) : "",
      el("div", { class: "rows" }, head, ...rows),
      el("div", { class: "actions" },
        el("button", {
          type: "button",
          class: "secondary",
          on: { click: () => { items.push(blank()); markDirty(); draw(); } },
        }, "Add row"),
        ...(extraActions ? extraActions(items, draw) : [])));
  };
  draw();
  return section;
}

function bind(item, key, placeholder) {
  return textInput(typeof item[key] === "string" ? item[key] : "", (value) => { item[key] = value; }, { placeholder: placeholder || "", "aria-label": key });
}

function sizeText(resource) {
  if (!Number.isInteger(resource.size)) return "";
  const path = String(resource.path || "").toLowerCase();
  const unit = path.endsWith(".csv") ? "row" : path.endsWith(".json") ? "item" : "file";
  return resource.size === 1 ? `1 ${unit}` : `${resource.size} ${unit}s`;
}

function renderEdit() {
  const pkg = state.pkg;
  if (!pkg) {
    return el("p", { class: "muted" }, "datapackage.json has a problem the form can't show. Fix it in the JSON tab.");
  }
  const description = el("textarea", {
    rows: 4,
    value: typeof pkg.description === "string" ? pkg.description : "",
    autocomplete: "off",
    on: { input: (event) => { pkg.description = event.target.value; markDirty(); } },
  });
  return el("form", { autocomplete: "off", on: { submit: (event) => event.preventDefault() } },
    el("section", { class: "form-section" },
      field("Name", bind(pkg, "name")),
      field("Title", bind(pkg, "title")),
      field("Description", description)),
    renderKeywords(),
    renderCreated(),
    rowSection({
      key: "contributors",
      title: "Contributors",
      rowClass: "row-2",
      headers: ["Name", "Roles, separated by commas"],
      blank: () => ({ title: "", roles: [] }),
      cells: (item) => [
        bind(item, "title"),
        textInput(Array.isArray(item.roles) ? item.roles.join(", ") : "", (value) => {
          item.roles = value.split(",").map((role) => role.trim()).filter(Boolean);
        }, { "aria-label": "roles", placeholder: "creator" }),
      ],
    }),
    rowSection({
      key: "sources",
      title: "Sources",
      hint: "Optional. Where this data came from. A listed source needs a title. A path or URL is optional and isn't checked.",
      rowClass: "row-2",
      headers: ["Title", "Path or URL (optional)"],
      blank: () => ({ title: "" }),
      cells: (item) => [
        bind(item, "title"),
        textInput(typeof item.path === "string" ? item.path : "", (value) => {
          if (value) item.path = value;
          else delete item.path;
        }, { "aria-label": "path" }),
      ],
    }),
    rowSection({
      key: "resources",
      title: "Resources",
      hint: "Every root file and folder, except template files. buckets.csv doesn't need a row. Size is counted automatically.",
      rowClass: "row-4",
      headers: ["Name", "Path", "Title", "Format", "Size"],
      blank: () => ({ name: "", path: "", title: "", format: "" }),
      cells: (item) => [
        bind(item, "name"),
        bind(item, "path"),
        bind(item, "title"),
        bind(item, "format"),
        el("span", { class: "muted" }, sizeText(item)),
      ],
      extraActions: (items, draw) => {
        const known = new Set(items.map((item) => item.path));
        const stubs = state.detail.stubs.filter((stub) => !known.has(stub.path));
        if (!stubs.length) return [];
        return [el("button", {
          type: "button",
          class: "secondary",
          on: { click: () => { items.push(...structuredClone(stubs)); markDirty(); draw(); } },
        }, `Add ${plural(stubs.length, "undescribed item")}`)];
      },
    }),
    saveBar(() => ({ package: state.pkg })));
}

function renderJson() {
  const area = el("textarea", {
    class: "raw",
    value: state.raw,
    spellcheck: false,
    autocomplete: "off",
    "aria-label": "datapackage.json",
    on: { input: (event) => { state.raw = event.target.value; markDirty(); } },
  });
  return el("div", {}, area, saveBar(() => ({ raw: state.raw })));
}

function saveBar(payload) {
  const button = el("button", {
    type: "button",
    id: "save",
    on: {
      click: async () => {
        button.disabled = true;
        await save(payload());
        button.disabled = false;
      },
    },
  }, "Save");
  return el("div", { class: "save-bar" }, button,
    el("span", { class: "muted" }, "Saves datapackage.json and re-validates. Partial metadata is fine."));
}

async function save(payload) {
  try {
    const detail = await api(`/api/datasets/${encodeURIComponent(state.folder)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...payload, etag: state.detail.etag }),
    });
    applyDetail(detail);
    await refreshList();
    renderMain();
    const report = detail.report;
    if (!report.ok) toast(`Saved. ${plural(report.errors.length, "error")} left, so ${detail.readme_name} wasn't written.`);
    else if (report.readme_written) toast(`Saved. Passes, and ${detail.readme_name} was updated.`);
    else toast(`Saved. Passes, and ${detail.readme_name} is up to date.`);
  } catch (error) {
    toast(error.message);
  }
}

/* --------------------------------------------------------------- init */

$("#revalidate").addEventListener("click", async () => {
  if (!confirmDiscard()) return;
  try {
    const result = await api("/api/revalidate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    state.datasets = result.datasets;
    state.dirty = false;
    renderList();
    if (state.folder) await loadDetail();
    toast(result.readmes_written.length ? `Re-validated. Wrote ${plural(result.readmes_written.length, "README")}.` : "Re-validated.");
  } catch (error) {
    toast(error.message);
  }
});

window.addEventListener("beforeunload", (event) => {
  if (state.dirty) event.preventDefault();
});

(async () => {
  try {
    await refreshList();
  } catch (error) {
    toast(error.message);
    return;
  }
  const [hashFolder, hashTab] = decodeURIComponent(location.hash.slice(1)).split("/");
  const known = state.datasets.some((dataset) => dataset.folder === hashFolder);
  const tab = ["view", "edit", "json"].includes(hashTab) ? hashTab : "view";
  if (known) await selectDataset(hashFolder, tab);
})();
