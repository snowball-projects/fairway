import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import test from "node:test";

import {
  buildGolfCourseCatalog,
  CatalogInputError,
  generateGolfCourseCatalog,
} from "../scripts/generate-golf-course-catalog.ts";

const structuralFixture = resolve("audit/golf-course-catalog/structural-sample.jsonl");

test("minimal input keeps optional metadata unknown and coordinate provenance explicit", async () => {
  await withRows([course(1, {}, "node")], ({ catalog, summary }) => {
    assert.deepEqual(catalog.courses[0], {
      id: "osm:node/1",
      name: null,
      latitude: 41.9,
      longitude: -87.8,
      coordinate: { source: "node", approximate: false },
      holes: null,
      par: null,
      access: "unknown",
      format: null,
      operator: null,
      website: null,
      address: null,
      arrivalCandidates: [],
      osm: [{ type: "node", id: 1 }],
    });
    assert.equal(Object.values(summary.unknownCounts).reduce((sum, count) => sum + count, 0), 8);
  });
});

test("metadata normalization uses direct evidence and never infers from names or operators", async () => {
  const rows = [
    course(10, {
      access: "yes",
      holes: "18",
      par: "72",
      operator: "Example Operator",
      website: "https://example.com",
      "addr:housenumber": "1",
      "addr:street": "Main Street",
    }),
    course(11, { access: "private" }),
    course(12, { ownership: "municipal" }),
    course(13, { name: "Municipal Executive Par 3 Course", operator: "City of Example" }),
    course(14, { "golf:format": "par_3" }),
    course(15, { "golf:course": "pitch_and_putt" }),
  ];
  await withRows(rows, ({ catalog }) => {
    const byId = new Map(catalog.courses.map((record) => [record.id, record]));
    assert.equal(byId.get("osm:way/10").access, "public");
    assert.equal(byId.get("osm:way/10").holes, 18);
    assert.equal(byId.get("osm:way/10").par, 72);
    assert.equal(byId.get("osm:way/10").website, "https://example.com/");
    assert.deepEqual(byId.get("osm:way/10").address, {
      houseNumber: "1",
      street: "Main Street",
    });
    assert.equal(byId.get("osm:way/11").access, "private");
    assert.equal(byId.get("osm:way/12").access, "municipal");
    assert.equal(byId.get("osm:way/13").access, "unknown");
    assert.equal(byId.get("osm:way/13").format, null);
    assert.equal(byId.get("osm:way/14").format, "par-3");
    assert.equal(byId.get("osm:way/15").format, "pitch-and-putt");
  });
});

test("repeated identity folds while conflicting and invalid numeric evidence remains unknown", async () => {
  await withRows(
    [course(20, { holes: "18", par: "72 + 72" }), course(20, { "golf:holes": "9" })],
    ({ catalog, summary }) => {
      assert.equal(catalog.courses.length, 1);
      assert.equal(catalog.courses[0].holes, null);
      assert.equal(catalog.courses[0].par, null);
      assert.equal(summary.duplicateRecordCount, 1);
      assert.equal(summary.conflictCount, 1);
      assert.equal(summary.invalidCount, 1);
    },
  );
});

test("OSM multipolygon membership folds structurally while nearby names stay separate", async () => {
  const { catalog, summary } = await buildGolfCourseCatalog(structuralFixture);
  assert.equal(summary.sourceRecordCount, 4);
  assert.equal(summary.emittedCourseCount, 3);
  assert.equal(summary.duplicateRecordCount, 1);
  assert.equal(summary.conflictCount, 1);

  const folded = catalog.courses.find(({ id }) => id === "osm:relation/900100");
  assert.equal(folded.holes, null);
  assert.deepEqual(folded.osm, [
    { type: "relation", id: 900100 },
    { type: "way", id: 900101 },
  ]);
  assert.deepEqual(
    folded.arrivalCandidates.map(({ kind, verified }) => ({ kind, verified })),
    [
      { kind: "clubhouse", verified: false },
      { kind: "parking", verified: false },
    ],
  );

  const twins = catalog.courses.filter(({ name }) => name === "Twin Pines Golf Course");
  assert.equal(twins.length, 2);
  assert.deepEqual(
    twins.map(({ id }) => id),
    ["osm:way/900200", "osm:way/900201"],
  );
  assert.deepEqual(twins[0].coordinate, { source: "point_on_surface", approximate: true });
  assert.equal(twins[0].arrivalCandidates[0].kind, "entrance");
  assert.equal(twins[1].arrivalCandidates[0].kind, "parking");
  assert.equal(twins[1].arrivalCandidates[0].verified, false);
});

test("record and input ordering are deterministic", async () => {
  const directory = await mkdtemp(join(tmpdir(), "fairway-catalog-order-"));
  try {
    const reversedPath = join(directory, "reversed.jsonl");
    const lines = (await readFile(structuralFixture, "utf8")).trim().split("\n");
    await writeFile(reversedPath, `${lines.toReversed().join("\n")}\n`, "utf8");
    const original = await buildGolfCourseCatalog(structuralFixture);
    const reversed = await buildGolfCourseCatalog(reversedPath);
    assert.equal(JSON.stringify(original.catalog), JSON.stringify(reversed.catalog));
    assert.deepEqual(
      original.catalog.courses.map(({ id }) => id),
      ["osm:relation/900100", "osm:way/900200", "osm:way/900201"],
    );
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("malformed public input fails with its JSONL line number", async () => {
  const cases = [
    `${JSON.stringify(source())}\n{"kind":"course"\n`,
    `${JSON.stringify(source())}\n${JSON.stringify(course(30, {}).course)}\n`,
    jsonl([source(), { ...course(31, {}), course: { ...course(31, {}).course, coordinates: [999, 0] } }]),
  ];
  for (const [index, input] of cases.entries()) {
    const directory = await mkdtemp(join(tmpdir(), `fairway-catalog-bad-${index}-`));
    const path = join(directory, "input.jsonl");
    try {
      await writeFile(path, input, "utf8");
      await assert.rejects(
        buildGolfCourseCatalog(path),
        (error: unknown) => error instanceof CatalogInputError && /line 2/u.test(error.message),
      );
    } finally {
      await rm(directory, { recursive: true, force: true });
    }
  }
});

test("two generations are byte-for-byte reproducible", async () => {
  const directory = await mkdtemp(join(tmpdir(), "fairway-catalog-repro-"));
  try {
    const firstPath = join(directory, "first.json");
    const secondPath = join(directory, "second.json");
    const first = await generateGolfCourseCatalog(structuralFixture, firstPath);
    const second = await generateGolfCourseCatalog(structuralFixture, secondPath);
    const firstBytes = await readFile(firstPath);
    assert.deepEqual(firstBytes, await readFile(secondPath));
    assert.equal(first.outputBytes, second.outputBytes);
    assert.equal(firstBytes.toString("utf8").includes(directory), false);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

async function withRows(rows: any[], check: (result: any) => void) {
  const directory = await mkdtemp(join(tmpdir(), "fairway-catalog-"));
  const path = join(directory, "input.jsonl");
  try {
    await writeFile(path, jsonl([source(), ...rows]), "utf8");
    check(await buildGolfCourseCatalog(path));
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
}

function source() {
  return { kind: "source", snapshot: "test-snapshot" };
}

function course(id: number, tags: Record<string, string>, type: "node" | "way" = "way") {
  return {
    kind: "course",
    course: {
      type,
      id,
      tags: { leisure: "golf_course", ...tags },
      coordinates: [41.9, -87.8],
      coordinateSource: type === "node" ? "node" : "center",
    },
    contained: [],
  };
}

function jsonl(rows: any[]) {
  return `${rows.map(JSON.stringify).join("\n")}\n`;
}
