# Public catalog service policy

This describes the prepared public Pages release; publication is pending schema and
release review. Independent deployments set their own policies. The existing
calculation API is separate and its source, credentials and provider configuration
are unchanged by this work.

The public interface has no accounts, analytics, advertising or behavioral tracking.
Catalog search, filters, committed-coordinate selection and map fitting run in the
browser. The browser does not send origins to fairway's calculation service, modo,
TomTom, Spark or another routing provider. Driving times are unavailable.

GitHub Pages serves static assets and a checksummed SQLite-derived read projection.
Ordinary hosting requests expose standard connection metadata to GitHub. The full
SQLite, recovery SQL, private source controls and retained documents are not browser
assets. There is no editable JSON catalog or browser SQLite engine.

The map requests OpenStreetMap tiles; the tile service receives ordinary request
metadata and the visible map area. Committing an address with Enter or blur sends
the address directly to Photon, with omitted credentials and a ten-second timeout.
Typing alone does not send a lookup. Manually entered coordinates remain local.
No automatic browser location request or origin persistence is used. Operators'
external website links open separately; fairway does not broker bookings.

Catalog records are dated and incomplete. Property points are map context, not
necessarily drivable entrances. Courses, components and scoring rounds are distinct;
unknowns never mean zero, false or confirmed availability. At the frozen758 baseline,
optional JSON observations and retained historical prose are not uniformly normalized.
The consumer does not infer comparable prices, amenities or design credits from raw
keys. Typed optional-field migration and exact layout confirmation remain pending.
Quality/star ratings and live tee-time availability are not supplied. Tee difficulty
rating measures playing difficulty, not quality.

Source URLs, dates, scope, conflict qualifications, attribution and data licenses are
retained with public observations. Software is MIT; third-party data retain their
own terms. Catalog browsing grants no permission to republish restricted source
materials or to scrape external booking services.
