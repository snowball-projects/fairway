# National group-drive backend boundary

This first backend slice is deliberately provider-independent and is not wired
to the public browser or the production API. `fairway.national` composes three
bounded steps:

1. A `PromisingAreaProvider` receives the ordered origin coordinates, the
   `maximum` or `combined` objective, and an area limit no greater than eight.
2. fairway validates the response and round-robins the nearest eligible catalog
   courses inside each area's explicit radius, selecting at most 24 by
   great-circle distance from their reviewed routing arrivals to the returned
   area centers.
3. fairway makes one `MatrixProvider.calculate` call containing every origin
   and only that shortlist, then applies the same canonical millisecond ranking
   used by the current Chicago API.

The expected MODO adapter method is:

```python
find_promising_areas(origins, objective, *, limit) -> PromisingAreas
```

`PromisingAreas` echoes the ordered origins and objective, contains an ordered,
bounded tuple of stable
`PromisingArea(identifier, center, radius_kilometers)` values, and carries
provider, strategy, and scalar provenance metadata. Every radius must be
positive and no greater than 160 km. fairway uses a latitude index, a longitude
bound derived from the same spherical model, and then exact great-circle
distance to enforce each radius.
It does not expand an empty area or fall back to the nearest national course.
The result describes an approximate candidate search, not a global optimum. A
later thin adapter may translate MODO's native response into this type without
moving course discovery or eligibility into MODO.

Only catalog records marked `public` with `reviewed_osm_point` or
`verified_entrance` destinations and a course, clubhouse, or arrival address
purpose can enter the shortlist. Property centers and estimate points remain
browse-only even when they are closer to a promising area. If the catalog has
no reviewed arrival near the search, calculation fails instead of substituting
a property coordinate.

The 8-area limit, 160-km maximum radius, and 24-course route budget are initial
operational policy constants that can be deliberately retuned. They bound work;
they do not prove global optimality, complete facility coverage, or that the
true road-time optimum is in the shortlist. This boundary prevents a national
all-course matrix. The current Pages catalog browsing and Chicago production
calculation paths are unchanged.

MODO's `final_resolution_km` describes numerical search resolution, not a
useful facility-discovery catchment. The thin MODO adapter preserves that value
in provenance and applies a separate, explicit 25-km facility radius by default.
Callers may choose another positive value up to the 160-km hard ceiling. There
is no automatic widening after an empty search.

The hole filter remains 9 or 18 because those are fairway's documented playable
course choices and the validated ranking catalog contract. A facility's
`physical_holes` can legitimately be 27 or 36 without being one routable course.
Named, sourced component layouts are represented separately when their actual
counts and access are known, such as three named 9-hole layouts or two named
18-hole layouts. A reported 27/36-hole facility total does not cause fairway to
invent subdivisions, and an unresolved total cannot enter ranking until an
eligible named course and reviewed arrival are supported.
