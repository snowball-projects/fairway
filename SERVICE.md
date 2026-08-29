# Hosted service

This policy applies to snowball's official fairway deployment at
<https://fairway-n29h.onrender.com>. Operators of independent deployments set
their own service policies.

## Behavior

- fairway has no accounts, advertising, or analytics.
- Confirmed origin coordinates are sent to fairway for calculation and kept
  only in bounded process memory. They are not written to a database.
- Address text and suggestions go directly from the browser to Photon. Nearby
  searches open the selected external search service and are not sent to
  fairway.
- Results use the identified static road snapshot and cost profile. Traffic,
  depart-at, and arrive-by calculations are not currently supported.

## Acceptable use

Use the service for ordinary interactive meeting-region calculations. Do not
intentionally disrupt it, evade its limits, send automated bulk traffic, access
another person's data, or use it in violation of applicable law or another
person's rights. Good-faith security research is welcome when it avoids harm and
is reported privately.

snowball may reject, limit, or block abusive traffic. The service is provided
without a guarantee of availability.

## Current limits

Each request accepts at most 32 origins and 32 KiB of JSON. Each process retains
at most eight recent analyses, which expire through eviction or restart. These
limits may change as operating experience develops.

Report security issues through [GitHub's private vulnerability reporting
form](https://github.com/snowball-projects/fairway/security/advisories/new).
