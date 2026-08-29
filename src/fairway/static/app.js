const MAX_ORIGINS = 32;
const MAX_TOLERANCE_MINUTES = 5;
const state = {
  rows: [],
  activeRows: [],
  evaluation: null,
  request: null,
  pointRequest: null,
  pointPopup: null,
  photonBbox: null,
  layers: [],
};
const view = {
  addOrigin: document.querySelector("#add-origin"),
  origins: document.querySelector("#origins"),
  pointCoordinate: document.querySelector("#point-coordinate"),
  pointForm: document.querySelector("#point-form"),
  pointResult: document.querySelector("#point-result"),
  resultSummary: document.querySelector("#result-summary"),
  results: document.querySelector("#results"),
  status: document.querySelector("#status"),
  tolerance: document.querySelector("#tolerance"),
};
const map = L.map("map", { zoomControl: true }).setView([39.8, -98.6], 4);
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  maxZoom: 19,
}).addTo(map);
const canvas = L.canvas({ padding: 0.5 });
new ResizeObserver(() => map.invalidateSize()).observe(document.querySelector("#map"));

function color(index) {
  return `hsl(${(198 + index * 137.508) % 360} 62% 38%)`;
}

function setStatus(message) {
  view.status.textContent = message;
}

function cancelPointRequest() {
  state.pointRequest?.abort();
  state.pointRequest = null;
}

function closePointPopup() {
  state.pointPopup?.remove();
  state.pointPopup = null;
}

function clearResults() {
  state.request?.abort();
  state.request = null;
  cancelPointRequest();
  closePointPopup();
  state.evaluation = null;
  state.activeRows = [];
  state.layers.splice(0).forEach((layer) => layer.remove());
  map.closePopup();
  view.results.hidden = true;
  view.resultSummary.replaceChildren();
  view.pointResult.replaceChildren();
  view.pointCoordinate.value = "";
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

function duration(seconds) {
  const roundedSeconds = Math.round(seconds);
  if (roundedSeconds < 60) return `${roundedSeconds} sec`;
  return `${Number((roundedSeconds / 60).toFixed(1))} min`;
}

function address(feature) {
  const value = feature?.properties || {};
  return [value.name, value.street, value.city || value.district, value.state, value.country]
    .filter((part, index, parts) => part && parts.indexOf(part) === index)
    .join(", ");
}

function originIcon(index) {
  return L.divIcon({
    className: "",
    html: `<span class="origin-pin" style="background:${color(index)}">${index + 1}</span>`,
  });
}

function updateOriginMarker(row) {
  const index = state.rows.indexOf(row);
  if (index < 0 || !row.coordinate) return;
  if (row.marker) {
    row.marker.setLatLng(row.coordinate);
    row.marker.setIcon(originIcon(index));
  } else {
    row.marker = L.marker(row.coordinate, {
      icon: originIcon(index),
      keyboard: false,
    }).addTo(map);
  }
}

function setOrigin(row, label, latitude, longitude) {
  const coordinate = [Number(latitude), Number(longitude)];
  if (
    !coordinate.every(Number.isFinite) ||
    Math.abs(coordinate[0]) > 90 ||
    Math.abs(coordinate[1]) > 180
  ) {
    setStatus("Enter coordinates as latitude, longitude within their valid ranges.");
    return;
  }
  row.input.value = label;
  row.input.removeAttribute("title");
  row.input.removeAttribute("aria-description");
  row.coordinate = coordinate;
  row.controller?.abort();
  row.controller = null;
  row.suggestions.replaceChildren();
  updateOriginMarker(row);
  calculate();
}

async function suggest(row) {
  const query = row.input.value.trim();
  row.controller?.abort();
  row.suggestions.replaceChildren();
  const coordinates = parseCoordinate(query);
  if (coordinates) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = `Use ${formatCoordinate(coordinates)}`;
    button.onclick = () => setOrigin(row, formatCoordinate(coordinates), ...coordinates);
    const item = document.createElement("li");
    item.append(button);
    row.suggestions.append(item);
    return;
  }
  if (query.length < 3) return;
  const controller = new AbortController();
  row.controller = controller;
  try {
    const scope = state.photonBbox
      ? `&bbox=${state.photonBbox}`
      : "&countrycode=US";
    const response = await fetch(
      `https://photon.komoot.io/api/?limit=5${scope}&q=${encodeURIComponent(query)}`,
      { signal: controller.signal },
    );
    if (!response.ok) throw new Error("Address suggestions are unavailable.");
    const result = await response.json();
    if (
      row.controller !== controller ||
      row.input.value.trim() !== query ||
      !state.rows.includes(row)
    ) {
      return;
    }
    result.features.forEach((feature) => {
      const geometry = feature?.geometry?.coordinates;
      if (!Array.isArray(geometry) || geometry.length < 2) return;
      const coordinate = [Number(geometry[1]), Number(geometry[0])];
      if (
        !coordinate.every(Number.isFinite) ||
        Math.abs(coordinate[0]) > 90 ||
        Math.abs(coordinate[1]) > 180
      ) {
        return;
      }
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = address(feature) || formatCoordinate(coordinate);
      button.onclick = () => setOrigin(row, button.textContent, ...coordinate);
      const item = document.createElement("li");
      item.append(button);
      row.suggestions.append(item);
    });
  } catch (error) {
    if (error.name !== "AbortError") {
      setStatus("Address suggestions are unavailable. Enter latitude, longitude instead.");
    }
  }
}

function addOrigin() {
  if (state.rows.length >= MAX_ORIGINS) return;
  const row = {
    coordinate: null,
    marker: null,
    timer: null,
    controller: null,
    input: null,
    remove: null,
    suggestions: null,
  };
  const element = document.createElement("div");
  element.className = "origin";
  element.style.setProperty("--origin", color(state.rows.length));
  row.input = document.createElement("input");
  row.input.autocomplete = "off";
  row.suggestions = document.createElement("ul");
  row.suggestions.className = "suggestions";
  row.remove = document.createElement("button");
  row.remove.type = "button";
  row.remove.className = "remove";
  row.remove.textContent = "×";
  row.remove.onclick = () => {
    clearTimeout(row.timer);
    row.controller?.abort();
    row.marker?.remove();
    state.rows.splice(state.rows.indexOf(row), 1);
    element.remove();
    renumber();
    calculate();
  };
  row.input.oninput = () => {
    row.coordinate = null;
    row.controller?.abort();
    row.controller = null;
    row.suggestions.replaceChildren();
    row.input.removeAttribute("title");
    row.input.removeAttribute("aria-description");
    row.marker?.remove();
    row.marker = null;
    clearResults();
    clearTimeout(row.timer);
    row.timer = setTimeout(() => suggest(row), 350);
    calculate();
  };
  element.append(row.input, row.remove, row.suggestions);
  view.origins.append(element);
  state.rows.push(row);
  renumber();
}

function renumber() {
  state.rows.forEach((row, index) => {
    const label = `Origin ${index + 1}`;
    row.input.placeholder = label;
    row.input.ariaLabel = label;
    row.remove.ariaLabel = `Remove origin ${index + 1}`;
    row.input.parentElement.style.setProperty("--origin", color(index));
    if (row.marker) row.marker.setIcon(originIcon(index));
  });
  view.addOrigin.disabled = state.rows.length >= MAX_ORIGINS;
}

function reconcileOrigins(rows, snappedOrigins) {
  rows.forEach((row, index) => {
    const enteredAsCoordinate = parseCoordinate(row.input.value);
    row.coordinate = snappedOrigins[index];
    if (enteredAsCoordinate) row.input.value = formatCoordinate(row.coordinate);
    const description = `Road-network point ${formatCoordinate(row.coordinate)}`;
    row.input.title = description;
    row.input.setAttribute("aria-description", description);
    updateOriginMarker(row);
  });
}

function drawRegion(points, kind, tolerance) {
  const markers = points.map((point) => {
    const strength = tolerance ? Math.max(0, 1 - point.excess_seconds / tolerance) : 1;
    const exact = point.excess_seconds < 0.001;
    const options =
      kind === "total"
        ? {
            radius: exact ? 5 : 2 + 2.5 * strength,
            color: "#7652c8",
            weight: 0,
            fillOpacity: 0.08 + 0.64 * strength,
            renderer: canvas,
            interactive: false,
          }
        : {
            radius: exact ? 6 : 2.5 + 2.5 * strength,
            color: "#ed7b3a",
            weight: 0.6 + 1.8 * strength,
            opacity: 0.14 + 0.76 * strength,
            fillOpacity: 0,
            renderer: canvas,
            interactive: false,
          };
    return L.circleMarker(point.coordinate, options);
  });
  const group = L.layerGroup(markers).addTo(map);
  state.layers.push(group);
}

function objectiveSummary(title, result, measure) {
  const article = document.createElement("article");
  const heading = document.createElement("h3");
  heading.textContent = title;
  const detail = document.createElement("p");
  detail.textContent = `${measure}. Exact point: ${formatCoordinate(result.optimum)}. Region: ${result.region.length.toLocaleString()} road points.`;
  const inspect = document.createElement("button");
  inspect.type = "button";
  inspect.textContent = "Compare travel times here";
  inspect.onclick = () => {
    view.pointCoordinate.value = formatCoordinate(result.optimum);
    inspectPoint(result.optimum, null, true);
  };
  article.append(heading, detail, inspect);
  return article;
}

function renderEvaluation(result) {
  view.results.hidden = false;
  view.resultSummary.replaceChildren(
    objectiveSummary(
      "Least driving overall",
      result.total,
      `${duration(result.total.objective_seconds)} combined driving time`,
    ),
    objectiveSummary(
      "Shortest longest drive",
      result.maximum,
      `${duration(result.maximum.objective_seconds)} longest drive`,
    ),
  );
}

async function responseBody(response) {
  try {
    return await response.json();
  } catch {
    return { error: `Request failed with status ${response.status}.` };
  }
}

async function calculate() {
  clearResults();
  const activeRows = state.rows.filter((row) => row.coordinate);
  const origins = activeRows.map((row) => row.coordinate);
  if (origins.length < 2) {
    setStatus("Add at least two origins.");
    return;
  }
  const toleranceMinutes = Number(view.tolerance.value);
  if (
    !Number.isFinite(toleranceMinutes) ||
    toleranceMinutes < 0 ||
    toleranceMinutes > MAX_TOLERANCE_MINUTES
  ) {
    setStatus(`Region tolerance must be between 0 and ${MAX_TOLERANCE_MINUTES} minutes.`);
    return;
  }
  const tolerance = toleranceMinutes * 60;
  const controller = new AbortController();
  state.request = controller;
  setStatus("Calculating both regions…");
  try {
    const response = await fetch("/api/evaluations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ origins, tolerance_seconds: tolerance }),
      signal: controller.signal,
    });
    const result = await responseBody(response);
    if (!response.ok) throw new Error(result.error);
    if (state.request !== controller) return;
    reconcileOrigins(activeRows, result.origins);
    state.evaluation = result;
    state.activeRows = activeRows;
    drawRegion(result.total.region, "total", tolerance);
    drawRegion(result.maximum.region, "maximum", tolerance);
    renderEvaluation(result);
    const regionPoints = [...result.total.region, ...result.maximum.region].map(
      (point) => point.coordinate,
    );
    const bounds = L.latLngBounds([...result.origins, ...regionPoints]);
    if (bounds.isValid()) map.fitBounds(bounds.pad(0.12));
    setStatus("Results ready.");
  } catch (error) {
    if (error.name !== "AbortError" && state.request === controller) {
      setStatus(error.message || "fairway could not calculate these origins.");
    }
  } finally {
    if (state.request === controller) state.request = null;
  }
}

function searchForm(coordinate) {
  const form = document.createElement("form");
  const input = document.createElement("input");
  input.required = true;
  input.placeholder = "Mexican food, golf…";
  input.ariaLabel = "Search nearby";
  const button = document.createElement("button");
  button.textContent = "Search";
  form.append(input, button);
  form.onsubmit = (event) => {
    event.preventDefault();
    const query = `${input.value} near ${coordinate[0]}, ${coordinate[1]}`;
    window.open(`https://www.google.com/maps/search/${encodeURIComponent(query)}`, "_blank", "noopener");
  };
  return form;
}

function pointContent(result, activeRows, compact) {
  const content = document.createElement("div");
  content.className = "point-popup";
  const heading = document.createElement(compact ? "strong" : "h3");
  heading.className = "point-address";
  heading.textContent = formatCoordinate(result.coordinate);
  const list = document.createElement("ul");
  list.className = "travel-times";
  result.travel_times_seconds.forEach((time, index) => {
    const currentIndex = state.rows.indexOf(activeRows[index]);
    const originIndex = currentIndex < 0 ? index : currentIndex;
    const label = `Origin ${originIndex + 1}: ${duration(time)}`;
    const item = document.createElement("li");
    item.className = "time-pill";
    item.style.background = color(originIndex);
    item.textContent = compact ? duration(time) : label;
    if (compact) item.ariaLabel = label;
    list.append(item);
  });
  const total = result.travel_times_seconds.reduce((sum, time) => sum + time, 0);
  const totalItem = document.createElement("li");
  totalItem.className = "time-pill total-time";
  totalItem.textContent = `${duration(total)} total`;
  list.append(totalItem);
  content.append(heading, list, searchForm(result.coordinate));
  return content;
}

async function inspectPoint(coordinate, popup = null, focusResult = false) {
  if (state.pointPopup !== popup) closePointPopup();
  if (popup) state.pointPopup = popup;
  const evaluation = state.evaluation;
  const activeRows = [...state.activeRows];
  if (!evaluation) {
    const message = "Add at least two valid origins first.";
    setStatus(message);
    if (popup) popup.setContent(message);
    return;
  }
  if (
    !coordinate.every(Number.isFinite) ||
    Math.abs(coordinate[0]) > 90 ||
    Math.abs(coordinate[1]) > 180
  ) {
    const message = "Enter a point as latitude, longitude within their valid ranges.";
    setStatus(message);
    if (popup) popup.setContent(message);
    return;
  }
  cancelPointRequest();
  const controller = new AbortController();
  state.pointRequest = controller;
  view.pointResult.textContent = "Calculating travel times…";
  if (popup) popup.setContent("Calculating travel times…");
  try {
    const response = await fetch(`/api/evaluations/${evaluation.id}/travel-times`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ coordinate }),
      signal: controller.signal,
    });
    const result = await responseBody(response);
    if (!response.ok) throw new Error(result.error);
    if (state.pointRequest !== controller || state.evaluation !== evaluation) return;
    view.pointCoordinate.value = formatCoordinate(result.coordinate);
    view.pointResult.replaceChildren(pointContent(result, activeRows, false));
    if (popup) {
      popup.setLatLng(result.coordinate);
      popup.setContent(pointContent(result, activeRows, true));
    }
    if (focusResult) view.pointResult.focus();
    setStatus("Travel times ready.");
  } catch (error) {
    if (
      error.name !== "AbortError" &&
      state.pointRequest === controller &&
      state.evaluation === evaluation
    ) {
      const message = error.message || "Travel times are unavailable.";
      view.pointResult.textContent = message;
      if (popup) popup.setContent(message);
      setStatus(message);
    }
  } finally {
    if (state.pointRequest === controller) state.pointRequest = null;
  }
}

map.on("click", ({ latlng }) => {
  view.pointCoordinate.value = formatCoordinate([latlng.lat, latlng.lng]);
  const popup = L.popup()
    .setLatLng(latlng)
    .setContent("Calculating travel times…")
    .openOn(map);
  inspectPoint([latlng.lat, latlng.lng], popup);
});

view.pointForm.onsubmit = (event) => {
  event.preventDefault();
  cancelPointRequest();
  closePointPopup();
  const coordinate = parseCoordinate(view.pointCoordinate.value);
  if (!coordinate) {
    const message = "Enter a point as latitude, longitude within their valid ranges.";
    view.pointResult.textContent = message;
    setStatus(message);
    return;
  }
  inspectPoint(coordinate, null, true);
};
view.pointCoordinate.oninput = () => {
  cancelPointRequest();
  closePointPopup();
  view.pointResult.replaceChildren();
  if (state.evaluation) setStatus("Results ready.");
};
view.addOrigin.onclick = addOrigin;
view.tolerance.onchange = calculate;
map.on("popupclose", ({ popup }) => {
  if (state.pointPopup === popup) state.pointPopup = null;
});

async function configure() {
  try {
    const response = await fetch("/api/config");
    const config = await responseBody(response);
    if (!response.ok) throw new Error(config.error);
    const [south, west, north, east] = config.core_bounds;
    state.photonBbox = [west, south, east, north].join(",");
    map.fitBounds([
      [south, west],
      [north, east],
    ]);
  } catch {
    setStatus("Road coverage is unavailable. Enter latitude, longitude to retry.");
  }
}

addOrigin();
addOrigin();
configure();
