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
};
const REDUCED_MOTION = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

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
  mapKey: document.querySelector("#map-key"),
  filterToggle: document.querySelector("#filter-toggle"),
  filterPopover: document.querySelector("#filter-popover"),
};
let nextOriginId = 1;

const map = L.map("map", { zoomControl: true }).setView([41.94, -87.8], 10);
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution:
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  maxZoom: 19,
}).addTo(map);
new ResizeObserver(() => map.invalidateSize()).observe(document.querySelector("#map"));

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
  if (!visible) setFilterOpen(false);
  view.resultsPanel.hidden = !visible;
  view.mapKey.hidden = !visible;
  view.appShell.classList.toggle("has-results", visible);
  requestAnimationFrame(() => map.invalidateSize({ animate: false }));
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

function courseMarkerLabel(course, rank = null) {
  return rank ? `${course.name}, rank ${rank}` : course.name;
}

function courseIcon(course, rank = null) {
  const active = state.activeCourse === course.id ? " active" : "";
  const ranked = rank ? " ranked" : "";
  return L.divIcon({
    className: "",
    html: `<span class="course-pin${ranked}${active}"><span>${rank || ""}</span></span>`,
    iconSize: [27, 27],
    iconAnchor: [13, 24],
    popupAnchor: [0, -22],
  });
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
  return state.ranking?.courses.find((course) => course.id === courseId) || null;
}

function popupContent(course) {
  const result = currentResult(course.id);
  const content = document.createElement("div");
  content.className = "course-popup";
  const heading = document.createElement("h3");
  heading.textContent = course.name;
  const details = document.createElement("p");
  details.textContent = `${course.holes} holes · ${course.access} · ${course.address}`;
  content.append(heading, details);
  if (result) {
    const times = document.createElement("ul");
    times.className = "popup-times";
    result.travel_times_seconds.forEach((seconds, index) => {
      const item = document.createElement("li");
      item.style.background = state.activeRows[index]?.color || COLORS[index];
      item.textContent = `Golfer ${index + 1}: ${duration(seconds)}`;
      times.append(item);
    });
    content.append(times);
  }
  const link = document.createElement("a");
  link.href = course.website;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.textContent = "Open course site";
  content.append(link);
  return content;
}

function clearCourseMarkers() {
  state.courseMarkers.forEach((marker) => marker.remove());
  state.courseMarkers.clear();
}

function drawCourseMarkers() {
  clearCourseMarkers();
  state.ranking?.courses.forEach((course) => {
    const label = courseMarkerLabel(course, course.rank);
    const marker = L.marker(course.coordinate, {
      icon: courseIcon(course, course.rank),
      keyboard: true,
      title: label,
      alt: label,
    })
      .addTo(map)
      .bindPopup(() => popupContent(course));
    labelMarker(marker, label);
    marker.on("click", () => selectCourse(course.id, true));
    state.courseMarkers.set(course.id, marker);
  });
}

function updateCourseMarkers() {
  state.ranking?.courses.forEach((course) => {
    const marker = state.courseMarkers.get(course.id);
    if (!marker) return;
    marker.setIcon(courseIcon(course, course.rank));
    labelMarker(marker, courseMarkerLabel(course, course.rank));
    marker.setZIndexOffset(state.activeCourse === course.id ? 1000 : 500 - course.rank);
    if (marker.isPopupOpen()) marker.setPopupContent(popupContent(course));
  });
}

function selectCourse(courseId, scrollToCard = false) {
  state.activeCourse = courseId;
  updateCourseMarkers();
  document.querySelectorAll(".course-card").forEach((card) => {
    card.dataset.active = String(card.dataset.courseId === courseId);
  });
  const card = [...document.querySelectorAll(".course-card")].find(
    (candidate) => candidate.dataset.courseId === courseId,
  );
  if (scrollToCard) {
    card?.scrollIntoView({
      block: "nearest",
      behavior: REDUCED_MOTION ? "auto" : "smooth",
    });
  }
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
  if (map.getZoom() < 10) map.setView(coordinate, 10, { animate: !REDUCED_MOTION });
  calculate();
}

async function suggest(row) {
  const query = row.input.value.trim();
  closeSuggestions(row, true);
  if (parseCoordinate(query) || query.length < 3 || looksLikeCoordinateInput(query)) return;
  const controller = new AbortController();
  row.controller = controller;
  try {
    const scope = state.photonBbox ? `&bbox=${state.photonBbox}` : "&countrycode=US";
    const response = await fetch(
      `https://photon.komoot.io/api/?limit=5${scope}&q=${encodeURIComponent(query)}`,
      { signal: controller.signal },
    );
    if (!response.ok) throw new Error();
    const result = await response.json();
    if (row.controller !== controller || row.input.value.trim() !== query) return;
    result.features.forEach((feature) => {
      const geometry = feature?.geometry?.coordinates;
      if (!Array.isArray(geometry) || geometry.length < 2) return;
      const coordinate = [Number(geometry[1]), Number(geometry[0])];
      if (!coordinate.every(Number.isFinite) || !insideCore(coordinate)) return;
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
      setStatus("Address suggestions are unavailable. Enter latitude, longitude instead.", true);
    }
  } finally {
    if (row.controller === controller) row.controller = null;
  }
}

function unusedColor() {
  const used = new Set(state.rows.map((row) => row.color));
  return COLORS.find((candidate) => !used.has(candidate)) || COLORS[state.rows.length % COLORS.length];
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
      row.timer = setTimeout(calculate, 200);
      return;
    }
    row.coordinate = null;
    row.marker?.remove();
    row.marker = null;
    clearRanking();
    setStatus("Add at least two golfer origins.");
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
    calculate();
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
  state.ranking = null;
  state.activeRows = [];
  state.activeCourse = null;
  view.results.setAttribute("aria-busy", "false");
  view.results.replaceChildren();
  view.resultCount.textContent = "";
  view.rankingDescription.textContent = "";
  clearCourseMarkers();
  setResultsVisible(false);
}

function restoreFilters(result) {
  const objective = document.querySelector(
    `input[name="objective"][value="${result.objective}"]`,
  );
  const holesValue = result.holes.length === 2 ? "all" : String(result.holes[0]);
  const holes = document.querySelector(`input[name="holes"][value="${holesValue}"]`);
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
    const zoom = Math.max(map.getZoom(), 12);
    if (REDUCED_MOTION) map.setView(course.coordinate, zoom, { animate: false });
    else map.flyTo(course.coordinate, zoom);
    state.courseMarkers.get(course.id)?.openPopup();
  };
  const rank = document.createElement("span");
  rank.className = "rank";
  rank.textContent = course.rank;
  const body = document.createElement("div");
  const title = document.createElement("h3");
  title.className = "course-title";
  title.textContent = course.name;
  const meta = document.createElement("div");
  meta.className = "course-meta";
  [course.holes + " holes", course.access].forEach((label) => {
    const value = document.createElement("span");
    value.textContent = label;
    meta.append(value);
  });
  const scores = document.createElement("div");
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
    time.style.setProperty("--golfer", state.activeRows[index]?.color || COLORS[index]);
    time.textContent = `${index + 1} · ${duration(seconds)}`;
    time.ariaLabel = `Golfer ${index + 1}: ${duration(seconds)}`;
    times.append(time);
  });
  const footer = document.createElement("div");
  footer.className = "card-footer";
  const address = document.createElement("span");
  address.textContent = course.address;
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
  result.courses.forEach((course) => list.append(courseCard(course, result.objective)));
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
    map.fitBounds(bounds.pad(0.08), { maxZoom: 12, animate: !REDUCED_MOTION });
  });
}

async function responseBody(response) {
  try {
    return await response.json();
  } catch {
    return { error: `Request failed with status ${response.status}.` };
  }
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
  if (!previousRanking) clearRanking();
  const controller = new AbortController();
  state.request = controller;
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
    setStatus(`${result.courses.length} courses ranked on the current static road snapshot.`);
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
      view.results.setAttribute("aria-busy", "false");
    }
  }
}

async function configure() {
  try {
    const response = await fetch("/api/config");
    const config = await responseBody(response);
    if (!response.ok) throw new Error(config.error);
    state.maxOrigins = Math.min(config.max_origins, COLORS.length);
    const [south, west, north, east] = config.core_bounds;
    state.coreBounds = [south, west, north, east];
    state.photonBbox = [west, south, east, north].join(",");
    view.catalogName.textContent = `${config.course_catalog.title} · ${config.course_catalog.as_of}`;
    state.ready = true;
    calculate();
  } catch (error) {
    setStatus(error.message || "Course coverage is unavailable.", true);
    clearRanking();
  }
}

view.addOrigin.onclick = addOrigin;
document.querySelectorAll('input[name="objective"], input[name="holes"]').forEach((input) => {
  input.onchange = () => calculate({ preserveResults: true });
});
view.filterToggle.onclick = () => setFilterOpen(view.filterPopover.hidden, true);
view.filterPopover.addEventListener("keydown", (event) => {
  if (event.key !== "Tab") return;
  const tabStops = [...view.filterPopover.querySelectorAll("input:checked")];
  const first = tabStops[0];
  const last = tabStops[tabStops.length - 1];
  const leavingBackwards = event.shiftKey && document.activeElement === first;
  const leavingForwards = !event.shiftKey && document.activeElement === last;
  if (!leavingBackwards && !leavingForwards) return;
  event.preventDefault();
  setFilterOpen(false);
  const destination = leavingBackwards
    ? view.filterToggle
    : view.results.querySelector(".course-focus") || view.filterToggle;
  destination.focus();
});
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
map.on("popupclose", () => {
  state.activeCourse = null;
  updateCourseMarkers();
  document.querySelectorAll(".course-card").forEach((card) => {
    card.dataset.active = "false";
  });
});

addOrigin();
addOrigin();
configure();
