(function (global) {
  "use strict";

  const DATA_PATHS = Object.freeze({
    records: ["data/demo/contrast-records.json"],
    coverage: ["data/coverage/ledger.json", "data/coverage.json"],
    standards: ["data/standards/evaluation.json", "data/standards.json"],
    evaluation: ["data/evaluation/report.json", "data/evaluation.json"],
    mcp: ["data/ons/mcp-bindings.json", "data/mcp-selection.json"],
    spatial: ["data/ons/spatial-index.json"],
  });

  const MAX_RESULTS = 30;
  const RETAINED_ALTERNATIVE_LIMIT = 8;
  const ALLOWED_STANDARD_STATES = new Set([
    "aligned",
    "partial",
    "not-evaluated",
    "not-applicable",
  ]);
  const CREDENTIAL_KEYS = new Set([
    "access_token",
    "api_key",
    "apikey",
    "authorization",
    "client_secret",
    "key",
    "password",
    "secret",
    "signature",
    "token",
  ]);

  const state = {
    records: [],
    byId: new Map(),
    visible: [],
    retained: new Set(),
    selectedId: "",
    compareId: "",
    activeTab: "overview",
    coverage: null,
    standards: null,
    evaluation: null,
    mcp: null,
    spatial: null,
  };

  function asArray(value) {
    if (Array.isArray(value)) {
      return value;
    }
    if (value === null || value === undefined || value === "") {
      return [];
    }
    return [value];
  }

  function text(value) {
    if (value === null || value === undefined) {
      return "";
    }
    if (typeof value === "string") {
      return value.trim();
    }
    if (typeof value === "number" || typeof value === "boolean") {
      return String(value);
    }
    if (typeof value === "object") {
      for (const key of ["value", "label", "name", "title", "id"]) {
        if (value[key] !== undefined) {
          return text(value[key]);
        }
      }
    }
    return "";
  }

  function uniqueText(values) {
    const found = new Map();
    for (const value of asArray(values)) {
      const item = text(value);
      if (item && !found.has(item.toLocaleLowerCase("en-GB"))) {
        found.set(item.toLocaleLowerCase("en-GB"), item);
      }
    }
    return [...found.values()].sort((left, right) =>
      left.localeCompare(right, "en-GB", { sensitivity: "base" }),
    );
  }

  function recordId(record) {
    return text(
      record.record_id ||
        record.recordId ||
        record.id ||
        record.sourceRecordId ||
        record.native_id ||
        record.nativeId,
    );
  }

  function normaliseRecord(raw, ordinal) {
    const id = recordId(raw) || `demo-record-${ordinal + 1}`;
    const qualityScore = Number(
      raw.quality_score ??
        raw.quality?.overall ??
        raw.quality_evidence?.score ??
        raw.metadata_evidence_score ??
        0,
    );
    return {
      id,
      nativeId: text(raw.native_id || raw.nativeId || raw.sourceRecordId || raw.dataset_id || id),
      title: text(raw.title || raw.name) || id,
      description: text(raw.notes || raw.description || raw.summary),
      source: text(raw.source_surface || raw.sourceId || raw.source || "ons"),
      recordType: text(raw.record_type || raw.recordKind || raw.type || "Dataset"),
      topics: uniqueText(raw.topics || raw.keywords || raw.tags),
      tags: uniqueText(raw.tags || raw.keywords),
      frequency: text(raw.frequency || raw.releaseFrequency || raw.release_frequency),
      population: text(raw.population_type || raw.population || raw.universe),
      state: text(raw.state || raw.lifecycleState || raw.status || "published"),
      modified: text(raw.metadata_modified || raw.lastUpdated || raw.modified),
      geography: uniqueText(raw.geography || raw.coverage || raw.geographies),
      qualityScore: Number.isFinite(qualityScore) ? Math.max(0, Math.min(1, qualityScore)) : 0,
      alternatives: asArray(raw.alternatives).filter(
        (alternative) => alternative && typeof alternative === "object",
      ),
      raw,
    };
  }

  function tokenise(value) {
    return text(value)
      .toLocaleLowerCase("en-GB")
      .match(/[a-z0-9][a-z0-9'-]*/g) || [];
  }

  function scoreRecord(record, query) {
    const tokens = [...new Set(tokenise(query))];
    if (!tokens.length) {
      return { score: 1, fields: [] };
    }
    const phrase = text(query).toLocaleLowerCase("en-GB");
    const fields = {
      title: record.title.toLocaleLowerCase("en-GB"),
      identifiers: `${record.id} ${record.nativeId}`.toLocaleLowerCase("en-GB"),
      subjects: `${record.topics.join(" ")} ${record.tags.join(" ")}`.toLocaleLowerCase(
        "en-GB",
      ),
      description: record.description.toLocaleLowerCase("en-GB"),
      context: text(record.raw.context_note).toLocaleLowerCase("en-GB"),
    };
    const weights = {
      title: 20,
      identifiers: 8,
      subjects: 7,
      description: 4,
      context: 5,
    };
    let score = 0;
    const matched = [];
    for (const [field, haystack] of Object.entries(fields)) {
      let fieldMatches = 0;
      for (const token of tokens) {
        if (haystack.includes(token)) {
          fieldMatches += 1;
          score += weights[field];
        }
      }
      if (fieldMatches) {
        matched.push(field);
      }
      if (phrase.length > 2 && haystack.includes(phrase)) {
        score += weights[field] * 2;
      }
    }
    const distinctMatchedTokens = tokens.filter((token) =>
      Object.values(fields).some((haystack) => haystack.includes(token)),
    ).length;
    if (distinctMatchedTokens === tokens.length) {
      score += 15;
    }
    return { score, fields: matched };
  }

  function evidenceBand(record) {
    if (record.qualityScore >= 0.8) {
      return "high";
    }
    if (record.qualityScore >= 0.55) {
      return "medium";
    }
    return "low";
  }

  function sourceLabel(value) {
    const labels = {
      "ons-data-api": "ONS Data API",
      nomis: "Nomis",
      "nomis-dataset-definitions": "Nomis",
      "ons-open-geography": "Open Geography",
      "ons-explore-local-statistics": "Explore Local Statistics",
    };
    return labels[value] || value.replaceAll("-", " ");
  }

  function formatValue(value, fallback = "Not evidenced in this snapshot") {
    if (value === null || value === undefined || value === "") {
      return fallback;
    }
    if (Array.isArray(value)) {
      return value.length ? value.map((item) => formatValue(item, "")).filter(Boolean).join(", ") : fallback;
    }
    if (typeof value === "object") {
      const entries = Object.entries(value).filter(
        ([, item]) => item !== null && item !== undefined && item !== "",
      );
      if (!entries.length) {
        return fallback;
      }
      return entries
        .map(([key, item]) => `${humanLabel(key)}: ${formatValue(item, "")}`)
        .join("; ");
    }
    if (typeof value === "boolean") {
      return value ? "Yes" : "No";
    }
    return String(value);
  }

  function humanLabel(value) {
    return text(value)
      .replaceAll("_", " ")
      .replaceAll("-", " ")
      .replace(/([a-z])([A-Z])/g, "$1 $2")
      .replace(/\b\w/g, (letter) => letter.toLocaleUpperCase("en-GB"));
  }

  function safeLink(value) {
    const raw = text(value);
    if (!raw) {
      return "";
    }
    try {
      const url = new URL(raw, global.location?.href || "https://example.invalid/");
      if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) {
        return "";
      }
      for (const key of url.searchParams.keys()) {
        if (CREDENTIAL_KEYS.has(key.toLocaleLowerCase("en-GB"))) {
          return "";
        }
      }
      return url.href;
    } catch (_error) {
      return "";
    }
  }

  function extractRecords(payload) {
    if (Array.isArray(payload)) {
      return payload;
    }
    if (!payload || typeof payload !== "object") {
      return [];
    }
    for (const key of ["records", "items", "results", "datasets"]) {
      if (Array.isArray(payload[key])) {
        return payload[key];
      }
    }
    return [];
  }

  function findNumber(root, keys) {
    const wanted = new Set(keys.map((key) => key.toLocaleLowerCase("en-GB")));
    const queue = [{ value: root, depth: 0 }];
    const seen = new Set();
    while (queue.length) {
      const { value, depth } = queue.shift();
      if (!value || typeof value !== "object" || seen.has(value) || depth > 5) {
        continue;
      }
      seen.add(value);
      for (const [key, child] of Object.entries(value)) {
        const canonical = key.replaceAll("-", "_").toLocaleLowerCase("en-GB");
        if (wanted.has(canonical)) {
          const isNumericValue =
            (typeof child === "number" && Number.isFinite(child)) ||
            (typeof child === "string" && child.trim() !== "" && Number.isFinite(Number(child)));
          if (isNumericValue) {
            const numeric = Number(child);
            return numeric;
          }
        }
        if (child && typeof child === "object") {
          queue.push({ value: child, depth: depth + 1 });
        }
      }
    }
    return null;
  }

  function pathNumber(root, path) {
    let value = root;
    for (const key of path) {
      if (!value || typeof value !== "object") {
        return null;
      }
      value = value[key];
    }
    return (
      (typeof value === "number" && Number.isFinite(value)) ||
      (typeof value === "string" && value.trim() !== "" && Number.isFinite(Number(value)))
    )
      ? Number(value)
      : null;
  }

  function findCollection(root, keys) {
    if (!root || typeof root !== "object") {
      return [];
    }
    for (const key of keys) {
      if (Array.isArray(root[key])) {
        return root[key];
      }
    }
    for (const child of Object.values(root)) {
      if (child && typeof child === "object" && !Array.isArray(child)) {
        const found = findCollection(child, keys);
        if (found.length) {
          return found;
        }
      }
    }
    return [];
  }

  global.OKFONS = Object.freeze({
    normaliseRecord,
    scoreRecord,
    evidenceBand,
    formatValue,
    extractRecords,
  });

  if (typeof document === "undefined") {
    return;
  }

  const dom = {};

  function element(tag, className = "", content = "") {
    const node = document.createElement(tag);
    if (className) {
      node.className = className;
    }
    if (content !== "") {
      node.textContent = content;
    }
    return node;
  }

  function appendText(parent, tag, label, className = "") {
    const node = element(tag, className, label);
    parent.append(node);
    return node;
  }

  function addLink(parent, label, href) {
    const safe = safeLink(href);
    if (!safe) {
      return null;
    }
    const link = element("a", "", label);
    link.href = safe;
    link.rel = "noreferrer";
    parent.append(link);
    return link;
  }

  async function fetchFirst(paths) {
    let lastError = null;
    for (const path of paths) {
      try {
        const response = await fetch(path, {
          headers: { Accept: "application/json" },
          credentials: "same-origin",
        });
        if (!response.ok) {
          throw new Error(`${path} returned HTTP ${response.status}`);
        }
        return await response.json();
      } catch (error) {
        lastError = error;
      }
    }
    throw lastError || new Error("No data path was available");
  }

  async function optionalData(paths) {
    try {
      return await fetchFirst(paths);
    } catch (_error) {
      return null;
    }
  }

  function cacheDom() {
    for (const id of [
      "search-form",
      "search-input",
      "source-filter",
      "type-filter",
      "topic-filter",
      "frequency-filter",
      "evidence-filter",
      "sort-select",
      "clear-filters",
      "reset-search",
      "load-error",
      "results-status",
      "workspace",
      "results-list",
      "selected-source",
      "selected-title",
      "selected-context",
      "source-link",
      "detail-panel",
      "snapshot-status",
      "summary-records",
      "summary-sources",
      "summary-alternatives",
      "summary-omissions",
      "explorer-link",
    ]) {
      dom[id] = document.getElementById(id);
    }
    dom.tabs = [...document.querySelectorAll("[role='tab'][data-tab]")];
    dom.examples = [...document.querySelectorAll("[data-query]")];
  }

  async function initialise() {
    cacheDom();
    setExplorerLink();
    bindEvents();
    const [recordsResult, coverage, standards, evaluation, mcp, spatial] =
      await Promise.all([
        fetchFirst(DATA_PATHS.records).catch((error) => ({ __error: error })),
        optionalData(DATA_PATHS.coverage),
        optionalData(DATA_PATHS.standards),
        optionalData(DATA_PATHS.evaluation),
        optionalData(DATA_PATHS.mcp),
        optionalData(DATA_PATHS.spatial),
      ]);

    if (recordsResult?.__error) {
      dom["load-error"].hidden = false;
      dom["results-status"].textContent =
        "Discovery data is unavailable. The evidence files remain directly accessible.";
      updateSnapshotSummary();
      return;
    }

    state.coverage = coverage;
    state.standards = standards;
    state.evaluation = evaluation;
    state.mcp = mcp;
    state.spatial = spatial;
    state.records = extractRecords(recordsResult).map(normaliseRecord);
    state.byId = new Map(state.records.map((record) => [record.id, record]));
    populateFacets();
    restoreUrlState();
    updateSnapshotSummary();
    applyFilters();
    dom.workspace.hidden = false;
  }

  function setExplorerLink() {
    const descriptor = new URL("okf-explorer.json", global.location.href).href;
    dom["explorer-link"].href =
      `https://chris-page-gov.github.io/okf-explorer/?bundle=${encodeURIComponent(descriptor)}`;
  }

  function bindEvents() {
    dom["search-form"].addEventListener("submit", (event) => {
      event.preventDefault();
      applyFilters();
    });
    dom["search-input"].addEventListener("input", () => {
      global.clearTimeout(bindEvents.searchTimer);
      bindEvents.searchTimer = global.setTimeout(applyFilters, 180);
    });
    for (const id of [
      "source-filter",
      "type-filter",
      "topic-filter",
      "frequency-filter",
      "evidence-filter",
      "sort-select",
    ]) {
      dom[id].addEventListener("change", applyFilters);
    }
    dom["clear-filters"].addEventListener("click", clearFilters);
    dom["reset-search"].addEventListener("click", clearFilters);
    for (const button of dom.examples) {
      button.addEventListener("click", () => {
        dom["search-input"].value = button.dataset.query || "";
        applyFilters();
        dom["search-input"].focus();
      });
    }
    for (const tab of dom.tabs) {
      tab.addEventListener("click", () => activateTab(tab.dataset.tab));
      tab.addEventListener("keydown", handleTabKeys);
    }
  }

  function restoreUrlState() {
    const params = new URLSearchParams(global.location.search);
    const controls = {
      q: "search-input",
      source: "source-filter",
      type: "type-filter",
      topic: "topic-filter",
      frequency: "frequency-filter",
      evidence: "evidence-filter",
      sort: "sort-select",
    };
    for (const [parameter, id] of Object.entries(controls)) {
      const value = params.get(parameter);
      if (value !== null) {
        dom[id].value = value;
      }
    }
    state.selectedId = params.get("record") || "";
    state.compareId = params.get("compare") || "";
    const requestedTab = params.get("tab") || "overview";
    if (dom.tabs.some((tab) => tab.dataset.tab === requestedTab)) {
      state.activeTab = requestedTab;
    }
  }

  function updateUrl() {
    const params = new URLSearchParams();
    const values = {
      q: dom["search-input"].value.trim(),
      source: dom["source-filter"].value,
      type: dom["type-filter"].value,
      topic: dom["topic-filter"].value,
      frequency: dom["frequency-filter"].value,
      evidence: dom["evidence-filter"].value,
      sort: dom["sort-select"].value === "relevance" ? "" : dom["sort-select"].value,
      record: state.selectedId,
      compare: state.compareId,
      tab: state.activeTab === "overview" ? "" : state.activeTab,
    };
    for (const [key, value] of Object.entries(values)) {
      if (value) {
        params.set(key, value);
      }
    }
    const query = params.toString();
    global.history.replaceState(null, "", `${global.location.pathname}${query ? `?${query}` : ""}`);
  }

  function populateSelect(select, values, emptyLabel) {
    const counts = new Map();
    for (const value of values.flat()) {
      const label = text(value);
      if (label) {
        counts.set(label, (counts.get(label) || 0) + 1);
      }
    }
    const selected = select.value;
    select.replaceChildren();
    const empty = element("option", "", emptyLabel);
    empty.value = "";
    select.append(empty);
    const sorted = [...counts].sort(
      (left, right) => right[1] - left[1] || left[0].localeCompare(right[0], "en-GB"),
    );
    for (const [value, count] of sorted.slice(0, 80)) {
      const option = element("option", "", `${sourceOrValue(select.id, value)} (${count})`);
      option.value = value;
      select.append(option);
    }
    if ([...select.options].some((option) => option.value === selected)) {
      select.value = selected;
    }
  }

  function sourceOrValue(selectId, value) {
    return selectId === "source-filter" ? sourceLabel(value) : value;
  }

  function populateFacets() {
    populateSelect(
      dom["source-filter"],
      state.records.map((record) => record.source),
      "All sources",
    );
    populateSelect(
      dom["type-filter"],
      state.records.map((record) => record.recordType),
      "All record types",
    );
    populateSelect(
      dom["topic-filter"],
      state.records.map((record) => record.topics),
      "All subjects",
    );
    populateSelect(
      dom["frequency-filter"],
      state.records.map((record) => record.frequency),
      "All frequencies",
    );
  }

  function passesFacets(record) {
    return (
      (!dom["source-filter"].value || record.source === dom["source-filter"].value) &&
      (!dom["type-filter"].value || record.recordType === dom["type-filter"].value) &&
      (!dom["topic-filter"].value || record.topics.includes(dom["topic-filter"].value)) &&
      (!dom["frequency-filter"].value ||
        record.frequency === dom["frequency-filter"].value) &&
      (!dom["evidence-filter"].value ||
        evidenceBand(record) === dom["evidence-filter"].value)
    );
  }

  function alternativeId(alternative) {
    return text(
      alternative.record_id ||
        alternative.id ||
        alternative.target_record_id ||
        alternative.target,
    );
  }

  function applyFilters() {
    const query = dom["search-input"].value.trim();
    let ranked = state.records
      .filter(passesFacets)
      .map((record) => ({ record, ...scoreRecord(record, query), retained: false }))
      .filter((row) => !query || row.score > 0);
    const sort = dom["sort-select"].value;
    ranked.sort((left, right) => compareRows(left, right, sort));

    state.retained = new Set();
    const shown = ranked.slice(0, MAX_RESULTS);
    const shownIds = new Set(shown.map((row) => row.record.id));
    if (query) {
      for (const anchor of shown.slice(0, 8)) {
        for (const alternative of anchor.record.alternatives) {
          if (state.retained.size >= RETAINED_ALTERNATIVE_LIMIT) {
            break;
          }
          const id = alternativeId(alternative);
          const record = state.byId.get(id);
          if (record && passesFacets(record) && !shownIds.has(id)) {
            shown.push({
              record,
              score: 0,
              fields: [],
              retained: true,
              retainedFor: anchor.record.title,
            });
            shownIds.add(id);
            state.retained.add(id);
          }
        }
      }
    }
    state.visible = shown;

    if (!state.byId.has(state.selectedId) || !shownIds.has(state.selectedId)) {
      state.selectedId = shown[0]?.record.id || "";
      state.compareId = "";
    }
    renderResults(ranked.length);
    renderSelected();
    updateUrl();
  }

  function compareRows(left, right, sort) {
    if (sort === "evidence") {
      return (
        right.record.qualityScore - left.record.qualityScore ||
        left.record.title.localeCompare(right.record.title, "en-GB")
      );
    }
    if (sort === "updated") {
      return (
        right.record.modified.localeCompare(left.record.modified) ||
        left.record.title.localeCompare(right.record.title, "en-GB")
      );
    }
    if (sort === "title") {
      return left.record.title.localeCompare(right.record.title, "en-GB");
    }
    return (
      right.score - left.score ||
      left.record.title.localeCompare(right.record.title, "en-GB")
    );
  }

  function clearFilters() {
    for (const id of [
      "search-input",
      "source-filter",
      "type-filter",
      "topic-filter",
      "frequency-filter",
      "evidence-filter",
    ]) {
      dom[id].value = "";
    }
    dom["sort-select"].value = "relevance";
    state.compareId = "";
    applyFilters();
  }

  function renderResults(matchCount) {
    dom["results-list"].replaceChildren();
    const retainedCount = state.retained.size;
    if (!state.visible.length) {
      dom["results-status"].textContent =
        "No candidates match every search term and facet. Clear a filter or try a broader description.";
      const notice = element("div", "notice");
      appendText(notice, "h3", "No reduced set");
      appendText(
        notice,
        "p",
        "Nothing has been selected automatically. Broaden the query to review possible alternatives.",
      );
      dom["results-list"].append(notice);
      return;
    }
    const shownMatches = state.visible.length - retainedCount;
    dom["results-status"].textContent =
      `${formatInteger(matchCount)} matching candidate${matchCount === 1 ? "" : "s"}; ` +
      `${formatInteger(retainedCount)} close alternative${retainedCount === 1 ? "" : "s"} ` +
      `retained. Showing ${formatInteger(shownMatches + retainedCount)}.`;

    for (const row of state.visible) {
      const record = row.record;
      const card = element("article", "result-card");
      if (record.id === state.selectedId) {
        card.classList.add("is-selected");
      } else if (row.retained) {
        card.classList.add("is-retained");
      }
      const button = element("button");
      button.type = "button";
      button.dataset.selectRecord = record.id;
      if (record.id === state.selectedId) {
        button.setAttribute("aria-current", "true");
      }
      const badges = element("div", "badge-row");
      badges.append(element("span", "badge", sourceLabel(record.source)));
      if (row.retained) {
        badges.append(element("span", "badge badge-alt", "Close alternative retained"));
      } else if (record.alternatives.length) {
        badges.append(
          element(
            "span",
            "badge badge-alt",
            `${record.alternatives.length} alternative${record.alternatives.length === 1 ? "" : "s"}`,
          ),
        );
      }
      button.append(badges);
      appendText(button, "h4", record.title);
      if (record.description) {
        appendText(button, "p", shorten(record.description, 180));
      }
      const meta = element("div", "result-meta");
      meta.append(element("span", "", record.recordType));
      if (record.frequency) {
        meta.append(element("span", "", record.frequency));
      }
      meta.append(
        element(
          "span",
          "",
          `${Math.round(record.qualityScore * 100)}% metadata evidence`,
        ),
      );
      button.append(meta);
      if (row.retained) {
        appendText(
          button,
          "div",
          `Retained because it is a documented alternative to ${row.retainedFor}.`,
          "match-reason",
        );
      } else if (row.fields.length) {
        appendText(
          button,
          "div",
          `Matched in ${row.fields.map(humanLabel).join(", ")}.`,
          "match-reason",
        );
      }
      button.addEventListener("click", () => selectRecord(record.id));
      card.append(button);
      dom["results-list"].append(card);
    }
  }

  function selectRecord(id) {
    state.selectedId = id;
    state.compareId = "";
    renderResults(
      state.records.filter(passesFacets).filter((record) => {
        const query = dom["search-input"].value.trim();
        return !query || scoreRecord(record, query).score > 0;
      }).length,
    );
    renderSelected();
    updateUrl();
  }

  function selectedRecord() {
    return state.byId.get(state.selectedId) || null;
  }

  function renderSelected() {
    const record = selectedRecord();
    for (const tab of dom.tabs) {
      tab.setAttribute(
        "aria-selected",
        tab.dataset.tab === state.activeTab ? "true" : "false",
      );
    }
    dom["detail-panel"].setAttribute("aria-labelledby", `tab-${state.activeTab}`);
    if (!record) {
      dom["selected-source"].textContent = "No candidate selected";
      dom["selected-title"].textContent = "Broaden the search to continue";
      dom["selected-context"].textContent =
        "The bundle will not silently choose a dataset when the reduced set is empty.";
      dom["source-link"].hidden = true;
      dom["detail-panel"].replaceChildren();
      return;
    }
    dom["selected-source"].textContent =
      `${sourceLabel(record.source)} · ${record.recordType}`;
    dom["selected-title"].textContent = record.title;
    dom["selected-context"].textContent =
      text(record.raw.context_note) ||
      (record.alternatives.length
        ? "Review the documented alternatives before treating this as the exact dataset."
        : "No close alternative is evidenced in this bounded snapshot.");
    const official = safeLink(record.raw.url || record.raw.documentation);
    dom["source-link"].hidden = !official;
    if (official) {
      dom["source-link"].href = official;
      dom["source-link"].rel = "noreferrer";
    }
    renderActiveTab(record);
  }

  function activateTab(tabName) {
    state.activeTab = tabName;
    renderSelected();
    updateUrl();
  }

  function handleTabKeys(event) {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
      return;
    }
    event.preventDefault();
    const current = dom.tabs.indexOf(event.currentTarget);
    let target = current;
    if (event.key === "ArrowLeft") {
      target = (current - 1 + dom.tabs.length) % dom.tabs.length;
    } else if (event.key === "ArrowRight") {
      target = (current + 1) % dom.tabs.length;
    } else if (event.key === "Home") {
      target = 0;
    } else if (event.key === "End") {
      target = dom.tabs.length - 1;
    }
    dom.tabs[target].focus();
    activateTab(dom.tabs[target].dataset.tab);
  }

  function renderActiveTab(record) {
    dom["detail-panel"].replaceChildren();
    const renderers = {
      overview: renderOverview,
      compare: renderCompare,
      quality: renderQuality,
      production: renderProduction,
      versions: renderVersions,
      dimensions: renderDimensions,
      geography: renderGeography,
      mcp: renderMcp,
      standards: renderStandards,
    };
    (renderers[state.activeTab] || renderOverview)(record, dom["detail-panel"]);
  }

  function addDecisionGrid(parent, rows) {
    const list = element("dl", "decision-grid");
    for (const [label, value] of rows) {
      const wrapper = element("div");
      appendText(wrapper, "dt", label);
      appendText(wrapper, "dd", formatValue(value));
      list.append(wrapper);
    }
    parent.append(list);
  }

  function renderOverview(record, panel) {
    appendText(panel, "h4", "Decision signature");
    appendText(
      panel,
      "p",
      record.description || "No source description is present in this snapshot.",
      "lead",
    );
    const raw = record.raw;
    addDecisionGrid(panel, [
      ["Native identifier", record.nativeId],
      ["Population or universe", record.population || raw.population_scope],
      ["Measure", raw.measure || raw.measured_concept || raw.statistical?.measure],
      ["Unit", raw.unit_of_measure || raw.unitOfMeasure || raw.unit],
      ["Geography", record.geography],
      ["Reference period", raw.time_coverage || raw.reference_period],
      ["Frequency", record.frequency],
      ["Release state", record.state],
      ["Edition / version", editionVersion(raw)],
    ]);
    const context = element(
      "div",
      record.alternatives.length ? "notice notice-warning" : "notice",
    );
    appendText(
      context,
      "h4",
      record.alternatives.length
        ? "Do not settle on the title alone"
        : "No close alternative evidenced",
    );
    appendText(
      context,
      "p",
      record.alternatives.length
        ? `${record.alternatives.length} similar record${record.alternatives.length === 1 ? " is" : "s are"} retained. Compare population, measure, geography, period and method before selection.`
        : "The current metadata did not identify a close alternative. This is not proof that none exists.",
    );
    panel.append(context);
  }

  function renderCompare(record, panel) {
    appendText(panel, "h4", "Alternatives a careful user should consider");
    if (!record.alternatives.length) {
      const notice = element("div", "notice");
      appendText(notice, "p", "No evidence-backed alternative is present in this demo record.");
      panel.append(notice);
      return;
    }
    const list = element("div", "alternative-list");
    for (const alternative of record.alternatives) {
      const row = element("article", "alternative");
      const content = element("div");
      appendText(content, "h5", text(alternative.title) || alternativeId(alternative));
      appendText(
        content,
        "p",
        alternativeSummary(alternative),
      );
      const badges = element("div", "badge-row");
      badges.append(
        element(
          "span",
          "badge",
          humanLabel(alternative.relationship_type || "alternative"),
        ),
      );
      if (Number.isFinite(Number(alternative.similarity))) {
        badges.append(
          element(
            "span",
            "badge",
            `${Math.round(Number(alternative.similarity) * 100)}% metadata similarity`,
          ),
        );
      }
      content.append(badges);
      const button = element("button", "button button-secondary button-small", "Compare");
      button.type = "button";
      button.addEventListener("click", () => {
        state.compareId = alternativeId(alternative);
        renderActiveTab(record);
        updateUrl();
      });
      row.append(content, button);
      list.append(row);
    }
    panel.append(list);
    const chosen = record.alternatives.find(
      (alternative) => alternativeId(alternative) === state.compareId,
    );
    if (chosen) {
      renderComparisonTable(record, chosen, panel);
    }
  }

  function alternativeSummary(alternative) {
    const differences = asArray(alternative.differences);
    if (differences.length) {
      return `Material differences recorded in ${differences
        .slice(0, 4)
        .map((difference) => humanLabel(difference.field))
        .join(", ")}.`;
    }
    if (alternative.not_enough_evidence) {
      return "The metadata identifies similarity but does not yet evidence a material distinction.";
    }
    const shared = uniqueText(alternative.shared_terms);
    return shared.length
      ? `Shared terms: ${shared.slice(0, 6).join(", ")}.`
      : "Review the source metadata before treating these records as equivalent.";
  }

  function renderComparisonTable(record, alternative, panel) {
    appendText(panel, "h4", `Side-by-side: ${record.title} and ${text(alternative.title)}`);
    const tableWrap = element("div", "table-wrap");
    const table = element("table");
    const caption = element(
      "caption",
      "sr-only",
      "Material metadata differences between the selected dataset and alternative",
    );
    const head = document.createElement("thead");
    const headRow = document.createElement("tr");
    for (const value of ["Decision field", record.title, text(alternative.title)]) {
      appendText(headRow, "th", value);
    }
    head.append(headRow);
    const body = document.createElement("tbody");
    let differences = asArray(alternative.differences);
    const other = state.byId.get(alternativeId(alternative));
    if (!differences.length && other) {
      differences = standardDifferences(record, other);
    }
    if (!differences.length) {
      differences = [
        {
          field: "Evidence",
          selected: "Insufficient structured contrast metadata",
          alternative: "Insufficient structured contrast metadata",
        },
      ];
    }
    for (const difference of differences) {
      const row = document.createElement("tr");
      appendText(row, "th", humanLabel(difference.field));
      appendText(row, "td", formatValue(difference.selected));
      appendText(row, "td", formatValue(difference.alternative));
      body.append(row);
    }
    table.append(caption, head, body);
    tableWrap.append(table);
    panel.append(tableWrap);
    if (alternative.not_enough_evidence) {
      const warning = element("div", "notice notice-warning");
      appendText(
        warning,
        "p",
        "The source metadata is not sufficient to assert equivalence or a stronger relationship.",
      );
      panel.append(warning);
    }
  }

  function standardDifferences(left, right) {
    const values = [
      ["source surface", sourceLabel(left.source), sourceLabel(right.source)],
      ["record type", left.recordType, right.recordType],
      ["population", left.population, right.population],
      ["frequency", left.frequency, right.frequency],
      ["geography", left.geography, right.geography],
      ["release state", left.state, right.state],
      ["last updated", left.modified, right.modified],
      ["edition / version", editionVersion(left.raw), editionVersion(right.raw)],
    ];
    return values
      .filter(([, selected, alternative]) => formatValue(selected, "") !== formatValue(alternative, ""))
      .map(([field, selected, alternative]) => ({ field, selected, alternative }));
  }

  function renderQuality(record, panel) {
    const warning = element("div", "notice notice-warning");
    appendText(warning, "h4", "Metadata evidence is not statistical accuracy");
    appendText(
      warning,
      "p",
      "Presence and consistency of quality metadata can be evaluated here. Observation values, calculations and fitness for a particular use have not been validated.",
    );
    panel.append(warning);
    appendText(
      panel,
      "h4",
      `${Math.round(record.qualityScore * 100)}% metadata evidence availability`,
    );
    const evidence =
      record.raw.quality_evidence?.evidence ||
      record.raw.qualityEvidence?.evidence ||
      deriveEvidence(record);
    const grid = element("div", "evidence-grid");
    for (const [key, value] of Object.entries(evidence)) {
      const item = element("div", "evidence-item");
      appendText(item, "span", humanLabel(key));
      appendText(
        item,
        "span",
        value ? "Present" : "Not evidenced",
        `evidence-state ${value ? "is-present" : "is-missing"}`,
      );
      grid.append(item);
    }
    panel.append(grid);
    renderEvidenceLinks(
      panel,
      "Quality and methodology information",
      record.raw.quality_links ||
        record.raw.qualityMethodologyInformation ||
        record.raw.qmi,
    );
    renderEvaluationSummary(panel);
  }

  function deriveEvidence(record) {
    const raw = record.raw;
    return {
      identity: Boolean(record.id && record.nativeId),
      description: Boolean(record.description),
      publisher: Boolean(raw.publisher || raw.publisher_title),
      release_or_modified: Boolean(record.modified),
      frequency: Boolean(record.frequency),
      population: Boolean(record.population),
      geography: Boolean(record.geography.length || raw.spatial),
      methodology: Boolean(asArray(raw.methodology_links || raw.methodologies).length),
      quality_documentation: Boolean(
        asArray(raw.quality_links || raw.qualityMethodologyInformation).length,
      ),
      provenance: Boolean(raw.provenance),
    };
  }

  function renderEvaluationSummary(panel) {
    if (!state.evaluation) {
      return;
    }
    const metrics = [
      ["Recall at 5", pathNumber(state.evaluation, ["metrics", "recall_at_k", "5"])],
      ["Primary MRR", findNumber(state.evaluation, ["primary_mrr"])],
      [
        "Alternative exposure",
        findNumber(state.evaluation, ["alternative_exposure_coverage"]),
      ],
      ["Contrast coverage", findNumber(state.evaluation, ["contrast_coverage"])],
    ].filter(([, value]) => value !== null);
    if (!metrics.length) {
      return;
    }
    appendText(panel, "h4", "Discovery evaluation snapshot");
    addDecisionGrid(
      panel,
      metrics.map(([label, value]) => [label, formatRatio(value)]),
    );
    const note = element("p", "", "");
    note.append("See the ");
    const link = element("a", "", "complete evaluation report");
    link.href = "data/evaluation/report.json";
    note.append(link, " for denominators and per-query evidence.");
    panel.append(note);
  }

  function renderProduction(record, panel) {
    appendText(panel, "h4", "Production and catalogue provenance");
    renderEvidenceLinks(
      panel,
      "Published methodology",
      record.raw.methodology_links || record.raw.methodologies,
    );
    const provenance = record.raw.provenance || {};
    addDecisionGrid(panel, [
      [
        "Statistical producer",
        record.raw.statistical_producer || "Not evidenced in this metadata record",
      ],
      [
        "Catalogue publisher / metadata service",
        record.raw.publisher_title || record.raw.publisher,
      ],
      ["Provider agency ID", record.raw.agency_id],
      ["Content source code", record.raw.content_source],
      ["Native publisher reference", record.raw.publisher_uri],
      ["Dataset mnemonic", record.raw.mnemonic],
      ["Portal owner", record.raw.portal_owner],
      ["Source organisation", record.raw.source_organisation],
      ["Source surface", sourceLabel(record.source)],
      ["Source adapter", provenance.source_adapter || record.raw.source_adapter],
      ["Retrieved", provenance.retrieved_at || record.raw.retrievedAt],
      ["Source modified", record.modified],
      ["First released", record.raw.first_released],
      ["Snapshot", provenance.snapshot_id || record.raw.snapshot_id],
      ["Source digest", provenance.source_sha256 || record.raw.source_sha256],
      ["Production process", record.raw.production_process || record.raw.gsbpm_phase],
      ["Collection mode", record.raw.collection_mode],
    ]);
    if (!asArray(record.raw.methodology_links || record.raw.methodologies).length) {
      const missing = element("div", "notice notice-warning");
      appendText(
        missing,
        "p",
        "A methodology link is not evidenced in this record. The bundle reports the gap rather than inferring a production method.",
      );
      panel.append(missing);
    }
  }

  function renderVersions(record, panel) {
    appendText(panel, "h4", "Version and revision evidence");
    const versions = asArray(record.raw.versions || record.raw.version_chain);
    const timeline = element("ol", "timeline");
    if (versions.length) {
      for (const version of versions) {
        const item = element("li");
        appendText(
          item,
          "strong",
          formatValue(version.version || version.id || version.label),
        );
        appendText(
          item,
          "p",
          formatValue(version.release_date || version.modified || version.notes),
        );
        timeline.append(item);
      }
    } else {
      const item = element("li");
      appendText(
        item,
        "strong",
        editionVersion(record.raw) || "Current catalogue record",
      );
      appendText(
        item,
        "p",
        record.modified
          ? `Source metadata modified ${record.modified}.`
          : "No source-modified date is evidenced.",
      );
      timeline.append(item);
    }
    panel.append(timeline);
    addDecisionGrid(panel, [
      ["Edition", record.raw.latest_edition || record.raw.edition],
      ["Version", record.raw.latest_version || record.raw.version],
      ["Release state", record.state],
      ["Revision status", record.raw.revision_status],
      ["Next release", record.raw.next_release || record.raw.nextRelease],
      ["First released", record.raw.first_released],
    ]);
    const note = element("div", "notice");
    appendText(
      note,
      "p",
      versions.length
        ? "Version relationships are source-backed and keep native identifiers."
        : "The bounded demo record does not contain a complete version chain; no history has been inferred.",
    );
    panel.append(note);
  }

  function renderDimensions(record, panel) {
    appendText(panel, "h4", "Dimensions and valid-selection evidence");
    const dimensions = asArray(record.raw.dimensions || record.raw.components);
    if (dimensions.length) {
      const tableWrap = element("div", "table-wrap");
      const table = element("table");
      const head = document.createElement("thead");
      const row = document.createElement("tr");
      for (const value of ["Dimension", "Code list", "Options / constraint", "Required"]) {
        appendText(row, "th", value);
      }
      head.append(row);
      const body = document.createElement("tbody");
      for (const dimension of dimensions) {
        const data = typeof dimension === "object" ? dimension : { name: dimension };
        const bodyRow = document.createElement("tr");
        appendText(
          bodyRow,
          "th",
          text(data.name || data.id || data.concept || data.dimension || data.kind),
        );
        appendText(bodyRow, "td", formatValue(data.codeList || data.codelist));
        appendText(
          bodyRow,
          "td",
          formatValue(
            data.option_count ||
              data.optionCount ||
              data.allowed_values ||
              data.constraint,
          ),
        );
        appendText(bodyRow, "td", formatValue(data.required));
        body.append(bodyRow);
      }
      table.append(head, body);
      tableWrap.append(table);
      panel.append(tableWrap);
    } else {
      const missing = element("div", "notice notice-warning");
      appendText(
        missing,
        "p",
        "Dimension definitions are not present in this bounded record. MCP execution must remain incomplete until the exact version is inspected.",
      );
      panel.append(missing);
    }
    const selection = record.raw.selection || {};
    addDecisionGrid(panel, [
      ["Selection tool", selection.tool],
      ["Query tool", selection.query_tool],
      ["Selection complete", selection.complete],
      ["Why incomplete", selection.reason],
    ]);
    appendText(
      panel,
      "p",
      "Option identifiers are preserved; observation combinations are never materialised in this bundle.",
    );
  }

  function spatialEntry(record) {
    const rows = findCollection(state.spatial, ["profiles", "records", "items", "entries"]);
    return (
      rows.find((item) => {
        const id = recordId(item);
        return id === record.id || id === record.nativeId;
      }) || null
    );
  }

  function portalBbox(extent) {
    const points = [];
    function visit(value) {
      if (!Array.isArray(value)) {
        return;
      }
      if (
        value.length >= 2 &&
        Number.isFinite(Number(value[0])) &&
        Number.isFinite(Number(value[1]))
      ) {
        points.push([Number(value[0]), Number(value[1])]);
        return;
      }
      for (const child of value) {
        visit(child);
      }
    }
    visit(extent?.coordinates);
    if (
      !points.length ||
      points.some(([longitude, latitude]) => Math.abs(longitude) > 180 || Math.abs(latitude) > 90)
    ) {
      return [];
    }
    return [
      Math.min(...points.map(([longitude]) => longitude)),
      Math.min(...points.map(([, latitude]) => latitude)),
      Math.max(...points.map(([longitude]) => longitude)),
      Math.max(...points.map(([, latitude]) => latitude)),
    ];
  }

  function renderGeography(record, panel) {
    appendText(panel, "h4", "Geographic scope and reference system");
    const indexed = spatialEntry(record) || {};
    const spatial =
      (record.raw.spatial && Object.keys(record.raw.spatial).length
        ? record.raw.spatial
        : null) ||
      record.raw.spatialEnvelope ||
      indexed.spatial ||
      indexed;
    const bboxCandidates = [
      spatial?.bbox,
      spatial?.bounding_box,
      record.raw.bbox,
      indexed.bbox,
      portalBbox(record.raw.portal_extent),
    ];
    let bbox = [];
    for (const candidate of bboxCandidates) {
      const values = asArray(candidate).map(Number).filter(Number.isFinite);
      if (values.length >= 4) {
        bbox = values.slice(0, 4);
        break;
      }
    }
    const layout = element("div", "geography-layout");
    const visual = element("div");
    if (bbox.length === 4) {
      const diagram = element("div", "extent-diagram");
      diagram.setAttribute(
        "aria-label",
        `Extent diagram: west ${bbox[0]}, south ${bbox[1]}, east ${bbox[2]}, north ${bbox[3]}`,
      );
      diagram.append(
        element("span", "north", `N ${bbox[3]}`),
        element("span", "south", `S ${bbox[1]}`),
        element("span", "west", `W ${bbox[0]}`),
        element("span", "east", `E ${bbox[2]}`),
      );
      visual.append(diagram);
      appendText(
        visual,
        "p",
        "Extent diagram only — not a boundary map. The table provides the same information.",
        "extent-caption",
      );
    } else {
      const notice = element("div", "notice");
      appendText(notice, "p", "No coordinate extent is evidenced in this record.");
      visual.append(notice);
    }
    const textual = element("div");
    appendText(textual, "h5", "Text alternative to the extent diagram");
    addDecisionGrid(textual, [
      ["Named coverage", record.geography],
      ["West", bbox[0]],
      ["South", bbox[1]],
      ["East", bbox[2]],
      ["North", bbox[3]],
      [
        "Source spatial reference",
        spatial?.crs ||
          record.raw.spatial_reference ||
          indexed.source_spatial_reference ||
          indexed.sourceSpatialReference ||
          indexed.crs,
      ],
      ["Extent evidence", indexed.bbox_evidence || indexed.bboxEvidence],
      ["Geography code family", record.raw.geography_code_family || indexed.code_family],
      ["Reference vintage", record.raw.geography_vintage || indexed.vintage],
      ["Boundary variant", record.raw.boundary_variant || indexed.boundary_variant],
    ]);
    layout.append(visual, textual);
    panel.append(layout);
    const note = element("div", "notice");
    appendText(
      note,
      "p",
      "No external map or API key is used. A spatial envelope helps discovery but does not prove that a dataset is available for every place inside it.",
    );
    panel.append(note);
  }

  function findBinding(record) {
    const rows = findCollection(state.mcp, ["bindings", "records", "items", "entries"]);
    return (
      rows.find((item) => {
        const id = recordId(item);
        const native = text(item.native_id || item.nativeId || item.dataset);
        return id === record.id || id === record.nativeId || native === record.nativeId;
      }) || null
    );
  }

  function selectionPlan(record) {
    const binding = findBinding(record) || {};
    const selection = {
      ...(binding.selection || binding),
      ...(record.raw.selection || {}),
    };
    const structurallyComplete = Boolean(selection.complete);
    const inspectionTool = selection.inspection_tool || selection.tool || null;
    const queryTool = selection.query_tool || (structurallyComplete ? selection.tool : null);
    const tool = structurallyComplete
      ? queryTool
      : inspectionTool;
    const directMetadataUrl = safeLink(selection.direct_metadata_url);
    const available =
      selection.mcp_available !== false &&
      Boolean(queryTool || inspectionTool || directMetadataUrl);
    const complete = structurallyComplete && available;
    return {
      schema: "okf-ons-selection-plan.v1",
      source: record.source,
      record_id: record.id,
      tool,
      inspection_tool: inspectionTool,
      query_tool: queryTool,
      next_step: complete
        ? "query"
        : directMetadataUrl
          ? "inspect-sdmx-structure-and-configure"
          : available
            ? "inspect-and-configure"
            : "binding-planned",
      arguments: selection.arguments || { dataset: record.nativeId },
      direct_metadata_url: directMetadataUrl,
      mcp_available: available,
      binding_status: selection.binding_status || (available ? "available" : "planned"),
      validation: {
        complete,
        unknown_dimensions: asArray(selection.unknown_dimensions),
        invalid_options: asArray(selection.invalid_options),
        reason: complete
          ? "The metadata binding is complete for this read-only operation."
          : selection.reason ||
            "Inspect this version's dimensions and valid options before execution.",
      },
    };
  }

  function renderMcp(record, panel) {
    appendText(panel, "h4", "Read-only MCP selection plan");
    const plan = selectionPlan(record);
    const notice = element("div", "notice");
    appendText(
      notice,
      "p",
      plan.mcp_available
        ? "GitHub Pages does not call upstream APIs or MCP and never requests an API key. Copy this metadata-derived plan to a trusted live-data service for validation and authorisation."
        : "GitHub Pages does not call upstream APIs or MCP. This record preserves a planned-binding gap because no reviewed live execution binding is published for this source surface.",
    );
    panel.append(notice);
    const copyRow = element("div", "copy-row");
    appendText(
      copyRow,
      "strong",
      !plan.mcp_available
        ? "MCP binding planned"
        : plan.validation.complete
          ? "Structurally complete"
          : "More selections required",
    );
    const copy = element("button", "button button-secondary button-small", "Copy plan");
    copy.type = "button";
    copy.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(JSON.stringify(plan, null, 2));
        copy.textContent = "Copied";
      } catch (_error) {
        copy.textContent = "Copy unavailable";
      }
    });
    copyRow.append(copy);
    const block = element("div", "code-block");
    const pre = document.createElement("pre");
    const code = document.createElement("code");
    code.textContent = JSON.stringify(plan, null, 2);
    pre.append(code);
    block.append(pre);
    panel.append(copyRow, block);
    const rawLink = element("p");
    rawLink.append("Inspect all ");
    const link = element("a", "", "generated MCP bindings");
    link.href = "data/ons/mcp-bindings.json";
    rawLink.append(link, ".");
    panel.append(rawLink);
  }

  function renderStandards(record, panel) {
    const warning = element("div", "notice notice-warning");
    appendText(warning, "h4", "Alignment is not certification");
    appendText(
      warning,
      "p",
      "Every claim is limited to aligned, partial, not-evaluated or not-applicable and should carry source evidence. Missing evidence is not rendered as non-compliance.",
    );
    panel.append(warning);
    const standards =
      record.raw.standards_evidence ||
      record.raw.standardsEvidence ||
      record.raw.standards ||
      {};
    const list = element("div", "standards-list");
    for (const [identifier, rawClaim] of Object.entries(standards)) {
      if (identifier === "schema" || identifier === "claims_are_alignment_not_certification") {
        continue;
      }
      const claim =
        rawClaim && typeof rawClaim === "object" ? rawClaim : { status: "not-evaluated" };
      const proposed = text(claim.status).toLocaleLowerCase("en-GB");
      const status = ALLOWED_STANDARD_STATES.has(proposed)
        ? proposed
        : "not-evaluated";
      const row = element("div", "standard-row");
      const heading = element("div");
      heading.append(element("strong", "", humanLabel(identifier)));
      heading.append(
        element("span", `standard-status ${status}`, humanLabel(status)),
      );
      appendText(
        row,
        "div",
        formatValue(claim.evidence || claim.notes || claim.evidenceUrl),
      );
      row.prepend(heading);
      list.append(row);
    }
    if (!list.children.length) {
      appendText(
        list,
        "p",
        "No record-level standards claims are present in this bounded demo record.",
      );
    }
    panel.append(list);
    if (state.standards) {
      const assessed = findNumber(state.standards, [
        "assessed_records",
        "records_assessed",
        "record_count",
      ]);
      const summary = element("div", "notice");
      appendText(
        summary,
        "p",
        assessed === null
          ? "The bundle-level standards evaluation is available as machine-readable evidence."
          : `${formatInteger(assessed)} records are represented in the bundle-level standards evaluation.`,
      );
      const link = element("a", "", "Open the standards evaluation");
      link.href = "data/standards/evaluation.json";
      summary.append(link);
      panel.append(summary);
    }
  }

  function renderEvidenceLinks(panel, heading, values) {
    const rows = asArray(values);
    if (!rows.length) {
      return;
    }
    appendText(panel, "h4", heading);
    const list = element("ul", "link-list");
    for (const value of rows) {
      const href = safeLink(
        typeof value === "object" ? value.href || value.url || value.id : value,
      );
      if (!href) {
        continue;
      }
      const item = element("li");
      addLink(
        item,
        text(typeof value === "object" ? value.title || value.label : "") ||
          "Official evidence",
        href,
      );
      list.append(item);
    }
    if (list.children.length) {
      panel.append(list);
    }
  }

  function editionVersion(raw) {
    const edition = text(raw.latest_edition || raw.edition);
    const version = text(raw.latest_version || raw.version);
    if (edition && version) {
      return `${edition} · version ${version}`;
    }
    return edition || (version ? `Version ${version}` : "");
  }

  function formatInteger(value) {
    return new Intl.NumberFormat("en-GB").format(Number(value) || 0);
  }

  function formatRatio(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) {
      return "Not reported";
    }
    return `${Math.round((number <= 1 ? number * 100 : number) * 10) / 10}%`;
  }

  function shorten(value, maximum) {
    const source = text(value);
    return source.length <= maximum ? source : `${source.slice(0, maximum - 1).trim()}…`;
  }

  function updateSnapshotSummary() {
    const omissions = findNumber(state.coverage, [
      "unexplained_omissions",
      "unexplainedomissions",
    ]);
    const sourceCount =
      findNumber(state.coverage, ["source_count", "sources"]) ??
      new Set(state.records.map((record) => record.source)).size;
    const alternatives = state.records.filter((record) => record.alternatives.length).length;
    dom["summary-records"].textContent = formatInteger(state.records.length);
    dom["summary-sources"].textContent = formatInteger(sourceCount);
    dom["summary-alternatives"].textContent = formatInteger(alternatives);
    dom["summary-omissions"].textContent =
      omissions === null ? "Not yet reported" : formatInteger(omissions);
    dom["snapshot-status"].classList.remove("is-complete", "is-partial");
    if (omissions === 0 && state.records.length) {
      dom["snapshot-status"].textContent =
        "Coverage ledger reports zero unexplained omissions for its stated scope.";
      dom["snapshot-status"].classList.add("is-complete");
    } else if (omissions !== null) {
      dom["snapshot-status"].textContent =
        `${formatInteger(omissions)} unexplained omission${omissions === 1 ? "" : "s"} remain. No “all ONS” claim is made.`;
      dom["snapshot-status"].classList.add("is-partial");
    } else {
      dom["snapshot-status"].textContent =
        "Coverage denominator unavailable in this build. No “all ONS” claim is made.";
      dom["snapshot-status"].classList.add("is-partial");
    }
  }

  initialise();
})(globalThis);
