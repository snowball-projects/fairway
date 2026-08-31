# fairway working agreements

- Write `snowball`, `fairway`, and `modo` in lowercase in visible copy.
- Keep fairway an independent group golf-course chooser. It accepts two or more
  golfer origins and ranks a bounded course catalog by either the longest
  individual drive or combined driving time. It does not calculate or display
  an optimal midpoint or meeting region.
- Keep ranking inputs trustworthy and reproducible. The official catalog,
  supported filters, source links, routing points, and update method are
  canonical in `data/README.md`.
- Keep travel-time providers replaceable. The current provider uses modo and an
  immutable static OpenStreetMap road snapshot. Do not make fairway depend on a
  hosted modo interface.
- Use Apache-2.0 for software. Treat OpenStreetMap-derived road and course data
  as separately licensed under ODbL and preserve its attribution.
- Keep the service stateless, private by default, and free of accounts,
  analytics, advertising, behavioral tracking, and personalized results.
- Do not claim live traffic, prices, ratings, tee times, or availability without
  a lawful, reliable source. Outbound links to official course sites are enough.
- Keep official hosted-service behavior and limits canonical in `SERVICE.md`.
- Keep the linked AI-agent provenance statement exactly `Built by AI agents`,
  without qualifiers, and link it to snowball's canonical policy.
- Prefer the smallest reliable design and never use em dashes.
