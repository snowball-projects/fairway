import {located,mapEligible,catalogCounts,cityLabel,searchCatalog,courseMatches,sortCourses,browseCard,STYLES,priceFacts} from "./catalog-read.mjs";
import {shapeRings} from "./catalog.mjs"; // Static state geometry only.
import { createFacilityDots } from "./facility-dots.mjs";
import {
  canRemoveOrigin,
  originLimit,
  requiredOriginRows,
} from "./origin-rows.mjs";
import { LogicalPlanningSession } from "./logical-planning-session.mjs";

// A local harness may inject the reviewed staged adapter before module loading.
// No national endpoint or authentication/CORS change is selected implicitly.
const planningAdapter = await (globalThis.__fairwayPlanningAdapter || null);
const catalogAdapter = await (globalThis.__fairwayCatalogAdapter || null);
let planningSession = null;
const meetingLayer = L.layerGroup();
const preparationFacilities = L.layerGroup();
let planningMode = false;
let planningDisplaySort = "maximum";
const rankingNodes = new Map();
const rowInteractions = new Set();


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
  ranking: null,
  activeRows: [],
  activeCourse: null,
  request: null,
  photonBbox: null,
  coreBounds: [24, -125, 50, -66],
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
planningAdapter?.offlineMap?.(L, map);
meetingLayer.addTo(map);
preparationFacilities.addTo(map);
new ResizeObserver(() => map.invalidateSize()).observe(
  document.querySelector("#map"),
);

function setStatus(message, error = false) {
  view.status.textContent = message;
  view.status.dataset.error = String(error);
  const resultsStatus = document.getElementById("preparation-status");
  resultsStatus.textContent = message;
  resultsStatus.dataset.error = String(error);
  resultsStatus.hidden = !planningMode;
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
  if (seconds === null || seconds === undefined) return "Pending";
  if (!Number.isFinite(seconds) || seconds < 0) return "Unavailable";
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
    row.lookupPromise = null;
    row.lookupQuery = null;
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

function committedOrigins() {
  return state.rows.filter(row => row.coordinate).map(row => ({id:row.id, coordinate:row.coordinate}));
}
function fitCommittedOrigins() {
  const points = state.rows.filter(row => row.coordinate).map(row => row.coordinate);
  requestAnimationFrame(() => { map.invalidateSize({animate:false}); fitPoints(points, points.length === 1 ? 14 : 12); });
}
function syncPlanning() {
  if (planningMode && planningSession) planningSession.update(committedOrigins(), selected("objective"), selectedHoles());
}
function setOrigin(row, label, coordinate) {
  if (!state.rows.includes(row)) return;
  row.input.value = label;
  row.committedLabel = label.trim();
  row.coordinate = coordinate;
  closeSuggestions(row, true);
  updateOriginMarker(row);
  updatePlan();
  syncPlanning();
  fitCommittedOrigins();
}
async function commitOrigin(row, trigger = "blur") {
  const query = row.input.value.trim();
  if (row.coordinate && row.committedLabel === query) {
    if (trigger === "enter" && planningSession?.error?.retryable) planningSession.retry();
    else if (trigger === "enter" && planningMode && !planningSession?.key && !planningSession?.blocked) syncPlanning();
    return true;
  }
  if (row.lookupPromise && row.lookupQuery === query && row.controller && !row.controller.signal.aborted) return row.lookupPromise;
  if (!query) {if(planningMode&&planningSession?.hasAdmitted)syncPlanning();return false;}
  if (query.length < 3 || query.length > 256) return false;
  const coordinate = parseCoordinate(query);
  if (coordinate) { if (!insideCore(coordinate)) { setStatus("Enter a valid lower 48 coordinate (latitude, longitude).", true); return false; } setOrigin(row, query, coordinate); return true; }
  if (looksLikeCoordinateInput(query)) return false;
  const controller = new AbortController();
  row.controller = controller; row.lookupQuery = query;
  row.lookupPromise = (async () => {
    try {
      let result;
      if (planningAdapter?.resolveOrigin) result = await planningAdapter.resolveOrigin(query);
      else throw new Error("Offline address fixture unavailable");
      if (!state.rows.includes(row) || row.controller !== controller || row.input.value.trim() !== query) return false;
      const choices = (result.features || []).slice(0,5).map(feature => ({feature, coordinate:feature?.geometry?.coordinates}))
        .filter(value => Array.isArray(value.coordinate) && value.coordinate.length >= 2 && value.coordinate.every(Number.isFinite) && Math.abs(value.coordinate[1]) <= 90 && Math.abs(value.coordinate[0]) <= 180);
      if (choices.length === 1) {
        const choice = choices[0]; setOrigin(row, address(choice.feature) || query, [choice.coordinate[1], choice.coordinate[0]]); return true;
      }
      closeSuggestions(row);
      for (const choice of choices) {
        const button = document.createElement("button"); button.type = "button"; button.role = "option"; button.tabIndex = -1;
        button.id = `${row.suggestions.id}-option-${row.suggestions.childElementCount}`; button.setAttribute("aria-selected","false");
        button.textContent = address(choice.feature) || query; button.onmousedown = event => event.preventDefault();
        button.onclick = () => setOrigin(row, button.textContent, [choice.coordinate[1],choice.coordinate[0]]);
        const item = document.createElement("li"); item.role = "none"; item.append(button); row.suggestions.append(item);
      }
      row.input.setAttribute("aria-expanded", String(choices.length > 0));
      setStatus(choices.length ? "Choose the matching address." : "Address not found. Check the complete address.", !choices.length);
      return false;
    } catch (error) {
      if (error.name !== "AbortError" && row.controller === controller) setStatus("Address suggestions are unavailable. Try the address again.", true);
      return false;
    } finally {
      if (row.controller === controller) {
        row.controller = null; row.lookupPromise = null; row.lookupQuery = null;
      }
    }
  })();
  return row.lookupPromise;
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
    id: `o${nextOriginId-1}`,
    committedLabel: null,
    lookupQuery: null,
    lookupPromise: null,
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
    row.coordinate = null; row.committedLabel = null;
    row.marker?.remove(); row.marker = null;
    updatePlan();
    planningSession?.invalidate(committedOrigins());
    // Keystrokes invalidate local state only. No timer or preparation runs.
  };
  row.input.onkeydown = (event) => {
    if (event.key === "ArrowDown" && moveSuggestion(row, 1)) {
      event.preventDefault();
    } else if (event.key === "ArrowUp" && moveSuggestion(row, -1)) {
      event.preventDefault();
    } else if (event.key === "Enter" && !event.isComposing) {
      event.preventDefault();
      if (!chooseActiveSuggestion(row)) commitOrigin(row, "enter");
    } else if (event.key === "Escape") {
      closeSuggestions(row, true);
    }
  };
  row.input.onblur = () => commitOrigin(row, "blur");
  remove.onclick = () => {
    const index = state.rows.indexOf(row);
    if (!canRemoveOrigin(state.rows.length, index)) return;
    row.controller?.abort();
    row.marker?.remove();
    state.rows.splice(index, 1);
    element.remove();
    renumber();
    updatePlan();
    syncPlanning();
    fitCommittedOrigins();
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
    const canRemove = canRemoveOrigin(state.rows.length, index);
    row.number.textContent = index + 1;
    row.input.placeholder = `Golfer ${index + 1} address`;
    row.input.ariaLabel = `Golfer ${index + 1} origin`;
    row.suggestions.ariaLabel = `Address suggestions for Golfer ${index + 1}`;
    row.remove.ariaLabel = `Remove golfer ${index + 1}`;
    row.remove.hidden = !canRemove;
    row.remove.disabled = !canRemove;
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
  state.ranking = null;
  state.activeRows = [];
  state.activeCourse = null;
  view.results.setAttribute("aria-busy", "false");
  view.results.replaceChildren();
  view.resultCount.textContent = "";
  view.rankingDescription.textContent = "";
  browseMode = true;
  drawFacilities();
  renderCourses();
}

function updatePlan() {
  clearRanking();
  const count = state.rows.filter((row) => row.coordinate).length;
  setStatus(
    count ? "Preparing nearby courses…" : "Enter a golfer address.",
  );
}

function renderPreparation(session) {
  state.routingCatalogLabel="Synthetic logical-plan fixture · no live travel times";
  state.activeRows = session.origins.map(origin => state.rows.find(row => row.id === origin.id));
  const courses = session.courseCards();
  const facilities = [...new Map(courses.filter(course=>course.coordinate).map(course=>[course.facility_id,course])).values()].sort((a,b)=>a.facility_id.localeCompare(b.facility_id));
  const facilityKey = JSON.stringify(facilities.map(course=>[course.facility_id,course.coordinate,course.facility_name]));
  if (preparationFacilities.key !== facilityKey) {
    preparationFacilities.key = facilityKey;preparationFacilities.clearLayers();
    for (const course of facilities.filter(c=>!catalogModel?.facilityById.has(c.facility_id))) {
      const label = document.createElement("span");label.textContent = course.facility_name;
      L.circleMarker(course.coordinate,{radius:7,color:"#fff",weight:2,fillColor:"#1d644b",fillOpacity:.95,className:"preparation-facility"})
        .bindTooltip(label,{className:"preparation-facility-label"}).on("click",()=>selectCourse(course.id,true)).addTo(preparationFacilities);
    }
  }
  state.ranking = {courses, objective: session.objective, holes: session.holes, phase: session.phase, error:session.error, blocked:session.blocked};
  const areaKey = JSON.stringify(session.areas);
  if (meetingLayer.areaKey !== areaKey) {
    meetingLayer.areaKey = areaKey; meetingLayer.clearLayers();
    for (const area of session.areas) {
      const shape = Number.isFinite(area.resolution_kilometers) && area.resolution_kilometers > 0
        ? L.circle(area.center, {radius: area.resolution_kilometers * 1000, color: "#d2a344", weight: 2, fillOpacity: .12})
        : L.circleMarker(area.center, {radius: 9, color: "#d2a344", weight: 2, fillOpacity: .3});
      shape.bindTooltip(`modo meeting area${area.approximate ? " (approximate)" : ""}`, {permanent: true, direction: "top", className: "meeting-area-label"}).addTo(meetingLayer).bringToFront();
    }
  }
  if (planningMode) {
    browseMode = false;
    // Preserve the active address field in the existing mobile sheet flow.
    if (session.origins.length && (!mobile() || !$("plan-panel").contains(document.activeElement))) setDrawer("courses", true);
    renderCourses();
  }
  view.results.setAttribute("aria-busy", String(Boolean(session.active || session.pending)));
  $("cancel-calculate").hidden = !session.origins.length || ["complete", "partial", "error"].includes(session.phase);
  if (session.blocked) setStatus("Driving-time comparison is blocked until the outstanding routing work is reconciled.", true);
  else if (session.error?.code === "preparation_read_incomplete") setStatus("Course results could not be read completely. The comparison is unavailable.", true);
  else if (session.error) setStatus(session.error.retryable
    ? "Driving times are unavailable. Press Enter in an origin field to retry."
    : "Driving times are unavailable.", true);
  else if (session.limited) setStatus(`Routing work reached its limit. ${courses.filter(c=>c.maximum_seconds!==null).length} provisional comparisons retained; remaining courses are unscored${session.areaSearchComplete===false?" and the modo area search is incomplete":""}.`);
  else if (session.phase === "clearing") setStatus("Inputs cleared. Waiting for previously started driving-time work.");
  else if (session.phase === "cleared") setStatus("Comparison cleared.");
  else if (session.phase === "area") setStatus("Preparing nearby driving times and finding a modo meeting area…");
  else if (session.phase === "partial") setStatus(`${courses.filter(c => c.maximum_seconds !== null).length} courses compared; ${courses.filter(c => c.maximum_seconds === null && !c.reason).length} still awaiting driving times.`);
  else if (session.phase === "complete") setStatus(courses.length ? `${courses.filter(c => !c.reason).length} nearby courses compared without traffic.` : "No eligible documented courses within the selected radius.");
  else if (session.origins.length) setStatus("Nearby courses shown. Driving times are being prepared…");
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
    if (course.coordinate) fitPoints([course.coordinate], 14);
    selectFacilityById(course.facility_id, false);
  };
  const rank = document.createElement("span");
  rank.className = "rank";
  rank.textContent = course.rank ?? "…";
  rank.hidden = course.browseOnly === true;
  const body = document.createElement("span");
  const title = document.createElement("span");
  title.className = "course-title";
  title.setAttribute("role", "heading");
  title.setAttribute("aria-level", "3");
  title.textContent = course.course_name === null ? course.facility_name : course.name;
  const meta = document.createElement("span");
  meta.className = "course-meta";
  [course.course_name === null ? "Course name not recorded" : null, course.holes === null ? "Holes unconfirmed" : course.holes + " holes", course.course_name === null ? null : course.facility_name, course.access, course.identity_status === "needs_review" ? "Course identity unconfirmed" : null].filter(Boolean).forEach((label) => {
    const value = document.createElement("span");
    value.textContent = label;
    meta.append(value);
  });
  const scores = document.createElement("span");
  scores.className = "score-row";
  [
    ["maximum", course.maximum_seconds === null ? "Pending" : duration(course.maximum_seconds), "longest drive"],
    ["combined", course.combined_seconds === null ? "Pending" : duration(course.combined_seconds), "combined drive"],
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
  if (course.browseOnly) {scores.hidden = true;body.style.gridColumn = "1 / -1";}
  focus.append(rank, body);
  const times = document.createElement("ul");
  times.className = "golfer-times";
  times.hidden = course.browseOnly === true;
  course.travel_times_seconds.forEach((seconds, index) => {
    const time = document.createElement("li");
    time.className = "golfer-time";
    time.style.setProperty(
      "--golfer",
      state.activeRows[index]?.color || COLORS[index],
    );
    const value = seconds === null ? "Pending" : duration(seconds);
    time.textContent = `${index + 1} · ${value}`;
    time.ariaLabel = `Golfer ${index + 1}: ${value}`;
    times.append(time);
  });
  const footer = document.createElement("div");
  footer.className = "card-footer";
  const address = document.createElement("span");
  address.textContent = `${course.address} · ${course.routing_basis === "arrival_unavailable" ? "Routing destination unavailable" : course.routing_basis === "approximate_facility_point" ? "approximate facility point, course arrival unverified" : course.destination_kind === "verified_entrance" ? "verified entrance" : course.destination_kind === "property_point" ? "property point, entrance unverified" : "reviewed OSM routing point"}`;
  const link = document.createElement("a");
  let safeWebsite=null;try{const candidate=new URL(course.website);if(["https:","http:"].includes(candidate.protocol))safeWebsite=candidate.href;}catch{}
  if(safeWebsite)link.href = safeWebsite;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.textContent = "Course site";
  footer.append(address);
  if (safeWebsite) footer.append(link);
  article.append(focus, times, footer);
  if(course.browseOnly)article.append(courseMetadata(course));
  item.append(article);
  return item;
}

function courseMetadata(course) {
  const details=node("details",undefined,"course-facts");details.append(node("summary","Course details"));
  details.append(node("p",course.game_kind==="obstacle_minigolf"?"Obstacle miniature golf":STYLES[course.style] || "Style unconfirmed"));
  const rounds=course.round_options||[];
  details.append(node("p",rounds.length?rounds.map(r=>`${r.round_holes} hole round${r.scope==='facility'?" · documented course combination":""}`).join("; "):"Round options not documented"));
  if(course.booking_conditions)details.append(node("p",course.booking_conditions));
  details.append(node("p",course.nonmember_bookable===true?"Nonmember booking documented; availability unknown":course.nonmember_bookable===false?"Ordinary nonmember booking unavailable":"Nonmember booking unconfirmed"));
  const prices=priceFacts(course.source_course || course);
  if(!prices.length)details.append(node("p","Price information not recorded"));
  for(const fact of prices) {
    const g=fact.group,p=fact.payload;
    const amounts=['amount','green_fee_low','green_fee_high','cart_fee_low','cart_fee_high'].filter(k=>Number.isFinite(p[k])&&p[k]>=0).map(k=>`${k.replaceAll('_',' ')}: ${p[k]}`);
    details.append(node("p",fact.known?`${p.currency} · ${p.basis} · ${amounts.join("; ")} · ${fact.scope} scope${p.historical===true?" · historical information":""}${p.current_rate!==true?" · current rate unconfirmed":""}${fact.conflict?" · conflicting observations":""}`:"Price observation has unknown or incomplete fields"));
    if(typeof p.qualification==='string')details.append(node("p",p.qualification));
    if(g.observed_on)details.append(node("p",`Observed ${g.observed_on} · collected ${g.collected_on || "date unknown"} · ${g.status}`));
    if(typeof p.source_information_as_of==='string')details.append(node("p",`Source information dated ${p.source_information_as_of}`));
    try {const url=new URL(g.source_url);if(['https:','http:'].includes(url.protocol)){const link=node("a","Price source");link.href=url.href;link.target="_blank";link.rel="noopener noreferrer";details.append(link);}}catch{}
  }
  details.append(node("p","Amenities and quality ratings unconfirmed"));
  return details;
}

function renderRanking(result) {
  const sort = $("browse-sort").value;
  const originIndex = sort.startsWith("origin:") ? state.activeRows.findIndex(row => row?.id === sort.slice(7)) : -1;
  const value = course => sort === "holes" ? course.holes : sort === "name" ? null : originIndex >= 0 ? course.travel_times_seconds[originIndex] : course[`${sort}_seconds`];
  result = {...result, courses:result.courses.filter(course => matchesCourseFilters(course.source_course || {access:course.access === "Public play"?"public":course.access === "Access unconfirmed"?"unknown":course.access.toLowerCase(),state:course.state,physical_holes:course.holes,plan_eligible:course.plan_eligible,style:course.style,round_options:course.round_options,fact_groups:course.fact_groups})).sort((a,b) => {
    if (sort === "name") return a.name.localeCompare(b.name);
    const av=value(a),bv=value(b);return av===null?(bv===null?0:1):bv===null?-1:av-bv||a.name.localeCompare(b.name);
  })};
  result.courses.forEach((course, index) => { course.rank = ["maximum","combined"].includes(sort) && course.maximum_seconds !== null ? index + 1 : null; });
  let list = view.results.querySelector(".course-list");
  if (!list || list.dataset.planning !== "true") {
    rankingNodes.clear(); rowInteractions.clear(); list = document.createElement("ol");
    list.className = "course-list"; list.dataset.planning = "true"; view.results.replaceChildren(list);
  }
  const desired = result.courses.map(course => course.id);
  const pendingOrder = JSON.stringify([...list.children].map(item => item.firstElementChild.dataset.courseId)) !== JSON.stringify(desired);
  for (const course of result.courses) {
    let item = rankingNodes.get(course.id);
    if (!item) {
      item = courseCard(course, result.objective); rankingNodes.set(course.id, item); list.append(item);
      const article = item.firstElementChild;
      article.addEventListener("focusin", () => rowInteractions.add(`focus:${course.id}`));
      article.addEventListener("focusout", event => {
        if (article.contains(event.relatedTarget)) return;
        const next = event.relatedTarget?.closest(".course-card");
        if (next && view.results.contains(next)) rowInteractions.add(`focus:${next.dataset.courseId}`);
        rowInteractions.delete(`focus:${course.id}`); renderCourses();
      });
      article.addEventListener("mouseenter", () => rowInteractions.add(`pointer:${course.id}`));
      article.addEventListener("mouseleave", () => {rowInteractions.delete(`pointer:${course.id}`);renderCourses();});
    }
    const article = item.firstElementChild;
    article.querySelector(".rank").textContent = rowInteractions.size && pendingOrder ? "…" : course.rank ?? "…";
    article.querySelectorAll(".score").forEach((score, index) => {
      const kind = index ? "combined" : "maximum", seconds = course[`${kind}_seconds`];
      score.classList.toggle("primary", kind === result.objective);
      score.querySelector("strong").textContent = result.blocked ? "Blocked" : result.error ? "Unavailable" : course.reason ? "Unranked" : seconds === null ? "Pending" : duration(seconds);
    });
    const times = article.querySelector(".golfer-times");
    while (times.children.length > course.travel_times_seconds.length) times.lastElementChild.remove();
    course.travel_times_seconds.forEach((seconds, index) => {
      let time = times.children[index]; if (!time) {time = document.createElement("li");time.className = "golfer-time";times.append(time);}
      time.style.setProperty("--golfer", state.activeRows[index]?.color || COLORS[index]);
      const reason = course.travel_time_reasons?.[index];
      const value = result.blocked ? "Blocked" : result.error ? "Unavailable" : seconds === null ? reason === "arrival_unavailable" ? "Destination unavailable" : reason === "error" ? "Unavailable" : reason === "outside-road-coverage" ? "Outside road coverage" : reason ? "Unreachable" : "Pending" : duration(seconds);
      time.textContent = `${index + 1} · ${value}`;time.ariaLabel = `Golfer ${index + 1}: ${value}`;
    });
  }
  for (const [id, item] of rankingNodes) if (!desired.includes(id)) {
    if ([...rowInteractions].some(key => key.endsWith(`:${id}`))) {
      item.querySelector(".rank").textContent = "…";
      item.querySelectorAll(".score strong").forEach(n => n.textContent = "Outside current regions");
      item.querySelectorAll(".golfer-time").forEach(n => n.textContent = "Pending");
    } else {item.remove();rankingNodes.delete(id);}
  }
  if (!rowInteractions.size) desired.forEach((id, index) => {
    const item = rankingNodes.get(id), current = list.children[index];
    if (item !== current) list.insertBefore(item, current || null);
  });
  view.resultCount.textContent = `${result.courses.length} ${result.courses.length === 1 ? "course" : "courses"}`;
  view.rankingDescription.textContent =
    (result.blocked ? "Driving-time comparison is blocked. " : result.error ? "Driving times are unavailable. " : result.phase && result.phase !== "complete" ? "Some driving times are pending; ranking is provisional. " : "") + `Sorted by ${$("browse-sort").selectedOptions[0].textContent.toLowerCase()}.` + (rowInteractions.size && pendingOrder ? " Order updates after course interaction ends." : "");
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


view.addOrigin.onclick = addOrigin;
document
  .querySelectorAll('input[name="objective"], input[name="holes"]')
  .forEach((input) => {
    input.onchange = () => { updatePlan(); syncPlanning(); };
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
const facilityDots = createFacilityDots(
  L,
  map,
  (id) => selectFacilityById(id, false),
  (ids, coordinate) => {
    popupSelection = { kind: "coincident", ids, coordinate };
    openSelectionPopup();
  },
);
let catalogDate = "";
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
function drawFacilities() {
  if (!catalogModel) return;
  facilityDots.update(catalogModel.facilities, activeFacility);
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
  article.dataset.facilityId = f.facility_id;
  article.dataset.active = String(activeFacility === f.facility_id);
  const title = node("button", f.name);
  title.type = "button";
  title.addEventListener("click", () => selectFacilityById(f.facility_id, true));
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
      f.access ? `${f.access} facility access · course booking conditions may differ` : "Facility access unconfirmed",
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
  if (f.course_inventory?.length) {
    const details = node("details");
    details.append(
      node(
        "summary",
        `${f.course_inventory.length} retained ${f.course_inventory.length === 1 ? "course" : "courses"}`,
      ),
    );
    for (const c of f.course_inventory)
      details.append(
        node(
          "p",
          `${c.name || "Unnamed course"} · ${c.physical_holes ?? "?"} holes · ${c.access} access`,
        ),
      );
    if (f.access_note) details.append(node("p", f.access_note));
    article.append(details);
  } else
    article.append(node("p", "Individual course inventory not recorded; no course cards inferred"));
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
  const times = (planningMode && !browseMode ? state.ranking?.courses || [] : []).filter(
    (c) => c.facility_id === f.facility_id,
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
  const f = catalogModel?.facilities.find((r) => r.facility_id === id);
  if (!f) return;
  activeFacility = id;
  if (fit && located(f))
    fitPoints([[f.map_location.latitude, f.map_location.longitude]], 15);
  if (located(f) && mapEligible(f)) {
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
    const f = catalogModel.facilities.find((r) => r.facility_id === popupSelection.id);
    if (!f) {
      closeSelection();
      return;
    }
    content.append(facilityDetails(f));
  } else {
    content.append(
      node("h3", `${popupSelection.ids.length} facilities at this point`),
    );
    for (const id of popupSelection.ids) {
      const f = catalogModel.facilities.find((r) => r.facility_id === id);
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
function filterOptions() {
  return {state:$("browse-state").value,access:$("browse-access").value,holes:$("browse-holes").value,
    roundHoles:$("browse-round").value,style:$("browse-style").value,price:$("browse-price").value};
}
function scopedRecords() {
  if (!catalogModel) return [];
  return sortCourses(catalogModel.courses.filter(course=>courseMatches(course,{...filterOptions(),
    bounds:browseScope?.kind === "viewport"?map.getBounds():null,
    facilityIds:browseScope?.ids?new Set(browseScope.ids):null})), $("browse-sort").value);
}
function matchesCourseFilters(course) {return courseMatches(course,filterOptions());}
function updateDisplaySortOptions() {
  const sort = $("browse-sort"), choices = [["name","Name"],["holes","Physical course holes"]];
  if (planningMode) choices.push(["maximum","Longest driving time"],["combined","Combined driving time"],
    ...state.rows.filter(row => row.coordinate).map(row => [`origin:${row.id}`,`Golfer ${state.rows.indexOf(row)+1} driving time`]));
  const key = JSON.stringify(choices);
  if (sort.optionsKey !== key) {
    sort.optionsKey = key;sort.replaceChildren(...choices.map(([value,label]) => {const option=document.createElement("option");option.value=value;option.textContent=label;return option;}));
  }
  const value = planningMode && choices.some(([value]) => value === planningDisplaySort) ? planningDisplaySort : choices.some(([value])=>value===sort.value)?sort.value:"name";
  sort.value = value;
}
function renderCourses() {
  if (!catalogModel) return;
  view.catalogName.textContent = browseMode
    ? `Catalog ${catalogDate || "date unknown"}`
    : state.routingCatalogLabel;
  updateDisplaySortOptions();
  $("browse-access").querySelector('[value="nonmember"]').hidden = !planningMode;
  $("browse-description").hidden = !browseMode;
  view.rankingDescription.hidden = browseMode;
  $("preparation-status").hidden = !planningMode;
  if (!planningMode) {preparationFacilities.clearLayers();preparationFacilities.key = null;}
  if (planningMode && !browseMode && state.ranking) {
    renderRanking(state.ranking);
    return;
  }
  const records = scopedRecords();
  view.resultCount.textContent = fmt(records.length);
  $("browse-description").textContent =
    browseScope?.label || "Retained course records. Identities and booking may need review; unresolved facilities remain on the map.";
  const nodes = [];
  if (activeFacility) {
    const selected = catalogModel.facilities.find((r) => r.facility_id === activeFacility);
    if (selected) {
      nodes.push(facilityDetails(selected));
      nodes.push(node("hr"));
    }
  }
  const browseList = node("ol", undefined, "course-list");
  for (const course of records.slice(0,listLimit)) browseList.append(courseCard(browseCard(course,catalogModel.destinations),selected("objective")));
  nodes.push(browseList);
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
    catalogModel?.facilities || [],
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
  planningMode = false; planningSession?.invalidate(committedOrigins()); $("browse-access").value = "all"; setDrawer("plan", false);
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
        ? catalogModel.facilities.filter((f) => f.state === result.id)
        : result.records;
    browseScope = { ids: records.map((f) => f.facility_id), label: result.label };
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
  const counts = catalogCounts(catalogModel.facilities);
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
  const provenance=$("native-provenance");
  provenance.replaceChildren(node("p",`Catalog revision ${catalogModel.revision}. ${catalogModel.qualification || "Native read qualification unavailable."}`),
    node("p","Facility property points are map context, not canonical course arrivals. Retained course records may need identity review; actual booking and availability remain separately qualified."));
  const groups=new Map();
  for(const record of [...catalogModel.facilities,...catalogModel.courses])for(const group of record.fact_groups||[]) {
    const key=JSON.stringify([group.id,group.facility_id,group.course_id]);if(!groups.has(key))groups.set(key,group);
  }
  if(!groups.size)provenance.append(node("p","No field-level source observations are supplied by these selected native examples."));
  for(const group of groups.values()) {
    const entry=node("p",`${group.module} · ${group.course_id?"course":"facility"} scope · ${group.status || "status unknown"} · observed ${group.observed_on || "date unknown"} · collected ${group.collected_on || "date unknown"}${group.conflict===true?" · conflicting observations":""}`);
    try {const url=new URL(group.source_url);if(["https:","http:"].includes(url.protocol)){const link=node("a"," Source");link.href=url.href;link.target="_blank";link.rel="noopener noreferrer";entry.append(link);}}catch{}
    provenance.append(entry);
  }
  $("activity-log").replaceChildren(node("p","Research history is not supplied by this native read interface."));
}

function applyCatalog(next) {
  catalogDate = `revision ${next.revision}`;
  state.routingCatalogLabel = `Catalog ${catalogDate} · ${planningAdapter?.policy?.label || "driving times unavailable"}`;
  catalogModel = next;
  $("native-provenance-toggle").disabled=false;
  const selectedState = $("browse-state").value;
  $("browse-state").replaceChildren(new Option("All states","all"), ...[...new Set(next.facilities.map(f => f.state).filter(Boolean))].sort().map(state => new Option(geometry?.states.find(s => s.id === state)?.name || state,state)));
  if ([...$("browse-state").options].some(o => o.value === selectedState)) $("browse-state").value = selectedState;
  if (activeFacility && !next.facilityById.has(activeFacility)) closeSelection();
  const counts = catalogCounts(next.facilities);
  $("catalog-status").textContent = `${fmt(counts.onMap)} on map · ${fmt(counts.pending)} not mapped · local read examples`;
  drawFacilities();renderCourses();renderProgress();
  if (cataloguePopup?.isOpen() && popupSelection) openSelectionPopup();
}
$("cancel-calculate").onclick = () => {
  for(const row of state.rows){closeSuggestions(row,true);row.input.value="";row.coordinate=null;row.committedLabel=null;row.marker?.remove();row.marker=null;}
  updatePlan();planningSession?.update([],selected("objective"),selectedHoles());
};
$("planning-radius").onchange = () => {
  if (planningMode && planningSession) planningSession.radiusChanged(Number($("planning-radius").value) * 1.609344);
};
$("plan-toggle").onclick = () => {
  planningMode = $("plan-panel").hidden;
  $("browse-access").value = planningMode ? "nonmember" : "all";
  if (planningSession && planningMode) planningSession.accessPolicy = "nonmember";
  setDrawer("plan", planningMode);
  browseMode = !planningMode;
  if (planningMode) syncPlanning(); else planningSession?.invalidate(committedOrigins());
  renderCourses();
};
$("courses-toggle").onclick = () => { browseMode = !planningMode; setDrawer("courses", view.resultsPanel.hidden); };
$("close-plan").onclick = () => {planningMode = false; browseMode = true; $("browse-access").value = "all"; planningSession?.invalidate(committedOrigins());setDrawer("plan", false);renderCourses();};
$("close-courses").onclick = () => setDrawer("courses", false);
$("progress-toggle").onclick = () => $("catalog-progress").showModal();
$("native-provenance-toggle").onclick = () => {renderProgress();$("catalog-progress").showModal();};
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
for (const id of ["browse-state", "browse-holes", "browse-round", "browse-access", "browse-style", "browse-price", "browse-sort"])
  $(id).onchange = () => {
    if (id === "browse-access" && planningMode) planningSession?.accessChanged($(id).value);
    if (id === "browse-sort" && planningMode) planningDisplaySort = $(id).value;
    listLimit = 60;
    renderCourses();
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
  planningMode = false; planningSession?.invalidate(committedOrigins()); $("browse-access").value = "all"; setDrawer("plan", false);
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
    const r = await fetch("./research-map/boundaries.json");
    if (!r.ok) throw new Error();
    geometry = await r.json();
  } catch {
    geometry = { states: [], counties: [] };
  }
  try {
    if(!catalogAdapter?.transport?.offlineOnly||catalogAdapter.transport.protocol!=="immutable-plan-07a6806")throw new Error("Offline native catalog adapter required");
    applyCatalog(await catalogAdapter.transport.readCatalog());
  } catch {
    $("catalog-status").textContent="Catalog unavailable. Native read could not be completed.";
    view.results.replaceChildren(node("p","Catalog unavailable. No course list can be shown."));
  }
}
planningSession = planningAdapter?.transport ? new LogicalPlanningSession({
  transport:planningAdapter.transport,notify:renderPreparation,
}) : null;

for (let count = requiredOriginRows(state.rows.length); count > 0; count -= 1)
  addOrigin();
planningAdapter?.onSessionReady?.(planningSession);
loadCatalog();
