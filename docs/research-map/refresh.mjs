// Poll tiny publication hashes. Large snapshots are fetched only after a change.
export function watchSnapshots({
  onCatalog,
  onProgress,
  onAdditions,
  onStatus,
  visibility = document,
  fetcher = fetch,
  interval = 60000,
  setTimer = setTimeout,
  clearTimer = clearTimeout,
}) {
  let timer,
    active = null,
    stopped = false,
    delay = interval;
  let catalogHash = null,
    progressHash = null,
    additionsHash = null;
  const schedule = () => {
    clearTimer(timer);
    if (!stopped && !visibility.hidden) timer = setTimer(check, delay);
  };
  async function read(path, hash = null) {
    if (stopped || visibility.hidden || active.signal.aborted)
      throw new Error("Paused");
    const response = await fetcher(path, {
      cache: "no-cache",
      signal: AbortSignal.any([active.signal, AbortSignal.timeout(15000)]),
    });
    if (!response.ok) throw new Error("Snapshot unavailable");
    const body = await response.arrayBuffer();
    if (hash) {
      const digest = [
        ...new Uint8Array(await crypto.subtle.digest("SHA-256", body)),
      ]
        .map((n) => n.toString(16).padStart(2, "0"))
        .join("");
      if (digest !== hash) throw new Error("Publication changed during fetch");
    }
    return JSON.parse(new TextDecoder().decode(body));
  }
  async function check() {
    clearTimer(timer);
    if (stopped || active || visibility.hidden) return;
    active = new AbortController();
    try {
      const publication = await read("./publication.json");
      if (visibility.hidden || stopped) return;
      if (!/^[a-f0-9]{64}$/.test(publication?.catalog_sha256))
        throw new Error("Invalid publication");
      let changed = false;
      if (publication.catalog_sha256 !== catalogHash) {
        const catalog = await read(
          "../../data/public-courses.json",
          publication.catalog_sha256,
        );
        if (visibility.hidden || stopped) return;
        onCatalog(catalog);
        changed = catalogHash !== null;
        catalogHash = publication.catalog_sha256;
      }
      if (
        /^[a-f0-9]{64}$/.test(publication.additions_sha256) &&
        publication.additions_sha256 !== additionsHash
      ) {
        try {
          const additions = await read(
            "../../data/catalog-additions.json",
            publication.additions_sha256,
          );
          if (visibility.hidden || stopped) return;
          onAdditions(additions);
          additionsHash = publication.additions_sha256;
        } catch {
          if (!additionsHash) onAdditions(null);
        }
      }
      // Missing research status must never block an otherwise valid catalog.
      if (
        /^[a-f0-9]{64}$/.test(publication.progress_sha256) &&
        publication.progress_sha256 !== progressHash
      ) {
        try {
          const progress = await read(
            "../../data/research-progress.json",
            publication.progress_sha256,
          );
          if (visibility.hidden || stopped) return;
          onProgress(progress);
          progressHash = publication.progress_sha256;
        } catch {
          if (!progressHash) onProgress(null);
        }
      }
      delay = interval;
      if (!visibility.hidden && !stopped) onStatus({ state: "ok", changed });
    } catch {
      if (!visibility.hidden && !stopped) {
        delay = Math.min(delay * 2, 600000);
        onStatus({ state: "delayed" });
      }
    } finally {
      active = null;
      schedule();
    }
  }
  function visible() {
    clearTimer(timer);
    if (visibility.hidden) {
      active?.abort();
      onStatus({ state: "paused" });
    } else if (!active) check();
  }
  visibility.addEventListener("visibilitychange", visible);
  check();
  return () => {
    stopped = true;
    clearTimer(timer);
    active?.abort();
    visibility.removeEventListener("visibilitychange", visible);
  };
}
