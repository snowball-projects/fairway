# Hosted service

This policy applies to snowball's official fairway deployment at
<https://fairway-n29h.onrender.com>. Operators of independent deployments set
their own service policies.

## Behavior

- fairway has no accounts, advertising, or analytics.
- Confirmed origin coordinates and points selected for travel-time comparison
  are sent to fairway for calculation and kept only in bounded process memory.
  They are not written to a database.
- Results use the identified static road snapshot and cost profile. Traffic,
  depart-at, and arrive-by calculations are not currently supported.

## Browser services

- Address text goes directly from the browser to the public Photon demo
  service. Suggestion requests are restricted to the active snapshot's
  supported core. Photon receives the query and ordinary request metadata,
  such as the browser's IP address. Manually entered coordinates do not go to
  Photon.
- The browser loads Leaflet JavaScript from unpkg and map tiles directly from
  OpenStreetMap's tile service. Those services receive ordinary request
  metadata. Tile requests also identify the viewed map tiles.
- Nearby searches open Google Maps in a new window. The search text and
  selected coordinates go directly to Google and are not sent through fairway.

## Acceptable use

Use the service for ordinary interactive meeting-region calculations. Do not
intentionally disrupt it, evade its limits, send automated bulk traffic, access
another person's data, or use it in violation of applicable law or another
person's rights. Good-faith security research is welcome when it avoids harm and
is reported privately.

snowball may reject, limit, or block abusive traffic. The service is provided
without a guarantee of availability.

## Current limits

An evaluation accepts between two and 32 origins, a tolerance from zero to five
minutes, and at most 32 KiB of JSON. Coordinates must be valid latitude and
longitude pairs no more than 5 km from a road vertex in the active snapshot.
The initial Chicago snapshot spans 41.8500077 to 42.1799662 latitude and
-88.1399989 to -87.6012705 longitude.

The two returned regions may contain at most 5,000 road points combined. fairway
rejects a wider exact result instead of silently truncating it; use a smaller
tolerance and try again. Each process retains at most eight successful recent
analyses, which expire through eviction or restart. These limits may change as
operating experience develops.

Report security issues through [GitHub's private vulnerability reporting
form](https://github.com/snowball-projects/fairway/security/advisories/new).
