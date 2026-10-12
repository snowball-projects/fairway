import {
  buildModel,
  located,
  parseProgress,
  parseAdditions,
  activityBatches,
  chicagoTime,
} from "./research-map/model.mjs";
import { watchSnapshots } from "./research-map/refresh.mjs";
import {
  publicPlay,
  mapEligible,
  catalogCounts,
  cityLabel,
  searchCatalog,
  shapeRings,
  clusterPoints,
} from "./catalog.mjs";

const COLORS = [
  "#2f6fba",
  "#c14c70",
  "#a86412",
  "#6d50ad",
  "#087c6b",
  "#b44838",
  "#4a6f24",
  "#8c4f84",
];

const state = {
  rows: [],
  courseMarkers: new Map(),
  ranking: null,
  activeRows: [],
  activeCourse: null,
  request: null,
  photonBbox: null,
  coreBounds: null,
  ready: false,
  maxOrigins: COLORS.length,
  routingCatalogLabel: "",
};
const REDUCED_MOTION = window.matchMedia(
  "(prefers-reduced-motion: reduce)",
).matches;

const view = {
  appShell: document.querySelector(".app-shell"),
  addOrigin: document.querySelector("#add-origin"),
  origins: document.querySelector("#origins"),
  status: document.querySelector("#status"),
  resultsPanel: document.querySelector("#results-panel"),
  results: document.querySelector("#results"),
  resultCount: document.querySelector("#result-count"),
  rankingDescription: document.querySelector("#ranking-description"),
  catalogName: document.querySelector("#catalog-name"),

  filterToggle: document.querySelector("#filter-toggle"),
  filterPopover: document.querySelector("#filter-popover"),
  routingDescription: document.querySelector("#routing-description"),
  routingAttribution: document.querySelector("#routing-attribution"),
};
let nextOriginId = 1;

const map = L.map("map", {
  zoomControl: true,
  zoomSnap: 0.25,
  zoomDelta: 0.5,
}).fitBounds(
  [
    [24, -125],
    [50, -66],
  ],
  { padding: [40, 100] },
);
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution:
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  maxZoom: 19,
}).addTo(map);
new ResizeObserver(() => map.invalidateSize()).observe(
  document.querySelector("#map"),
);

function setStatus(message, error = false) {
  view.status.textContent = message;
  view.status.dataset.error = String(error);
}

function setFilterOpen(open, focus = false) {
  const nextOpen = open && !view.resultsPanel.hidden;
  view.filterPopover.hidden = !nextOpen;
  view.filterToggle.setAttribute("aria-expanded", String(nextOpen));
  if (nextOpen && focus) {
    view.filterPopover.querySelector("input:checked")?.focus();
  }
}

function setResultsVisible(visible) {
  if (visible) {
    browseMode = false;
    setDrawer("courses", true);
  }
  document.querySelector("#ranking-mode").disabled = !state.ranking;
  renderCourses();
}

function selected(name) {
  return document.querySelector(`input[name="${name}"]:checked`)?.value;
}

function selectedHoles() {
  const value = selected("holes");
  return value === "all" ? [9, 18] : [Number(value)];
}

function parseCoordinate(value) {
  const match = value.match(
    /^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*,\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*$/,
  );
  if (!match) return null;
  const coordinate = [Number(match[1]), Number(match[2])];
  if (
    !coordinate.every(Number.isFinite) ||
    Math.abs(coordinate[0]) > 90 ||
    Math.abs(coordinate[1]) > 180
  ) {
    return null;
  }
  return coordinate;
}

function formatCoordinate(coordinate) {
  return `${coordinate[0].toFixed(5)}, ${coordinate[1].toFixed(5)}`;
}

function looksLikeCoordinateInput(value) {
  return /^[+\-\d.,\s]+$/.test(value);
}

function insideCore(coordinate) {
  if (!state.coreBounds) return true;
  const [south, west, north, east] = state.coreBounds;
  return (
    coordinate[0] >= south &&
    coordinate[0] <= north &&
    coordinate[1] >= west &&
    coordinate[1] <= east
  );
}

function duration(seconds) {
  const minutes = Math.max(0, Math.round(seconds / 60));
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return remainder ? `${hours} hr ${remainder} min` : `${hours} hr`;
}

function address(feature) {
  const value = feature?.properties || {};
  return [value.name, value.street, value.city || value.district, value.state]
    .filter((part, index, parts) => part && parts.indexOf(part) === index)
    .join(", ");
}

function originIcon(row) {
  const index = state.rows.indexOf(row);
  return L.divIcon({
    className: "",
    html: `<span class="origin-pin" style="background:${row.color}">${index + 1}</span>`,
    iconSize: [30, 30],
    iconAnchor: [15, 15],
  });
}

function labelMarker(marker, label) {
  marker.options.title = label;
  marker.options.alt = label;
  const element = marker.getElement();
  if (element) {
    element.setAttribute("aria-label", label);
    element.setAttribute("title", label);
  }
}

function updateOriginMarker(row) {
  if (!row.coordinate) return;
  const label = `Golfer ${state.rows.indexOf(row) + 1}`;
  if (row.marker) {
    row.marker.setLatLng(row.coordinate).setIcon(originIcon(row));
  } else {
    row.marker = L.marker(row.coordinate, {
      icon: originIcon(row),
      keyboard: true,
      title: label,
      alt: label,
    })
      .addTo(map)
      .bindTooltip(() => `Golfer ${state.rows.indexOf(row) + 1}`);
  }
  labelMarker(row.marker, label);
}

function currentResult(courseId) {
  return (
    state.ranking?.courses.find((course) => course.id === courseId) || null
  );
}

function clearCourseMarkers() {
  state.courseMarkers.forEach((marker) => marker.remove());
  state.courseMarkers.clear();
}

function drawCourseMarkers() {
  drawFacilities();
}
function updateCourseMarkers() {
  drawFacilities();
}
function selectCourse(courseId, scrollToCard = false) {
  state.activeCourse = courseId;
  const course = currentResult(courseId);
  if (course) selectFacilityById(course.facility_id, false);
  document.querySelectorAll(".course-card").forEach((card) => {
    card.dataset.active = String(card.dataset.courseId === courseId);
    if (scrollToCard && card.dataset.active === "true")
      card.scrollIntoView({ block: "nearest" });
  });
}

function closeSuggestions(row, abort = false) {
  if (abort) {
    row.controller?.abort();
    row.controller = null;
  }
  row.suggestions.replaceChildren();
  row.activeSuggestion = -1;
  row.input.setAttribute("aria-expanded", "false");
  row.input.removeAttribute("aria-activedescendant");
}

function suggestionOptions(row) {
  return [...row.suggestions.querySelectorAll('[role="option"]')];
}

function setActiveSuggestion(row, index) {
  const options = suggestionOptions(row);
  if (!options.length) return false;
  const activeIndex = (index + options.length) % options.length;
  row.activeSuggestion = activeIndex;
  options.forEach((option, optionIndex) => {
    option.setAttribute("aria-selected", String(optionIndex === activeIndex));
  });
  row.input.setAttribute("aria-activedescendant", options[activeIndex].id);
  options[activeIndex].scrollIntoView({ block: "nearest" });
  return true;
}

function moveSuggestion(row, direction) {
  const options = suggestionOptions(row);
  if (!options.length) return false;
  const next =
    row.activeSuggestion < 0
      ? direction > 0
        ? 0
        : options.length - 1
      : row.activeSuggestion + direction;
  return setActiveSuggestion(row, next);
}

function chooseActiveSuggestion(row) {
  const option = suggestionOptions(row)[row.activeSuggestion];
  if (!option) return false;
  option.click();
  return true;
}

function setOrigin(row, label, coordinate) {
  row.input.value = label;
  row.coordinate = coordinate;
  closeSuggestions(row, true);
  updateOriginMarker(row);
  if (map.getZoom() < 10) fitPoints([coordinate], 12);
  updatePlan();
}

async function suggest(row) {
  const query = row.input.value.trim();
  closeSuggestions(row, true);
  if (
    parseCoordinate(query) ||
    query.length < 3 ||
    looksLikeCoordinateInput(query)
  )
    return;
  const controller = new AbortController();
  row.controller = controller;
  try {
    const scope = "&countrycode=US";
    const response = await fetch(
      `https://photon.komoot.io/api/?limit=5${scope}&q=${encodeURIComponent(query)}`,
      { signal: controller.signal },
    );
    if (!response.ok) throw new Error();
    const result = await response.json();
    if (row.controller !== controller || row.input.value.trim() !== query)
      return;
    result.features.forEach((feature) => {
      const geometry = feature?.geometry?.coordinates;
      if (!Array.isArray(geometry) || geometry.length < 2) return;
      const coordinate = [Number(geometry[1]), Number(geometry[0])];
      if (!coordinate.every(Number.isFinite)) return;
      const button = document.createElement("button");
      button.type = "button";
      button.id = `${row.suggestions.id}-option-${row.suggestions.childElementCount}`;
      button.role = "option";
      button.tabIndex = -1;
      button.setAttribute("aria-selected", "false");
      button.textContent = address(feature) || formatCoordinate(coordinate);
      button.onmousedown = (event) => event.preventDefault();
      button.onclick = () => setOrigin(row, button.textContent, coordinate);
      button.onmouseenter = () => {
        const index = suggestionOptions(row).indexOf(button);
        if (index >= 0) setActiveSuggestion(row, index);
      };
      const item = document.createElement("li");
      item.role = "none";
      item.append(button);
      row.suggestions.append(item);
    });
    row.input.setAttribute(
      "aria-expanded",
      String(row.suggestions.childElementCount > 0),
    );
  } catch (error) {
    if (error.name !== "AbortError") {
      setStatus(
        "Address suggestions are unavailable. Enter latitude, longitude instead.",
        true,
      );
    }
  } finally {
    if (row.controller === controller) row.controller = null;
  }
}

function unusedColor() {
  const used = new Set(state.rows.map((row) => row.color));
  return (
    COLORS.find((candidate) => !used.has(candidate)) ||
    COLORS[state.rows.length % COLORS.length]
  );
}

function addOrigin() {
  if (state.rows.length >= state.maxOrigins) return;
  const row = {
    color: unusedColor(),
    coordinate: null,
    marker: null,
    timer: null,
    controller: null,
    activeSuggestion: -1,
    input: document.createElement("input"),
    suggestions: document.createElement("ul"),
  };
  const element = document.createElement("div");
  element.className = "origin";
  element.style.setProperty("--origin", row.color);
  const number = document.createElement("span");
  number.className = "origin-number";
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "remove";
  remove.textContent = "×";
  row.input.autocomplete = "off";
  row.input.spellcheck = false;
  row.suggestions.className = "suggestions";
  row.suggestions.id = `origin-${nextOriginId}-suggestions`;
  nextOriginId += 1;
  row.suggestions.setAttribute("role", "listbox");
  row.input.setAttribute("role", "combobox");
  row.input.setAttribute("aria-autocomplete", "list");
  row.input.setAttribute("aria-haspopup", "listbox");
  row.input.setAttribute("aria-controls", row.suggestions.id);
  row.input.setAttribute("aria-expanded", "false");
  row.input.oninput = () => {
    closeSuggestions(row, true);
    clearTimeout(row.timer);
    const coordinate = parseCoordinate(row.input.value);
    if (coordinate) {
      row.coordinate = coordinate;
      updateOriginMarker(row);
      clearRanking();
      updatePlan();
      return;
    }
    row.coordinate = null;
    row.marker?.remove();
    row.marker = null;
    clearRanking();
    updatePlan();
    row.timer = setTimeout(() => suggest(row), 300);
  };
  row.input.onkeydown = (event) => {
    if (event.key === "ArrowDown" && moveSuggestion(row, 1)) {
      event.preventDefault();
    } else if (event.key === "ArrowUp" && moveSuggestion(row, -1)) {
      event.preventDefault();
    } else if (event.key === "Enter" && chooseActiveSuggestion(row)) {
      event.preventDefault();
    } else if (event.key === "Escape") {
      closeSuggestions(row, true);
    }
  };
  row.input.onblur = () => closeSuggestions(row, true);
  remove.onclick = () => {
    clearTimeout(row.timer);
    row.controller?.abort();
    row.marker?.remove();
    state.rows.splice(state.rows.indexOf(row), 1);
    element.remove();
    renumber();
    updatePlan();
  };
  element.append(number, row.input, remove, row.suggestions);
  row.element = element;
  row.number = number;
  row.remove = remove;
  view.origins.append(element);
  state.rows.push(row);
  renumber();
}

function renumber() {
  state.rows.forEach((row, index) => {
    row.number.textContent = index + 1;
    row.input.placeholder = `Golfer ${index + 1} address`;
    row.input.ariaLabel = `Golfer ${index + 1} origin`;
    row.suggestions.ariaLabel = `Address suggestions for Golfer ${index + 1}`;
    row.remove.ariaLabel = `Remove golfer ${index + 1}`;
    if (row.marker) {
      row.marker.setIcon(originIcon(row));
      labelMarker(row.marker, `Golfer ${index + 1}`);
    }
  });
  view.addOrigin.disabled = state.rows.length >= state.maxOrigins;
}

function clearRanking() {
  state.request?.abort();
  state.request = null;
  $("cancel-calculate").hidden = true;
  $("calculate").disabled =
    state.rows.filter((row) => row.coordinate).length < 2;
  state.ranking = null;
  state.activeRows = [];
  state.activeCourse = null;
  view.results.setAttribute("aria-busy", "false");
  view.results.replaceChildren();
  view.resultCount.textContent = "";
  view.rankingDescription.textContent = "";
  clearCourseMarkers();
  browseMode = true;
  document.querySelector("#ranking-mode").disabled = true;
  drawFacilities();
  renderCourses();
}

function updatePlan() {
  clearRanking();
  const count = state.rows.filter((row) => row.coordinate).length;
  document.querySelector("#calculate").disabled = count < 2;
  setStatus(
    count < 2 ? "Add at least two golfer origins." : "Ready to rank courses.",
  );
}

function restoreFilters(result) {
  const objective = document.querySelector(
    `input[name="objective"][value="${result.objective}"]`,
  );
  const holesValue =
    result.holes.length === 2 ? "all" : String(result.holes[0]);
  const holes = document.querySelector(
    `input[name="holes"][value="${holesValue}"]`,
  );
  if (objective) objective.checked = true;
  if (holes) holes.checked = true;
}

function courseCard(course, objective) {
  const item = document.createElement("li");
  const article = document.createElement("article");
  article.className = "course-card";
  article.dataset.courseId = course.id;
  article.dataset.active = String(state.activeCourse === course.id);
  const focus = document.createElement("button");
  focus.type = "button";
  focus.className = "course-focus";
  focus.onclick = () => {
    selectCourse(course.id);
    fitPoints([course.coordinate], 14);
    selectFacilityById(course.facility_id, false);
  };
  const rank = document.createElement("span");
  rank.className = "rank";
  rank.textContent = course.rank;
  const body = document.createElement("span");
  const title = document.createElement("span");
  title.className = "course-title";
  title.setAttribute("role", "heading");
  title.setAttribute("aria-level", "3");
  title.textContent = course.name;
  const meta = document.createElement("span");
  meta.className = "course-meta";
  [course.holes + " holes", course.access].forEach((label) => {
    const value = document.createElement("span");
    value.textContent = label;
    meta.append(value);
  });
  const scores = document.createElement("span");
  scores.className = "score-row";
  [
    ["maximum", duration(course.maximum_seconds), "longest drive"],
    ["combined", duration(course.combined_seconds), "combined drive"],
  ].forEach(([kind, value, label]) => {
    const score = document.createElement("span");
    score.className = `score${kind === objective ? " primary" : ""}`;
    const strong = document.createElement("strong");
    strong.textContent = value;
    const small = document.createElement("small");
    small.textContent = label;
    score.append(strong, small);
    scores.append(score);
  });
  body.append(title, meta, scores);
  focus.append(rank, body);
  const times = document.createElement("ul");
  times.className = "golfer-times";
  course.travel_times_seconds.forEach((seconds, index) => {
    const time = document.createElement("li");
    time.className = "golfer-time";
    time.style.setProperty(
      "--golfer",
      state.activeRows[index]?.color || COLORS[index],
    );
    time.textContent = `${index + 1} · ${duration(seconds)}`;
    time.ariaLabel = `Golfer ${index + 1}: ${duration(seconds)}`;
    times.append(time);
  });
  const footer = document.createElement("div");
  footer.className = "card-footer";
  const address = document.createElement("span");
  address.textContent = `${course.address} · ${course.destination_kind === "verified_entrance" ? "verified entrance" : "reviewed OSM routing point"}`;
  const link = document.createElement("a");
  link.href = course.website;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.textContent = "Course site";
  footer.append(address, link);
  article.append(focus, times, footer);
  item.append(article);
  return item;
}

function renderRanking(result) {
  const list = document.createElement("ol");
  list.className = "course-list";
  result.courses.forEach((course) =>
    list.append(courseCard(course, result.objective)),
  );
  view.results.replaceChildren(list);
  view.resultCount.textContent = `${result.courses.length} ${result.courses.length === 1 ? "course" : "courses"}`;
  view.rankingDescription.textContent =
    result.objective === "maximum"
      ? "Ranked by each course's longest individual drive."
      : "Ranked by the group's combined driving time.";
}

function fitRanking(activeRows, result) {
  const points = [
    ...activeRows.map((row) => row.coordinate),
    ...result.courses.map((course) => course.coordinate),
  ];
  const bounds = L.latLngBounds(points);
  requestAnimationFrame(() => {
    if (state.ranking !== result || !bounds.isValid()) return;
    map.invalidateSize({ animate: false });
    map.fitBounds(bounds.pad(0.08), {
      maxZoom: 12,
      animate: !REDUCED_MOTION,
      ...fitPadding(),
    });
  });
}

async function responseBody(response) {
  try {
    return await response.json();
  } catch {
    return { error: `Request failed with status ${response.status}.` };
  }
}

function rankingBasis(provenance) {
  const labels = {
    "traffic-unaware": "without traffic",
    live: "with live traffic",
    historical: "with historical traffic",
    predicted: "with predicted traffic",
    blended: "with live and historical traffic",
  };
  return labels[provenance?.traffic_basis] || "with provider travel times";
}

async function calculate({ preserveResults = false } = {}) {
  const previousRanking = preserveResults ? state.ranking : null;
  state.request?.abort();
  state.request = null;
  if (!state.ready) {
    if (!previousRanking) clearRanking();
    setStatus("Loading course coverage...");
    return;
  }
  const activeRows = state.rows.filter((row) => row.coordinate);
  if (activeRows.length < 2) {
    clearRanking();
    setStatus("Add at least two golfer origins.");
    return;
  }
  if (activeRows.some((row) => !insideCore(row.coordinate))) {
    clearRanking();
    setStatus(
      "These origins are outside current routing coverage. Catalog browsing works nationwide; lower-48 group routing is not available yet.",
      true,
    );
    return;
  }
  if (!previousRanking) clearRanking();
  const controller = new AbortController();
  state.request = controller;
  $("calculate").disabled = true;
  $("cancel-calculate").hidden = false;
  view.results.setAttribute("aria-busy", "true");
  setStatus(previousRanking ? "Updating ranking..." : "Ranking courses...");
  try {
    const response = await fetch("/api/rankings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        origins: activeRows.map((row) => row.coordinate),
        objective: selected("objective"),
        holes: selectedHoles(),
      }),
      signal: controller.signal,
    });
    const result = await responseBody(response);
    if (!response.ok) throw new Error(result.error);
    if (state.request !== controller) return;
    state.ranking = result;
    state.activeRows = activeRows;
    state.activeCourse = null;
    restoreFilters(result);
    renderRanking(result);
    drawCourseMarkers();
    setResultsVisible(true);
    fitRanking(activeRows, result);
    const omitted = result.unranked_courses || [];
    const largestSnap = Math.max(
      0,
      ...(result.origin_snap_distances_kilometers || []),
      ...result.courses.map((course) => course.snap_distance_kilometers || 0),
    );
    const notes = [];
    const unreachable = omitted.filter(
      (course) => course.reason === "unreachable",
    ).length;
    const outsideCoverage = omitted.filter(
      (course) => course.reason === "outside-road-coverage",
    ).length;
    const otherOmissions = omitted.length - unreachable - outsideCoverage;
    if (unreachable)
      notes.push(
        `${unreachable} unreachable ${unreachable === 1 ? "course was" : "courses were"} omitted.`,
      );
    if (outsideCoverage)
      notes.push(
        `${outsideCoverage} ${outsideCoverage === 1 ? "course was" : "courses were"} outside modeled roads.`,
      );
    if (otherOmissions)
      notes.push(
        `${otherOmissions} ${otherOmissions === 1 ? "course was" : "courses were"} omitted.`,
      );
    if (largestSnap >= 0.25)
      notes.push(`Nearest-road adjustment: ${largestSnap.toFixed(1)} km.`);
    setStatus(
      `${result.courses.length} courses ranked ${rankingBasis(result.provenance)}.${notes.length ? ` ${notes.join(" ")}` : ""}`,
    );
  } catch (error) {
    if (error.name !== "AbortError" && state.request === controller) {
      const message = error.message || "fairway could not rank these courses.";
      if (previousRanking) {
        restoreFilters(previousRanking);
        setStatus(`${message} Previous results are still shown.`, true);
      } else {
        clearRanking();
        setStatus(message, true);
      }
    }
  } finally {
    if (state.request === controller) {
      state.request = null;
      $("cancel-calculate").hidden = true;
      $("calculate").disabled =
        state.rows.filter((row) => row.coordinate).length < 2;
      view.results.setAttribute("aria-busy", "false");
    }
  }
}

async function configure() {
  try {
    const response = await fetch("/api/config", {
      signal: AbortSignal.timeout(15000),
    });
    const config = await responseBody(response);
    if (!response.ok) throw new Error(config.error);
    state.maxOrigins = Math.min(config.max_origins, COLORS.length);
    const [south, west, north, east] = config.core_bounds;
    state.coreBounds = [south, west, north, east];
    state.photonBbox = [west, south, east, north].join(",");
    state.routingCatalogLabel = `${config.course_catalog.title} · ${config.course_catalog.as_of}`;
    view.catalogName.textContent = state.routingCatalogLabel;
    view.routingDescription.textContent = config.routing.description;
    view.routingAttribution.hidden =
      config.routing.provider !== "tomtom-matrix-v2";
    state.ready = true;
    updatePlan();
  } catch (error) {
    setStatus(error.message || "Course coverage is unavailable.", true);
    clearRanking();
  }
}

view.addOrigin.onclick = addOrigin;
document
  .querySelectorAll('input[name="objective"], input[name="holes"]')
  .forEach((input) => {
    input.onchange = updatePlan;
  });
view.filterToggle.onclick = () =>
  setFilterOpen(view.filterPopover.hidden, true);
document.addEventListener("click", (event) => {
  if (
    !view.filterPopover.hidden &&
    !view.filterPopover.contains(event.target) &&
    !view.filterToggle.contains(event.target)
  ) {
    setFilterOpen(false);
  }
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !view.filterPopover.hidden) {
    setFilterOpen(false);
    view.filterToggle.focus();
  }
});

// One shared map, selection and catalog. No saved state or automatic location request.
const $ = (id) => document.getElementById(id);
const fmt = (n) => n.toLocaleString("en-US");
const facilitiesLayer = L.layerGroup().addTo(map),
  countiesLayer = L.layerGroup();
let catalogDate = "",
  countyIndex = 0;
let catalogModel = null,
  geometry = null,
  progress = null,
  additions = null;
let activeFacility = null,
  popupSelection = null,
  browseMode = true,
  browseScope = null;
let searchMatches = [],
  searchIndex = -1,
  listLimit = 60,
  cataloguePopup = null;
let lastSearch = "";
function node(tag, text, className) {
  const n = document.createElement(tag);
  if (text !== undefined) n.textContent = text;
  if (className) n.className = className;
  return n;
}
function mobile() {
  return window.matchMedia("(max-width:800px)").matches;
}
function setDrawer(which, open) {
  const panel = which === "plan" ? $("plan-panel") : view.resultsPanel;
  const toggle = which === "plan" ? $("plan-toggle") : $("courses-toggle");
  panel.hidden = !open;
  toggle.setAttribute("aria-expanded", String(open));
  if (open && mobile()) {
    const other = which === "plan" ? "courses" : "plan";
    (other === "plan" ? $("plan-panel") : view.resultsPanel).hidden = true;
    $(other === "plan" ? "plan-toggle" : "courses-toggle").setAttribute(
      "aria-expanded",
      "false",
    );
  }
  view.appShell.classList.toggle(
    "mobile-sheet-open",
    mobile() && (!$("plan-panel").hidden || !view.resultsPanel.hidden),
  );
  if (!open && panel.contains(document.activeElement)) toggle.focus();
  if (which === "courses" && open) renderCourses();
}
function fitPadding() {
  if (mobile())
    return {
      paddingTopLeft: [24, 170],
      paddingBottomRight: [
        24,
        !$("plan-panel").hidden || !view.resultsPanel.hidden
          ? window.innerHeight * 0.58 + 20
          : 75,
      ],
    };
  return {
    paddingTopLeft: [!$("plan-panel").hidden ? 370 : 60, 140],
    paddingBottomRight: [!view.resultsPanel.hidden ? 410 : 60, 90],
  };
}
function fitPoints(points, maxZoom = 15) {
  if (!points.length) return;
  const bounds = L.latLngBounds(points);
  if (bounds.isValid())
    map.fitBounds(bounds, {
      maxZoom,
      animate: !REDUCED_MOTION,
      ...fitPadding(),
    });
}
function onMapRecords() {
  if (!catalogModel) return [];
  return catalogModel.records.filter(
    (f) =>
      mapEligible(f) ||
      ($("show-estimates").checked &&
        located(f) &&
        f.map_location.kind === "address_range_estimate"),
  );
}
function drawFacilities() {
  if (!catalogModel) return;
  facilitiesLayer.clearLayers();
  state.courseMarkers.clear();
  const records = onMapRecords();
  const groups = clusterPoints(
    records,
    (location) => map.project([location.latitude, location.longitude]),
    map.getZoom(),
  );
  for (const group of groups) {
    const coordinates = map.unproject(L.point(group.x, group.y));
    if (!map.getBounds().pad(0.25).contains(coordinates)) continue;
    const many = group.records.length > 1;
    const qualified = group.records.every(mapEligible);
    const icon = node(
      "span",
      many ? fmt(group.records.length) : "",
      `${many ? "facility-cluster" : "facility-dot"}${qualified ? "" : " estimate"}${!many && activeFacility === group.records[0].id ? " active" : ""}`,
    );
    const marker = L.marker(coordinates, {
      icon: L.divIcon({
        className: "",
        html: icon,
        iconSize: many ? [38, 38] : [16, 16],
        iconAnchor: many ? [19, 19] : [8, 8],
      }),
      keyboard: true,
      alt: many ? `${group.records.length} facilities` : group.records[0].name,
    });
    marker.on("add", () => {
      const e = marker.getElement();
      if (e)
        e.setAttribute(
          "aria-label",
          many
            ? `${group.records.length} facilities, zoom to explore`
            : `${group.records[0].name}, ${qualified ? "property point" : "unconfirmed estimate"}`,
        );
    });
    marker.on("click", () => {
      if (many && map.getZoom() < 16)
        fitPoints(
          group.records.map((f) => [
            f.map_location.latitude,
            f.map_location.longitude,
          ]),
          Math.min(map.getZoom() + 3, 16),
        );
      else if (many) {
        popupSelection = {
          kind: "cluster",
          ids: group.records.map((f) => f.id),
          coordinate: coordinates,
        };
        openSelectionPopup();
      } else selectFacilityById(group.records[0].id, false);
    });
    marker.addTo(facilitiesLayer);
    if (!many)
      for (const c of state.ranking?.courses || [])
        if (c.facility_id === group.records[0].id)
          state.courseMarkers.set(c.id, marker);
  }
}
function websiteState(f) {
  if (f.website_status === "not_found")
    return `Website not found in check${f.website_checked_on ? ` · ${f.website_checked_on}` : ""}`;
  if (f.website_status === "found")
    return `Website checked${f.website_checked_on ? ` · ${f.website_checked_on}` : ""}`;
  return "Website check not recorded";
}
function facilityDetails(f, compact = false) {
  const article = node("article", undefined, "facility-card");
  article.dataset.facilityId = f.id;
  article.dataset.active = String(activeFacility === f.id);
  const title = node("button", f.name);
  title.type = "button";
  title.addEventListener("click", () => selectFacilityById(f.id, true));
  article.append(title);
  article.append(
    node(
      "p",
      `${cityLabel(f) ? `${cityLabel(f)}, ` : ""}${f.state} · ${f.physical_holes ?? "Unknown"} physical holes`,
    ),
  );
  article.append(
    node(
      "p",
      publicPlay(f) ? "Public play available" : "Public play not documented",
    ),
  );
  if (compact) {
    article.append(
      node(
        "p",
        mapEligible(f)
          ? "On map"
          : located(f)
            ? "Point awaits property confirmation"
            : "Awaiting a property point",
      ),
    );
    return article;
  }
  article.append(node("p", f.address?.text || "Address not documented"));
  if (f.courses?.length) {
    const details = node("details");
    details.append(
      node(
        "summary",
        `${f.courses.length} documented ${f.courses.length === 1 ? "course" : "courses"}`,
      ),
    );
    for (const c of f.courses)
      details.append(
        node(
          "p",
          `${c.name || "Unnamed course"} · ${c.holes ?? "?"} holes · ${c.access} access`,
        ),
      );
    if (f.access_note) details.append(node("p", f.access_note));
    article.append(details);
  } else
    article.append(node("p", "Individual course breakdown not documented"));
  if (f.map_location)
    article.append(
      node(
        "p",
        f.map_location.kind === "address_range_estimate"
          ? "Address estimate · property match unconfirmed"
          : f.map_location.kind === "verified_entrance"
            ? "Verified entrance point"
            : "Property point · entrance unverified",
      ),
    );
  else article.append(node("p", "Awaiting a property point"));
  const times = (state.ranking?.courses || []).filter(
    (c) => c.facility_id === f.id,
  );
  for (const c of times) {
    article.append(
      node(
        "p",
        `${c.name}: longest ${duration(c.maximum_seconds)} · combined ${duration(c.combined_seconds)}`,
      ),
    );
    article.append(
      node(
        "p",
        c.travel_times_seconds
          .map((s, i) => `Golfer ${i + 1}: ${duration(s)}`)
          .join(" · "),
      ),
    );
  }
  if (f.website) {
    try {
      const url = new URL(f.website);
      if (["http:", "https:"].includes(url.protocol)) {
        const a = node("a", "Website");
        a.href = url.href;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        article.append(a);
      }
    } catch {}
  }
  article.append(node("p", websiteState(f)));
  return article;
}
function selectFacilityById(id, fit = true) {
  const f = catalogModel?.records.find((r) => r.id === id);
  if (!f) return;
  activeFacility = id;
  if (fit && located(f))
    fitPoints([[f.map_location.latitude, f.map_location.longitude]], 15);
  if (located(f) && (mapEligible(f) || $("show-estimates").checked)) {
    popupSelection = {
      kind: "facility",
      id,
      coordinate: L.latLng(f.map_location.latitude, f.map_location.longitude),
    };
    openSelectionPopup();
  } else {
    setDrawer("courses", true);
    renderCourses();
  }
  drawFacilities();
  renderCourses();
}
function openSelectionPopup() {
  if (!popupSelection || !catalogModel) return;
  const content = node("div");
  if (popupSelection.kind === "facility") {
    const f = catalogModel.records.find((r) => r.id === popupSelection.id);
    if (!f) {
      closeSelection();
      return;
    }
    content.append(facilityDetails(f));
  } else if (popupSelection.kind === "county") {
    const c = catalogModel.byId.get(popupSelection.id);
    if (!c) return;
    const counts = catalogCounts(c.records);
    content.append(
      node("h3", `${c.name}, ${c.state}`),
      node(
        "p",
        `${counts.total} catalog facilities · ${counts.onMap} on map · ${counts.pending} pending`,
      ),
      node(
        "p",
        "Catalog records only; county discovery is not confirmed complete.",
      ),
    );
    if (c.searchedOn)
      content.append(node("p", `Last documented search: ${c.searchedOn}`));
  } else {
    content.append(
      node("h3", `${popupSelection.ids.length} facilities at this point`),
    );
    for (const id of popupSelection.ids) {
      const f = catalogModel.records.find((r) => r.id === id);
      if (f) content.append(facilityDetails(f, true));
    }
  }
  if (cataloguePopup?.isOpen())
    cataloguePopup.setLatLng(popupSelection.coordinate).setContent(content);
  else {
    cataloguePopup = L.popup({
      maxWidth: 312,
      minWidth: 280,
      autoPan: false,
      closeOnClick: false,
    })
      .setLatLng(popupSelection.coordinate)
      .setContent(content)
      .openOn(map);
    cataloguePopup.on("remove", () => {
      popupSelection = null;
      cataloguePopup = null;
    });
  }
}
function closeSelection() {
  popupSelection = null;
  activeFacility = null;
  if (cataloguePopup) map.closePopup(cataloguePopup);
  cataloguePopup = null;
  drawFacilities();
  renderCourses();
}
function scopedRecords() {
  if (!catalogModel) return [];
  let records = catalogModel.records;
  if (browseScope?.kind === "viewport")
    records = records.filter(
      (f) =>
        located(f) &&
        map
          .getBounds()
          .contains([f.map_location.latitude, f.map_location.longitude]),
    );
  else if (browseScope?.ids) {
    const ids = new Set(browseScope.ids);
    records = records.filter((f) => ids.has(f.id));
  }
  const holes = $("browse-holes").value;
  records = records.filter(
    (f) =>
      (holes === "all" || f.physical_holes === Number(holes)) &&
      ($("browse-access").value !== "public" || publicPlay(f)),
  );
  return [...records].sort((a, b) =>
    $("browse-sort").value === "holes"
      ? (b.physical_holes || 0) - (a.physical_holes || 0) ||
        a.name.localeCompare(b.name)
      : a.name.localeCompare(b.name),
  );
}
function renderCourses() {
  if (!catalogModel) return;
  view.catalogName.textContent = browseMode
    ? `Catalog ${catalogDate || "date unknown"}`
    : state.routingCatalogLabel;
  $("browse-mode").setAttribute("aria-pressed", String(browseMode));
  $("ranking-mode").setAttribute("aria-pressed", String(!browseMode));
  $("browse-description").hidden = !browseMode;
  view.rankingDescription.hidden = browseMode;
  if (!browseMode && state.ranking) {
    renderRanking(state.ranking);
    return;
  }
  const records = scopedRecords();
  view.resultCount.textContent = fmt(records.length);
  $("browse-description").textContent =
    browseScope?.label || "Facilities in the catalog";
  const nodes = [];
  if (activeFacility) {
    const selected = catalogModel.records.find((r) => r.id === activeFacility);
    if (selected) {
      nodes.push(facilityDetails(selected));
      nodes.push(node("hr"));
    }
  }
  for (const f of records
    .filter((r) => r.id !== activeFacility)
    .slice(0, listLimit))
    nodes.push(facilityDetails(f, true));
  if (records.length > listLimit) {
    const more = node("button", "Show more", "quiet-button");
    more.addEventListener("click", () => {
      listLimit += 60;
      renderCourses();
    });
    nodes.push(more);
  }
  if (!records.length)
    nodes.push(
      node("p", "No matching catalog records. Discovery remains incomplete."),
    );
  const top = view.results.scrollTop;
  view.results.replaceChildren(...nodes);
  view.results.scrollTop = top;
}
function closeSearch() {
  $("place-suggestions").replaceChildren();
  $("place-query").setAttribute("aria-expanded", "false");
  $("place-query").removeAttribute("aria-activedescendant");
  searchIndex = -1;
}
function showSearch() {
  lastSearch = $("place-query").value;
  searchMatches = searchCatalog(
    catalogModel?.records || [],
    geometry?.states || [],
    lastSearch,
  );
  const list = $("place-suggestions");
  list.replaceChildren();
  searchIndex = -1;
  for (const [i, result] of searchMatches.slice(0, 12).entries()) {
    const li = node("li");
    li.role = "none";
    const button = node("button", result.label);
    button.type = "button";
    button.role = "option";
    button.id = `place-option-${i}`;
    button.tabIndex = -1;
    button.setAttribute("aria-selected", "false");
    button.append(
      node(
        "small",
        result.subtitle ||
          (result.kind === "city" ? "City · catalog locations" : "State"),
      ),
    );
    button.addEventListener("mousedown", (e) => e.preventDefault());
    button.addEventListener("click", () => chooseSearch(result));
    li.append(button);
    list.append(li);
  }
  $("place-query").setAttribute(
    "aria-expanded",
    String(list.childElementCount > 0),
  );
}
function chooseSearch(result) {
  closeSearch();
  $("place-query").value =
    result.kind === "facility"
      ? `${result.label}, ${result.subtitle}`
      : result.label;
  browseMode = true;
  listLimit = 60;
  if (result.kind === "facility") {
    browseScope = { ids: [result.id], label: "Facility search" };
    selectFacilityById(result.id, true);
    setDrawer("courses", true);
  } else {
    const records =
      result.kind === "state"
        ? catalogModel.records.filter((f) => f.state === result.id)
        : result.records;
    browseScope = { ids: records.map((f) => f.id), label: result.label };
    setDrawer("courses", true);
    const points =
      result.kind === "state"
        ? shapeRings(result.state).flat()
        : records
            .filter(located)
            .map((f) => [f.map_location.latitude, f.map_location.longitude]);
    fitPoints(points, result.kind === "city" ? 12 : 10);
    renderCourses();
  }
}
function renderProgress() {
  if (!catalogModel) return;
  const counts = catalogCounts(catalogModel.records);
  $("progress-counts").replaceChildren(
    ...[
      [counts.onMap, "On map"],
      [counts.pending, "Not yet on map"],
    ].map(([n, label]) => {
      const d = node("div");
      d.append(node("strong", fmt(n)), node("span", label));
      return d;
    }),
  );
  const open = new Set(
    [...$("activity-log").querySelectorAll("details[open]")].map(
      (d) => d.dataset.commit,
    ),
  );
  const batches = activityBatches(additions, progress).slice(0, 12);
  $("activity-log").replaceChildren(
    ...batches.map((b) => {
      const article = node("article", undefined, "activity-batch"),
        time = node("time", chicagoTime(b.committedAt));
      if (b.committedAt) time.dateTime = b.committedAt;
      time.title = `${b.reported ? "Reported" : "Committed"} ${b.committedAt || "time unknown"}`;
      const changes = b.baseline
        ? `Initial catalog · ${fmt(b.added)} facilities`
        : [
            b.added ? `${fmt(b.added)} added` : "",
            b.updated ? `${fmt(b.updated)} updated` : "",
            b.removed ? `${fmt(b.removed)} removed` : "",
          ]
            .filter(Boolean)
            .join(" · ") || "Catalog update";
      article.append(time, node("strong", changes));
      const detail = node("details");
      detail.dataset.commit = b.commit;
      detail.open = open.has(b.commit);
      detail.append(node("summary", "Changes"));
      if (b.correction) detail.append(node("p", b.correction));
      for (const f of (b.facilities || []).slice(0, 20))
        detail.append(node("p", `${f.name}, ${f.state}`));
      const a = node("a", "Committed change");
      a.href = `https://github.com/snowball-projects/fairway/commit/${b.commit}`;
      detail.append(a);
      article.append(detail);
      return article;
    }),
  );
  if (!batches.length)
    $("activity-log").append(node("p", "History unavailable."));
}
function drawCounties() {
  const focused = document.activeElement?.dataset.countyId;
  countiesLayer.clearLayers();
  if (!$("show-counties").checked || !geometry || !catalogModel) return;
  const polygons = [];
  for (const [index, shape] of geometry.counties.entries()) {
    const polygon = L.polygon(shapeRings(shape), {
      color: "#6b8073",
      weight: 0.5,
      fillOpacity: 0,
      opacity: 0.5,
    });
    const activate = (coordinate) => {
      popupSelection = { kind: "county", id: shape.id, coordinate };
      openSelectionPopup();
    };
    polygon.on("click", (event) => activate(event.latlng));
    polygon.on("add", () => {
      const path = polygon.getElement();
      if (!path) return;
      path.dataset.countyId = shape.id;
      path.setAttribute("role", "button");
      path.setAttribute("tabindex", index === countyIndex ? "0" : "-1");
      path.setAttribute(
        "aria-label",
        `${shape.name}, ${shape.state}: ${catalogModel.byId.get(shape.id)?.records.length ?? "unknown"} catalog facilities`,
      );
      path.addEventListener("focus", () => {
        if (!map.getBounds().contains(polygon.getBounds().getCenter()))
          fitPoints(
            [
              polygon.getBounds().getSouthWest(),
              polygon.getBounds().getNorthEast(),
            ],
            10,
          );
      });
      path.addEventListener("keydown", (event) => {
        if (["Enter", " "].includes(event.key)) {
          event.preventDefault();
          activate(polygon.getBounds().getCenter());
        } else if (
          ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(
            event.key,
          )
        ) {
          event.preventDefault();
          event.stopPropagation();
          countyIndex =
            (index +
              (["ArrowRight", "ArrowDown"].includes(event.key) ? 1 : -1) +
              polygons.length) %
            polygons.length;
          polygons.forEach((p, i) =>
            p
              .getElement()
              ?.setAttribute("tabindex", i === countyIndex ? "0" : "-1"),
          );
          const next = polygons[countyIndex];
          fitPoints(
            [next.getBounds().getSouthWest(), next.getBounds().getNorthEast()],
            10,
          );
          next.getElement()?.focus({ preventScroll: true });
        }
      });
    });
    polygons.push(polygon);
    polygon.addTo(countiesLayer);
  }
  countiesLayer.addTo(map);
  if (focused)
    [...countiesLayer.getLayers()]
      .find((p) => p.getElement()?.dataset.countyId === focused)
      ?.getElement()
      ?.focus({ preventScroll: true });
}

function applyCatalog(catalog) {
  const next = buildModel(catalog);
  catalogDate = catalog.updated_on || "";
  catalogModel = next;
  if (activeFacility && !next.records.some((f) => f.id === activeFacility))
    closeSelection();
  const counts = catalogCounts(next.records);
  $("catalog-status").textContent =
    `${fmt(counts.onMap)} on map · ${fmt(counts.pending)} pending${$("show-estimates").checked ? ` · ${fmt(counts.estimates)} estimates shown` : ""}`;
  drawFacilities();
  renderCourses();
  renderProgress();
  drawCounties();
  if (cataloguePopup?.isOpen() && popupSelection) openSelectionPopup();
}
$("calculate").onclick = async () => {
  $("calculate").disabled = true;
  if (!state.ready) await configure();
  if (state.ready) calculate();
  else
    $("calculate").disabled =
      state.rows.filter((row) => row.coordinate).length < 2;
};
$("cancel-calculate").onclick = () => {
  updatePlan();
  setStatus("Comparison cancelled.");
};
$("plan-toggle").onclick = () => setDrawer("plan", $("plan-panel").hidden);
$("courses-toggle").onclick = () =>
  setDrawer("courses", view.resultsPanel.hidden);
$("close-plan").onclick = () => setDrawer("plan", false);
$("close-courses").onclick = () => setDrawer("courses", false);
$("progress-toggle").onclick = () => $("catalog-progress").showModal();
$("close-progress").onclick = () => $("catalog-progress").close();
$("catalog-progress").addEventListener("click", (e) => {
  if (e.target === $("catalog-progress")) {
    const b = e.target.getBoundingClientRect();
    if (
      e.clientX < b.left ||
      e.clientX > b.right ||
      e.clientY < b.top ||
      e.clientY > b.bottom
    )
      e.target.close();
  }
});
$("browse-mode").onclick = () => {
  browseMode = true;
  renderCourses();
};
$("ranking-mode").onclick = () => {
  browseMode = false;
  renderCourses();
};
for (const id of ["browse-holes", "browse-access", "browse-sort"])
  $(id).onchange = () => {
    listLimit = 60;
    renderCourses();
  };
$("show-estimates").onchange = () => {
  drawFacilities();
  if (catalogModel) {
    const counts = catalogCounts(catalogModel.records);
    $("catalog-status").textContent =
      `${fmt(counts.onMap)} on map · ${fmt(counts.pending)} pending${$("show-estimates").checked ? ` · ${fmt(counts.estimates)} estimates shown` : ""}`;
  }
};
$("show-counties").onchange = () => {
  if (!$("show-counties").checked) map.removeLayer(countiesLayer);
  else drawCounties();
};
$("us-view").onclick = () => {
  browseScope = null;
  listLimit = 60;
  fitPoints(
    [
      [24, -125],
      [50, -66],
    ],
    5,
  );
  renderCourses();
};
$("search-area").onclick = () => {
  browseScope = { kind: "viewport", label: "Mapped facilities in this area" };
  browseMode = true;
  listLimit = 60;
  setDrawer("courses", true);
  renderCourses();
  $("search-area").hidden = true;
};
$("place-query").oninput = showSearch;
$("place-query").onkeydown = (e) => {
  const options = [...$("place-suggestions").querySelectorAll("button")];
  if (["ArrowDown", "ArrowUp"].includes(e.key) && options.length) {
    e.preventDefault();
    searchIndex =
      (searchIndex + (e.key === "ArrowDown" ? 1 : -1) + options.length) %
      options.length;
    options.forEach((b, i) =>
      b.setAttribute("aria-selected", String(i === searchIndex)),
    );
    $("place-query").setAttribute(
      "aria-activedescendant",
      options[searchIndex].id,
    );
  } else if (e.key === "Enter" && options.length) {
    e.preventDefault();
    chooseSearch(searchMatches[Math.max(searchIndex, 0)]);
  } else if (e.key === "Escape") closeSearch();
};
$("catalog-search").onsubmit = (e) => {
  e.preventDefault();
  showSearch();
  if (searchMatches.length === 1) chooseSearch(searchMatches[0]);
  else if (!searchMatches.length) {
    browseScope = { ids: [], label: "No local catalog matches" };
    setDrawer("courses", true);
    renderCourses();
  }
};
document.addEventListener("click", (e) => {
  if (!$("catalog-search").contains(e.target)) closeSearch();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    closeSearch();
    closeSelection();
  }
});
map.on("moveend zoomend", () => {
  drawFacilities();
  if (catalogModel) {
    $("search-area").hidden = false;
  }
});
map.on("popupclose", (e) => {
  if (e.popup === cataloguePopup) {
    popupSelection = null;
    cataloguePopup = null;
  }
});
async function loadCatalog() {
  try {
    const r = await fetch("/research-map/boundaries.json");
    if (!r.ok) throw new Error();
    geometry = await r.json();
  } catch {
    geometry = { states: [], counties: [] };
  }
  watchSnapshots({
    publicationPath: "/research-map/publication.json",
    dataPath: "/data/",
    onCatalog: applyCatalog,
    onProgress: (v) => {
      progress = v ? parseProgress(v) : null;
      renderProgress();
    },
    onAdditions: (v) => {
      additions = v ? parseAdditions(v) : null;
      renderProgress();
    },
    onStatus: ({ state: status }) => {
      if (status === "delayed")
        $("catalog-status").textContent = catalogModel
          ? "Catalog updates delayed; current records retained."
          : "Catalog unavailable · retrying.";
    },
  });
}
addOrigin();
addOrigin();
loadCatalog();
