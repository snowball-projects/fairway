# snowball rules
Stage
- Early-stage project with one user, the founder. Build for that.
  No guards, migrations, compatibility code, release processes or docs
  for users who don't exist yet.

Design
- Choose the simplest, least costly design that works, in everything:
  architecture, hosting, backend, frontend and data.
- Within that, make it as fast and light as possible.
- When there are several reasonable ways to do something that matters,
  propose the best 2 or 3 with their trade-offs, recommend one, and
  wait for the founder to choose. Make small choices yourself and
  mention them.

Less is more
- Prefer deleting to adding. At the end of each task, say what can now
  be removed, and remove it if it is in scope.
- No dead code, old experiments, research notes or drafts in the repo.
  Tag anything worth keeping, then delete it.
- Validate data once, where it is produced. Trust our own files.
- Keep the README to one screen, written for a person. Add no other
  docs unless asked, and don't edit AGENTS.md unless asked.

Work
- Keep each PR to one coherent piece of work, then stop and report.
- Ask the founder first before anything irreversible (force-push,
  deleting unmerged work, changing repo settings, spending money) or
  any change of direction (new architecture, new service, change of
  scope). Otherwise proceed, and merge when checks pass.
- GitHub is the source of truth. Push all work; nothing lives only on
  one machine.

Public copy and data
- Write snowball and every project name in lowercase.
- Never label anything as made by or with AI, anywhere.
- Never use em dashes.
- Code is MIT. Data we create is CC0. Data from others keeps its
  source's license and credit.
- Store each fact with its source link and the date checked, never
  copies of other sites' pages.
- Principles: https://snowball-projects.github.io/principles/

## Repo notes
A static golf catalog with map browsing and nearby-course selection.
Python: `uv run --locked ruff check .`; `uv run --locked ruff format --check .`; `uv run --locked python -m pytest`; `uv build`.
Web: `node --check src/fairway/static/app.js`; `node --check src/fairway/static/leaflet.js`; `node --test --test-isolation=none tests/*.test.mjs`; `python3 scripts/build_pages.py --check`.
