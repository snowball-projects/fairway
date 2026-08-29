const state = { rows: [], evaluation: null, request: null, layers: [] };
const map = L.map("map", { zoomControl: true }).setView([41.88, -87.82], 9);
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  maxZoom: 19,
}).addTo(map);
const canvas = L.canvas({ padding: 0.5 });
new ResizeObserver(() => map.invalidateSize()).observe(document.querySelector("#map"));

function color(index) {
  return `hsl(${(198 + index * 137.508) % 360} 62% 38%)`;
}

function clearResults() {
  state.evaluation = null;
  state.layers.splice(0).forEach((layer) => layer.remove());
}

function setStatus(message) {
  document.querySelector("#status").textContent = message;
}

function address(feature) {
  const value = feature.properties;
  return [value.name, value.street, value.city || value.district, value.state, value.country]
    .filter((part, index, parts) => part && parts.indexOf(part) === index)
    .join(", ");
}

function setOrigin(row, label, latitude, longitude) {
  row.input.value = label;
  row.coordinate = [Number(latitude), Number(longitude)];
  row.suggestions.replaceChildren();
  row.marker?.remove();
  const index = state.rows.indexOf(row);
  row.marker = L.marker(row.coordinate, {
    icon: L.divIcon({ className: "", html: `<span class="origin-pin" style="background:${color(index)}">${index + 1}</span>` }),
  }).addTo(map);
  calculate();
}

async function suggest(row) {
  const query = row.input.value.trim();
  row.controller?.abort();
  row.suggestions.replaceChildren();
  const coordinates = query.match(/^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$/);
  if (coordinates) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = `Use ${coordinates[1]}, ${coordinates[2]}`;
    button.onclick = () => setOrigin(row, button.textContent.slice(4), coordinates[1], coordinates[2]);
    const item = document.createElement("li");
    item.append(button);
    row.suggestions.append(item);
    return;
  }
  if (query.length < 3) return;
  row.controller = new AbortController();
  try {
    const response = await fetch(`https://photon.komoot.io/api/?limit=5&q=${encodeURIComponent(query)}`, { signal: row.controller.signal });
    const result = await response.json();
    result.features.forEach((feature) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = address(feature);
      button.onclick = () => setOrigin(row, button.textContent, feature.geometry.coordinates[1], feature.geometry.coordinates[0]);
      const item = document.createElement("li");
      item.append(button);
      row.suggestions.append(item);
    });
  } catch (error) {
    if (error.name !== "AbortError") setStatus("Address suggestions are unavailable. Enter latitude, longitude instead.");
  }
}

function addOrigin() {
  const row = { coordinate: null, marker: null, timer: null, controller: null };
  const element = document.createElement("div");
  element.className = "origin";
  element.style.setProperty("--origin", color(state.rows.length));
  row.input = document.createElement("input");
  row.input.placeholder = `Origin ${state.rows.length + 1}`;
  row.input.autocomplete = "off";
  row.input.ariaLabel = row.input.placeholder;
  row.suggestions = document.createElement("ul");
  row.suggestions.className = "suggestions";
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "remove";
  remove.ariaLabel = `Remove ${row.input.placeholder.toLowerCase()}`;
  remove.textContent = "×";
  remove.onclick = () => {
    row.marker?.remove();
    state.rows.splice(state.rows.indexOf(row), 1);
    element.remove();
    renumber();
    calculate();
  };
  row.input.oninput = () => {
    row.coordinate = null;
    row.marker?.remove();
    row.marker = null;
    clearResults();
    clearTimeout(row.timer);
    row.timer = setTimeout(() => suggest(row), 350);
    calculate();
  };
  element.append(row.input, remove, row.suggestions);
  document.querySelector("#origins").append(element);
  state.rows.push(row);
  renumber();
}

function renumber() {
  state.rows.forEach((row, index) => {
    row.input.placeholder = `Origin ${index + 1}`;
    row.input.parentElement.style.setProperty("--origin", color(index));
    if (row.marker) row.marker.setIcon(L.divIcon({ className: "", html: `<span class="origin-pin" style="background:${color(index)}">${index + 1}</span>` }));
  });
}

function drawRegion(points, kind) {
  const options = kind === "total"
    ? { radius: 3, color: "#7652c8", weight: 0, fillOpacity: 0.42, renderer: canvas }
    : { radius: 4, color: "#ed7b3a", weight: 1.5, fillOpacity: 0, renderer: canvas };
  const group = L.layerGroup(points.map((point) => L.circleMarker(point, options))).addTo(map);
  state.layers.push(group);
}

async function calculate() {
  state.request?.abort();
  clearResults();
  const origins = state.rows.filter((row) => row.coordinate).map((row) => row.coordinate);
  if (origins.length < 2) {
    setStatus("Add at least two origins.");
    return;
  }
  state.request = new AbortController();
  setStatus("Calculating both regions…");
  try {
    const response = await fetch("/api/evaluations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ origins, tolerance_seconds: Number(document.querySelector("#tolerance").value) * 60 }),
      signal: state.request.signal,
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error);
    state.evaluation = result;
    drawRegion(result.total.region, "total");
    drawRegion(result.maximum.region, "maximum");
    const bounds = L.latLngBounds([...origins, ...result.total.region, ...result.maximum.region]);
    if (bounds.isValid()) map.fitBounds(bounds.pad(0.12));
    const tolerance = Number(document.querySelector("#tolerance").value);
    setStatus(`Showing exact ${tolerance}-minute regions from ${result.provenance.snapshot}. Click anywhere to compare trips.`);
  } catch (error) {
    if (error.name !== "AbortError") setStatus(error.message || "fairway could not calculate these origins.");
  }
}

function minutes(seconds) {
  return `${Math.round(seconds / 60)} min`;
}

map.on("click", async ({ latlng }) => {
  if (!state.evaluation) {
    L.popup().setLatLng(latlng).setContent("Add at least two valid origins first.").openOn(map);
    return;
  }
  const popup = L.popup().setLatLng(latlng).setContent("Calculating travel times…").openOn(map);
  try {
    const response = await fetch(`/api/evaluations/${state.evaluation.id}/travel-times`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ coordinate: [latlng.lat, latlng.lng] }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error);
    const content = document.createElement("div");
    content.className = "point-popup";
    content.innerHTML = `<strong>${result.coordinate[0].toFixed(5)}, ${result.coordinate[1].toFixed(5)}</strong>`;
    const list = document.createElement("ul");
    result.travel_times_seconds.forEach((time, index) => {
      const item = document.createElement("li");
      item.innerHTML = `<span style="color:${color(index)}">Origin ${index + 1}</span><strong>${minutes(time)}</strong>`;
      list.append(item);
    });
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
      const query = `${input.value} near ${result.coordinate[0]}, ${result.coordinate[1]}`;
      window.open(`https://www.google.com/maps/search/${encodeURIComponent(query)}`, "_blank", "noopener");
    };
    content.append(list, form);
    popup.setContent(content);
  } catch (error) {
    popup.setContent(error.message || "Travel times are unavailable.");
  }
});

document.querySelector("#add-origin").onclick = addOrigin;
document.querySelector("#tolerance").onchange = calculate;
addOrigin();
addOrigin();
