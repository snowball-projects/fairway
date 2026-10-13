# South Dakota public facility proposal, 2026-10-13

Eight net-new public facilities, two documented physical courses, zero new map or arrival points. Based on catalog commit `3fe8f486cce87ec1e38524c7e49c732ed368d05e` (7,176 facilities). Candidate total 7,184; mapped total remains 4,428. All existing facilities and the eight-course Chicago ranking projection remain unchanged. No UI changes, source denial retries, publication or remote writes.

| Facility | Physical total | Physical courses | Evidence |
| --- | ---: | --- | --- |
| Britton Country Club | 9 | One unnamed public 9-hole course | [Operator](https://www.brittoncountryclub.com/), [explicit Public profile](https://www.sdga.org/golf_course/britton-country-club/) |
| Fisher Grove Country Club | 10 | One unnamed public 10-hole course | [State recreation page](https://gfp.sd.gov/parks/detail/-fisher-grove-state-park/), [explicit Public profile](https://www.sdga.org/golf_course/fisher-grove-country-club/) |
| Miller Golf Course | Unknown | Unverified | [Public profile](https://www.sdga.org/golf_course/miller-golf-course/) |
| Webster Municipal Golf Course | Unknown | Unverified | [Public profile](https://www.sdga.org/golf_course/webster-municipal-golf-course/) |
| Olive Grove Golf Course | Unknown | Unverified | [Public profile](https://www.sdga.org/golf_course/olive-grove-golf-course/) |
| Bowdle Golf Club | Unknown | Unverified | [Public profile](https://www.sdga.org/golf_course/bowdle-golf-club/) |
| Newell Golf Club | Unknown | Unverified | [Public profile](https://www.sdga.org/golf_course/newell-golf-club/) |
| Cattail Crossing Golf Course | 27 | Component inventory unverified | [Municipality](https://www.watertownsd.us/177/Cattail-Crossing-Golf-Course), [Public profile](https://www.sdga.org/golf_course/cattail-crossing-golf-course/) |

## Qualifications

Public access comes from individual explicit Public classifications, never association membership or directory inclusion. Five physical totals remain null. Repeated front/back ratings, 9/18 playing prices and a 27-hole whole-facility total do not establish component layouts. Cattail has no invented course rows. County, map and arrivals remain null for every addition.

Britton's operator supports the street address, without the association's Box F. Fisher Grove retains the association's combined Box 22/street address as mailing evidence; conflicting Frankfort/state-park address and park GPS are excluded. The state page's County Club spelling is preserved as a qualification, corroborated by the matching association name and telephone. Webster's live association street address is blank; an indexed older address is not admitted. Its linked operator path returned404 and website stays null. Bowdle's address combines a street and PO Box, so purpose stays unspecified. Social links from the association are not converted into found official websites.

## Source controls and reuse

`source-controls.json` records both recovered archive hashes and complete matching records. All 1,003 textual archive entries were searched during per-request screens. Host-specific matches for admitted sources were old SDGA citations, not holds. Current robots and full linked policies were separately reviewed. Missing controls never served as clearance. There was one preflight bookkeeping exception: the first Britton robots check followed a screen for brittonsd.com; the exact operator-host screen was completed immediately afterward, before fact requests, and had no hits.

`policy-decisions.json` records each admitted source's policy scope. SDGA has an unrestricted wildcard robots policy; its full linked Terms of Usage/Privacy Policy contains privacy terms and no identified scraping/reuse restriction. Britton's robots denies only `/api/`; homepage navigation/footer has no linked terms. Watertown's page and navigation/footer have no linked terms. The GFP disclaimer permits copying/distributing information for personal or informational use, subject to third-party rights and accuracy qualifications. This proposal uses independently written bare facts for an informational catalog; it claims no open-data license for these websites and includes no raw pages, imagery or protected descriptions. Parent review remains required before integration.

`new-stops.json` contains Philip's wildcard robots denial, Parkston's TLS hostname mismatch, Eureka's missing robots, and Webster's missing operator path. None was revisited or bypassed. Existing parent holds, including MD/PA/PGA/MCG/Classic5/LeRoy, remained untouched.

`request-audit.json` records request start/completion UTC, response status/redirect and SHA256. Raw captures are outside Git in sibling `south-dakota-evidence` for private parent inspection. Cookie/header data is excluded from deliverables. Minimum inter-request completion-to-start gaps: SDGA15.000s, GFP15.000s (required5), Britton40.294s, Watertown72.176s (conservative20), Webster37.296s. No crawl-delay deviations. First Redfield policy request failed sandbox DNS before HTTP and was not retried.

## Integration

`delta.json` is portable: merge only its facilities, sources, notes and research after parent provenance/diff review. IDs are minted once; source/note keys use a cohort prefix to avoid numeric-key collisions. Rebase/remap only source/note keys if needed, retaining facility/course IDs. Do not overwrite a changed parent catalog with this whole candidate. Publish locally with `scripts/publish_research_map.py` and validate after applying. Preserve admission qualifications and append a parent integration history batch.

`deduplication.json` records global normalized name checks, South Dakota address checks, exact website checks, and South Dakota history checks including null-ID rows. No matches were found. Similar Cattails records in other states and unrelated Webster/Newell street names are distinct.

## Next cohort

Continue with a bounded individually Public-labeled SDGA cohort such as Murdo, Oahe Hills, Lake Waggoner, Bison and Elkhorn Ridge. Check both archives and current policies before collecting; independent government/operator physical evidence can fill counts later. Never use Philip's held municipal source to supply Lake Waggoner counts. Unknown hole totals remain honest gaps.
