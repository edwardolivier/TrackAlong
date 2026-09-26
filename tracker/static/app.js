// TrackAlong Tracker — single-page frontend. No build step, no dependencies.
// Routes:  #/                 projects
//          #/p/KEY            project board / list
//          #/t/KEY-12         ticket detail
"use strict";

const app = document.getElementById("app");
const crumbs = document.getElementById("crumbs");
const meInput = document.getElementById("me");
let META = { types: [], statuses: [], priorities: [] };

const STATUS_LABEL = {
  open: "Open", in_progress: "In progress", blocked: "Blocked",
  review: "In review", done: "Done", wont_do: "Won't do",
};
const label = (s) => STATUS_LABEL[s] || s.charAt(0).toUpperCase() + s.slice(1);

// ---------------------------------------------------------------- helpers
function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v == null) continue;
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "class") el.className = v;
    else if (k === "value") el.value = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch("/api" + path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

function toast(msg, error = false) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.className = "toast" + (error ? " error" : "");
  t.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => (t.hidden = true), 2600);
}

const me = () => meInput.value.trim();
const ago = (iso) => {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return Math.floor(s / 60) + "m ago";
  if (s < 86400) return Math.floor(s / 3600) + "h ago";
  if (s < 86400 * 30) return Math.floor(s / 86400) + "d ago";
  return new Date(iso).toLocaleDateString();
};
const typeBadge = (t) => h("span", { class: `badge type-${t}` }, t);
const prioBadge = (p) => h("span", { class: `badge prio-${p}` }, p);
const statusBadge = (s) => h("span", { class: "badge status" }, label(s));
const options = (list, selected, fmt = (x) => x) =>
  list.map((x) => h("option", { value: x, selected: x === selected }, fmt(x)));

function setCrumbs(...parts) {
  crumbs.replaceChildren(...parts.flatMap((p, i) => (i ? [" / ", p] : [p])));
}

// ---------------------------------------------------------------- dialog
function openDialog(title, fields, submitText, onSubmit) {
  const dlg = document.getElementById("dialog");
  const form = document.getElementById("dialog-form");
  const err = h("div", { class: "muted", style: "color:var(--danger)" });
  form.replaceChildren(
    h("h2", {}, title),
    ...fields,
    err,
    h("div", { class: "actions" },
      h("button", { type: "button", onclick: () => dlg.close() }, "Cancel"),
      h("button", { type: "submit", class: "primary" }, submitText)),
  );
  form.onsubmit = async (e) => {
    e.preventDefault();
    try {
      await onSubmit(new FormData(form));
      dlg.close();
    } catch (ex) {
      err.textContent = ex.message;
    }
  };
  dlg.showModal();
  form.querySelector("input, textarea, select")?.focus();
}

function newProjectDialog() {
  openDialog("New project", [
    h("label", {}, "Name", h("input", { name: "name", required: true, maxlength: 120 })),
    h("label", {}, "Key (2-10 letters/digits, used in ticket IDs e.g. TRK-12)",
      h("input", { name: "key", required: true, maxlength: 10, pattern: "[A-Za-z][A-Za-z0-9]{1,9}",
        style: "text-transform:uppercase" })),
    h("label", {}, "Description", h("textarea", { name: "description", rows: 3 })),
  ], "Create project", async (fd) => {
    const p = await api("POST", "/projects", Object.fromEntries(fd));
    location.hash = `#/p/${p.key}`;
  });
  // Suggest a key from the name
  const form = document.getElementById("dialog-form");
  const nameEl = form.elements.namedItem("name");
  const keyEl = form.elements.namedItem("key");
  nameEl.addEventListener("input", () => {
    if (keyEl.dataset.touched) return;
    keyEl.value = nameEl.value.replace(/[^A-Za-z0-9 ]/g, "").split(/\s+/).filter(Boolean)
      .map((w, _, a) => (a.length > 1 ? w[0] : w.slice(0, 4))).join("").slice(0, 10).toUpperCase();
  });
  keyEl.addEventListener("input", () => (keyEl.dataset.touched = "1"));
}

function newTicketDialog(projectKey, defaults = {}) {
  openDialog(`New ticket in ${projectKey}`, [
    h("label", {}, "Title", h("input", { name: "title", required: true, maxlength: 200 })),
    h("div", { class: "row" },
      h("label", {}, "Type", h("select", { name: "type" }, options(META.types, defaults.type || "improvement"))),
      h("label", {}, "Priority", h("select", { name: "priority" }, options(META.priorities, "medium"))),
      h("label", {}, "Status", h("select", { name: "status" }, options(META.statuses, defaults.status || "open", label)))),
    h("label", {}, "Description", h("textarea", { name: "description", placeholder:
      "What's the problem or idea? Steps to reproduce / expected outcome / acceptance criteria…" })),
    h("div", { class: "row" },
      h("label", {}, "Assignee", h("input", { name: "assignee", maxlength: 80 })),
      h("label", { style: "grid-column: span 2" }, "Labels (comma separated)", h("input", { name: "labels" }))),
  ], "Create ticket", async (fd) => {
    const body = Object.fromEntries(fd);
    body.reporter = me();
    const t = await api("POST", `/projects/${projectKey}/tickets`, body);
    toast(`Created ${t.ref}`);
    route();
  });
}

// ---------------------------------------------------------------- views
async function viewProjects() {
  setCrumbs("Projects");
  const projects = await api("GET", "/projects");
  const total = (c) => Object.values(c).reduce((a, b) => a + b, 0);
  const openCount = (c) => total(c) - (c.done || 0) - (c.wont_do || 0);
  app.replaceChildren(
    h("div", { class: "page-head" },
      h("div", {}, h("h1", {}, "Projects"),
        h("div", { class: "muted" }, "Raise bugs, improvements and tasks for each project you're building.")),
      h("button", { class: "primary", onclick: newProjectDialog }, "+ New project")),
    projects.length
      ? h("div", { class: "grid" }, projects.map((p) =>
          h("a", { class: "card project-card", href: `#/p/${p.key}` },
            h("div", { class: "key" }, p.key),
            h("h2", {}, p.name),
            h("div", { class: "muted" }, p.description || "—"),
            h("div", { class: "stats" },
              h("div", {}, h("b", {}, openCount(p.counts)), "open"),
              h("div", {}, h("b", {}, p.counts.in_progress || 0), "in progress"),
              h("div", {}, h("b", {}, p.counts.done || 0), "done"),
              h("div", {}, h("b", {}, total(p.counts)), "total")))))
      : h("div", { class: "card empty" }, "No projects yet. Create one to start raising tickets."),
  );
}

const projectState = { view: localStorage.getItem("tracker.view") || "board", filters: {} };

async function viewProject(key) {
  const project = await api("GET", `/projects/${key}`);
  setCrumbs(h("a", { href: "#/" }, "Projects"), project.name);

  const f = projectState.filters[key] || (projectState.filters[key] = {});
  const qs = new URLSearchParams(Object.entries(f).filter(([, v]) => v)).toString();
  const tickets = await api("GET", `/projects/${key}/tickets${qs ? "?" + qs : ""}`);

  const setFilter = (name) => (e) => { f[name] = e.target.value; viewProject(key); };
  const setView = (v) => () => { projectState.view = v; localStorage.setItem("tracker.view", v); viewProject(key); };
  let searchTimer;

  app.replaceChildren(
    h("div", { class: "page-head" },
      h("div", {}, h("h1", {}, project.name, " ", h("span", { class: "ref" }, project.key)),
        h("div", { class: "muted" }, project.description)),
      h("div", { class: "toolbar" },
        h("button", { onclick: () => editProjectDialog(project) }, "Edit project"),
        h("button", { class: "primary", onclick: () => newTicketDialog(key) }, "+ New ticket"))),
    h("div", { class: "toolbar" },
      h("div", { class: "seg" },
        h("button", { class: projectState.view === "board" ? "on" : "", onclick: setView("board") }, "Board"),
        h("button", { class: projectState.view === "list" ? "on" : "", onclick: setView("list") }, "List")),
      h("input", { type: "search", placeholder: "Search title, description, labels…", value: f.q || "",
        oninput: (e) => { clearTimeout(searchTimer); searchTimer = setTimeout(() => setFilter("q")(e), 250); } }),
      h("select", { onchange: setFilter("type") }, h("option", { value: "" }, "All types"), options(META.types, f.type)),
      h("select", { onchange: setFilter("priority") }, h("option", { value: "" }, "All priorities"), options(META.priorities, f.priority)),
      projectState.view === "list" &&
        h("select", { onchange: setFilter("status") }, h("option", { value: "" }, "All statuses"), options(META.statuses, f.status, label)),
      h("span", { class: "muted" }, `${tickets.length} ticket${tickets.length === 1 ? "" : "s"}`)),
    projectState.view === "board" ? board(key, tickets) : list(tickets),
  );
  // keep focus in search box while typing
  if (f.q) { const s = app.querySelector("input[type=search]"); s.focus(); s.setSelectionRange(s.value.length, s.value.length); }
}

function board(key, tickets) {
  return h("div", { class: "board" }, META.statuses.map((status) => {
    const items = tickets.filter((t) => t.status === status);
    const col = h("div", { class: "column" },
      h("h3", {}, label(status), h("span", {}, items.length)),
      items.map((t) => ticketCard(t)));
    col.addEventListener("dragover", (e) => { e.preventDefault(); col.classList.add("drop"); });
    col.addEventListener("dragleave", () => col.classList.remove("drop"));
    col.addEventListener("drop", async (e) => {
      e.preventDefault();
      col.classList.remove("drop");
      const ref = e.dataTransfer.getData("text/ticket");
      if (!ref) return;
      try {
        await api("PATCH", `/tickets/${ref}`, { status, actor: me() });
        viewProject(key);
      } catch (ex) { toast(ex.message, true); }
    });
    return col;
  }));
}

function ticketCard(t) {
  const card = h("a", { class: `tcard ${t.type}`, href: `#/t/${t.ref}`, draggable: "true" },
    h("div", { class: "meta" }, h("span", { class: "ref" }, t.ref), typeBadge(t.type)),
    h("div", { class: "title" }, t.title),
    h("div", { class: "meta" }, prioBadge(t.priority),
      t.assignee && h("span", {}, "@" + t.assignee),
      t.comment_count ? h("span", {}, `💬 ${t.comment_count}`) : null,
      t.labels.map((l) => h("span", { class: "badge label" }, l))));
  card.addEventListener("dragstart", (e) => e.dataTransfer.setData("text/ticket", t.ref));
  return card;
}

function list(tickets) {
  if (!tickets.length) return h("div", { class: "card empty" }, "No tickets match.");
  return h("table", { class: "list" },
    h("thead", {}, h("tr", {}, ["ID", "Title", "Type", "Priority", "Status", "Assignee", "Updated"].map((c) => h("th", {}, c)))),
    h("tbody", {}, tickets.map((t) =>
      h("tr", {},
        h("td", { class: "ref" }, t.ref),
        h("td", {}, h("a", { href: `#/t/${t.ref}` }, t.title), " ",
          t.labels.map((l) => h("span", { class: "badge label" }, l))),
        h("td", {}, typeBadge(t.type)),
        h("td", {}, prioBadge(t.priority)),
        h("td", {}, statusBadge(t.status)),
        h("td", {}, t.assignee || h("span", { class: "muted" }, "—")),
        h("td", { class: "muted", title: t.updated_at }, ago(t.updated_at))))));
}

function editProjectDialog(p) {
  openDialog(`Edit ${p.key}`, [
    h("label", {}, "Name", h("input", { name: "name", required: true, value: p.name, maxlength: 120 })),
    h("label", {}, "Description", h("textarea", { name: "description", rows: 3 }, p.description)),
    h("div", {}, h("button", { type: "button", class: "danger", onclick: async () => {
      if (prompt(`This permanently deletes ${p.key} and ALL its tickets. Type ${p.key} to confirm.`) !== p.key) return;
      await api("DELETE", `/projects/${p.key}`);
      document.getElementById("dialog").close();
      location.hash = "#/";
    } }, "Delete project")),
  ], "Save", async (fd) => {
    await api("PATCH", `/projects/${p.key}`, Object.fromEntries(fd));
    route();
  });
}

async function viewTicket(ref) {
  const t = await api("GET", `/tickets/${ref}`);
  const project = await api("GET", `/projects/${t.project_key}`);
  setCrumbs(h("a", { href: "#/" }, "Projects"), h("a", { href: `#/p/${project.key}` }, project.name), t.ref);

  const save = async (patch) => {
    try {
      await api("PATCH", `/tickets/${ref}`, { ...patch, actor: me() });
      toast("Saved");
      viewTicket(ref);
    } catch (ex) { toast(ex.message, true); }
  };
  const field = (name, list, fmt) =>
    h("select", { onchange: (e) => save({ [name]: e.target.value }) }, options(list, t[name], fmt));
  const text = (name, value) =>
    h("input", { value, onchange: (e) => save({ [name]: e.target.value }) });

  const desc = h("div", { class: "desc" }, t.description || h("span", { class: "muted" }, "No description."));
  const editDesc = () => {
    const ta = h("textarea", {}, t.description);
    desc.replaceWith(h("div", {}, ta, h("div", { class: "toolbar", style: "margin-top:8px" },
      h("button", { class: "primary", onclick: () => save({ description: ta.value }) }, "Save"),
      h("button", { onclick: () => viewTicket(ref) }, "Cancel"))));
    ta.focus();
  };

  const commentBox = h("textarea", { placeholder: "Add a comment…", style: "min-height:80px" });

  app.replaceChildren(h("div", { class: "detail" },
    h("div", {},
      h("div", { class: "ref" }, t.ref, " · ", typeBadge(t.type)),
      h("input", { class: "title-input", value: t.title, maxlength: 200,
        onchange: (e) => save({ title: e.target.value }) }),
      h("div", { class: "card" },
        h("div", { class: "toolbar", style: "justify-content:space-between" },
          h("h2", { style: "margin:0" }, "Description"),
          h("button", { onclick: editDesc }, "Edit")),
        desc),
      h("div", { class: "timeline" },
        h("h2", {}, "Activity"),
        t.comments.length ? null : h("div", { class: "muted" }, "No activity yet."),
        t.comments.map((c) => c.kind === "change"
          ? h("div", { class: "entry change" }, `${c.author || "someone"} changed ${c.body} · ${ago(c.created_at)}`)
          : h("div", { class: "entry" },
              h("span", { class: "who" }, c.author || "anonymous"), " ",
              h("span", { class: "muted", title: c.created_at }, ago(c.created_at)),
              h("div", { class: "body" }, c.body))),
        h("div", { style: "margin-top:12px" }, commentBox,
          h("div", { class: "toolbar", style: "margin-top:8px" },
            h("button", { class: "primary", onclick: async () => {
              if (!commentBox.value.trim()) return;
              try {
                await api("POST", `/tickets/${ref}/comments`, { body: commentBox.value, author: me() });
                viewTicket(ref);
              } catch (ex) { toast(ex.message, true); }
            } }, "Comment"))))),
    h("aside", { class: "side card" },
      h("dl", {},
        h("dt", {}, "Status"), h("dd", {}, field("status", META.statuses, label)),
        h("dt", {}, "Type"), h("dd", {}, field("type", META.types)),
        h("dt", {}, "Priority"), h("dd", {}, field("priority", META.priorities)),
        h("dt", {}, "Assignee"), h("dd", {}, text("assignee", t.assignee)),
        h("dt", {}, "Labels"), h("dd", {}, text("labels", t.labels.join(", "))),
        h("dt", {}, "Reporter"), h("dd", {}, t.reporter || h("span", { class: "muted" }, "—")),
        h("dt", {}, "Created"), h("dd", { title: t.created_at }, ago(t.created_at)),
        h("dt", {}, "Updated"), h("dd", { title: t.updated_at }, ago(t.updated_at))),
      h("div", { style: "margin-top:16px; display:flex; gap:8px; flex-wrap:wrap" },
        t.assignee !== me() && me() && h("button", { onclick: () => save({ assignee: me() }) }, "Assign to me"),
        h("button", { class: "danger", onclick: async () => {
          if (!confirm(`Delete ${t.ref}? This cannot be undone.`)) return;
          await api("DELETE", `/tickets/${ref}`);
          location.hash = `#/p/${t.project_key}`;
        } }, "Delete")))));
}

// ---------------------------------------------------------------- router
async function route() {
  const hash = location.hash.replace(/^#\/?/, "");
  const [kind, id] = hash.split("/");
  try {
    if (kind === "p" && id) await viewProject(decodeURIComponent(id));
    else if (kind === "t" && id) await viewTicket(decodeURIComponent(id));
    else await viewProjects();
  } catch (ex) {
    app.replaceChildren(h("div", { class: "card empty" }, ex.message, h("br"), h("a", { href: "#/" }, "Back to projects")));
  }
}

meInput.value = localStorage.getItem("tracker.me") || "";
meInput.addEventListener("change", () => localStorage.setItem("tracker.me", me()));
window.addEventListener("hashchange", route);
api("GET", "/meta").then((m) => { META = m; route(); });
