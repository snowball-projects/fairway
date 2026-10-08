import {
  buildModel,
  selectCounties,
  selectRecords,
  summarize,
  located,
  project,
  regions,
  parseProgress,
  facilityIdentity,
  addedFacilities,
  parseAdditions,
} from "./model.mjs";
import { watchSnapshots } from "./refresh.mjs";

const $ = (id) => document.getElementById(id);
const number = (value) => value.toLocaleString("en-US");
const ns = "http://www.w3.org/2000/svg";
let model,
  catalog,
  boundaries,
  progress = null,
  additions = null,
  selectedCounty = null,
  selectedFacility = null,
  countyLimit = 80,
  facilityLimit = 20;
let filteredCounties = [],
  filteredRecords = [],
  detailRecords = [];
const countyPaths = new Map();
let freshIdentities = new Set(),
  freshTimer,
  lastAdded = 0;

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function metric(value, label, note) {
  const node = element("div", undefined, "metric");
  node.append(
    element("strong", number(value)),
    element("span", label),
    element("small", note),
  );
  return node;
}
function list(pairs) {
  const node = element("dl");
  for (const [label, value] of pairs)
    node.append(
      element("dt", label),
      element("dd", typeof value === "number" ? number(value) : value),
    );
  return node;
}
function filters() {
  return {
    state: $("state").value,
    region: $("region").value,
    status: $("status").value,
    query: $("query").value.trim(),
  };
}
function color(c) {
  if (!c) return "url(#unknown-county)";
  if (c.confirmed) return "#15483c";
  if (c.records.length && c.searched) return "#668a63";
  if (c.records.length) return "#83b9a1";
  if (c.searched) return "#dbc58a";
  return "#e2e8dc";
}
function selectCounty(id, focus = false) {
  selectedCounty = model.byId.get(id);
  selectedFacility = null;
  facilityLimit = 20;
  renderMap();
  renderDetail();
  if (focus) {
    $("selection-heading").tabIndex = -1;
    $("selection-heading").focus();
  }
}
function selectFacility(record) {
  selectedCounty = null;
  selectedFacility = facilityIdentity(record);
  facilityLimit = 20;
  renderDetail();
}
function svg(tag, attributes) {
  const node = document.createElementNS(ns, tag);
  for (const [key, value] of Object.entries(attributes))
    node.setAttribute(key, value);
  return node;
}
function buildMap() {
  for (const shape of boundaries.counties) {
    const county = model.byId.get(shape.id);
    const path = svg("path", { d: shape.d, fill: color(county) });
    const title = svg("title", {});
    const search = county?.confirmed
      ? "searched, confirmed complete"
      : county?.searched
        ? "searched, incomplete"
        : county?.status === "unsearched"
          ? "unsearched"
          : "search status unknown";
    title.textContent = `${shape.name}, ${shape.state}: ${county ? county.records.length : "unknown"} facilities; ${search}; ${county?.confirmed ? "confirmed complete" : "completeness unconfirmed"}`;
    path.append(title);
    path.dataset.label = `${shape.name}, ${shape.state}`;
    path.addEventListener("click", () => selectCounty(shape.id));
    countyPaths.set(shape.id, path);
    $("counties").append(path);
  }
  for (const shape of boundaries.states)
    $("states").append(svg("path", { d: shape.d }));
}
function renderMap(preserveView = false) {
  const ids = new Set(filteredCounties.map((c) => c.id));
  for (const [id, path] of countyPaths) {
    const county = model.byId.get(id);
    path.setAttribute("fill", color(county));
    path.querySelector("title").textContent =
      `${path.dataset.label}: ${county ? county.records.length : "unknown"} facilities; ${county?.searched ? "searched" : county?.status === "unsearched" ? "unsearched" : "search status unknown"}; ${county?.confirmed ? "confirmed complete" : "completeness unconfirmed"}`;
    path.classList.toggle(
      "fresh",
      Boolean(
        county?.records.some((r) => freshIdentities.has(facilityIdentity(r))),
      ),
    );
    path.classList.toggle("dim", !ids.has(id));
    path.classList.toggle("selected", selectedCounty?.id === id);
  }
  const state = boundaries.states.find((s) => s.id === $("state").value);
  if (!preserveView && state) {
    const [x1, y1, x2, y2] = state.bounds;
    $("map").setAttribute(
      "viewBox",
      `${x1 - 15} ${y1 - 15} ${x2 - x1 + 30} ${y2 - y1 + 30}`,
    );
  } else if (!preserveView) $("map").setAttribute("viewBox", "0 0 1000 600");
  $("focus-regions").replaceChildren();
  if (progress && !progress.stale)
    for (const target of progress.activeRegions) {
      const county = model.byId.get(target.countyFips);
      const shape =
        county?.state === target.state
          ? boundaries.counties.find((c) => c.id === county.id)
          : target.countyFips === null
            ? boundaries.states.find((s) => s.id === target.state)
            : null;
      if (shape) $("focus-regions").append(svg("path", { d: shape.d }));
    }
  $("points").replaceChildren();
  if ($("markers").checked)
    for (const record of filteredRecords.filter(located)) {
      const c = record.coordinates;
      const [x, y] = project(c.longitude, c.latitude, record.state);
      const kind =
        c.kind === "verified_entrance"
          ? "Verified entrance"
          : c.kind === "address_range_estimate"
            ? "Address-range estimate, not an entrance"
            : `Published coordinate (${c.kind || "kind unspecified"}), entrance unverified`;
      const marker = svg("circle", {
        cx: x,
        cy: y,
        r: state ? 1 : 1.7,
        class:
          c.kind === "verified_entrance"
            ? "entrance"
            : c.kind === "address_range_estimate"
              ? "estimate"
              : "other",
      });
      marker.classList.toggle(
        "fresh",
        freshIdentities.has(facilityIdentity(record)),
      );
      const title = svg("title", {});
      title.textContent = `${record.name}: ${kind}`;
      marker.append(title);
      marker.addEventListener("click", () => {
        const id = model.assigned.get(record);
        if (id) selectCounty(id);
        else {
          selectedCounty = null;
          selectFacility(record);
        }
      });
      $("points").append(marker);
    }
}
function renderCounties() {
  const rows = document.createDocumentFragment();
  for (const county of filteredCounties.slice(0, countyLimit)) {
    const row = element("tr");
    row.classList.toggle(
      "fresh",
      county.records.some((r) => freshIdentities.has(facilityIdentity(r))),
    );
    const name = element("td");
    const button = element("button", `${county.name}, ${county.state}`);
    button.type = "button";
    button.dataset.focusKey = `county:${county.id}`;
    button.addEventListener("click", () => selectCounty(county.id, true));
    name.append(button);
    row.append(
      name,
      element("td", number(county.records.length)),
      element(
        "td",
        county.searched
          ? "Searched"
          : county.status === "unsearched"
            ? "Unsearched"
            : "Unknown",
      ),
      element("td", county.confirmed ? "Confirmed" : "Unconfirmed"),
    );
    rows.append(row);
  }
  $("county-rows").replaceChildren(rows);
  $("county-count").textContent = number(filteredCounties.length);
  $("county-summary").textContent =
    `${number(filteredCounties.filter((c) => c.records.length).length)} represented · ${number(filteredCounties.filter((c) => c.searched).length)} searched · ${number(filteredCounties.filter((c) => c.confirmed).length)} complete`;
  $("more-counties").hidden = countyLimit >= filteredCounties.length;
}
function renderFacilities() {
  const nodes = document.createDocumentFragment();
  for (const record of detailRecords.slice(0, facilityLimit)) {
    const item = element("article", undefined, "facility");
    item.classList.toggle(
      "fresh",
      freshIdentities.has(facilityIdentity(record)),
    );
    item.append(
      element("h3", record.name),
      element("p", record.address || "Address unknown"),
    );
    item.append(
      element("span", `${record.holes ?? "?"} facility holes`, "pill"),
      element(
        "span",
        `${record.courses?.length || 0} documented layouts`,
        "pill",
      ),
    );
    item.append(
      element(
        "p",
        located(record)
          ? record.coordinates.kind === "address_range_estimate"
            ? "Address-range estimate · entrance unverified"
            : record.coordinates.kind === "verified_entrance"
              ? "Verified entrance"
              : "Published coordinate · entrance unverified"
          : "Unlocated · no marker",
      ),
    );
    const url = record.website;
    if (typeof url === "string" && /^https?:\/\//i.test(url)) {
      const link = element("a", "Official website");
      link.href = url;
      link.dataset.focusKey = `website:${facilityIdentity(record)}`;
      link.rel = "noreferrer";
      item.append(link);
    }
    nodes.append(item);
  }
  $("facilities").replaceChildren(nodes);
  $("more-facilities").hidden = facilityLimit >= detailRecords.length;
}
function renderDetail(override, heading) {
  const selected =
    selectedFacility &&
    model.records.find((r) => facilityIdentity(r) === selectedFacility);
  if (selected) {
    override = [selected];
    heading = selected.name;
  } else selectedFacility = null;
  detailRecords =
    override || (selectedCounty ? selectedCounty.records : filteredRecords);
  const totals = summarize(detailRecords);
  $("selection-heading").textContent =
    heading ||
    (selectedCounty
      ? `${selectedCounty.name}, ${selectedCounty.state}`
      : $("state").value || $("region").value || "United States");
  const node = $("selection-detail");
  node.replaceChildren();
  if (selectedCounty)
    node.append(
      element(
        "p",
        `${selectedCounty.searched ? `Searched ${selectedCounty.searchedOn || "(date unknown)"}` : "No published search"} · ${selectedCounty.confirmed ? "confirmed complete" : "completeness unconfirmed"}`,
      ),
    );
  node.append(
    list([
      ["Facility entries", totals.facilities],
      ["Documented course layouts", totals.courses],
      ["Unlocated facilities", totals.facilities - totals.located],
      ["Four fields complete", totals.four],
      ["Five fields complete", totals.five],
    ]),
  );
  if (!selectedCounty && !override) {
    const unknown = detailRecords.filter((r) => !model.assigned.has(r)).length;
    node.append(
      element(
        "p",
        `${number(unknown)} facilities without a matched checklist county.`,
      ),
    );
    // Unlocated records stay in aggregates and this list, never on the map.
    const states = new Map();
    for (const r of detailRecords.filter((r) => !located(r)))
      states.set(r.state, (states.get(r.state) || 0) + 1);
    const aggregate = element("details");
    aggregate.dataset.detailKey = "unlocated";
    aggregate.append(element("summary", "Unlocated facilities by state"));
    aggregate.append(list([...states].sort()));
    node.append(aggregate);
  }
  if (selectedCounty && !countyPaths.has(selectedCounty.id))
    node.append(element("p", "Boundary unavailable · included in counts."));
  renderFacilities();
  const showFacilities = Boolean(
    override ||
    selectedCounty ||
    $("state").value ||
    $("region").value ||
    $("query").value.trim(),
  );
  $("facilities").hidden = !showFacilities;
  if (!showFacilities) $("more-facilities").hidden = true;
}
function render(preserveView = false) {
  const f = filters();
  filteredCounties = selectCounties(model, f);
  filteredRecords = selectRecords(model, f, filteredCounties);
  if (selectedCounty && !filteredCounties.includes(selectedCounty))
    selectedCounty = null;
  const totals = summarize(filteredRecords);
  $("metrics").replaceChildren(
    metric(totals.facilities, "Facility entries", "Provisional grouping"),
    metric(totals.courses, "Course layouts", "Documented subdivisions only"),
    metric(
      totals.four,
      "Four fields complete",
      "Name · address · county · holes",
    ),
    metric(totals.five, "Five fields complete", "Four fields + website"),
    metric(
      totals.located,
      "Facilities with coordinates",
      "Estimates may not be entrances",
    ),
    metric(
      totals.facilities - totals.located,
      "Unlocated facilities",
      "Included in area counts",
    ),
  );
  $("remaining").replaceChildren(
    list([
      ...Object.entries(totals.missing).map(([key, count]) => [
        `Missing ${key}`,
        count,
      ]),
      ["Unresolved course details", totals.unresolved],
      [
        "Unsearched counties",
        filteredCounties.filter((c) => c.status === "unsearched").length,
      ],
      [
        "Coverage unconfirmed",
        filteredCounties.filter((c) => !c.confirmed).length,
      ],
    ]),
  );
  renderCounties();
  renderMap(preserveView);
  renderDetail();
}
function utcLabel(value) {
  return value
    ? new Date(value).toISOString().slice(0, 16).replace("T", " ") + " UTC"
    : "Time unknown";
}
function renderProgress() {
  $("targets").replaceChildren();
  $("recent").replaceChildren();
  $("progress-status").classList.toggle("stale", Boolean(progress?.stale));
  if (!progress) {
    $("progress-status").textContent = "Status snapshot unavailable.";
    $("recent-status").textContent = "Addition snapshot unavailable.";
    return;
  }
  $("progress-status").textContent =
    `${progress.stale ? "Stale snapshot" : "Snapshot"} · ${utcLabel(progress.updatedAt)}`;
  for (const target of progress.activeRegions) {
    const county = model.byId.get(target.countyFips);
    const label =
      county?.state === target.state
        ? `${county.name}, ${target.state}`
        : target.countyFips === null
          ? target.state
          : `${target.state} · county unavailable`;
    const button = element("button", `${label} · ${target.stage}`, "target");
    button.type = "button";
    button.dataset.focusKey = `target:${target.state}:${target.countyFips}:${target.stage}`;
    button.addEventListener("click", () => {
      $("region").value = "";
      $("state").value = target.state;
      $("query").value = "";
      $("status").value = "all";
      selectedCounty = county?.state === target.state ? county : null;
      selectedFacility = null;
      countyLimit = 80;
      facilityLimit = 20;
      render();
    });
    $("targets").append(button);
  }
  if (!progress.activeRegions.length)
    $("targets").append(element("p", "No region status published."));
  $("recent-status").textContent = progress.recentBatches.length
    ? "Partial status history"
    : "No recent batches published.";
  const byIdentity = new Map();
  for (const record of model.records) {
    const identity = facilityIdentity(record);
    const records = byIdentity.get(identity) || [];
    records.push(record);
    byIdentity.set(identity, records);
  }
  for (const batch of progress.recentBatches) {
    const item = element("article", undefined, "batch");
    item.append(
      element(
        "h3",
        `${batch.added ?? "?"} added · ${batch.updated ?? "?"} updated`,
      ),
      element("p", utcLabel(batch.publishedAt)),
    );
    const details = element("details");
    details.dataset.detailKey = `research:${batch.commit || batch.publishedAt}`;
    details.append(
      element(
        "summary",
        `${number(batch.facilities.length)} published addition names`,
      ),
    );
    for (const addition of batch.facilities) {
      const matches = byIdentity.get(facilityIdentity(addition)) || [];
      const record = matches.length === 1 ? matches[0] : null;
      if (record) {
        const button = element(
          "button",
          `${addition.name}, ${addition.state}`,
          "addition",
        );
        button.type = "button";
        button.dataset.focusKey = `research:${facilityIdentity(record)}`;
        button.addEventListener("click", () => {
          selectFacility(record);
        });
        details.append(button);
      } else
        details.append(
          element(
            "p",
            `${addition.name}, ${addition.state} · ${matches.length > 1 ? "identity ambiguous in loaded catalog" : "absent from loaded catalog"}`,
          ),
        );
    }
    item.append(details);
    if (batch.commit) {
      const link = element("a", "Published change");
      link.href = `https://github.com/snowball-projects/fairway/commit/${batch.commit}`;
      item.append(link);
    }
    $("recent").append(item);
  }
  if (progress.catalogCommit) {
    const link = element("a", "Status catalog revision");
    link.href = `https://github.com/snowball-projects/fairway/commit/${progress.catalogCommit}`;
    $("targets").append(link);
  }
}
function renderAdditions() {
  $("additions-log").replaceChildren();
  if (!additions) {
    $("additions-summary").textContent = "History unavailable.";
    return;
  }
  const batches = additions.batches.filter((b) => !b.baseline);
  const localTime = (value) =>
    new Date(value).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      timeZoneName: "short",
    });
  $("additions-summary").textContent =
    `${number(batches.reduce((n, b) => n + b.added, 0))} facilities added · ${number(batches.reduce((n, b) => n + b.removed, 0))} removed · ${number(batches.length)} logged batches · ${additions.completeFrom ? `History from ${localTime(additions.completeFrom)}` : "Partial history"}`;
  const byIdentity = new Map();
  for (const record of model.records) {
    const identity = facilityIdentity(record);
    byIdentity.set(identity, byIdentity.has(identity) ? null : record);
  }
  for (const batch of [...additions.batches]
    .sort((a, b) => Date.parse(b.committedAt) - Date.parse(a.committedAt))
    .slice(0, 12)) {
    const article = element("article", undefined, "batch");
    article.append(
      element(
        "h3",
        batch.baseline
          ? `Initial catalog · ${number(batch.added)} entries`
          : `${number(batch.added)} facilities added${batch.removed ? ` · ${number(batch.removed)} removed` : ""}`,
      ),
    );
    const time = element("time", `Committed ${localTime(batch.committedAt)}`);
    time.dateTime = batch.committedAt;
    time.title = batch.committedAt;
    article.append(time);
    const details = element("details");
    details.dataset.detailKey = `log:${batch.commit}`;
    details.append(
      element(
        "summary",
        `${number(batch.facilities.length)} facility names${batch.redacted ? ` · ${number(batch.redacted)} omitted` : ""}`,
      ),
    );
    for (const facility of batch.facilities.slice(0, 20)) {
      const record = byIdentity.get(facilityIdentity(facility));
      if (record) {
        const button = element(
          "button",
          `${facility.name}, ${facility.state}`,
          "addition",
        );
        button.type = "button";
        button.dataset.focusKey = `log:${batch.commit}:${facilityIdentity(facility)}`;
        button.addEventListener("click", () => selectFacility(record));
        details.append(button);
      } else
        details.append(element("p", `${facility.name}, ${facility.state}`));
    }
    if (batch.facilities.length > 20)
      details.append(element("p", "More names in the full log."));
    article.append(details);
    const change = element("a", "Committed change");
    change.href = `https://github.com/snowball-projects/fairway/commit/${batch.commit}`;
    article.append(change);
    $("additions-log").append(article);
  }
  const full = element("a", "Full additions log");
  full.href = "../../data/catalog-additions.json";
  $("additions-log").append(full);
}
function preserveView(update) {
  const focused = document.activeElement?.dataset.focusKey;
  const scrolls = [
    ...document.querySelectorAll(
      ".table-wrap, #facilities, #recent, #additions-log",
    ),
  ].map((node) => [node, node.scrollTop]);
  const expanded = new Map(
    [...document.querySelectorAll("details[data-detail-key]")].map((node) => [
      node.dataset.detailKey,
      node.open,
    ]),
  );
  const scroll = [window.scrollX, window.scrollY];
  update();
  for (const node of document.querySelectorAll("details[data-detail-key]"))
    node.open = expanded.get(node.dataset.detailKey) || false;
  for (const [node, top] of scrolls) node.scrollTop = top;
  if (focused)
    [...document.querySelectorAll("[data-focus-key]")]
      .find((node) => node.dataset.focusKey === focused)
      ?.focus({ preventScroll: true });
  window.scrollTo(...scroll);
}
function applyCatalog(next) {
  const nextModel = buildModel(next); // Validate before replacing a working view.
  const first = !model;
  const added = first ? [] : addedFacilities(model.records, nextModel.records);
  const previousFacility = model?.records.find(
    (r) => facilityIdentity(r) === selectedFacility,
  );
  preserveView(() => {
    catalog = next;
    model = nextModel;
    selectedCounty = selectedCounty
      ? model.byId.get(selectedCounty.id) || null
      : null;
    if (previousFacility) {
      const matches = model.records.filter(
        (r) =>
          r.state === previousFacility.state &&
          r.name === previousFacility.name,
      );
      if (matches.length === 1) selectedFacility = facilityIdentity(matches[0]);
    }
    freshIdentities = new Set(added.map(facilityIdentity));
    lastAdded = added.length;
    clearTimeout(freshTimer);
    freshTimer = setTimeout(() => {
      freshIdentities.clear();
      for (const node of document.querySelectorAll(".fresh"))
        node.classList.remove("fresh");
    }, 30000);
    const age =
      (Date.now() - Date.parse(`${catalog.updated_on}T00:00:00Z`)) / 86400000;
    $("snapshot").textContent =
      `Catalog ${catalog.updated_on || "date unknown"} · incomplete snapshot${age > 2 ? " · stale" : ""}`;
    $("snapshot").classList.toggle("stale", age > 2);
    if (first) buildMap();
    const unmapped = model.counties.filter(
      (c) => !countyPaths.has(c.id),
    ).length;
    const unmatched = boundaries.counties.filter(
      (c) => !model.byId.has(c.id),
    ).length;
    $("map-coverage-warning").hidden = !(unmapped || unmatched);
    $("map-coverage-warning").textContent =
      `${number(unmapped)} county boundaries unavailable · ${number(unmatched)} shapes without checklist matches. Unknown areas are not zero coverage.`;
    render(!first);
    renderProgress();
    renderAdditions();
    $("error").hidden = true;
    for (const input of $("filters").elements) input.disabled = false;
    $("markers").disabled = false;
  });
}
async function loadJSON(path) {
  const response = await fetch(path, {
    cache: "no-cache",
    signal: AbortSignal.timeout(15000),
  });
  if (!response.ok)
    throw new Error(`Snapshot unavailable (${response.status})`);
  return response.json();
}
async function init() {
  try {
    for (const input of $("filters").elements) input.disabled = true;
    $("markers").disabled = true;
    boundaries = await loadJSON("./boundaries.json");
    for (const s of boundaries.states) {
      const option = element("option", `${s.name} (${s.id})`);
      option.value = s.id;
      $("state").append(option);
    }
    $("filters").addEventListener("submit", (event) => event.preventDefault());
    $("filters").addEventListener("input", () => {
      selectedFacility = null;
      countyLimit = 80;
      facilityLimit = 20;
      render();
    });
    $("region").addEventListener("change", () => {
      if (
        $("region").value &&
        !regions[$("region").value].includes($("state").value)
      )
        $("state").value = "";
      render();
    });
    $("filters").addEventListener("reset", () => {
      selectedCounty = null;
      selectedFacility = null;
      countyLimit = 80;
      facilityLimit = 20;
      $("markers").checked = false;
      setTimeout(render, 0);
    });
    $("markers").addEventListener("change", () => renderMap());
    $("more-counties").addEventListener("click", () => {
      countyLimit += 80;
      renderCounties();
    });
    $("more-facilities").addEventListener("click", () => {
      facilityLimit += 20;
      renderFacilities();
    });
    watchSnapshots({
      onCatalog: applyCatalog,
      onProgress: (value) => {
        const next = value ? parseProgress(value) : null;
        preserveView(() => {
          progress = next;
          renderProgress();
          renderMap(true);
        });
      },
      onAdditions: (value) => {
        const next = value ? parseAdditions(value) : null;
        preserveView(() => {
          additions = next;
          renderAdditions();
        });
      },
      onStatus: ({ state, changed }) => {
        const time = new Date().toLocaleTimeString(undefined, {
          hour: "2-digit",
          minute: "2-digit",
        });
        $("refresh-status").textContent =
          state === "paused"
            ? "Paused · tab hidden"
            : state === "delayed"
              ? "Updates delayed · retrying"
              : `${changed ? "Updated" : "Checked"} ${time}${changed && lastAdded ? ` · ${number(lastAdded)} added` : ""}`;
        if (!model && state === "delayed") {
          $("error").hidden = false;
          $("error").textContent = "Catalog unavailable · retrying.";
        }
      },
    });
  } catch {
    $("error").hidden = false;
    $("error").textContent = "Map snapshot unavailable. Reload to retry.";
    $("snapshot").textContent = "Snapshot unavailable";
    for (const input of $("filters").elements) input.disabled = true;
    $("markers").disabled = true;
  }
}
init();
