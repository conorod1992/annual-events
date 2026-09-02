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
const MONTH_NAMES = Array.from({ length: 12 }, (_, index) =>
  new Intl.DateTimeFormat(undefined, { month: "long" }).format(new Date(2000, index, 1))
);

const escapeHtml = (value) => String(value ?? "")
  .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;").replaceAll("'", "&#039;");

const formatDate = (iso) => {
  if (!iso) return "";
  const [year, month, day] = iso.split("-").map(Number);
  return new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short" })
    .format(new Date(year, month - 1, day));
};

const titleCaseCategory = (value) => String(value || "")
  .replaceAll("_", " ")
  .replace(/\b\w/g, (character) => character.toUpperCase());

const normalizeAdvanceDays = (value) => {
  if (Array.isArray(value)) return value.map(Number).filter(Number.isFinite);
  if (value == null || value === "") return [];
  return String(value).split(",").map((item) => Number(item.trim())).filter(Number.isFinite);
};

const reminderSummary = (days, dayOf) => {
  const normalized = [...new Set(normalizeAdvanceDays(days))].sort((a, b) => b - a);
  const parts = normalized.map((day) => `${day} day${day === 1 ? "" : "s"} before`);
  if (dayOf) parts.push("on the day");
  return parts.length ? parts.join(", ") : "No proactive reminders";
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
    this._dialogKeyHandler = undefined;
    this._lastFocused = undefined;
    this._formDirty = false;
    this._formSaving = false;
  }

  set hass(value) {
    this._hass = value;
    if (this.isConnected && !this._loaded) this.load();
  }

  connectedCallback() {
    this.render();
    if (this._hass && !this._loaded) this.load();
  }

  disconnectedCallback() {
    this._removeDialogKeyHandler();
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

  iconTemplate(icon, className = "event-icon") {
    return icon
      ? `<ha-icon class="${className}" icon="${escapeHtml(icon)}" aria-hidden="true"></ha-icon>`
      : "";
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
    const icon = this.events.find((event) => event.id === item.event_id)?.icon;
    return `<div class="overview-item">
      <div class="overview-name">${this.iconTemplate(icon, "overview-icon")}<div><strong>${escapeHtml(item.name)}</strong><div class="overview-meta">${escapeHtml(titleCaseCategory(item.category || "uncategorized"))}${number}</div></div></div>
      <span>${escapeHtml(when)}</span>
    </div>`;
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
        button:disabled,input:disabled,select:disabled { opacity:.55; cursor:not-allowed; }
        .overview { display:grid; grid-template-columns:1fr 1.4fr; gap:14px; margin-bottom:18px; }
        .overview-card { background:var(--card-background-color,#fff); border-radius:14px; box-shadow:var(--ha-card-box-shadow,0 2px 8px #0001); padding:16px; }
        .overview-list { display:grid; gap:8px; }
        .overview-item { display:flex; justify-content:space-between; align-items:center; gap:14px; padding:8px 0; border-top:1px solid var(--divider-color,#eee); }
        .overview-item:first-child { border-top:0; padding-top:0; }
        .overview-item > span { color:var(--secondary-text-color,#666); font-size:13px; white-space:nowrap; }
        .overview-name { display:flex; align-items:center; gap:9px; min-width:0; }
        .overview-icon,.event-icon { flex:0 0 auto; color:var(--secondary-text-color,#666); }
        .overview-meta,.overview-empty { color:var(--secondary-text-color,#666); font-size:13px; margin-top:3px; }
        .filters { display:grid; grid-template-columns:minmax(220px,2fr) repeat(3,minmax(130px,1fr)); gap:10px; padding:15px; background:var(--card-background-color,#fff); border-radius:14px; box-shadow:var(--ha-card-box-shadow,0 2px 8px #0001); margin-bottom:14px; }
        input,select,textarea { width:100%; padding:10px 11px; border:1px solid var(--divider-color,#ccc); border-radius:9px; color:var(--primary-text-color,#222); background:var(--card-background-color,#fff); font:inherit; }
        label { display:grid; gap:5px; color:var(--secondary-text-color,#666); font-size:13px; }
        .hint { color:var(--secondary-text-color,#666); font-size:12px; line-height:1.45; }
        .check { display:flex; align-items:center; gap:8px; align-self:center; font-size:14px; color:var(--primary-text-color,#222); }
        .check input { width:auto; }
        .list { display:grid; gap:10px; }
        .list-footer { display:flex; justify-content:center; align-items:center; gap:14px; padding:18px 0 4px; color:var(--secondary-text-color,#666); font-size:13px; }
        .event { background:var(--card-background-color,#fff); border-radius:14px; box-shadow:var(--ha-card-box-shadow,0 2px 8px #0001); padding:16px; display:grid; grid-template-columns:minmax(180px,1.5fr) minmax(160px,1fr) auto; gap:15px; align-items:center; }
        .name { font-weight:650; font-size:17px; display:flex; align-items:center; gap:8px; } .star { color:#f9a825; }
        .meta { color:var(--secondary-text-color,#666); font-size:13px; margin-top:5px; }
        .date { font-weight:600; } .days { color:var(--secondary-text-color,#666); font-size:13px; margin-top:3px; }
        .actions { display:flex; align-items:center; gap:12px; } .switches { display:flex; gap:10px; }
        .switch { display:grid; justify-items:center; gap:3px; font-size:11px; color:var(--secondary-text-color,#666); } .switch input { width:18px; height:18px; }
        .status { text-align:center; padding:45px 15px; color:var(--secondary-text-color,#666); } .error { color:var(--error-color,#db4437); }

        .modal-backdrop { position:fixed; inset:0; z-index:10; display:grid; place-items:center; padding:18px; background:#0008; }
        .modal { width:min(680px,100%); max-height:92vh; overflow:auto; background:var(--card-background-color,#fff); border-radius:16px; box-shadow:0 12px 48px #0006; }
        .modal-header { position:sticky; top:0; z-index:2; padding:20px 22px 14px; background:var(--card-background-color,#fff); border-bottom:1px solid var(--divider-color,#e6e6e6); }
        .modal-header h2 { margin:0; }
        .modal-body { padding:18px 22px 4px; }
        .form { display:grid; gap:18px; }
        .form-section { display:grid; grid-template-columns:1fr 1fr; gap:13px; padding:16px; border:1px solid var(--divider-color,#e3e3e3); border-radius:13px; background:var(--secondary-background-color,var(--card-background-color,#fff)); }
        .section-heading { grid-column:1/-1; display:grid; gap:3px; margin-bottom:2px; }
        .section-heading h3 { margin:0; font-size:15px; color:var(--primary-text-color,#222); }
        .section-heading p { margin:0; color:var(--secondary-text-color,#666); font-size:12px; line-height:1.4; }
        .full { grid-column:1/-1; }
        .icon-field { min-height:62px; }
        .native-icon-picker { display:block; width:100%; }
        .settings-list { grid-column:1/-1; display:grid; gap:0; border:1px solid var(--divider-color,#ddd); border-radius:10px; overflow:hidden; }
        .setting-row { display:flex; align-items:center; justify-content:space-between; gap:16px; padding:12px; color:var(--primary-text-color,#222); background:var(--card-background-color,#fff); border-top:1px solid var(--divider-color,#eee); cursor:pointer; }
        .setting-row:first-child { border-top:0; }
        .setting-copy { display:grid; gap:2px; }
        .setting-title { font-size:14px; font-weight:600; }
        .setting-description { color:var(--secondary-text-color,#666); font-size:12px; line-height:1.35; }
        .setting-row input { flex:0 0 auto; width:18px; height:18px; }
        .proactive-custom[hidden] { display:none; }
        .modal-actions { position:sticky; bottom:0; z-index:2; display:flex; align-items:center; gap:10px; padding:14px 22px 18px; margin-top:14px; background:var(--card-background-color,#fff); border-top:1px solid var(--divider-color,#e6e6e6); }
        .modal-actions .spacer { flex:1; }
        .form-error { min-height:18px; padding:0 22px; }
        .saving-label { display:none; }
        .is-saving .save-label { display:none; }
        .is-saving .saving-label { display:inline; }

        @media (max-width:760px) {
          .wrap{padding:15px} header{align-items:center}.subtitle{display:none}.overview{grid-template-columns:1fr}.filters{grid-template-columns:1fr 1fr}.filters .search{grid-column:1/-1}.event{grid-template-columns:1fr auto}.datebox{grid-column:1}.actions{grid-column:2;grid-row:1/3;flex-direction:column}.switches{flex-direction:column}
          .form-section{grid-template-columns:1fr}.full,.section-heading,.settings-list{grid-column:auto}.modal-header{padding:18px 18px 13px}.modal-body{padding:15px 18px 2px}.modal-actions{padding:13px 18px 16px}
        }
        @media (max-width:460px) {
          .filters{grid-template-columns:1fr}.filters .search{grid-column:auto}.event{grid-template-columns:1fr}.actions{grid-column:1;grid-row:auto;flex-direction:row;justify-content:space-between}.switches{flex-direction:row}.overview-item{align-items:flex-start;flex-direction:column;gap:4px}.list-footer{flex-direction:column;gap:8px}
          .modal-backdrop{padding:0}.modal{width:100%;max-height:100vh;height:100vh;border-radius:0}.form-section{padding:13px}.modal-actions{padding-bottom:max(16px,env(safe-area-inset-bottom))}
        }
      </style>
      <div class="wrap">
        <header><div><h1>${TEXT.title}</h1><p class="subtitle">${TEXT.subtitle}</p></div>${this.settings.is_admin ? `<button id="add">＋ ${TEXT.add}</button>` : ""}</header>
        ${!this.loading && !this.error ? this.overviewTemplate() : ""}
        <section class="filters" aria-label="Event filters">
          <label class="search">Search<input id="search" type="search" value="${escapeHtml(this.filters.search)}" placeholder="${TEXT.search}" /></label>
          <label>Category<select id="category"><option value="">All categories</option>${categories.map((c) => `<option value="${escapeHtml(c)}" ${this.filters.category === c ? "selected" : ""}>${escapeHtml(titleCaseCategory(c))}</option>`).join("")}</select></label>
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
    const proactive = event.proactive_mode === "off" ? " · reminders off" : event.proactive_mode === "custom" ? " · custom reminders" : "";
    return `<article class="event" data-id="${event.id}">
      <div><div class="name">${this.iconTemplate(event.icon)}${event.important ? '<span class="star" aria-label="Important">★</span>' : ""}${escapeHtml(event.name)}</div><div class="meta">${escapeHtml(titleCaseCategory(event.category || "uncategorized"))}${event.year ? ` · since ${event.year}` : ""}${proactive}</div></div>
      <div class="datebox"><div class="date">${escapeHtml(formatDate(event.next_occurrence))}</div><div class="days">${event.days_until === 0 ? "Today" : `${event.days_until} day${event.days_until === 1 ? "" : "s"} away`}${number}</div></div>
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
      try {
        await this.call({ type: "annual_events/update", event_id: input.closest("article").dataset.id, [input.dataset.toggle]: input.checked });
        await this.refreshAfterMutation();
      } catch (e) {
        this.error = e.message;
        this.render();
      }
    }));
  }

  monthOptions(selectedMonth) {
    return `<option value="" ${selectedMonth ? "" : "selected"}>Select month</option>${MONTH_NAMES.map((name, index) => {
      const month = index + 1;
      return `<option value="${month}" ${Number(selectedMonth) === month ? "selected" : ""}>${escapeHtml(name)}</option>`;
    }).join("")}`;
  }

  dayOptions(month, selectedDay) {
    if (!month) return '<option value="">Select month first</option>';
    const maximum = new Date(2000, Number(month), 0).getDate();
    return `<option value="" ${selectedDay ? "" : "selected"}>Select day</option>${Array.from({ length: maximum }, (_, index) => {
      const day = index + 1;
      return `<option value="${day}" ${Number(selectedDay) === day ? "selected" : ""}>${day}</option>`;
    }).join("")}`;
  }

  defaultReminderSummary() {
    const days = this.settings.options?.advance_notice_days ?? 7;
    const dayOf = this.settings.options?.emit_day_of !== false;
    return reminderSummary(days, dayOf);
  }

  _removeDialogKeyHandler() {
    if (this._dialogKeyHandler) {
      document.removeEventListener("keydown", this._dialogKeyHandler);
      this._dialogKeyHandler = undefined;
    }
  }

  closeForm({ force = false } = {}) {
    if (!force && this._formDirty && !window.confirm("Discard unsaved changes?")) return false;
    const modal = this.shadowRoot.getElementById("modal");
    if (modal) modal.innerHTML = "";
    this._removeDialogKeyHandler();
    this._formDirty = false;
    this._formSaving = false;
    const previous = this._lastFocused;
    this._lastFocused = undefined;
    previous?.focus?.();
    return true;
  }

  installIconPicker(modal, currentIcon) {
    const host = modal.querySelector("#icon-picker-host");
    if (!host) return;

    const renderFallback = (value = currentIcon) => {
      host.innerHTML = `<label>Icon<input name="icon" placeholder="mdi:calendar-heart" value="${escapeHtml(value || "")}" /></label><span class="hint">Material Design or another Home Assistant icon ID.</span>`;
      host.querySelector("input")?.addEventListener("input", () => { this._formDirty = true; });
    };

    const renderNative = (value = currentIcon) => {
      if (!customElements.get("ha-icon-picker") || !host.isConnected) return false;
      const fallbackValue = host.querySelector('input[name="icon"]')?.value;
      host.innerHTML = "";
      const picker = document.createElement("ha-icon-picker");
      picker.className = "native-icon-picker";
      picker.label = "Icon";
      picker.placeholder = "mdi:calendar-heart";
      picker.required = false;
      picker.value = fallbackValue ?? value ?? "";
      picker.addEventListener("value-changed", () => { this._formDirty = true; });
      host.appendChild(picker);
      const hint = document.createElement("span");
      hint.className = "hint";
      hint.textContent = "Search Home Assistant's available icons.";
      host.appendChild(hint);
      return true;
    };

    if (renderNative()) return;
    renderFallback();

    const timeout = new Promise((resolve) => setTimeout(resolve, 4000));
    Promise.race([customElements.whenDefined("ha-icon-picker"), timeout]).then(() => {
      if (customElements.get("ha-icon-picker") && host.isConnected) renderNative();
    });
  }

  updateDaySelector(modal, selectedDay = null) {
    const month = modal.querySelector('[name="month"]')?.value;
    const day = modal.querySelector('[name="day"]');
    if (!day) return;
    const current = selectedDay ?? day.value;
    day.innerHTML = this.dayOptions(month, current);
    day.disabled = !month;
    if (current && ![...day.options].some((option) => option.value === String(current))) day.value = "";
  }

  openForm(event = null) {
    const modal = this.shadowRoot.getElementById("modal");
    const aliases = event?.aliases?.join(", ") || "";
    const proactiveMode = event?.proactive_mode || "default";
    const proactiveDays = event?.proactive_advance_days?.join(", ") || "";
    const proactiveDayOf = event == null || event.proactive_day_of !== false;
    const categories = [...new Set([...this.settings.categories, ...this.events.map((item) => item.category).filter(Boolean)])].sort();
    this._lastFocused = this.shadowRoot.activeElement;
    this._formDirty = false;
    this._formSaving = false;

    modal.innerHTML = `<div class="modal-backdrop" role="presentation"><section class="modal" role="dialog" aria-modal="true" aria-labelledby="dialog-title">
      <div class="modal-header"><h2 id="dialog-title">${event ? TEXT.edit : TEXT.add}</h2></div>
      <div class="modal-body">
        <form id="event-form" class="form">
          <section class="form-section" aria-labelledby="event-section-title">
            <div class="section-heading"><h3 id="event-section-title">Event</h3><p>The date and identity of this annual event.</p></div>
            <label class="full">Name *<input name="name" required maxlength="120" value="${escapeHtml(event?.name || "")}" autofocus /></label>
            <label>Month *<select name="month" required>${this.monthOptions(event?.month)}</select></label>
            <label>Day *<select name="day" required ${event?.month ? "" : "disabled"}>${this.dayOptions(event?.month, event?.day)}</select></label>
            <label>Category<input name="category" list="event-categories" maxlength="64" value="${escapeHtml(event?.category || "")}" placeholder="e.g. birthday" /><datalist id="event-categories">${categories.map((category) => `<option value="${escapeHtml(category)}">${escapeHtml(titleCaseCategory(category))}</option>`).join("")}</datalist><span class="hint">Choose an existing category or type a new one.</span></label>
            <label>Original year<input name="year" type="number" min="1" max="9999" value="${event?.year || ""}" placeholder="Optional" /><span class="hint">Used to calculate age or anniversary number.</span></label>
          </section>

          <section class="form-section" aria-labelledby="details-section-title">
            <div class="section-heading"><h3 id="details-section-title">Details</h3><p>Optional information that makes events easier to identify and search.</p></div>
            <div id="icon-picker-host" class="icon-field full"></div>
            <label class="full">Aliases<input name="aliases" value="${escapeHtml(aliases)}" placeholder="e.g. Mam, Mum" /><span class="hint">Other names used when searching, separated by commas.</span></label>
            <label class="full">Notes<textarea name="notes" rows="3" placeholder="Anything useful to remember about this event">${escapeHtml(event?.notes || "")}</textarea></label>
          </section>

          <section class="form-section" aria-labelledby="behaviour-section-title">
            <div class="section-heading"><h3 id="behaviour-section-title">Behaviour</h3><p>Control reminders and how this event appears in Home Assistant.</p></div>
            <label class="full">Reminders<select name="proactive_mode">
              <option value="default" ${proactiveMode === "default" ? "selected" : ""}>Use integration defaults</option>
              <option value="custom" ${proactiveMode === "custom" ? "selected" : ""}>Set custom reminder schedule</option>
              <option value="off" ${proactiveMode === "off" ? "selected" : ""}>No proactive reminders</option>
            </select><span id="reminder-summary" class="hint"></span></label>
            <div id="proactive-custom" class="proactive-custom full" ${proactiveMode === "custom" ? "" : "hidden"}>
              <div class="form-section">
                <label class="full">Days before event<input name="proactive_advance_days" value="${escapeHtml(proactiveDays)}" placeholder="30, 7, 1" /><span class="hint">Comma-separated whole numbers. Leave blank for day-of only.</span></label>
                <label class="check full"><input name="proactive_day_of" type="checkbox" ${proactiveDayOf ? "checked" : ""}/> Also remind on the day</label>
              </div>
            </div>
            <div class="settings-list">
              <label class="setting-row"><span class="setting-copy"><span class="setting-title">Important</span><span class="setting-description">Highlight this event and include it in important-event views.</span></span><input name="important" type="checkbox" ${event?.important ? "checked" : ""}/></label>
              <label class="setting-row"><span class="setting-copy"><span class="setting-title">Enabled</span><span class="setting-description">Include this event in calculations, calendars and reminders.</span></span><input name="enabled" type="checkbox" ${event == null || event.enabled ? "checked" : ""}/></label>
              <label class="setting-row"><span class="setting-copy"><span class="setting-title">Create individual sensor</span><span class="setting-description">Create a dedicated sensor entity for this event.</span></span><input name="expose_entity" type="checkbox" ${event?.expose_entity ? "checked" : ""}/></label>
            </div>
          </section>
        </form>
      </div>
      <div id="form-error" class="error form-error" role="alert"></div>
      <div class="modal-actions">
        ${event ? `<button id="delete" class="danger">${TEXT.delete}</button>` : ""}
        <span class="spacer"></span>
        <button id="cancel" class="secondary">${TEXT.cancel}</button>
        <button id="save"><span class="save-label">${TEXT.save}</span><span class="saving-label">Saving…</span></button>
      </div>
    </section></div>`;

    this.installIconPicker(modal, event?.icon || "");
    this.updateDaySelector(modal, event?.day);

    const form = modal.querySelector("#event-form");
    const reminderMode = modal.querySelector('[name="proactive_mode"]');
    const customDays = modal.querySelector('[name="proactive_advance_days"]');
    const customDayOf = modal.querySelector('[name="proactive_day_of"]');
    const summary = modal.querySelector("#reminder-summary");

    const updateReminderSummary = () => {
      if (reminderMode.value === "default") {
        summary.textContent = `Defaults: ${this.defaultReminderSummary()}.`;
      } else if (reminderMode.value === "off") {
        summary.textContent = "This event will not emit proactive reminders.";
      } else {
        summary.textContent = `Custom: ${reminderSummary(customDays.value, customDayOf.checked)}.`;
      }
    };

    reminderMode.addEventListener("change", () => {
      modal.querySelector("#proactive-custom").hidden = reminderMode.value !== "custom";
      updateReminderSummary();
    });
    customDays.addEventListener("input", updateReminderSummary);
    customDayOf.addEventListener("change", updateReminderSummary);
    updateReminderSummary();

    modal.querySelector('[name="month"]').addEventListener("change", () => this.updateDaySelector(modal));
    form.addEventListener("input", () => { this._formDirty = true; });
    form.addEventListener("change", () => { this._formDirty = true; });

    modal.querySelector("#cancel").addEventListener("click", () => this.closeForm());
    modal.querySelector(".modal-backdrop").addEventListener("click", (e) => {
      if (e.target.classList.contains("modal-backdrop")) this.closeForm();
    });
    modal.querySelector("#save").addEventListener("click", () => this.saveForm(event));
    modal.querySelector("#delete")?.addEventListener("click", () => this.deleteEvent(event));

    this._removeDialogKeyHandler();
    this._dialogKeyHandler = (e) => {
      if (e.key === "Escape" && this.shadowRoot.getElementById("event-form")) {
        e.preventDefault();
        this.closeForm();
      }
    };
    document.addEventListener("keydown", this._dialogKeyHandler);
    modal.querySelector('[name="name"]')?.focus();
  }

  validateSpecificDate(data) {
    const yearText = data.get("year");
    if (!yearText) return true;
    const year = Number(yearText);
    const month = Number(data.get("month"));
    const day = Number(data.get("day"));
    const date = new Date(year, month - 1, day);
    return date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day;
  }

  async saveForm(event) {
    if (this._formSaving) return;
    const form = this.shadowRoot.getElementById("event-form");
    if (!form || !form.reportValidity()) return;
    const data = new FormData(form);
    const error = this.shadowRoot.getElementById("form-error");
    error.textContent = "";

    if (!this.validateSpecificDate(data)) {
      error.textContent = "The selected day is not valid in the original year.";
      return;
    }

    const rawDays = String(data.get("proactive_advance_days") || "").trim();
    const proactiveDays = rawDays ? [...new Set(rawDays.split(",").map((value) => Number(value.trim())))].sort((a, b) => b - a) : [];
    if (proactiveDays.some((value) => !Number.isInteger(value) || value < 1 || value > 366)) {
      error.textContent = "Reminder days must be whole numbers from 1 to 366.";
      return;
    }

    const picker = this.shadowRoot.querySelector("#modal ha-icon-picker");
    const icon = picker ? String(picker.value || "").trim() : String(data.get("icon") || "").trim();
    const payload = {
      type: event ? "annual_events/update" : "annual_events/create",
      name: String(data.get("name") || "").trim(),
      month: Number(data.get("month")),
      day: Number(data.get("day")),
      year: data.get("year") ? Number(data.get("year")) : null,
      category: String(data.get("category") || "").trim() || null,
      aliases: String(data.get("aliases") || "").split(",").map((value) => value.trim()).filter(Boolean),
      icon: icon || null,
      notes: String(data.get("notes") || "").trim() || null,
      proactive_mode: data.get("proactive_mode"),
      proactive_advance_days: proactiveDays,
      proactive_day_of: data.has("proactive_day_of"),
      important: data.has("important"),
      enabled: data.has("enabled"),
      expose_entity: data.has("expose_entity"),
    };
    if (event) payload.event_id = event.id;

    const dialog = this.shadowRoot.querySelector("#modal .modal");
    const save = this.shadowRoot.getElementById("save");
    const cancel = this.shadowRoot.getElementById("cancel");
    const deleteButton = this.shadowRoot.getElementById("delete");
    this._formSaving = true;
    dialog?.classList.add("is-saving");
    if (save) save.disabled = true;
    if (cancel) cancel.disabled = true;
    if (deleteButton) deleteButton.disabled = true;

    try {
      await this.call(payload);
      this._formDirty = false;
      this.closeForm({ force: true });
      await this.refreshAfterMutation();
    } catch (err) {
      error.textContent = err?.message || "Could not save this event.";
      this._formSaving = false;
      dialog?.classList.remove("is-saving");
      if (save) save.disabled = false;
      if (cancel) cancel.disabled = false;
      if (deleteButton) deleteButton.disabled = false;
    }
  }

  async deleteEvent(event) {
    if (this._formSaving || !window.confirm(`Delete “${event.name}”? This cannot be undone.`)) return;
    const error = this.shadowRoot.getElementById("form-error");
    const deleteButton = this.shadowRoot.getElementById("delete");
    if (deleteButton) deleteButton.disabled = true;
    try {
      await this.call({ type: "annual_events/delete", event_id: event.id });
      this._formDirty = false;
      this.closeForm({ force: true });
      await this.refreshAfterMutation();
    } catch (err) {
      if (deleteButton) deleteButton.disabled = false;
      error.textContent = err?.message || "Could not delete this event.";
    }
  }
}

if (!customElements.get("annual-events-panel")) customElements.define("annual-events-panel", AnnualEventsPanel);
