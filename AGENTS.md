# snowball working agreements

- Write `snowball`, `fairway`, and `modo` in lowercase in visible copy.
- Keep fairway a thin interface around modo. Fairway owns inputs, road snapshots,
  deployment, and presentation. modo owns optimization semantics.
- Use Apache-2.0 for software. Treat OpenStreetMap-derived data as separately
  licensed under ODbL and preserve its attribution.
- Keep the service stateless, private by default, and free of accounts,
  analytics, advertising, and destination ranking.
- Prefer the smallest reliable design. Explain current limits plainly and do not
  present future traffic support as implemented.
- Keep official service behavior and limits canonical in `SERVICE.md`.
- Keep the linked AI-agent provenance statement in the public interface and
  README exactly `Built by AI agents`, without qualifiers. Link it to
  snowball's canonical
  `../snowball-projects.github.io/src/pages/licensing.md#how-snowball-is-built`
  policy.
- Never use em dashes. Use regular hyphens.
