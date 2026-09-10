import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import test from "node:test";

const manifestPath = resolve("scripts/contiguous-us-osm-sources.json");
const runnerPath = resolve("scripts/run-contiguous-us-osm-golf-catalog.ps1");

test("fixed source manifest covers only the contiguous states and Washington, DC", async () => {
  const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
  const jurisdictions = manifest.jurisdictions;
  const slugs = jurisdictions.map(({ slug }: { slug: string }) => slug);

  assert.equal(manifest.extractDate, "2026-07-31");
  assert.equal(jurisdictions.length, 49);
  assert.deepEqual(slugs, [...slugs].sort());
  assert.equal(new Set(slugs).size, 49);
  assert.equal(slugs.includes("district-of-columbia"), true);
  assert.equal(slugs.includes("alaska"), false);
  assert.equal(slugs.includes("hawaii"), false);
  assert.equal(slugs.includes("puerto-rico"), false);
  assert.equal(
    jurisdictions.reduce((sum: number, source: { expectedBytes: number }) => sum + source.expectedBytes, 0),
    11_691_605_431,
  );
  for (const source of jurisdictions) {
    assert.equal(source.file, `${source.slug}-260731.osm.pbf`);
    assert.match(source.md5, /^[0-9a-f]{32}$/u);
    assert.equal(Number.isSafeInteger(source.expectedBytes) && source.expectedBytes > 0, true);
  }
  const fingerprint = [
    manifest.provider,
    manifest.dataset,
    manifest.extractDate,
    manifest.baseUrl,
    ...jurisdictions.map(
      (source: { name: string; slug: string; file: string; expectedBytes: number; md5: string }) =>
        `${source.name}|${source.slug}|${source.file}|${source.expectedBytes}|${source.md5}`,
    ),
  ].join("\n");
  assert.equal(
    createHash("sha256").update(fingerprint).digest("hex"),
    "cee4a8888f4665bdb755340a0535eeb5050c5fd240120a94857281d6d52233f4",
  );
});

test("national runner keeps artifacts ignored and records resumable state completion", async () => {
  const runner = await readFile(runnerPath, "utf8");
  assert.match(runner, /\.local\\contiguous-us-osm-rehearsal/u);
  assert.match(runner, /check-ignore/u);
  assert.match(runner, /Manifest jurisdictions must be in deterministic ordinal slug order/u);
  assert.match(runner, /complete\.json/u);
  assert.match(runner, /outputJsonlSha256/u);
});
