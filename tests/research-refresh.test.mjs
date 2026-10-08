import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { setImmediate } from "node:timers/promises";
import { watchSnapshots } from "../docs/research-map/refresh.mjs";
import {
  addedFacilities,
  buildModel,
  parseAdditions,
} from "../docs/research-map/model.mjs";

const record = (name, address = null) => ({
  name,
  state: "MN",
  address,
  county: null,
  holes: 18,
});
const catalog = (...facilities) => ({ facilities, county_checklist: [] });
const json = (value) => JSON.stringify(value);
const hash = (body) => createHash("sha256").update(body).digest("hex");
const response = (body, status = 200) => new Response(body, { status });
const log = {
  schema_version: 1,
  time_basis: "git_commit_time",
  count_unit: "provisional_facility_entry",
  history_complete_from: null,
  batches: [],
};

async function until(condition) {
  for (let i = 0; i < 1000; i++) {
    if (condition()) return;
    await setImmediate();
  }
  assert.fail("refresh did not settle");
}
function harness(options = {}) {
  const visibility = new EventTarget();
  visibility.hidden = false;
  const timers = new Set(),
    calls = [],
    views = [],
    states = [],
    histories = [];
  const h = {
    body: json(catalog(record("Original"))),
    logBody: null,
    progressBody: null,
    manifestBody: null,
    failure: false,
    pending: null,
    ...options,
  };
  const stop = watchSnapshots({
    visibility,
    setTimer: (callback, delay) => {
      const timer = { callback, delay };
      timers.add(timer);
      return timer;
    },
    clearTimer: (timer) => timers.delete(timer),
    fetcher: async (path, options) => {
      calls.push({ path, options });
      if (h.pending) return h.pending(path, options);
      if (h.failure) return response("unavailable", 503);
      if (path === "./publication.json")
        return response(
          h.manifestBody ??
            json({
              catalog_sha256: hash(h.body),
              additions_sha256: h.logBody && hash(h.logBody),
              progress_sha256: h.progressBody && hash(h.progressBody),
            }),
        );
      if (path.includes("catalog-additions")) return response(h.logBody);
      if (path.includes("research-progress")) return response(h.progressBody);
      return response(h.body);
    },
    onCatalog: (value) => views.push(buildModel(value)),
    onProgress: () => {},
    onAdditions: (value) => histories.push(value && parseAdditions(value)),
    onStatus: (value) => states.push(value),
  });
  return Object.assign(h, {
    timers,
    calls,
    views,
    states,
    histories,
    stop,
    async tick() {
      assert.equal(timers.size, 1);
      const [timer] = timers;
      timers.delete(timer);
      await timer.callback();
    },
    visible(hidden) {
      visibility.hidden = hidden;
      visibility.dispatchEvent(new Event("visibilitychange"));
    },
  });
}
test("an initially unavailable catalog retries without inventing a baseline", async () => {
  const h = harness({ failure: true });
  try {
    await until(() => h.timers.size === 1);
    assert.equal(h.views.length, 0);
    assert.equal(h.states.at(-1).state, "delayed");
    h.failure = false;
    await h.tick();
    assert.equal(h.views.length, 1);
    assert.equal(h.states.at(-1).changed, false);
  } finally {
    h.stop();
  }
});

test("unchanged hashes skip large catalog downloads and changed data ignores optional status failure", async () => {
  const h = harness();
  try {
    await until(() => h.timers.size === 1);
    assert.equal(h.views.length, 1);
    assert.equal(h.states.at(-1).changed, false);
    await h.tick();
    assert.equal(
      h.calls.filter((c) => c.path.includes("public-courses")).length,
      1,
    );
    h.body = json(catalog(record("Original"), record("Addition")));
    h.progressBody = "not JSON";
    await h.tick();
    assert.equal(h.views.at(-1).records.length, 2);
    assert.equal(h.states.at(-1).changed, true);
    assert.equal([...h.timers][0].delay, 60000);
    assert.ok(h.calls.every((c) => c.options.cache === "no-cache"));
  } finally {
    h.stop();
  }
});
test("HTTP, malformed JSON, invalid models and mismatched hashes retain the old view with bounded backoff", async () => {
  const h = harness();
  try {
    await until(() => h.timers.size === 1);
    h.failure = true;
    await h.tick();
    assert.equal([...h.timers][0].delay, 120000);
    h.failure = false;
    h.manifestBody = "not JSON";
    await h.tick();
    assert.equal([...h.timers][0].delay, 240000);
    h.manifestBody = json({ catalog_sha256: "a".repeat(64) });
    await h.tick();
    assert.equal(h.views.length, 1);
    h.manifestBody = null;
    h.body = json({ facilities: [null], county_checklist: [] });
    await h.tick();
    assert.equal(h.views.length, 1);
    assert.equal([...h.timers][0].delay, 600000);
    h.body = json(catalog(record("Recovered")));
    await h.tick();
    assert.equal(h.views.at(-1).records[0].name, "Recovered");
    assert.equal([...h.timers][0].delay, 60000);
  } finally {
    h.stop();
  }
});
test("requests never overlap; hiding aborts and pauses; showing resumes; stop removes timers", async () => {
  const h = harness();
  try {
    await until(() => h.timers.size === 1);
    let inFlight = 0,
      maximum = 0;
    h.pending = (_path, { signal }) =>
      new Promise((_resolve, reject) => {
        inFlight++;
        maximum = Math.max(maximum, inFlight);
        signal.addEventListener(
          "abort",
          () => {
            inFlight--;
            reject(new Error("aborted"));
          },
          { once: true },
        );
      });
    const [timer] = h.timers;
    timer.callback();
    await until(() => inFlight === 1);
    h.visible(false);
    h.visible(false);
    assert.equal(maximum, 1);
    h.visible(true);
    await until(() => inFlight === 0);
    await setImmediate();
    assert.equal(h.timers.size, 0);
    assert.equal(h.states.at(-1).state, "paused");
    h.pending = null;
    h.visible(false);
    await until(() => h.timers.size === 1);
    assert.equal(h.states.at(-1).state, "ok");
    assert.equal(h.views.length, 1);
  } finally {
    h.stop();
  }
  assert.equal(h.timers.size, 0);
});
test("the durable log refreshes independently and rejects invented publication times or invalid counts", async () => {
  const h = harness();
  try {
    await until(() => h.timers.size === 1);
    h.logBody = json(log);
    await h.tick();
    assert.deepEqual(h.histories.at(-1), { completeFrom: null, batches: [] });
    assert.equal(
      h.calls.filter((c) => c.path.includes("public-courses")).length,
      1,
    );
    h.logBody = json({ ...log, time_basis: "published_at" });
    await h.tick();
    assert.equal(h.histories.length, 1);
    assert.equal(h.states.at(-1).state, "ok");
  } finally {
    h.stop();
  }
  const batch = {
    commit: "a".repeat(40),
    committed_at: "2026-10-08T21:45:43Z",
    initial_baseline: false,
    facilities_added: 1,
    added_facilities: [record("Addition")],
  };
  assert.equal(
    parseAdditions({ ...log, batches: [batch] }).batches[0].added,
    1,
  );
  assert.equal(
    parseAdditions({
      ...log,
      batches: [{ ...batch, facilities_added: 2, redacted_entries: 1 }],
    }).batches[0].redacted,
    1,
  );
  assert.throws(() =>
    parseAdditions({ ...log, batches: [{ ...batch, facilities_added: 2 }] }),
  );
  assert.throws(() =>
    parseAdditions({
      ...log,
      batches: [{ ...batch, committed_at: "unknown" }],
    }),
  );
});
test("addition identity survives order, address/name corrections and distinguishes another same-named facility", () => {
  const original = record("Original", "1 Main St");
  assert.deepEqual(
    addedFacilities([original], [{ ...original, address: "2 Main St" }]),
    [],
  );
  assert.deepEqual(
    addedFacilities([original], [{ ...original, name: "Corrected name" }]),
    [],
  );
  const another = record("Original", "3 Main St");
  assert.deepEqual(addedFacilities([original], [another, original]), [another]);
  assert.deepEqual(
    addedFacilities([original, another], [another, original]),
    [],
  );
});
