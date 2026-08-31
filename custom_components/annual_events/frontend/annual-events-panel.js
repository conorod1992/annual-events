const TEXT = {
  title: "Annual Events",
  subtitle: "Birthdays, anniversaries, memorials and every date worth remembering.",
  add: "Add event",
  edit: "Edit event",
  save: "Save",
  cancel: "Cancel",
  delete: "Delete",
  search: "Search names, aliases, categories or notes",
  empty: "No annual events match these filters.",
  loading: "Loading annual events…",
  enabled: "Enabled",
  exposed: "Entity",
};

const PAGE_SIZE = 500;

const escapeHtml = (value) => String(value ?? "")
  .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;").replaceAll("'", "&#039;");

const formatDate = (iso) => {
  if (!iso) return "";
  const [year, month, day] = iso.split("-").map(Number);
  return new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short" })
    .format(new Date(year, month - 1, day));
};

class AnnualEventsPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.events = [];
    this.total = 0;
    this.dashboard = { today: [], upcoming: [] };
    this.settings = { categories: [], options: {}, is_admin: false };
    this.loading = true;
    this.loadingMore = false;
    this.error = "";
    this.filters = { search: "", category: "", enabled: "", important: false, sort: "next_occurrence", direction: "asc" };
    this._timer = undefined;
    this._refreshGeneration = 0;
  }

  set hass(value) {
    this._hass = value;
    if (this.isConnected && !this._loaded) this.load();
  }

  connectedCallback() {
    this.render();
    if (this._hass && !this._loaded) this.load();
  }

  async call(message) {
    return this._hass.connection.sendMessagePromise(message);
  }

  async load() {
    this._loaded = true;
    this.loading = true;
    this.error = "";
    this.render();
    try {
      this.settings = await this.call({ type: "annual_events/settings" });
      await Promise.all([this.refresh(), this.refreshDashboard()]);
    } catch (err) {
      this.error = err?.message || "Could not load Annual Events.";
    } finally {
      this.loading = false;
      this.render();
    }
  }

  async refresh({ append = false } = {}) {
    const generation = ++this._refreshGeneration;
    if (!append) this.loadingMore = false;
    const request = {
      type: "annual_events/list",
      sort: this.filters.sort,
      direction: this.filters.direction,
      offset: append ? this.events.length : 0,
      limit: PAGE_SIZE,
    };
    if (this.filters.search) request.search = this.filters.search;
    if (this.filters.category) request.category = this.filters.category;
    if (this.filters.enabled !== "") request.enabled = this.filters.enabled === "true";
    if (this.filters.important) request.important = true;

    let result;
    try {
      result = await this.call(request);
    } catch (err) {
      if (generation !== this._refreshGeneration) return false;
      throw err;
    }
    if (generation !== this._refreshGeneration) return false;

    this.events = append ? [...this.events, ...result.events] : result.events;
    this.total = result.pagination?.total ?? this.events.length;
    this.loadingMore = false;
    this.render();
    return true;
  }

  async loadMore() {
    if (this.loadingMore || this.events.length >= this.total) return;
    this.loadingMore = true;
    this.render();
    try {
      await this.refresh({ append: true });
    } catch (err) {
      this.loadingMore = false;
      this.error = err?.message || "Could not load more annual events.";
      this.render();
    }
  }

  async refreshDashboard() {
    const days = Math.max(1, Number(this.settings.options?.upcoming_days || 30));
    const result = await this.call({
      type: "annual_events/upcoming",
      days,
      limit: 50,
      enabled_only: true,
    });
    this.dashboard.today = result.occurrences.filter((item) => item.days_until === 0);
    this.dashboard.upcoming = result.occurrences.filter((item) => item.days_until > 0).slice(0, 8);
  }

  overviewTemplate() {
    const today = this.dashboard.today.length
      ? this.dashboard.today.map((item) => this.overviewItem(item, true)).join("")
      : '<div class="overview-empty">Nothing today.</div>';
    const upcoming = this.dashboard.upcoming.length
      ? this.dashboard.upcoming.map((item) => this.overviewItem(item, false)).join("")
      : '<div class="overview-empty">Nothing coming up in the current horizon.</div>';
    return `<section class="overview" aria-label="Today and upcoming events">
      <article class="overview-card"><h2>Today</h2><div class="overview-list">${today}</div></article>
      <article class="overview-card"><h2>Upcoming</h2><div class="overview-list">${upcoming}</div></article>
    </section>`;
  }

  overviewItem(item, today) {
    const number = item.occurrence_number == null ? "" : ` · #${item.occurrence_number}`;
    const when = today ? "Today" : `${formatDate(item.occurrence_date)} · ${item.days_until} day${item.days_until === 1 ? "" : "s"}`;
    return `<div class="overview-item"><div><strong>${escapeHtml(item.name)}</strong><div class="overview-meta">${escapeHtml((item.category || "uncategorized").replaceAll("_", " "))}${number}</div></div><span>${escapeHtml(when)}</span></div>`;
  }

  listFooterTemplate() {
    if (!this.events.length || this.total <= this.events.length) return "";
    return `<div class="list-footer"><span>Showing ${this.events.length.toLocaleString()} of ${this.total.toLocaleString()}</span><button id="load-more" class="secondary" ${this.loadingMore ? "disabled" : ""}>${this.loadingMore ? "Loading…" : "Load more"}</button></div>`;
  }

  render() {
    const categories = [...new Set([...this.settings.categories, ...this.events.map((e) => e.category).filter(Boolean)])].sort();
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; color:var(--primary-text-color,#222); background:var(--primary-background-color,#fafafa); min-height:100vh; font-family:var(--paper-font-body1_-_font-family,system-ui,sans-serif); }
        * { box-sizing:border-box; }
        .wrap { max-width:1120px; margin:auto; padding:24px; }
        header { display:flex; gap:20px; align-items:flex-start; justify-content:space-between; margin-bottom:22px; }
        h1 { margin:0; font-size:28px; } h2 { margin:0 0 12px; font-size:18px; }
        .subtitle { color:var(--secondary-text-color,#666); margin:5px 0 0; }
        button,.button { border:0; border-radius:10px; padding:10px 15px; cursor:pointer; background:var(--primary-color,#03a9f4); color:var(--text-primary-color,#fff); font:inherit; font-weight:600; }
        button.secondary { background:transparent; color:var(--primary-text-color,#222); border:1px solid var(--divider-color,#ddd); }
        button.danger { background:var(--error-color,#db4437); } button.icon { padding:8px 10px; }
        button:disabled,input:disabled { opacity:.55; cursor:not-allowed; }
        .overview { display:grid; grid-template-columns:1fr 1.4fr; gap:14px; margin-bottom:18px; }
        .overview-card { background:var(--card-background-color,#fff); border-radius:14px; box-shadow:var(--ha-card-box-shadow,0 2px 8px #0001); padding:16px; }
        .overview-list { display:grid; gap:8px; }
        .overview-item { display:flex; justify-content:space-between; align-items:center; gap:14px; padding:8px 0; border-top:1px solid var(--divider-color,#eee); }
        .overview-item:first-child { border-top:0; padding-top:0; }
        .overview-item > span { color:var(--secondary-text-color,#666); font-size:13px; white-space:nowrap; }
        .overview-meta,.overview-empty { color:var(--secondary-text-color,#666); font-size:13px; margin-top:3px; }
        .filters { display:grid; grid-template-columns:minmax(220px,2fr) repeat(3,minmax(130px,1fr)); gap:10px; padding:15px; background:var(--card-background-color,#fff); border-radius:14px; box-shadow:var(--ha-card-box-shadow,0 2px 8px #0001); margin-bottom:14px; }
        input,select,textarea { width:100%; padding:10px 11px; border:1px solid var(--divider-color,#ccc); border-radius:9px; color:var(--primary-text-color,#222); background:var(--card-background-color,#fff); font:inherit; }
        label { display:grid; gap:5px; color:var(--secondary-text-color,#666); font-size:13px; }
        .hint { color:var(--secondary-text-color,#666); font-size:12px; line-height:1.35; }
        .check { display:flex; align-items:center; gap:8px; align-self:center; font-size:14px; color:var(--primary-text-color,#222); }
        .check input { width:auto; }
        .list { display:grid; gap:10px; }
        .list-footer { display:flex; justify-content:center; align-items:center; gap:14px; padding:18px 0 4px; color:var(--secondary-text-color,#666); font-size:13px; }
        .event { background:var(--card-background-color,#fff); border-radius:14px; box-shadow:var(--ha-card-box-shadow,0 2px 8px #0001); padding:16px; display:grid; grid-template-columns:minmax(180px,1.5fr) minmax(160px,1fr) auto; gap:15px; align-items:center; }
        .name { font-weight:650; font-size:17px; display:flex; align-items:center; gap:7px; } .star { color:#f9a825; }
        .meta { color:var(--secondary-text-color,#666); font-size:13px; margin-top:5px; }
        .date { font-weight:600; } .days { color:var(--secondary-text-color,#666); font-size:13px; margin-top:3px; }
        .actions { display:flex; align-items:center; gap:12px; } .switches { display:flex; gap:10px; }
        .switch { display:grid; justify-items:center; gap:3px; font-size:11px; color:var(--secondary-text-color,#666); } .switch input { width:18px; height:18px; }
        .status { text-align:center; padding:45px 15px; color:var(--secondary-text-color,#666); } .error { color:var(--error-color,#db4437); }
        .modal-backdrop { position:fixed; inset:0; z-index:10; display:grid; place-items:center; padding:18px; background:#0008; }
        .modal { width:min(650px,100%); max-height:92vh; overflow:auto; background:var(--card-background-color,#fff); border-radius:16px; padding:22px; box-shadow:0 12px 48px #0006; }
        .modal h2 { margin-top:0; } .form { display:grid; grid-template-columns:1fr 1fr; gap:13px; } .full { grid-column:1/-1; }
        .checks { display:flex; flex-wrap:wrap; gap:18px; padding:5px 0; } .modal-actions { display:flex; justify-content:flex-end; gap:10px; margin-top:20px; }
        .proactive-custom[hidden] { display:none; }
        @media (max-width:760px) { .wrap{padding:15px} header{align-items:center}.subtitle{display:none}.overview{grid-template-columns:1fr}.filters{grid-template-columns:1fr 1fr}.filters .search{grid-column:1/-1}.event{grid-template-columns:1fr auto}.datebox{grid-column:1}.actions{grid-column:2;grid-row:1/3;flex-direction:column}.switches{flex-direction:column}.form{grid-template-columns:1fr}.full{grid-column:auto} }
        @media (max-width:460px) { .filters{grid-template-columns:1fr}.filters .search{grid-column:auto}.event{grid-template-columns:1fr}.actions{grid-column:1;grid-row:auto;flex-direction:row;justify-content:space-between}.switches{flex-direction:row}.overview-item{align-items:flex-start;flex-direction:column;gap:4px}.list-footer{flex-direction:column;gap:8px} }
      </style>
      <div class="wrap">
        <header><div><h1>${TEXT.title}</h1><p class="subtitle">${TEXT.subtitle}</p></div>${this.settings.is_admin ? `<button id="add">＋ ${TEXT.add}</button>` : ""}</header>
        ${!this.loading && !this.error ? this.overviewTemplate() : ""}
        <section class="filters" aria-label="Event filters">
          <label class="search">Search<input id="search" type="search" value="${escapeHtml(this.filters.search)}" placeholder="${TEXT.search}" /></label>
          <label>Category<select id="category"><option value="">All categories</option>${categories.map((c) => `<option value="${escapeHtml(c)}" ${this.filters.category === c ? "selected" : ""}>${escapeHtml(c.replaceAll("_", " "))}</option>`).join("")}</select></label>
          <label>Status<select id="enabled"><option value="">All</option><option value="true" ${this.filters.enabled === "true" ? "selected" : ""}>Enabled</option><option value="false" ${this.filters.enabled === "false" ? "selected" : ""}>Disabled</option></select></label>
          <label>Sort<select id="sort"><option value="next_occurrence" ${this.filters.sort === "next_occurrence" ? "selected" : ""}>Next occurrence</option><option value="name" ${this.filters.sort === "name" ? "selected" : ""}>Name</option></select></label>
          <label class="check"><input id="important" type="checkbox" ${this.filters.important ? "checked" : ""}/> Important only</label>
        </section>
        ${this.loading ? `<div class="status">${TEXT.loading}</div>` : this.error ? `<div class="status error" role="alert">${escapeHtml(this.error)}<br/><button id="retry" class="secondary">Retry</button></div>` : this.events.length ? `<main class="list">${this.events.map((event) => this.eventTemplate(event)).join("")}</main>${this.listFooterTemplate()}` : `<div class="status">${TEXT.empty}</div>`}
        <div id="modal"></div>
      </div>`;
    this.bind();
  }

  eventTemplate(event) {
    const number = event.occurrence_number == null ? "" : ` · #${event.occurrence_number}`;
    const proactive = event.proactive_mode === "off" ? " · proactive off" : event.proactive_mode === "custom" ? " · custom proactive" : "";
    return `<article class="event" data-id="${event.id}">
      <div><div class="name">${event.important ? '<span class="star" aria-label="Important">★</span>' : ""}${escapeHtml(event.name)}</div><div class="meta">${escapeHtml((event.category || "uncategorized").replaceAll("_", " "))}${event.year ? ` · since ${event.year}` : ""}${proactive}</div></div>
      <div class="datebox"><div class="date">${escapeHtml(event.next_occurrence)}</div><div class="days">${event.days_until === 0 ? "Today" : `${event.days_until} day${event.days_until === 1 ? "" : "s"} away`}${number}</div></div>
      <div class="actions"><div class="switches"><label class="switch"><input data-toggle="enabled" type="checkbox" ${event.enabled ? "checked" : ""} ${this.settings.is_admin ? "" : "disabled"}/>${TEXT.enabled}</label><label class="switch"><input data-toggle="expose_entity" type="checkbox" ${event.expose_entity ? "checked" : ""} ${this.settings.is_admin ? "" : "disabled"}/>${TEXT.exposed}</label></div>${this.settings.is_admin ? `<button class="secondary icon edit" aria-label="Edit ${escapeHtml(event.name)}">Edit</button>` : ""}</div>
    </article>`;
  }

  async refreshAfterMutation() {
    await Promise.all([this.refresh(), this.refreshDashboard()]);
  }

  bind() {
    this.shadowRoot.getElementById("add")?.addEventListener("click", () => this.openForm());
    this.shadowRoot.getElementById("retry")?.addEventListener("click", () => this.load());
    this.shadowRoot.getElementById("load-more")?.addEventListener("click", () => this.loadMore());
    const refreshFilters = async () => {
      this.error = "";
      this.loadingMore = false;
      try {
        await this.refresh();
      } catch (e) {
        this.error = e.message;
        this.render();
      }
    };
    const updateFilter = async (key, value) => {
      this.filters[key] = value;
      await refreshFilters();
    };
    this.shadowRoot.getElementById("search")?.addEventListener("input", (e) => {
      this.filters.search = e.target.value.trim();
      clearTimeout(this._timer);
      this._timer = setTimeout(() => refreshFilters(), 250);
    });
    for (const key of ["category", "enabled", "sort"]) this.shadowRoot.getElementById(key)?.addEventListener("change", (e) => updateFilter(key, e.target.value));
    this.shadowRoot.getElementById("important")?.addEventListener("change", (e) => updateFilter("important", e.target.checked));
    this.shadowRoot.querySelectorAll(".edit").forEach((button) => button.addEventListener("click", () => this.openForm(this.events.find((e) => e.id === button.closest("article").dataset.id))));
    this.shadowRoot.querySelectorAll("[data-toggle]").forEach((input) => input.addEventListener("change", async () => {
      input.disabled = true;
      try { await this.call({ type: "annual_events/update", event_id: input.closest("article").dataset.id, [input.dataset.toggle]: input.checked }); await this.refreshAfterMutation(); }
      catch (e) { this.error = e.message; this.render(); }
    }));
  }

  openForm(event = null) {
    const modal = this.shadowRoot.getElementById("modal");
    const aliases = event?.aliases?.join(", ") || "";
    const proactiveMode = event?.proactive_mode || "default";
    const proactiveDays = event?.proactive_advance_days?.join(", ") || "";
    const defaultDays = Array.isArray(this.settings.options?.advance_notice_days)
      ? this.settings.options.advance_notice_days.join(", ")
      : (this.settings.options?.advance_notice_days ?? 7);
    modal.innerHTML = `<div class="modal-backdrop" role="presentation"><section class="modal" role="dialog" aria-modal="true" aria-labelledby="dialog-title">
      <h2 id="dialog-title">${event ? TEXT.edit : TEXT.add}</h2><form id="event-form" class="form">
      <label class="full">Name *<input name="name" required maxlength="120" value="${escapeHtml(event?.name || "")}" autofocus /></label>
      <label>Month *<input name="month" type="number" min="1" max="12" required value="${event?.month || ""}" /></label>
      <label>Day *<input name="day" type="number" min="1" max="31" required value="${event?.day || ""}" /></label>
      <label>Original year (optional)<input name="year" type="number" min="1" max="9999" value="${event?.year || ""}" /></label>
      <label>Category<input name="category" list="categories" maxlength="64" value="${escapeHtml(event?.category || "")}" /><datalist id="categories">${this.settings.categories.map((c) => `<option value="${escapeHtml(c)}"></option>`).join("")}</datalist></label>
      <label class="full">Aliases, comma separated<input name="aliases" value="${escapeHtml(aliases)}" /></label>
      <label>Icon<input name="icon" placeholder="mdi:calendar-heart" value="${escapeHtml(event?.icon || "")}" /></label>
      <label class="full">Notes<textarea name="notes" rows="3">${escapeHtml(event?.notes || "")}</textarea></label>
      <label class="full">Proactive events<select name="proactive_mode"><option value="default" ${proactiveMode === "default" ? "selected" : ""}>Use integration defaults</option><option value="custom" ${proactiveMode === "custom" ? "selected" : ""}>Custom for this event</option><option value="off" ${proactiveMode === "off" ? "selected" : ""}>Off for this event</option></select><span class="hint">Integration defaults currently use advance day(s): ${escapeHtml(defaultDays)}.</span></label>
      <div id="proactive-custom" class="proactive-custom full" ${proactiveMode === "custom" ? "" : "hidden"}>
        <div class="form">
          <label class="full">Advance days before event<input name="proactive_advance_days" value="${escapeHtml(proactiveDays)}" placeholder="30, 7, 1" /><span class="hint">Comma-separated. Leave blank for day-of only.</span></label>
          <label class="check full"><input name="proactive_day_of" type="checkbox" ${event == null || event.proactive_day_of !== false ? "checked" : ""}/> Also emit on the day</label>
        </div>
      </div>
      <div class="checks full"><label class="check"><input name="important" type="checkbox" ${event?.important ? "checked" : ""}/> Important</label><label class="check"><input name="enabled" type="checkbox" ${event == null || event.enabled ? "checked" : ""}/> Enabled</label><label class="check"><input name="expose_entity" type="checkbox" ${event?.expose_entity ? "checked" : ""}/> Expose individual sensor</label></div>
      <div id="form-error" class="error full" role="alert"></div></form>
      <div class="modal-actions">${event ? `<button id="delete" class="danger">${TEXT.delete}</button>` : ""}<button id="cancel" class="secondary">${TEXT.cancel}</button><button id="save">${TEXT.save}</button></div>
      </section></div>`;
    modal.querySelector('[name="proactive_mode"]').addEventListener("change", (e) => {
      modal.querySelector("#proactive-custom").hidden = e.target.value !== "custom";
    });
    modal.querySelector("#cancel").addEventListener("click", () => { modal.innerHTML = ""; });
    modal.querySelector(".modal-backdrop").addEventListener("click", (e) => { if (e.target.classList.contains("modal-backdrop")) modal.innerHTML = ""; });
    modal.querySelector("#save").addEventListener("click", () => this.saveForm(event));
    modal.querySelector("#delete")?.addEventListener("click", () => this.deleteEvent(event));
    modal.querySelector("input")?.focus();
  }

  async saveForm(event) {
    const form = this.shadowRoot.getElementById("event-form");
    if (!form.reportValidity()) return;
    const data = new FormData(form);
    const rawDays = data.get("proactive_advance_days").trim();
    const proactiveDays = rawDays ? [...new Set(rawDays.split(",").map((value) => Number(value.trim())))].sort((a, b) => b - a) : [];
    if (proactiveDays.some((value) => !Number.isInteger(value) || value < 1 || value > 366)) {
      this.shadowRoot.getElementById("form-error").textContent = "Advance days must be whole numbers from 1 to 366.";
      return;
    }
    const payload = {
      type: event ? "annual_events/update" : "annual_events/create",
      name: data.get("name").trim(), month: Number(data.get("month")), day: Number(data.get("day")),
      year: data.get("year") ? Number(data.get("year")) : null,
      category: data.get("category").trim() || null,
      aliases: data.get("aliases").split(",").map((v) => v.trim()).filter(Boolean),
      icon: data.get("icon").trim() || null, notes: data.get("notes").trim() || null,
      proactive_mode: data.get("proactive_mode"), proactive_advance_days: proactiveDays,
      proactive_day_of: data.has("proactive_day_of"),
      important: data.has("important"), enabled: data.has("enabled"), expose_entity: data.has("expose_entity"),
    };
    if (event) payload.event_id = event.id;
    try { await this.call(payload); this.shadowRoot.getElementById("modal").innerHTML = ""; await this.refreshAfterMutation(); }
    catch (err) { this.shadowRoot.getElementById("form-error").textContent = err.message || "Could not save this event."; }
  }

  async deleteEvent(event) {
    if (!window.confirm(`Delete “${event.name}”? This cannot be undone.`)) return;
    try { await this.call({ type: "annual_events/delete", event_id: event.id }); this.shadowRoot.getElementById("modal").innerHTML = ""; await this.refreshAfterMutation(); }
    catch (err) { this.shadowRoot.getElementById("form-error").textContent = err.message || "Could not delete this event."; }
  }
}

if (!customElements.get("annual-events-panel")) customElements.define("annual-events-panel", AnnualEventsPanel);