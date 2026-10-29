import {located,mapEligible,catalogCounts,cityLabel,searchCatalog,courseMatches,browseCard,STYLES,accessLabel,displayAddress,recordLabel} from "./catalog-read.mjs";
import {shapeRings} from "./map-geometry.mjs";
import { createFacilityDots } from "./facility-dots.mjs";
import {
  canRemoveOrigin,
  originLimit,
  requiredOriginRows,
} from "./origin-rows.mjs";
import {PublicPlanningSession,resolvePublicOrigin} from "./public-planning.mjs";
import {loadPublicCatalog,loadInitialMap} from "./public-catalog.mjs";
import {renderKnownOptional} from "./optional-facts.mjs";
import { bindCoursesDrawer } from "./courses-drawer.mjs";

// Public catalog selection owns no routing or native admission.
const planningAdapter={resolveOrigin:resolvePublicOrigin,policy:{label:"Driving times unavailable"}};
let planningSession = null;
const meetingLayer = L.layerGroup();
const preparationFacilities = L.layerGroup();
let planningMode = false;
let planningDisplaySort = "maximum";
const rankingNodes = new Map();
const browseNodes = new Map();
let movingCourseCard = false;
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

  filterToggle: document.querySelector("#filter-toggle"),
  filterPopover: document.querySelector("#filter-popover"),
  routingDescription: document.querySelector("#routing-description"),
};
let nextOriginId = 1;
let coursesDrawer = null;
let automaticCoursesKey = null;

const map = L.map("map", {
  zoomControl: true,
  zoomSnap: 1,
  zoomDelta: 1,
}).fitBounds(
  [
    [24, -125],
    [50, -66],
  ],
  { padding: [40, 100] },
);
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {maxZoom:19,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors · <a href="./credits.html" target="_blank" rel="noopener noreferrer">Data credits</a>'}).addTo(map);
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

function selectableCourses() {
  if (planningMode) return (state.ranking?.courses || []).filter(course => matchesCourseFilters(course.source_course || catalogModel?.courseById.get(course.id)));
  return scopedRecords();
}

function selectCourse(courseId, focusMap = true, facilityId = null) {
  const course = selectableCourses().find(course => (course.course_id || course.id) === courseId)
    || (!planningMode && facilityId ? catalogModel.facilityCourses(facilityId).find(course=>course.course_id===courseId&&matchesCourseFilters(course)) : null);
  if (!course) return false;
  state.activeCourse = courseId;
  activeFacility = course.facility_id ?? course.course_id ?? course.id;
  const record = course.source_course || course;
  const coordinate = course.coordinate || (record.map_location ? [record.map_location.latitude, record.map_location.longitude] : null);
  setDrawer("courses", true, false);
  if (focusMap && coordinate) fitPoints([coordinate], 14, !mobile()&&!REDUCED_MOTION);
  popupSelection = coordinate ? {kind:"course",id:courseId,coordinate:L.latLng(...coordinate)} : null;
  if (popupSelection) openSelectionPopup();
  else if (cataloguePopup) {const previous=cataloguePopup;cataloguePopup=null;map.closePopup(previous);}
  drawFacilities();
  renderCourses();
  view.results.scrollTop = 0;
  return true;
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
  closeSuggestions(row, true);
  if (!query) {if(planningMode)syncPlanning();return false;}
  if (query.length < 3 || query.length > 256) return false;
  const coordinate = parseCoordinate(query);
  if (coordinate) { if (!insideCore(coordinate)) { setStatus("Coordinates are outside the lower 48.", true); return false; } setOrigin(row, query, coordinate); return true; }
  if (looksLikeCoordinateInput(query)) return false;
  const controller = new AbortController();
  row.controller = controller; row.lookupQuery = query;
  row.lookupPromise = (async () => {
    try {
      let result;
      if (planningAdapter?.resolveOrigin) result = await planningAdapter.resolveOrigin(query, {signal: controller.signal});
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
      setStatus(choices.length ? "Address matches available." : "Address not found.", !choices.length);
      return false;
    } catch (error) {
      if (!controller.signal.aborted && error.name !== "AbortError" && state.rows.includes(row) && row.controller === controller) setStatus("Address suggestions unavailable.", true);
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
    count ? "Selecting nearby catalog courses…" : "No golfer origins.",
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
      L.circleMarker(course.coordinate,{radius:7,color:"#fff",weight:2,fillColor:"#1d644b",fillOpacity:.95,bubblingMouseEvents:false,className:"preparation-facility"})
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
  setStatus(session.origins.length ? "Driving times are unavailable. These courses are within the selected straight-line radius of at least one golfer." : "No golfer origins.");
}

function moveCourseCard(list, item, before) {
  if(item===before)return;
  const focused=item.contains(document.activeElement)?document.activeElement:null;
  movingCourseCard=true;
  try {
    if(list.moveBefore&&item.parentElement===list)list.moveBefore(item,before);
    else list.insertBefore(item,before);
    if(focused&&document.activeElement!==focused)focused.focus({preventScroll:true});
  } finally {movingCourseCard=false;}
}

function bindPillSelection(article, focus, select) {
  const selectingText=()=>{
    const selection=document.getSelection?.();
    return selection&&!selection.isCollapsed&&selection.containsNode(article,true);
  };
  // The native button remains the only selection tab stop, alongside any links.
  focus.onclick=event=>{if(!event?.detail||!selectingText())select();};
  article.classList.toggle("selectable-pill",true);
  article.addEventListener("click",event=>{
    if(event.defaultPrevented||event.button>0||
      event.target.closest(".facility-group, .course-card")!==article||
      event.target.closest("a, button, input, select, textarea, summary, [role='button'], [contenteditable]")||selectingText())return;
    focus.focus({preventScroll:true});select();
  });
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
  bindPillSelection(article,focus,()=>selectCourse(course.id));
  const rank = document.createElement("span");
  rank.className = "rank";
  rank.textContent = course.rank ?? "…";
  rank.hidden = course.browseOnly === true || course.catalogOnly === true;
  const body = document.createElement("span");
  const title = document.createElement("span");
  title.className = "course-title";
  title.setAttribute("role", "heading");
  title.setAttribute("aria-level", "4");
  title.textContent = course.course_name ?? "not recorded";
  title.setAttribute("aria-label", `Course name: ${title.textContent}`);
  const meta = document.createElement("span");
  meta.className = "course-meta";
  meta.textContent = Number.isFinite(course.holes) ? course.holes + " holes" : "Holes: not recorded";
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
  article.append(focus, times);
  item.append(article);
  return item;
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
  reconcilePopupChoices(result.courses,course=>course.id);
  if(state.activeCourse&&!result.courses.some(course=>course.id===state.activeCourse))closeSelection(false);
  const desired = selectedFirst(result.courses,course=>course.id).map(course => course.id);
  const currentOrder = [...list.querySelectorAll(".course-card")].map(article=>article.dataset.courseId);
  const pendingOrder = JSON.stringify(currentOrder) !== JSON.stringify(desired);
  for (const course of result.courses) {
    let item = rankingNodes.get(course.id);
    if (!item) {
      item = courseCard(course, result.objective); rankingNodes.set(course.id, item);
      const article = item.firstElementChild;
      article.addEventListener("focusin", () => rowInteractions.add(`focus:${course.id}`));
      article.addEventListener("focusout", event => {
        if (movingCourseCard || article.contains(event.relatedTarget)) return;
        const next = event.relatedTarget?.closest(".course-card");
        if (next && view.results.contains(next)) rowInteractions.add(`focus:${next.dataset.courseId}`);
        rowInteractions.delete(`focus:${course.id}`); renderCourses();
      });
      article.addEventListener("mouseenter", () => rowInteractions.add(`pointer:${course.id}`));
      article.addEventListener("mouseleave", () => {rowInteractions.delete(`pointer:${course.id}`);renderCourses();});
    }
    const article = item.firstElementChild;
    article.dataset.active=String(course.id===state.activeCourse);
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
  const order=rowInteractions.size
    ? [...new Set([state.activeCourse,...currentOrder,...desired])].filter(id=>rankingNodes.has(id))
    : desired;
  renderFacilityGroups(list,order.map(id=>({record:catalogModel.courseById.get(id),item:rankingNodes.get(id)})));
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
  (id, coordinate) => selectMapDot([id], coordinate),
  (ids, coordinate) => selectMapDot(ids, coordinate),
);
let catalogDate = "";
let catalogModel = null,
  geometry = null,
  progress = null,
  additions = null;
let initialMap = null, detailsRequest = null, deferredSelection = null;
const catalogURL = new URL("./data/catalog-release.json",import.meta.url);
let activeFacility = null,
  popupSelection = null,
  browseMode = true,
  browseScope = {kind:"viewport",label:"Courses in this map area"};
let viewportFrame = null, browseGroupFrame = null;
let searchMatches = [],
  searchIndex = -1,
  listLimit = 60,
  cataloguePopup = null;
let lastSearch = "";
let searchChoiceFrame = null, pendingSearchChoice = null, searchCameraActive = false;
function node(tag, text, className) {
  const n = document.createElement(tag);
  if (text !== undefined) n.textContent = text;
  if (className) n.className = className;
  return n;
}
function mobile() {
  return window.matchMedia("(max-width:800px)").matches;
}
function setDrawer(which, open, render = true) {
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
  if (which === "courses" && open && render) renderCourses();
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
function fitPoints(points, maxZoom = 15, animate = !REDUCED_MOTION) {
  if (!points.length) return;
  const bounds = L.latLngBounds(points);
  if (bounds.isValid())
    map.fitBounds(bounds, {
      maxZoom,
      animate,
      ...fitPadding(),
    });
}
function drawFacilities() {
  const records=initialMap?.mapRecords || catalogModel?.mapRecords;
  if(records)facilityDots.update(records,activeFacility);
}
function selectMapDot(ids, coordinate) {
  setDrawer("courses",true,false);
  map.setView(coordinate,13,{animate:false});
  if(ids.length>1)selectCoincidentFacilities(ids,coordinate);
  else selectFacilityById(ids[0],false);
}
function knownLink(container, value, label) {
  try {
    const url = new URL(value);
    if (!["http:", "https:"].includes(url.protocol)) return;
    const link=node("a",label);link.href=url.href;link.target="_blank";link.rel="noopener noreferrer";
    container.append(link);
  } catch {}
}
function knownAddress(container, address) {
  if (address?.text || [address?.street_line1,address?.street_line2,address?.city,address?.region,address?.postal_code,address?.country].some(Boolean))
    container.append(node("p",displayAddress(address)));
}
function appendKnownOptional(container, optional, subjectLabel) {
  const details=renderKnownOptional(optional,{subjectLabel});
  if(details)container.append(details);
}
function knownRounds(container, rounds) {
  for(const round of rounds || []) {
    const values=[round.name,round.round_holes!==null&&round.round_holes!==undefined?`${round.round_holes} holes`:null].filter(Boolean);
    const details=node("details");details.append(node("summary",values.join(" · ") || "Round"));
    if(round.description)details.append(node("p",round.description));
    appendKnownOptional(details,round.optional,round.name || "Round");
    if(details.children.length>1)container.append(details);
    else if(values.length)container.append(node("p",values.join(" · ")));
  }
}
function coursePopupDetails(course) {
  const article=node("article",undefined,"facility-card");
  article.append(node("h3",recordLabel(course,"course")));
  if(course.name&&course.facility_name!==course.name)article.append(node("p",course.facility_name));
  const facts=[Number.isFinite(course.physical_holes)?`${course.physical_holes} holes`:null,STYLES[course.style],course.access?accessLabel(course.access):null].filter(Boolean);
  if(facts.length)article.append(node("p",facts.join(" · ")));
  if(course.nonmember_bookable===true)article.append(node("p","Nonmember booking documented"));
  if(course.nonmember_bookable===false)article.append(node("p","Nonmember booking: No"));
  if(course.booking_conditions)article.append(node("p",course.booking_conditions));
  if(course.access_qualification)article.append(node("p",course.access_qualification));
  if(course.location_note)article.append(node("p",course.location_note));
  knownAddress(article,course.address);
  const entrance={verified_entrance:"Verified entrance",reviewed_osm_point:"Reviewed routing point"}[course.arrival?.kind];
  if(entrance)article.append(node("p",entrance));
  knownLink(article,course.website||course.facility_website,"Website");
  knownLink(article,course.booking_url,"Booking");
  knownLink(article,course.contact_url,"Contact");
  appendKnownOptional(article,course.optional,recordLabel(course,"course"));
  for(const component of course.components||[]) {
    const facts=[component.name,Number.isFinite(component.physical_holes)?`${component.physical_holes} holes`:null].filter(Boolean);
    const details=node("details");details.append(node("summary",facts.join(" · ") || "Component"));
    appendKnownOptional(details,component.optional,component.name || "Component");
    if(details.children.length>1)article.append(details);
    else if(facts.length)article.append(node("p",facts.join(" · ")));
  }
  const tees=[...(course.tee_sets||[]),...(course.round_options||[]).flatMap(round=>(round.tee_sets||[]).map(tee=>({...tee,round:round.name})))];
  if(tees.length) {
    const details=node("details");details.append(node("summary","Tees"));
    for(const tee of tees) {
      const fields=node("dl",undefined,"observation-fields");
      for(const [key,value] of Object.entries(tee))if(value!==null&&value!==undefined&&!['id','course_id','round_id'].includes(key))
        fields.append(node("dt",key==='difficulty_rating'?'course difficulty rating (not a quality rating)':key.replace(/^physical_holes/, 'holes').replaceAll('_',' ')),node("dd",String(value)));
      if(fields.children.length)details.append(fields);
    }
    if(details.children.length>1)article.append(details);
  }
  knownRounds(article,course.round_options);
  const facility=catalogModel?.facilityById.get(course.facility_id);
  if(facility) {
    appendKnownOptional(article,facility.optional,facility.name);
    knownRounds(article,(facility.round_options||[]).filter(round=>!(course.round_options||[]).some(own=>own.id===round.id)));
  }
  return article;
}
function facilityDetails(f, compact = false) {
  const article=node("article",undefined,"facility-card");
  article.dataset.facilityId=f.facility_id;
  const title=node("button",recordLabel(f));title.type="button";
  title.addEventListener("click",()=>selectFacilityById(f.facility_id,true));article.append(title);
  const facts=[cityLabel(f),f.state,Number.isFinite(f.physical_holes)?`${f.physical_holes} holes`:null].filter(Boolean);
  if(facts.length)article.append(node("p",facts.join(" · ")));
  if(f.access)article.append(node("p",`${accessLabel(f.access)} facility`));
  if(compact)return article;
  knownAddress(article,f.address);
  if(f.course_inventory?.length) {
    const details=node("details");details.append(node("summary",`${f.course_inventory.length} ${f.course_inventory.length===1?"course":"courses"}`));
    for(const course of f.course_inventory) {
      const values=[course.name,Number.isFinite(course.physical_holes)?`${course.physical_holes} holes`:null,course.access?accessLabel(course.access):null].filter(Boolean);
      if(!values.length)continue;
      if(selectableCourses().some(row=>(row.course_id||row.id)===course.course_id)) {
        const button=node("button",values.join(" · "));button.type="button";
        button.addEventListener("click",()=>selectCourse(course.course_id));details.append(button);
      } else details.append(node("p",values.join(" · ")));
    }
    article.append(details.children.length>1?details:node("p",`${f.course_inventory.length} ${f.course_inventory.length===1?"course":"courses"}`));
  }
  const point={verified_entrance:"Verified entrance",reviewed_osm_point:"Reviewed map point",address_range_estimate:"Address estimate"}[f.map_location?.kind];
  if(point)article.append(node("p",point));
  if(f.osm_identity&&f.map_location?.reference){
    article.append(node("p",`OSM source checked ${f.map_location.checked_on}; entrance unconfirmed`));
    knownLink(article,f.map_location.reference,"OpenStreetMap");
  }
  knownLink(article,f.website,"Website");knownLink(article,f.booking_url,"Booking");knownLink(article,f.contact_url,"Contact");
  if(f.access_note)article.append(node("p",f.access_note));
  appendKnownOptional(article,f.optional,recordLabel(f));
  knownRounds(article,f.round_options);
  return article;
}
function selectCoincidentFacilities(ids, coordinate) {
  if(!catalogModel){deferredSelection=()=>selectCoincidentFacilities(ids,coordinate);setDrawer("courses",true);ensureCatalog();return;}
  closeSelection(false);
  popupSelection={kind:"coincident",ids,coordinate};
  setDrawer("courses",true,false);
  openSelectionPopup();renderCourses();
}
function selectFacilityById(id, fit = true) {
  if(!catalogModel){
    const facility=initialMap?.mapRecords?.find(f=>f.facility_id===id);
    setDrawer("courses",true);
    if(fit&&facility&&located(facility))fitPoints([[facility.map_location.latitude,facility.map_location.longitude]],15,false);
    // Fit the verified map point now; replay only the latest detail selection.
    // A later pan while details load must not be undone by a second fit.
    deferredSelection=()=>selectFacilityById(id,false);
    ensureCatalog();return;
  }
  if(catalogModel?.courseById.has(id))return selectCourse(id,fit,id);
  const facility=catalogModel?.facilityById.get(id);
  if(!facility)return;
  if(!planningMode&&browseScope?.ids&&!browseScope.ids.includes(id)&&located(facility)&&map.getBounds().contains([facility.map_location.latitude,facility.map_location.longitude]))
    browseScope={kind:"viewport",label:"Courses in this map area"};
  const courses=planningMode?selectableCourses().filter(course=>course.facility_id===id):catalogModel.facilityCourses(id).filter(matchesCourseFilters);
  if(courses.length===1)return selectCourse(courses[0].course_id||courses[0].id,fit,id);
  if(!courses.some(course=>(course.course_id||course.id)===state.activeCourse))state.activeCourse=null;
  activeFacility=id;
  setDrawer("courses",true,false);
  if(fit&&located(facility))fitPoints([[facility.map_location.latitude,facility.map_location.longitude]],15,!mobile()&&!REDUCED_MOTION);
  popupSelection=located(facility)?{kind:"facility",id,coordinate:L.latLng(facility.map_location.latitude,facility.map_location.longitude)}:null;
  if(popupSelection)openSelectionPopup();
  else if(cataloguePopup){const previous=cataloguePopup;cataloguePopup=null;map.closePopup(previous);}
  drawFacilities();renderCourses();view.results.scrollTop=0;
}
function selectionPopupOptions() {
  const options={maxWidth:312,minWidth:280,maxHeight:null,autoPan:false,closeOnClick:false};
  if(mobile()) {
    let top=Math.max(120,document.querySelector(".map-actions").getBoundingClientRect().bottom+8);
    coursesDrawer?.makeMapRoom(window.innerHeight-top-16-104);
    const covered=!view.resultsPanel.hidden?view.resultsPanel.getBoundingClientRect().height:0;
    let bottom=covered+16;
    if(view.resultsPanel.hidden) {
      top=$("catalog-search").getBoundingClientRect().bottom+8;
      bottom=Math.max(16,window.innerHeight-document.querySelector(".map-actions").getBoundingClientRect().top+8);
    }
    const available=window.innerHeight-top-bottom-40;
    if(available<1)return null;
    options.maxHeight=Math.min(230,available);
    options.autoPan=true;
    options.autoPanPaddingTopLeft=[12,top];
    options.autoPanPaddingBottomRight=[12,bottom];
  }
  return options;
}
function openSelectionPopup() {
  if(!popupSelection||!catalogModel)return;
  const content=node("div");
  content.addEventListener("click",event=>event.stopPropagation());
  if(popupSelection.kind==="course") {
    const course=catalogModel.courseById.get(popupSelection.id);
    if(!course){closeSelection();return;}
    content.append(coursePopupDetails(course));
  } else if(popupSelection.kind==="facility") {
    const facility=catalogModel.facilityById.get(popupSelection.id);
    if(!facility){closeSelection();return;}
    popupSelection.courseChoices=selectableCourses().filter(course=>course.facility_id===facility.facility_id).map(course=>course.course_id||course.id).sort();
    content.append(facilityDetails(facility));
  } else {
    content.append(node("h3",`${popupSelection.ids.length} golf records at this point`));
    for(const id of popupSelection.ids){const course=catalogModel.courseById.get(id),facility=catalogModel.facilityById.get(id);if(course)content.append(coursePopupDetails(course));else if(facility)content.append(facilityDetails(facility,true));}
  }
  const options=selectionPopupOptions();
  if(!options) {
    const previous=cataloguePopup;cataloguePopup=null;
    if(previous)map.closePopup(previous);
    return;
  }
  if(cataloguePopup?.isOpen()) {
    Object.assign(cataloguePopup.options,options);
    cataloguePopup.setLatLng(popupSelection.coordinate).setContent(content);
  }
  else {
    const popup=L.popup(options).setLatLng(popupSelection.coordinate).setContent(content).openOn(map);
    cataloguePopup=popup;
    popup.on("remove",()=>{if(cataloguePopup===popup){cataloguePopup=null;closeSelection();}});
  }
}
function closeSelection(render = true) {
  if(!catalogModel)deferredSelection=null;
  popupSelection=null;activeFacility=null;state.activeCourse=null;
  const previous=cataloguePopup;cataloguePopup=null;
  const focusedPopup=previous?.getElement?.()?.contains(document.activeElement);
  if(previous)map.closePopup(previous);
  if(focusedPopup)$("courses-grip").focus({preventScroll:true});
  drawFacilities();
  if(render)renderCourses();
}
function reconcilePopupChoices(records, id = course => course.course_id) {
  if(popupSelection?.kind!=="facility"||!popupSelection.courseChoices)return;
  const current=records.filter(course=>course.facility_id===popupSelection.id).map(id).sort();
  if(JSON.stringify(current)!==JSON.stringify(popupSelection.courseChoices))closeSelection(false);
}
function reconcileBrowseSelection(records) {
  reconcilePopupChoices(records);
  if(popupSelection?.kind==="coincident"&&browseScope?.kind==="viewport"&&!map.getBounds().contains(popupSelection.coordinate))closeSelection(false);
  if(state.activeCourse&&!records.some(course=>course.course_id===state.activeCourse))closeSelection(false);
  else if(!state.activeCourse&&activeFacility) {
    const facility=catalogModel.facilityById.get(activeFacility);
    if(!facility||browseScope?.kind==="viewport"&&(!located(facility)||!map.getBounds().contains([facility.map_location.latitude,facility.map_location.longitude])))closeSelection(false);
  }
}
function selectedFirst(records, id = course => course.course_id) {
  const selected=[],facility=[],other=[];
  for(const record of records) {
    if(id(record)===state.activeCourse)selected.push(record);
    else if(record.facility_id===activeFacility)facility.push(record);
    else other.push(record);
  }
  return [...selected,...facility,...other];
}
function refreshBrowseViewport() {
  if(viewportFrame!==null)return;
  viewportFrame=requestAnimationFrame(()=>{
    viewportFrame=null;
    if(planningMode)return;
    browseMode=true;browseScope={kind:"viewport",label:"Courses in this map area"};
    if(catalogModel&&!view.resultsPanel.hidden)renderCourses(true);
  });
}

function filterOptions() {
  return {state:$("browse-state").value,access:$("browse-access").value,holes:$("browse-holes").value,
    roundHoles:$("browse-round").value,style:$("browse-style").value};
}
function scopedEntries() {
  if (!catalogModel) return [];
  const bounds=browseScope?.kind === "viewport"?map.getBounds():null;
  const facility=popupSelection?catalogModel.mapRecordById.get(activeFacility):null;
  const selectedFacilityVisible=bounds&&located(facility||{})&&bounds.contains([facility.map_location.latitude,facility.map_location.longitude]);
  const filters=filterOptions(), ids=browseScope?.ids?new Set(browseScope.ids):null;
  const unfiltered=Object.values(filters).every(value=>value==="all");
  const south=bounds?.getSouth(),north=bounds?.getNorth(),west=bounds?.getWest(),east=bounds?.getEast();
  return catalogModel.browseEntries[$("browse-sort").value].filter(record=>{
    if(planningMode&&!record.course_id)return false;
    const id=record.facility_id??record.course_id;
    if(ids&&!ids.has(id))return false;
    if(bounds&&!(selectedFacilityVisible&&record.course_id&&id===activeFacility)) {
      const p=record.map_location;
      if(!p||p.latitude<south||p.latitude>north||p.longitude<west||p.longitude>east)return false;
    }
    return unfiltered||courseMatches(record,filters);
  });
}
function scopedRecords() {return scopedEntries().filter(record=>record.course_id);}
function matchesCourseFilters(course) {return courseMatches(course,filterOptions());}
function browseRecordId(record) {return record.course_id??record.facility_id;}
function facilityGroup(facility, id) {
  const item=node("li"),article=node("article",undefined,"facility-group");
  item.dataset.groupId=id;
  if(facility)article.dataset.facilityId=facility.facility_id;
  const heading=node("h3"),title=node("button",facility?.name??"not recorded","facility-focus");
  title.type="button";title.setAttribute("aria-label",`Facility name: ${title.textContent}`);
  if(facility)bindPillSelection(article,title,()=>selectFacilityById(facility.facility_id,true));
  else title.disabled=true;
  heading.append(title);
  const facts=node("dl",undefined,"facility-facts");
  for(const [label,value] of [
    ["Town",facility?[cityLabel(facility)??"not recorded",facility.state].filter(Boolean).join(", "):null],
    ["Website",null],
    ["Access",facility?.access?accessLabel(facility.access):null],
    ["Facility holes",Number.isFinite(facility?.physical_holes)?`${facility.physical_holes} holes`:null],
  ]) {
    const row=node("div"),detail=node("dd",value??"not recorded");
    if(label==="Website"&&facility?.website) {
      const link=node("span");knownLink(link,facility.website,"Website");
      if(link.children.length)detail.replaceChildren(...link.children);
    }
    row.append(node("dt",label),detail);facts.append(row);
  }
  article.append(heading,facts);
  if(facility?.address)article.append(node("p",displayAddress(facility.address),"facility-address"));
  const courses=node("ol",undefined,"facility-courses"),empty=node("p","Courses: not recorded","facility-empty");
  article.append(courses,empty);item.append(article);return item;
}
function renderFacilityGroups(list, entries, incremental = false) {
  if(browseGroupFrame!==null)cancelAnimationFrame(browseGroupFrame);
  browseGroupFrame=null;
  const groups=new Map(),existing=new Map([...list.children].map(item=>[item.dataset.groupId,item]));
  for(const {record,item} of entries) {
    const id=record.facility_id??record.course_id;
    if(!groups.has(id))groups.set(id,{facility:catalogModel.facilityById.get(record.facility_id),items:[]});
    if(item)groups.get(id).items.push(item);
  }
  for(const [id,item] of existing)if(!groups.has(id))item.remove();
  let index=0;
  const pending=[...groups];
  function appendGroups() {
    browseGroupFrame=null;
    if(view.resultsPanel.hidden)return;
    const start=incremental?performance.now():0;
    while(index<pending.length) {
      const [id,group]=pending[index];
      const item=existing.get(id)||facilityGroup(group.facility,id),article=item.firstElementChild;
      article.dataset.active=String(group.facility?.facility_id===activeFacility);
      const courses=article.querySelector(".facility-courses");
      for(const child of [...courses.children])if(!group.items.includes(child))child.remove();
      group.items.forEach((child,at)=>{if(courses.children[at]!==child)moveCourseCard(courses,child,courses.children[at]||null);});
      courses.hidden=!group.items.length;
      article.querySelector(".facility-empty").hidden=Boolean(group.items.length);
      if(list.children[index]!==item)moveCourseCard(list,item,list.children[index]||null);
      index++;
      if(incremental&&performance.now()-start>=4&&index<pending.length) {
        browseGroupFrame=requestAnimationFrame(appendGroups);return;
      }
    }
  }
  appendGroups();
}
function updateDisplaySortOptions() {
  const sort = $("browse-sort"), choices = [["name","Name"],["holes","Holes"]];
  if (planningMode && state.ranking?.courses.some(c=>Number.isFinite(c.maximum_seconds))) choices.push(["maximum","Longest driving time"],["combined","Combined driving time"],
    ...state.rows.filter(row => row.coordinate).map(row => [`origin:${row.id}`,`Golfer ${state.rows.indexOf(row)+1} driving time`]));
  const key = JSON.stringify(choices);
  if (sort.optionsKey !== key) {
    sort.optionsKey = key;sort.replaceChildren(...choices.map(([value,label]) => {const option=document.createElement("option");option.value=value;option.textContent=label;return option;}));
  }
  const value = planningMode && choices.some(([value]) => value === planningDisplaySort) ? planningDisplaySort : choices.some(([value])=>value===sort.value)?sort.value:"name";
  sort.value = value;
}
function updateLoadedCount(count, facilities = 0) {
  view.resultCount.textContent = String(count);
  view.resultCount.setAttribute("title", facilities ? "Number of entries loaded" : "Number of courses loaded");
  view.resultCount.setAttribute("aria-label", facilities
    ? `Number of entries loaded: ${count} (${count-facilities} courses, ${facilities} facilities)`
    : `Number of courses loaded: ${count}`);
}
function catalogLoadMessage() {
  const unavailable=$("catalog-status").textContent?.includes("unavailable");
  if(!initialMap)return unavailable?"Catalog unavailable.":"Catalog is still loading. No browse course list is available yet.";
  return unavailable?"Course details unavailable.":"Course details are loading. The course list will appear when verified.";
}
function renderCourses(incremental = false) {
  if(view.resultsPanel.hidden)return;
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
    const message=catalogLoadMessage();
    $("browse-description").textContent=message;
    view.results.replaceChildren(node("p",message));
    return;
  }
  const selectedFacility=activeFacility;
  let entries=scopedEntries();
  reconcileBrowseSelection(entries.filter(record=>record.course_id));
  if(activeFacility!==selectedFacility)entries=scopedEntries();
  const facilities=entries.filter(record=>!record.course_id);
  if(catalogModel.facilityById.has(activeFacility)&&!catalogModel.facilityCourses(activeFacility).length&&!facilities.some(f=>f.facility_id===activeFacility))closeSelection(false);
  const ordered=selectedFirst(entries,browseRecordId),groupId=record=>record.facility_id??record.course_id;
  const shown=new Set([...new Set(ordered.map(groupId))].slice(0,listLimit));
  for(const item of view.results.querySelector(".course-list")?.children||[])if(item.contains(document.activeElement))shown.add(item.dataset.groupId);
  const visible=ordered.filter(record=>shown.has(groupId(record)));
  updateLoadedCount(visible.length,visible.filter(record=>!record.course_id).length);
  $("browse-description").textContent=browseScope?.label || "Courses in this map area";
  let list=view.results.querySelector(".course-list");
  if(!list||list.dataset.planning==="true") {
    rankingNodes.clear();rowInteractions.clear();browseNodes.clear();
    list=node("ol",undefined,"course-list");view.results.replaceChildren(list);
  }
  const desired=new Set(visible.map(browseRecordId));
  for(const [id,item] of browseNodes)if(!desired.has(id)){item.remove();browseNodes.delete(id);}
  const focused=document.activeElement;
  const grouped=visible.map(record=>{
    const id=browseRecordId(record);
    let item=browseNodes.get(id);
    if(record.course_id) {
      if(!item){item=courseCard(browseCard(record,catalogModel.destinations),selected("objective"));browseNodes.set(id,item);}
      item.firstElementChild.dataset.active=String(record.course_id===state.activeCourse);
    }
    return {record,item};
  });
  renderFacilityGroups(list,grouped,incremental);
  if(focused&&list.contains(focused)&&document.activeElement!==focused)focused.focus({preventScroll:true});
  view.results.querySelector(".browse-more")?.remove();view.results.querySelector(".browse-empty")?.remove();
  if(entries.length>visible.length) {
    const more=node("button","Show more","quiet-button browse-more");
    more.addEventListener("click",()=>{listLimit+=60;renderCourses();});view.results.append(more);
  }
  if(!entries.length) {
    view.results.append(node("p","No matching courses.","browse-empty"));
  }
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
    catalogModel?.mapRecords || initialMap?.mapRecords || [],
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
function cancelSearchChoice() {
  pendingSearchChoice=null;
  if(searchChoiceFrame!==null)cancelAnimationFrame(searchChoiceFrame);
  searchChoiceFrame=null;
}
function scheduleSearchChoice() {
  if(pendingSearchChoice===null||searchChoiceFrame!==null)return;
  searchChoiceFrame=requestAnimationFrame(()=>{
    searchChoiceFrame=null;
    if(searchCameraActive)return;
    const result=pendingSearchChoice;pendingSearchChoice=null;
    if(result)applySearchChoice(result);
  });
}
function chooseSearch(result) {
  pendingSearchChoice=result;
  closeSearch();
  scheduleSearchChoice();
}
function bindSearchChoices() {
  map.on("zoomstart movestart",()=>{searchCameraActive=true;});
  // Register after viewport reconciliation so the old camera settles first.
  map.on("moveend",()=>{
    searchCameraActive=false;
    if(searchChoiceFrame!==null)cancelAnimationFrame(searchChoiceFrame);
    searchChoiceFrame=null;
    scheduleSearchChoice();
  });
  document.addEventListener("pointerdown",cancelSearchChoice);
  document.addEventListener("keydown",event=>{if(event.key==="Escape")cancelSearchChoice();});
  map.getContainer().addEventListener("wheel",cancelSearchChoice,{passive:true});
  $("place-query").addEventListener("input",cancelSearchChoice);
  $("plan-toggle").addEventListener("click",cancelSearchChoice);
  $("courses-grip").addEventListener("click",cancelSearchChoice);
}
function applySearchChoice(result) {
  if(!catalogModel)deferredSelection=null;
  planningMode = false; planningSession?.invalidate(committedOrigins()); $("browse-access").value = "all"; setDrawer("plan", false);
  closeSearch();
  $("place-query").value =
    result.kind === "facility"
      ? `${result.label}, ${result.subtitle}`
      : result.label;
  browseMode = true;
  listLimit = 60;
  if (result.kind === "facility") {
    browseScope = { ids: [result.id], label: result.facility?.record_kind==="course"?"Course search":"Facility search" };
    selectFacilityById(result.id, true);
    setDrawer("courses", true);
  } else {
    const records =
      result.kind === "state"
        ? (catalogModel?.mapRecords || initialMap.mapRecords).filter((f) => f.state === result.id)
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
  if (!catalogModel && !initialMap) return;
  const counts = catalogCounts(catalogModel?.mapRecords || initialMap.mapRecords);
  $("progress-counts").replaceChildren(
    ...[
      [catalogModel?.facilities.length ?? initialMap.counts.facilities, "Facilities"],
      [catalogModel?.courses.length ?? initialMap.counts.courses, "Courses"],
      [counts.onMap, "On map"],
      [counts.pending, "Not yet mapped"],
    ].map(([n, label]) => {
      const d = node("div");
      d.append(node("strong", fmt(n)), node("span", label));
      return d;
    }),
  );
}

function applyCatalog(next) {
  catalogDate = `revision ${next.revision}`;
  state.routingCatalogLabel = `Catalog ${catalogDate} · ${planningAdapter?.policy?.label || "driving times unavailable"}`;
  catalogModel = next;
  browseNodes.clear();
  view.results.replaceChildren();
  planningSession?.setCatalog(next);
  const selectedState = $("browse-state").value;
  $("browse-state").replaceChildren(new Option("All states","all"), ...[...new Set(next.mapRecords.map(f => f.state).filter(Boolean))].sort().map(state => new Option(geometry?.states.find(s => s.id === state)?.name || state,state)));
  if ([...$("browse-state").options].some(o => o.value === selectedState)) $("browse-state").value = selectedState;
  if (activeFacility && !next.mapRecordById.has(activeFacility)) closeSelection();
  $("catalog-status").textContent = "";
  $("catalog-status").hidden = true;
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
  if (!planningMode) {browseScope={kind:"viewport",label:"Courses in this map area"};listLimit=60;}
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
$("close-plan").onclick = () => {planningMode = false; browseMode = true; browseScope={kind:"viewport",label:"Courses in this map area"};listLimit=60; $("browse-access").value = "all"; planningSession?.invalidate(committedOrigins());setDrawer("plan", false);renderCourses();};
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
for (const id of ["browse-state", "browse-holes", "browse-round", "browse-access", "browse-style", "browse-sort"])
  $(id).onchange = () => {
    if (id === "browse-access" && planningMode) planningSession?.accessChanged($(id).value);
    if (id === "browse-sort" && planningMode) planningDisplaySort = $(id).value;
    listLimit = 60;
    renderCourses();
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
// Immediate pin fits are synchronous, before recording the deferred intent.
// Any later camera start supersedes that pending selection while details load.
map.on("movestart zoomstart",()=>{if(!catalogModel)deferredSelection=null;});
map.on("moveend zoomend", () => {
  drawFacilities();
  refreshBrowseViewport();
});
map.on("click",()=>closeSelection());
map.on("popupclose",event=>{if(event.popup===cataloguePopup){cataloguePopup=null;closeSelection();}});
async function loadCatalog() {
  try {
    initialMap=await loadInitialMap(catalogURL);
    geometry={states:initialMap.states};
    $("catalog-status").hidden=true;
    drawFacilities();renderProgress();
    performance.mark("fairway-map-ready");
    // Let the initial canvas paint before starting the background details load.
    requestAnimationFrame(()=>setTimeout(ensureCatalog,0));
  } catch {
    $("catalog-status").hidden=false;
    $("catalog-status").textContent="Catalog unavailable.";
    if(planningMode && !browseMode && state.ranking)renderCourses();
    else view.results.replaceChildren(node("p","Catalog unavailable."));
  }
}
function ensureCatalog() {
  if(catalogModel||detailsRequest||!initialMap)return;
  $("catalog-status").hidden=false;
  $("catalog-status").textContent="Loading course details…";
  detailsRequest=loadPublicCatalog(catalogURL,{pinnedManifest:initialMap.manifest}).then(next=>{
    applyCatalog(next);
    performance.mark("fairway-details-ready");
    const select=deferredSelection;deferredSelection=null;
    select?.();
  }).catch(()=>{
    $("catalog-status").hidden=false;
    $("catalog-status").textContent="Course details unavailable.";
    renderCourses();
  }).finally(()=>{detailsRequest=null;});
}
planningSession = new PublicPlanningSession({notify:renderPreparation});
function detailPanelsChanged() {
  if(view.resultsPanel.hidden)deferredSelection=null;
  if(!view.resultsPanel.hidden || !$("plan-panel").hidden)ensureCatalog();
}
const detailsObserver=new MutationObserver(detailPanelsChanged);
for(const panel of [view.resultsPanel,$("plan-panel")])detailsObserver.observe(panel,{attributes:true,attributeFilter:["hidden"]});
bindSearchChoices();

for (let count = requiredOriginRows(state.rows.length); count > 0; count -= 1)
  addOrigin();
loadCatalog();
