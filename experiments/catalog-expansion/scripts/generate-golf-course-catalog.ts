import { createReadStream } from "node:fs";
import { writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { performance } from "node:perf_hooks";
import { createInterface } from "node:readline";
import { pathToFileURL } from "node:url";

type OsmType = "node" | "way" | "relation";
type CoordinateSource = "node" | "center" | "centroid" | "point_on_surface";
type OsmRef = { type: OsmType; id: number };
type Member = OsmRef & { role: string };
type OsmObject = OsmRef & {
  tags: Record<string, string>;
  coordinates: [number, number];
  coordinateSource: CoordinateSource;
  members: Member[];
};
type CourseInput = { course: OsmObject; contained: OsmObject[] };
type UnknownCounts = {
  name: number;
  holes: number;
  par: number;
  access: number;
  format: number;
  operator: number;
  website: number;
  address: number;
};
type UnknownField = keyof UnknownCounts;
type Counters = { conflictCount: number; invalidCount: number; unknownCounts: UnknownCounts };

const OSM_TYPES = ["node", "way", "relation"] as const;
const COORDINATE_SOURCES = ["node", "center", "centroid", "point_on_surface"] as const;

export type CatalogGenerationSummary = {
  sourceRecordCount: number;
  emittedCourseCount: number;
  skippedRecordCount: number;
  duplicateRecordCount: number;
  conflictCount: number;
  invalidCount: number;
  unknownCounts: UnknownCounts;
  outputBytes?: number;
  durationMs?: number;
};

export class CatalogInputError extends Error {}

export async function buildGolfCourseCatalog(inputPath: string) {
  const rows: CourseInput[] = [];
  let snapshot: string | undefined;
  let sourceHeaders = 0;
  let sourceRecordCount = 0;
  let skippedRecordCount = 0;
  let lineNumber = 0;
  const lines = createInterface({ input: createReadStream(inputPath, "utf8"), crlfDelay: Infinity });

  try {
    for await (const line of lines) {
      lineNumber += 1;
      if (!line.trim()) continue;
      let value: any;
      try {
        value = JSON.parse(line);
      } catch (error) {
        throw inputError(lineNumber, `invalid JSON: ${message(error)}`);
      }
      if (!record(value)) throw inputError(lineNumber, "record must be an object");
      if (value.kind === "source") {
        sourceHeaders += 1;
        if (sourceHeaders > 1) throw inputError(lineNumber, "only one source record is allowed");
        if (typeof value.snapshot !== "string" || !value.snapshot.trim()) {
          throw inputError(lineNumber, "source.snapshot must be a non-empty string");
        }
        snapshot = value.snapshot.trim();
        continue;
      }
      if (value.kind !== "course") {
        throw inputError(lineNumber, `unsupported record kind ${JSON.stringify(value.kind)}`);
      }
      sourceRecordCount += 1;
      const row = parseCourse(value, lineNumber);
      if (row.course.tags.leisure === "golf_course") rows.push(row);
      else skippedRecordCount += 1;
    }
  } catch (error) {
    lines.close();
    if (error instanceof CatalogInputError) throw error;
    throw new CatalogInputError(`Could not read catalog input: ${message(error)}`);
  }
  if (sourceHeaders !== 1 || !snapshot) {
    throw new CatalogInputError("Catalog input must contain exactly one source record.");
  }

  const groups = groupCourses(rows);
  const unknownCounts: UnknownCounts = {
    name: 0,
    holes: 0,
    par: 0,
    access: 0,
    format: 0,
    operator: 0,
    website: 0,
    address: 0,
  };
  const counters = { conflictCount: 0, invalidCount: 0, unknownCounts };
  const courses = groups.map((group) => normalizeCourse(group, counters)).sort((a, b) => cmp(a.id, b.id));
  const catalog = {
    schemaVersion: 1,
    source: { dataset: "openstreetmap", snapshot },
    courses,
  } as const;
  const summary: CatalogGenerationSummary = {
    sourceRecordCount,
    emittedCourseCount: courses.length,
    skippedRecordCount,
    duplicateRecordCount: rows.length - courses.length,
    ...counters,
  };
  return { catalog, summary };
}

export async function generateGolfCourseCatalog(inputPath: string, outputPath: string) {
  const started = performance.now();
  const { catalog, summary } = await buildGolfCourseCatalog(inputPath);
  const output = `${JSON.stringify(catalog)}\n`;
  await writeFile(outputPath, output, "utf8");
  return {
    ...summary,
    outputBytes: Buffer.byteLength(output),
    durationMs: Number((performance.now() - started).toFixed(1)),
  };
}

function parseCourse(value: any, line: number): CourseInput {
  if (!record(value.course)) throw inputError(line, "course must be an object");
  const course = parseObject(value.course, line, "course");
  const contained = value.contained ?? [];
  if (!Array.isArray(contained)) throw inputError(line, "contained must be an array");
  return {
    course,
    contained: contained.map((item, index) => parseObject(item, line, `contained[${index}]`)),
  };
}

function parseObject(value: any, line: number, field: string): OsmObject {
  if (!record(value)) throw inputError(line, `${field} must be an object`);
  const type = value.type as OsmType;
  if (!OSM_TYPES.includes(type)) throw inputError(line, `${field}.type is invalid`);
  if (!Number.isSafeInteger(value.id) || value.id <= 0) {
    throw inputError(line, `${field}.id must be a positive safe integer`);
  }
  if (!record(value.tags)) throw inputError(line, `${field}.tags must be an object`);
  const tags: Record<string, string> = {};
  for (const [key, tagValue] of Object.entries(value.tags)) {
    if (typeof tagValue !== "string") throw inputError(line, `${field}.tags.${key} must be a string`);
    tags[key] = tagValue;
  }
  if (
    !Array.isArray(value.coordinates) ||
    value.coordinates.length !== 2 ||
    !latitude(value.coordinates[0]) ||
    !longitude(value.coordinates[1])
  ) {
    throw inputError(line, `${field}.coordinates must be a valid [latitude, longitude] pair`);
  }
  const coordinateSource = value.coordinateSource as CoordinateSource;
  if (!COORDINATE_SOURCES.includes(coordinateSource)) {
    throw inputError(line, `${field}.coordinateSource is invalid`);
  }
  if ((type === "node") !== (coordinateSource === "node")) {
    throw inputError(line, `${field}.coordinateSource must be node only for OSM nodes`);
  }
  const rawMembers = value.members ?? [];
  if (!Array.isArray(rawMembers)) throw inputError(line, `${field}.members must be an array`);
  const members = rawMembers.map((member, index) => {
    if (!record(member)) throw inputError(line, `${field}.members[${index}] must be an object`);
    if (!OSM_TYPES.includes(member.type) || !Number.isSafeInteger(member.id) || member.id <= 0) {
      throw inputError(line, `${field}.members[${index}] has an invalid OSM identity`);
    }
    if (typeof member.role !== "string") {
      throw inputError(line, `${field}.members[${index}].role must be a string`);
    }
    return { type: member.type as OsmType, id: member.id, role: member.role };
  });
  return {
    type,
    id: value.id,
    tags,
    coordinates: [value.coordinates[0], value.coordinates[1]],
    coordinateSource,
    members,
  };
}

function groupCourses(rows: CourseInput[]) {
  const parent = rows.map((_, index) => index);
  const indexes = new Map<string, number[]>();
  rows.forEach(({ course }, index) => {
    const key = osmKey(course);
    indexes.set(key, [...(indexes.get(key) ?? []), index]);
  });
  for (const matches of indexes.values()) {
    for (const index of matches.slice(1)) union(parent, matches[0], index);
  }
  rows.forEach(({ course }, index) => {
    if (course.type !== "relation" || course.tags.type !== "multipolygon") return;
    for (const member of course.members) {
      if (member.type !== "way" || member.role !== "outer") continue;
      for (const memberIndex of indexes.get(osmKey(member)) ?? []) union(parent, index, memberIndex);
    }
  });
  const groups = new Map<number, CourseInput[]>();
  rows.forEach((row, index) => {
    const root = find(parent, index);
    groups.set(root, [...(groups.get(root) ?? []), row]);
  });
  return [...groups.values()];
}

function normalizeCourse(group: CourseInput[], counters: Counters) {
  const objects = group.map(({ course }) => course);
  const tags = objects.map(({ tags }) => tags);
  const provenance = uniqueRefs(objects);
  const coordinate = [...objects].sort(compareCoordinates)[0];
  const nameValues = tagValues(tags, ["name"]);
  const name = scalar(nameValues.length ? nameValues : tagValues(tags, ["official_name"]), text, "name", counters);
  const holes = scalar(tagValues(tags, ["holes", "golf:holes", "golf:course"]), holeCount, "holes", counters);
  const par = scalar(tagValues(tags, ["par", "golf:par"]), positiveInteger, "par", counters);
  const access = normalizeAccess(tags, counters);
  const format = normalizeFormat(tags, counters);
  const operator = scalar(tagValues(tags, ["operator"]), text, "operator", counters);
  const website = scalar(
    tagValues(tags, ["website", "contact:website", "url", "contact:url"]),
    httpUrl,
    "website",
    counters,
  );
  const address = normalizeAddress(tags, counters);
  return {
    id: `osm:${osmKey(provenance[0])}`,
    name,
    latitude: coordinate.coordinates[0],
    longitude: coordinate.coordinates[1],
    coordinate: {
      source: coordinate.coordinateSource,
      approximate: coordinate.coordinateSource !== "node",
    },
    holes,
    par,
    access,
    format,
    operator,
    website,
    address,
    arrivalCandidates: normalizeArrivals(group.flatMap(({ contained }) => contained)),
    osm: provenance,
  };
}

function normalizeAccess(tags: Record<string, string>[], counters: Counters) {
  const evidence = [
    ...taggedValues(tags, ["access", "golf:access"]),
    ...taggedValues(tags, ["golf:type"]).filter(({ value }) =>
      ["public", "private", "municipal"].includes(token(value)),
    ),
    ...taggedValues(tags, ["ownership"]),
  ];
  return scalar(
    evidence.map(({ key, value }) => `${key}\0${value}`),
    (entry) => {
      const [key, value] = entry.split("\0");
      const normalized = token(value);
      if (["access", "golf:access"].includes(key)) {
        if (["yes", "public", "permissive"].includes(normalized)) return "public";
        if (["private", "members"].includes(normalized)) return "private";
      }
      if (key === "golf:type") return normalized;
      if (key === "ownership" && normalized === "municipal") return "municipal";
    },
    "access",
    counters,
  ) ?? "unknown";
}

function normalizeFormat(tags: Record<string, string>[], counters: Counters) {
  const direct = tagValues(tags, ["golf:format", "course:type"]);
  const overloaded = tagValues(tags, ["golf:type", "golf:course"]).filter(
    (value) => courseFormat(value) !== undefined,
  );
  return scalar([...direct, ...overloaded], courseFormat, "format", counters);
}

function normalizeAddress(tags: Record<string, string>[], counters: Counters) {
  const parts = {
    full: addressPart(tags, "addr:full"),
    houseNumber: addressPart(tags, "addr:housenumber"),
    street: addressPart(tags, "addr:street"),
    unit: addressPart(tags, "addr:unit"),
    city: addressPart(tags, "addr:city"),
    region: addressPart(tags, "addr:state"),
    postalCode: addressPart(tags, "addr:postcode"),
    country: addressPart(tags, "addr:country"),
  };
  if (Object.values(parts).some((values) => values.length > 1)) {
    counters.conflictCount += 1;
    counters.unknownCounts.address += 1;
    return null;
  }
  const address = Object.fromEntries(
    Object.entries(parts).flatMap(([key, values]) => (values.length ? [[key, values[0]]] : [])),
  );
  if (!address.full && !(address.houseNumber && address.street)) {
    counters.unknownCounts.address += 1;
    return null;
  }
  return address;
}

function normalizeArrivals(objects: OsmObject[]) {
  const candidates = new Map<string, any>();
  for (const object of objects) {
    const kind =
      object.tags.golf === "clubhouse" ||
      object.tags.amenity === "clubhouse" ||
      object.tags.building === "clubhouse"
        ? "clubhouse"
        : object.tags.entrance === "main"
          ? "entrance"
          : object.tags.amenity === "parking" || object.tags.amenity === "parking_entrance"
            ? "parking"
            : undefined;
    if (!kind) continue;
    const candidate = {
      kind,
      latitude: object.coordinates[0],
      longitude: object.coordinates[1],
      coordinate: {
        source: object.coordinateSource,
        approximate: object.coordinateSource !== "node",
      },
      verified: false,
      osm: { type: object.type, id: object.id },
    };
    const key = osmKey(object);
    const previous = candidates.get(key);
    if (!previous || compareArrival(candidate, previous) < 0) candidates.set(key, candidate);
  }
  return [...candidates.values()].sort(compareArrival);
}

function scalar<T>(
  values: string[],
  parse: (value: string) => T | undefined,
  field: UnknownField,
  counters: Counters,
): T | null {
  if (!values.length) {
    counters.unknownCounts[field] += 1;
    return null;
  }
  const parsed = values.map(parse);
  const usable = unique(parsed.filter((value): value is T => value !== undefined));
  if (parsed.some((value) => value === undefined)) counters.invalidCount += 1;
  if (usable.length > 1) counters.conflictCount += 1;
  if (parsed.some((value) => value === undefined) || usable.length !== 1) {
    counters.unknownCounts[field] += 1;
    return null;
  }
  return usable[0];
}

function tagValues(tags: Record<string, string>[], keys: string[]) {
  return taggedValues(tags, keys).map(({ value }) => value);
}

function taggedValues(tags: Record<string, string>[], keys: string[]) {
  return tags.flatMap((record) =>
    keys.flatMap((key) => {
      const value = record[key]?.trim();
      return value ? [{ key, value }] : [];
    }),
  );
}

function addressPart(tags: Record<string, string>[], key: string) {
  return unique(tagValues(tags, [key]).map(text).filter((value): value is string => value !== undefined));
}

function text(value: string) {
  return value.trim().replaceAll(/\s+/gu, " ").normalize("NFC") || undefined;
}

function holeCount(value: string) {
  const match = /^(\d{1,2})(?:_hole)?$/u.exec(token(value));
  return match ? positiveInteger(match[1]) : undefined;
}

function positiveInteger(value: string) {
  const trimmed = value.trim();
  return /^\d{1,3}$/u.test(trimmed) && Number(trimmed) > 0 ? Number(trimmed) : undefined;
}

function courseFormat(value: string) {
  const normalized = token(value).replaceAll(/[- ]/gu, "_");
  if (["pitch_and_putt", "pitch_&_putt"].includes(normalized)) return "pitch-and-putt";
  if (["par_3", "par3"].includes(normalized)) return "par-3";
  if (normalized === "executive") return "executive";
  if (["full_length", "regulation"].includes(normalized)) return "full-length";
}

function httpUrl(value: string) {
  try {
    const url = new URL(value.trim());
    return ["http:", "https:"].includes(url.protocol) ? url.href : undefined;
  } catch {
    return undefined;
  }
}

function token(value: string) {
  return value.trim().toLowerCase();
}

function unique<T>(values: T[]) {
  return [...new Map(values.map((value) => [JSON.stringify(value), value])).values()];
}

function uniqueRefs(objects: OsmRef[]) {
  return [...new Map(objects.map((object) => [osmKey(object), { type: object.type, id: object.id }])).values()].sort(
    compareRefs,
  );
}

function compareRefs(left: OsmRef, right: OsmRef) {
  const rank = { relation: 0, way: 1, node: 2 };
  return rank[left.type] - rank[right.type] || left.id - right.id;
}

function compareCoordinates(left: OsmObject, right: OsmObject) {
  const rank = { node: 0, point_on_surface: 1, centroid: 2, center: 3 };
  return (
    rank[left.coordinateSource] - rank[right.coordinateSource] ||
    compareRefs(left, right) ||
    left.coordinates[0] - right.coordinates[0] ||
    left.coordinates[1] - right.coordinates[1]
  );
}

function compareArrival(left: any, right: any) {
  const rank = { clubhouse: 0, entrance: 1, parking: 2 };
  return rank[left.kind] - rank[right.kind] || compareRefs(left.osm, right.osm);
}

function find(parent: number[], index: number): number {
  if (parent[index] !== index) parent[index] = find(parent, parent[index]);
  return parent[index];
}

function union(parent: number[], left: number, right: number) {
  const a = find(parent, left);
  const b = find(parent, right);
  if (a !== b) parent[Math.max(a, b)] = Math.min(a, b);
}

function osmKey(object: OsmRef) {
  return `${object.type}/${object.id}`;
}

function cmp(left: string, right: string) {
  return left < right ? -1 : left > right ? 1 : 0;
}

function record(value: unknown): value is Record<string, any> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function latitude(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) && value >= -90 && value <= 90;
}

function longitude(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) && value >= -180 && value <= 180;
}

function inputError(line: number, detail: string) {
  return new CatalogInputError(`Catalog input line ${line}: ${detail}.`);
}

function message(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

export function formatGenerationSummary(summary: CatalogGenerationSummary) {
  const unknowns = Object.values(summary.unknownCounts).reduce((total, count) => total + count, 0);
  return [
    `${summary.sourceRecordCount} source records`,
    `${summary.emittedCourseCount} courses`,
    `${summary.skippedRecordCount} skipped`,
    `${summary.duplicateRecordCount} duplicates folded`,
    `${summary.conflictCount} conflicts`,
    `${summary.invalidCount} invalid fields`,
    `${unknowns} unknown fields`,
    `${summary.outputBytes ?? 0} bytes`,
    `${(summary.durationMs ?? 0).toFixed(1)} ms`,
  ].join("; ");
}

async function run() {
  const [input, output] = process.argv.slice(2);
  if (!input || !output) {
    throw new Error("Usage: npm run generate:golf-course-catalog -- <input.jsonl> <output.json>");
  }
  console.log(formatGenerationSummary(await generateGolfCourseCatalog(resolve(input), resolve(output))));
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) await run();
