# Public catalog service policy

The public Pages interface has no accounts, analytics, advertising or behavioral
tracking. Catalog search, filters, committed-coordinate selection and map fitting
run in the browser. The browser does not send origins to fairway's calculation
service, modo, TomTom, Spark or another routing provider. Driving times are
unavailable. The existing calculation API and its provider configuration remain
separate from this public catalog release. The unfinished private national API
prototype (PR15) is not a public service or an available routing fallback.

GitHub Pages serves static assets and a checksummed SQLite-derived read projection.
The browser first loads a derived map/search index, bounded to 4 MiB. Course
details load on demand from the same pinned release. The browser enforces a
16 KiB manifest limit, 64 MiB complete-catalog limit and a 30-second deadline per
load. Cached hash-named assets are still checksummed; unavailable or mismatched
details do not replace the map with data from another release.
The Pages builder bounds gzip expansion before parsing.
Ordinary hosting requests expose standard connection metadata to GitHub. The full
SQLite, recovery SQL, private source controls and retained documents are not browser
assets. There is no editable JSON catalog or browser SQLite engine.

The map requests OpenStreetMap tiles; the tile service receives ordinary request
metadata and the visible map area. Committing an address with Enter or blur sends
the address directly to Photon, with omitted credentials and a ten-second timeout.
Editing an origin, removing it or closing its suggestions cancels its active
lookup. Typing alone does not send a lookup. Manually entered coordinates remain
local.
No automatic browser location request or origin persistence is used. Operators'
external website links open separately; fairway does not broker bookings.

Catalog records are dated and incomplete. Property points provide map context,
not necessarily drivable entrances. Courses, components and scoring rounds are
distinct. Unknowns never mean zero, false, restricted or confirmed availability.
Typed optional observations keep their exact scope, dates and conditions; retained
historical prose is not a fallback and is not uniformly standardized. Prices are
observations, not current quotes. Quality/star ratings and live tee-time
availability are not supplied. Tee difficulty measures playing difficulty only.

Source URLs, dates, scope, conflicts, qualifications, attribution and data licenses
travel with public observations. Software is MIT; third-party data retain their
own terms. Catalog browsing grants no permission to republish restricted source
materials or scrape external booking services.
