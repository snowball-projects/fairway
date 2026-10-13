# National group-drive backend boundary

This first backend slice is deliberately provider-independent and is not wired
to the public browser or the production API. `fairway.national` composes three
bounded steps:

1. A `PromisingAreaProvider` receives the ordered origin coordinates, the
   `maximum` or `combined` objective, and an area limit no greater than eight.
2. fairway validates the response and round-robins the nearest eligible catalog
   courses for each area, selecting at most 24 by great-circle distance from
   their reviewed routing arrivals to the returned area centers.
3. fairway makes one `MatrixProvider.calculate` call containing every origin
   and only that shortlist, then applies the same canonical millisecond ranking
   used by the current Chicago API.

The expected MODO adapter method is:

```python
find_promising_areas(origins, objective, *, limit) -> PromisingAreas
```

`PromisingAreas` echoes the ordered origins and objective, contains an ordered,
bounded tuple of stable `PromisingArea(identifier, center)` values, and carries
provider, strategy, and scalar provenance metadata. The result describes an
approximate candidate search, not a global optimum. A later thin adapter may
translate MODO's native response into this type without moving course discovery
or eligibility into MODO.

Only catalog records marked `public` with `reviewed_osm_point` or
`verified_entrance` destinations and a course, clubhouse, or arrival address
purpose can enter the shortlist. Property centers and estimate points remain
browse-only even when they are closer to a promising area. If the catalog has
no reviewed arrival near the search, calculation fails instead of substituting
a property coordinate.

This boundary prevents a national all-course matrix: an area provider can
return at most eight areas and fairway can route at most 24 courses in one
ranking. The current Pages catalog browsing and Chicago production calculation
paths are unchanged.
