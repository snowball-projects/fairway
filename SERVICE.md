# Hosted service

This policy applies to snowball's official fairway deployment at
<https://fairway-n29h.onrender.com>. Operators of independent deployments set
their own service policies.

## Behavior

- fairway has no accounts, advertising, analytics, or behavioral tracking.
- Confirmed golfer coordinates, the hole filter, and the selected ranking are
  sent to fairway for one calculation. They are not written to a database,
  logged intentionally, or retained in an application cache.
- Results rank a dated, bounded course catalog using the identified static road
  snapshot and cost profile. Traffic, scheduled departures or arrivals,
  prices, ratings, tee times, and availability are not supported.
- Course links open the operator's official site. fairway does not broker
  bookings or receive booking information.

## Browser services

- Address text goes directly from the browser to the public Photon demo
  service. Suggestion requests are restricted to the active road snapshot's
  supported core. Photon receives the query and ordinary request metadata such
  as the browser's IP address. Manually entered coordinates do not go to Photon.
- The browser loads Leaflet JavaScript from unpkg and map tiles directly from
  OpenStreetMap's tile service. Those services receive ordinary request
  metadata. Tile requests also identify the viewed map tiles.
- Opening a course site sends an ordinary browser request to that site's
  operator. The official fairway service does not receive that request.

## Acceptable use

Use the service for ordinary interactive course comparisons. Do not disrupt it,
evade its limits, send automated bulk traffic, or violate applicable law or
another person's rights. Report good-faith security research privately and avoid
harm. snowball may reject, limit, or block abusive traffic. Availability is not
guaranteed.

## Current limits

One ranking accepts between two and eight origins, a nonempty 9- or 18-hole
filter, one of the two documented ranking methods, and at most 32 KiB of JSON.
Every origin must fall inside the `chicago-static-v1` supported core and be no
more than 5 km from a road vertex. The core spans 41.8500077 to 42.1799662
latitude and -88.1399989 to -87.6012705 longitude.

The `chicago-public-courses-v1` catalog contains eight public courses reviewed
as of August 30, 2026. It is incomplete, its facts and routing points can become
stale, and missing fields are not inferred. [data/README.md](data/README.md) is
the canonical coverage and provenance record.

Report security issues through [GitHub's private vulnerability reporting
form](https://github.com/snowball-projects/fairway/security/advisories/new).
