# Unfinished progressive-results experiment

This is the isolated stage/results interaction experiment from the older local
planning work. It is outside the production static directory and is not deployed
by the Pages build. The main application files are unchanged on this branch.

Existing catalog examples are historical; areas and all travel times are
synthetic. No API, routing provider or geocoder is connected. README and CONTRACT
retain the original design/review chronology; their old main/PR status is not a
statement about current production.

Run `node --test tests/progressive-results.test.mjs` for the model regressions.
The browser-check script is supplied for future contributor review and was not
run during this migration. The later offline logical-session integration is a
separate draft; this branch preserves the distinct isolated interaction model
without copying another old main app.js.
