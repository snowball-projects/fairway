import {located,mapEligible,catalogCounts,cityLabel,searchCatalog,courseMatches,sortCourses,browseCard,STYLES,accessLabel,displayAddress} from "./catalog-read.mjs";
import {shapeRings} from "./map-geometry.mjs";
import { createFacilityDots } from "./facility-dots.mjs";
import {
  canRemoveOrigin,
  originLimit,
  requiredOriginRows,
} from "./origin-rows.mjs";
import {PublicPlanningSession,resolvePublicOrigin} from "./public-planning.mjs";
import {loadPublicCatalog} from "./public-catalog.mjs";
import {renderOptional} from "./optional-facts.mjs";
import { bindCoursesDrawer } from "./courses-drawer.mjs";

// Public catalog selection owns no routing or native admission.
const planningAdapter={resolveOrigin:resolvePublicOrigin,policy:{label:"Driving times unavailable"}};
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
};
let nextOriginId = 1;
let coursesDrawer = null;
let automaticCoursesKey = null;

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
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {maxZoom:19,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}).addTo(map);
meetingLayer.addTo(map);
preparationFacilities.addTo(map);
new ResizeObserver(() => map.invalidateSize()).observe(
  document.querySelector("#map"),
);

function setStatus(message, error = false) {
  view.status.textContent = message;
  view.status.dataset.error = String(error);
  view.status.hidden = !message;
  const resultsStatus = document.getElementById("preparation-status");
  resultsStatus.textContent = message;
  resultsStatus.dataset.error = String(error);
  resultsStatus.hidden = !planningMode || !message;
}

function setFilterOpen(open, focus = false) {
  const nextOpen = open && !view.resultsPanel.hidden;
  view.filterPopover.hidden = !nextOpen;
  view.filterToggle.setAttribute("aria-expanded", String(nextOpen));
  if (nextOpen && focus) {
    view.filterPopover.querySelector("select, input, button")?.focus();
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
  if (seconds === null || seconds === undefined) return "Unavailable";
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
  if (!query) {if(planningMode)syncPlanning();return false;}
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
      else throw new Error("Address lookup unavailable");
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

function unusedOriginId() {
  let candidate=nextOriginId-1;
  while(state.rows.some(row=>row.id===`o${candidate}`))candidate++;
  return `o${candidate}`;
}
function addOrigin() {
  if (state.rows.length >= state.maxOrigins) return;
  const row = {
    color: unusedColor(),
    coordinate: null,
    marker: null,
    id: unusedOriginId(),
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
  updateLoadedCount(0);
  view.rankingDescription.textContent = "";
  browseMode = true;
  drawFacilities();
  renderCourses();
}

function updatePlan() {
  clearRanking();
  const count = state.rows.filter((row) => row.coordinate).length;
  setStatus(
    count ? "Selecting nearby catalog courses…" : "Enter a golfer address.",
  );
}

function openCoursesForOrigins(origins) {
  if (!origins.length) {automaticCoursesKey=null;return;}
  const key=JSON.stringify(origins);
  if (key===automaticCoursesKey || (mobile() && $("plan-panel").contains(document.activeElement))) return;
  automaticCoursesKey=key;
  setDrawer("courses",true);
}
function renderPreparation(session) {
  state.routingCatalogLabel="Nearby catalog courses · driving times unavailable";
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
  meetingLayer.clearLayers();
  if (planningMode) {
    browseMode = false;
    // Preserve the active address field in the existing mobile sheet flow.
    openCoursesForOrigins(session.origins);
    renderCourses();
  }
  view.results.setAttribute("aria-busy", String(Boolean(session.active || session.pending)));
  $("cancel-calculate").hidden = !session.origins.length || ["complete", "partial", "error"].includes(session.phase);
  setStatus(session.origins.length ? "Driving times are unavailable. These courses are within the selected straight-line radius of at least one golfer." : "Enter a golfer address or coordinate.");
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
  rank.hidden = course.browseOnly === true || course.catalogOnly === true;
  const body = document.createElement("span");
  const title = document.createElement("span");
  title.className = "course-title";
  title.setAttribute("role", "heading");
  title.setAttribute("aria-level", "3");
  title.textContent = course.course_name === null ? course.facility_name : course.name;
  const meta = document.createElement("span");
  meta.className = "course-meta";
  [course.course_name === null ? "Course name not recorded" : null, course.holes === null ? "Holes unconfirmed" : course.holes + " holes", course.course_name === null ? null : course.facility_name, course.access, course.identity_status === "needs_review" ? "Course identity unconfirmed" : course.identity_status === "component" ? "Component layout record; independent booking unconfirmed" : null].filter(Boolean).forEach((label) => {
    const value = document.createElement("span");
    value.textContent = label;
    meta.append(value);
  });
  const scores = document.createElement("span");
  scores.className = "score-row";
  [
    ["maximum", course.maximum_seconds === null ? "Unavailable" : duration(course.maximum_seconds), "longest drive"],
    ["combined", course.combined_seconds === null ? "Unavailable" : duration(course.combined_seconds), "combined drive"],
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
    const value = seconds === null ? "Unavailable" : duration(seconds);
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
  article.append(courseMetadata(course));
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
  const teeRecords=[...(course.tee_sets||[]),...(course.round_options||[]).flatMap(r=>(r.tee_sets||[]).map(t=>({...t,round_holes:r.round_holes})))];
  if(teeRecords.length){const tees=node("details");tees.append(node("summary",`${teeRecords.length} tee observations`));for(const tee of teeRecords)tees.append(observationFields(tee));details.append(tees);}
  else details.append(node("p","Tee yardage, rating and slope not documented"));
  if(course.planning_basis==='accepted_public_play_with_qualification')details.append(node("p","Preliminary public-play eligibility; nonmember booking and availability remain unconfirmed."));
  details.append(renderOptional(course.optional,{subjectLabel:'Course: '+(course.course_name??course.name??course.facility_name??'name unconfirmed')}));
  for(const component of course.components||[]){const part=node("details");part.append(node("summary",`Component: ${component.name || 'Name unconfirmed'} · ${component.physical_holes??'Unknown'} physical holes · independent booking unconfirmed`),renderOptional(component.optional,{subjectLabel:'Component: '+(component.name||'name unconfirmed')}));details.append(part);}
  for(const round of rounds){const part=node("details");part.append(node("summary",`Round: ${round.name || 'Name unconfirmed'} · ${round.round_holes??'Unknown'} holes · ${round.scope==='facility'?'facility-owned combination':'course-owned round'}`),renderOptional(round.optional,{subjectLabel:'Round: '+(round.name||'name unconfirmed')}));details.append(part);}
  return details;
}

function observationFields(value) {
  const list=node("dl",undefined,"observation-fields");
  for(const [key,item] of Object.entries(value||{})){
    if(['id','facility_id','course_id','round_id','source_id','batch_id'].includes(key))continue;
    list.append(node("dt",key==='difficulty_rating'?'course difficulty rating (not a quality rating)':key.replaceAll('_',' ')));
    const entry=node("dd");
    if(item===null||item===undefined||(Array.isArray(item)&&!item.length))entry.textContent="Not documented";
    else if(typeof item==='object'){if(Array.isArray(item))for(const part of item)entry.append(typeof part==='object'?observationFields(part):node("p",String(part)));else entry.append(observationFields(item));}
    else entry.textContent=typeof item==='boolean'?(item?'Yes':'No'):String(item);
    list.append(entry);
  }
  return list;
}
function renderRanking(result) {
  const sort = $("browse-sort").value;
  const originIndex = sort.startsWith("origin:") ? state.activeRows.findIndex(row => row?.id === sort.slice(7)) : -1;
  const value = course => sort === "holes" ? course.holes : sort === "name" ? null : originIndex >= 0 ? course.travel_times_seconds[originIndex] : course[`${sort}_seconds`];
  result = {...result, courses:result.courses.filter(course => matchesCourseFilters(course.source_course || {access:course.access === "Public play"?"public":course.access === "Access unconfirmed"?null:course.access.toLowerCase(),state:course.state,physical_holes:course.holes,plan_eligible:course.plan_eligible,style:course.style,round_options:course.round_options,optional:course.optional})).sort((a,b) => {
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
      score.querySelector("strong").textContent = result.blocked ? "Blocked" : result.error || course.catalogOnly ? "Unavailable" : course.reason ? "Unranked" : seconds === null ? "Pending" : duration(seconds);
    });
    const times = article.querySelector(".golfer-times");
    while (times.children.length > course.travel_times_seconds.length) times.lastElementChild.remove();
    course.travel_times_seconds.forEach((seconds, index) => {
      let time = times.children[index]; if (!time) {time = document.createElement("li");time.className = "golfer-time";times.append(time);}
      time.style.setProperty("--golfer", state.activeRows[index]?.color || COLORS[index]);
      const reason = course.travel_time_reasons?.[index];
      const value = result.blocked ? "Blocked" : result.error || course.catalogOnly ? "Unavailable" : seconds === null ? reason === "arrival_unavailable" ? "Destination unavailable" : reason === "error" ? "Unavailable" : reason === "outside-road-coverage" ? "Outside road coverage" : reason ? "Unreachable" : "Pending" : duration(seconds);
      time.textContent = `${index + 1} · ${value}`;time.ariaLabel = `Golfer ${index + 1}: ${value}`;
    });
  }
  for (const [id, item] of rankingNodes) if (!desired.includes(id)) {
    if ([...rowInteractions].some(key => key.endsWith(`:${id}`))) {
      item.querySelector(".rank").textContent = "…";
      item.querySelectorAll(".score strong").forEach(n => n.textContent = "Outside current regions");
      item.querySelectorAll(".golfer-time").forEach(n => n.textContent = "Unavailable");
    } else {item.remove();rankingNodes.delete(id);}
  }
  if (!rowInteractions.size) desired.forEach((id, index) => {
    const item = rankingNodes.get(id), current = list.children[index];
    if (item !== current) list.insertBefore(item, current || null);
  });
  updateLoadedCount(result.courses.length);
  view.rankingDescription.textContent = result.blocked ? "Driving-time comparison is blocked." : result.error ? "Driving times are unavailable." : "";
  view.rankingDescription.hidden = !view.rankingDescription.textContent;
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
  const toggle = which === "plan" ? $("plan-toggle") : $("courses-grip");
  panel.hidden = !open;
  toggle.setAttribute("aria-expanded", String(open));
  if (open && mobile()) {
    const other = which === "plan" ? "courses" : "plan";
    (other === "plan" ? $("plan-panel") : view.resultsPanel).hidden = true;
    $(other === "plan" ? "plan-toggle" : "courses-grip").setAttribute(
      "aria-expanded",
      "false",
    );
  }
  view.appShell.classList.toggle(
    "mobile-sheet-open",
    mobile() && (!$("plan-panel").hidden || !view.resultsPanel.hidden),
  );
  if (!open && panel.contains(document.activeElement)) toggle.focus();
  coursesDrawer?.sync(!view.resultsPanel.hidden);
  if (view.resultsPanel.hidden) setFilterOpen(false);
  if (which === "courses" && open) renderCourses();
}
function fitPadding() {
  if (mobile()) {
    const covered = !$("plan-panel").hidden ? $("plan-panel").getBoundingClientRect().height
      : !view.resultsPanel.hidden ? view.resultsPanel.getBoundingClientRect().height : 55;
    const bottom = Math.min(covered + 20, Math.max(0, window.innerHeight - 88));
    return {
      paddingTopLeft: [24, Math.min(170, Math.max(24, window.innerHeight - bottom - 64))],
      paddingBottomRight: [24, bottom],
    };
  }
  return {
    paddingTopLeft: [!$("plan-panel").hidden ? 370 : 60, 140],
    paddingBottomRight: [!view.resultsPanel.hidden ? view.resultsPanel.getBoundingClientRect().width + 44 : 60, 90],
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
      `${[cityLabel(f), f.state || "State not documented"].filter(Boolean).join(", ")} · ${f.physical_holes ?? "Unknown"} physical holes`,
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
  article.append(node("p", displayAddress(f.address)));
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
          `${c.name || "Unnamed course"} · ${c.physical_holes ?? "?"} holes · ${accessLabel(c.access)}`,
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
  article.append(node("p", websiteState(f)),renderOptional(f.optional,{subjectLabel:'Facility: '+f.name}));
  for(const round of f.round_options||[]){const part=node("details");part.append(node("summary",`Round: ${round.name||'Name unconfirmed'} · ${round.round_holes??'Unknown'} holes · facility-owned combination`),renderOptional(round.optional,{subjectLabel:'Round: '+(round.name||'name unconfirmed')}));article.append(part);}
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
    roundHoles:$("browse-round").value,style:$("browse-style").value};
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
  if (planningMode && state.ranking?.courses.some(c=>Number.isFinite(c.maximum_seconds))) choices.push(["maximum","Longest driving time"],["combined","Combined driving time"],
    ...state.rows.filter(row => row.coordinate).map(row => [`origin:${row.id}`,`Golfer ${state.rows.indexOf(row)+1} driving time`]));
  const key = JSON.stringify(choices);
  if (sort.optionsKey !== key) {
    sort.optionsKey = key;sort.replaceChildren(...choices.map(([value,label]) => {const option=document.createElement("option");option.value=value;option.textContent=label;return option;}));
  }
  const value = planningMode && choices.some(([value]) => value === planningDisplaySort) ? planningDisplaySort : choices.some(([value])=>value===sort.value)?sort.value:"name";
  sort.value = value;
}
function updateLoadedCount(count) {
  view.resultCount.textContent = String(count);
  view.resultCount.setAttribute("aria-label", `Number of courses loaded: ${count}`);
}
function renderCourses() {
  view.catalogName.textContent = browseMode
    ? `Catalog ${catalogDate || "date unknown"}`
    : state.routingCatalogLabel;
  updateDisplaySortOptions();
  $("browse-access").querySelector('[value="nonmember"]').hidden = !planningMode;
  $("browse-description").hidden = !browseMode;
  view.rankingDescription.hidden = browseMode;
  $("preparation-status").hidden = !planningMode || !$("preparation-status").textContent;
  if (!planningMode) {
    preparationFacilities.clearLayers();preparationFacilities.key = null;
    meetingLayer.clearLayers();meetingLayer.areaKey = null;
  }
  if (planningMode && !browseMode && state.ranking) {
    renderRanking(state.ranking);
    return;
  }
  if (!catalogModel) {
    rankingNodes.clear();rowInteractions.clear();
    view.results.setAttribute("aria-busy","false");
    updateLoadedCount(0);view.rankingDescription.textContent="";
    view.rankingDescription.hidden=true;
    const message=$("catalog-status").textContent?.includes("unavailable")
      ? "Catalog unavailable. No course list can be shown."
      : "Catalog is still loading. No browse course list is available yet.";
    $("browse-description").textContent=message;
    view.results.replaceChildren(node("p",message));
    return;
  }
  const records = scopedRecords();
  updateLoadedCount(Math.min(records.length, listLimit));
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
  provenance.append(node("p",`${fmt(catalogModel.optionalObservations.size)} distinct typed observations. Facility, course, component and round scopes are separate. Missing values are unconfirmed. Quality/star ratings are not supplied; tee rating describes playing difficulty.`));
  provenance.append(node("p",`${fmt(catalogModel.provenance.sources.length)} registered public sources. Individual observation details show their source link, license and attribution.`));
  for(const license of catalogModel.sourceLicenses||[]){const detail=node("details");detail.append(node("summary",`${license.source || "Data source"} · ${license.license || "See source policy"}`),observationFields(license));provenance.append(detail);}
  $("activity-log").replaceChildren(node("p","This is a frozen published catalog, not live research activity."));
}

function applyCatalog(next) {
  catalogDate = `revision ${next.revision}`;
  state.routingCatalogLabel = `Catalog ${catalogDate} · ${planningAdapter?.policy?.label || "driving times unavailable"}`;
  catalogModel = next;
  planningSession?.setCatalog(next);
  $("native-provenance-toggle").disabled=false;
  const selectedState = $("browse-state").value;
  $("browse-state").replaceChildren(new Option("All states","all"), ...[...new Set(next.facilities.map(f => f.state).filter(Boolean))].sort().map(state => new Option(geometry?.states.find(s => s.id === state)?.name || state,state)));
  if ([...$("browse-state").options].some(o => o.value === selectedState)) $("browse-state").value = selectedState;
  if (activeFacility && !next.facilityById.has(activeFacility)) closeSelection();
  const counts = catalogCounts(next.facilities);
  $("catalog-status").textContent = `${fmt(counts.onMap)} on map · ${fmt(counts.pending)} not mapped · catalog revision ${next.revision}`;
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
coursesDrawer = bindCoursesDrawer({shell:$("courses-drawer"), panel:view.resultsPanel, grip:$("courses-grip"),
  onActivate:()=>{if(planningSession?.origins.length)automaticCoursesKey=JSON.stringify(planningSession.origins);},
  setOpen:open=>{browseMode=!planningMode;setDrawer("courses",open);}, viewport:()=>window.innerWidth,viewportHeight:()=>window.innerHeight});
window.addEventListener("resize",()=>coursesDrawer.sync(!view.resultsPanel.hidden));
document.addEventListener("focusout",()=>requestAnimationFrame(()=>{
  if (planningMode && state.ranking) openCoursesForOrigins(planningSession.origins);
}));
$("close-plan").onclick = () => {planningMode = false; browseMode = true; $("browse-access").value = "all"; planningSession?.invalidate(committedOrigins());setDrawer("plan", false);renderCourses();};
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
for (const id of ["browse-state", "browse-holes", "browse-round", "browse-access", "browse-style", "browse-sort"])
  $(id).onchange = () => {
    if (id === "browse-access" && planningMode) planningSession?.accessChanged($(id).value);
    if (id === "browse-sort" && planningMode) planningDisplaySort = $(id).value;
    listLimit = 60;
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
    applyCatalog(await loadPublicCatalog(new URL("./data/catalog-release.json",import.meta.url)));
  } catch {
    $("catalog-status").textContent="Catalog unavailable. Published catalog could not be read.";
    if(planningMode && !browseMode && state.ranking)renderCourses();
    else view.results.replaceChildren(node("p","Catalog unavailable. No course list can be shown."));
  }
}
planningSession = new PublicPlanningSession({notify:renderPreparation});

for (let count = requiredOriginRows(state.rows.length); count > 0; count -= 1)
  addOrigin();
loadCatalog();
