# Hosted service

This policy applies to snowball's official fairway deployment at
<https://fairway-n29h.onrender.com>. Operators of independent deployments set
their own service policies.

## Behavior

- fairway has no accounts, advertising, analytics, or behavioral tracking.
- Confirmed golfer coordinates, the hole filter, and the selected ranking are
  sent to fairway for one calculation. They are not written to a database,
  logged intentionally, or retained in an application cache.
- Process-global calculation limits retain only counters and update times.
  They store no IP address, coordinate, request body, or other user identifier.
- Results rank a dated, bounded course catalog. The interface identifies the
  active travel-time provider in **How this works**. TomTom estimates leaving
  now with live and historical traffic; the static modo provider uses a named
  road snapshot without traffic. Scheduled departures or arrivals, prices,
  ratings, tee times, and availability are not supported.
- When TomTom is active, fairway sends confirmed origin and course coordinates
  to TomTom's Matrix Routing v2 service over HTTPS. TomTom receives the service's
  request metadata and processes data under its own
  [privacy policy](https://www.tomtom.com/privacy/). fairway does not send the
  golfer's address text, browser IP address, or an account identifier to TomTom.
  Static routing keeps confirmed coordinates within the fairway service.
- Course links open the operator's official site. fairway does not broker
  bookings or receive booking information.

## Browser services

- Address text goes directly from the browser to the public Photon demo
  service. Suggestion requests are restricted to the active road snapshot's
  supported core. Photon receives the query and ordinary request metadata such
  as the browser's IP address. Manually entered coordinates do not go to Photon.
- fairway serves its own copy of Leaflet JavaScript. The browser loads map
  tiles directly from OpenStreetMap's tile service, which receives ordinary
  request metadata and the viewed map tiles.
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
Every origin must fall inside the `chicago-static-v1` supported core. Static
routing also requires each origin to be no more than 1 km from a road vertex.
The core spans 41.8600077 to 42.1699662
latitude and -88.1299989 to -87.6112705 longitude.

Ranking calculations have a process-global burst allowance of 12, replenished
at one calculation every two seconds. Only one calculation runs at a time.
Excess requests receive `429` or `503` with a short `Retry-After` value. This
identifier-free limit protects the free service without tracking visitors.

TomTom requests have a 20-second deadline, no automatic retry, and a default
limit of 80 submitted origin-course pairs per UTC day per process. Failed
attempts count toward that limit. This operational guard resets when the
process restarts; TomTom's account quotas remain authoritative. Provider
failures return a retryable error without silently substituting static times.
The service does not retain or export TomTom matrices as reusable datasets.

TomTom resolves leave-now departures separately for each origin-course pair.
Result provenance gives the earliest and latest returned departure times and
the calculation time. The provider does not report a traffic-data update time,
so fairway does not claim one. Drive estimates can change between rankings.

The `chicago-public-courses-v1` catalog contains eight public courses reviewed
as of August 30, 2026. It is incomplete, its facts and routing points can become
stale, and missing fields are not inferred. [data/README.md](data/README.md) is
the canonical coverage and provenance record.

Report security issues through [GitHub's private vulnerability reporting
form](https://github.com/snowball-projects/fairway/security/advisories/new).
