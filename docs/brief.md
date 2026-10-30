# fairway: product brief

How fairway should behave and what it should achieve. It describes behavior and outcomes, not technology or visual design.

## What fairway is

fairway is a free, open catalog of every US golf facility and course, shown on a map. It has a "plan a round" mode that ranks facilities by how far each golfer has to drive.

- **The map is the main way in.** You see every facility and browse by moving around, rather than by filtering a list.
- **Plan a round:** the person using fairway enters starting places for themselves and up to 7 friends. fairway ranks facilities by drive time for everyone and draws everyone's route to the facility they pick. It's one person planning, not a shared multiplayer page.
- **US only** for now. Other countries could come later, if people want them.

## The catalog

The catalog aims to hold every public fact about every US golf facility and course. It should be as complete as anything published, for any facility.

- **What counts:** anything public and easy to gather. That includes holes, par, tee sets (such as white, black, red) with their slope and rating, the kind of course, who can play (public, private, resort, municipal), amenities, and more.
- **Always a website:** every facility should link to its own website, where people can book tee times or learn more. If it has none, link the most relevant official page, such as its park district's. This is the one fact we always try to have.
- **Honest gaps:** when a fact isn't known, fairway says so rather than guessing.
- **Sourced:** every fact keeps its source link and the date it was checked, and is only stored when the source allows reuse.
- **One entry per facility:** each real place appears once, with its courses grouped under it.

## Browsing the map and the courses panel

- **Every facility is on the map** as its own dot, never grouped into clusters.
- **Hover** shows a quick summary of the facility. At national zoom you can sweep across dots fast and see each one flash by.
- **Click** zooms in on the facility. On a phone, the first tap shows the summary and the second tap zooms in.
- **The courses panel lists what's on the map** and follows the map as you move around.
- **Each facility is one entry** in the panel, with its courses grouped inside it. Every entry shows the same kinds of facts whichever source they came from. Missing facts are marked as not known.
- **Clicking anywhere on an entry** selects that facility.

## Plan a round: what the user does and sees

1. **Start planning.** In plan-a-round mode, the panel stops following the map. It shows only the facilities that matter for the group.
2. **Add starting places.** The user types an address for themselves and for up to 7 friends. Each place gets its own color.
3. **The map follows.** As places are added, the map zooms to fit all of them. If no facility is in view, it zooms out until at least one is.
4. **Times pop in.** Each facility entry shows a drive time from every starting place. Every facility-and-place pair is worked out on its own and appears the moment it's ready, often nearest pairs first, with a small spinner for each pair still pending. Entries sort themselves as times arrive, and unfinished ones wait at the bottom, so the wait feels like a game rather than a blank screen.
5. **Ranking:** by the slowest drive in the group (minimax). Adding a place re-ranks the list.
6. **Which facilities are ranked:** one rule for every group, from one person to eight. The best meeting area is found first. Then fairway shows the facilities near it: the best 20 or so, or every facility within about 15 minutes of the best time, whichever list is longer. Facilities that can't win get no times and stay plain dots.
7. **Filters narrow the ranking:** public only, 18 holes, 9 holes. A facility stays in if any of its courses matches, and the ranking rule above applies to what's left.
8. **Pick a facility.** Clicking one shows its catalog details plus a route from every starting place, along real roads, each in that place's color.
9. **Share it.** The page's link reopens the same plan. The addresses live only in the link, never on a server.
10. **Stop planning.** The map goes back to normal browsing, keeping the last view.

## Example cases

| Case | What should happen |
| --- | --- |
| Just the user, at home | Nearby facilities ranked by their drive time. |
| Four friends in one metro area | The facilities around them get times, sorted as they arrive. |
| Seattle, New York, Miami and LA | The best meeting area somewhere mid-country, the facilities near it ranked, and everyone's routes on click. |
| Friends on both sides of a state line | Facilities across the border count too. |
| One place with no road route (an island) | That place's time says no road route, and the others still work. |
| A facility with five courses | It's ranked once, as one facility, since everyone drives to the same place. |

## What good means

| Quality | Target |
| --- | --- |
| Speed | Feels near-instant. Never more than 1 minute, kept as low as possible. Work starts while addresses are still being typed. |
| Ranking accuracy | Facilities in the right order, and each time within about 1 to 2 minutes. |
| Drive-time accuracy | Within about 2 minutes on short drives and 5% on long ones. |
| Roads | Every drivable road, no distance cap. Car, no traffic. |
| Map feel | Hover and panel stay smooth with every facility on the map. |
| Phones | Smooth on a phone. |
| Cost | $0 preferred. Up to $20 a month only when there's no other way. |
| Privacy and openness | No accounts, no ads, no tracking, no stored addresses. Code MIT, catalog open data with credit kept. |

## Not in scope

- Live traffic or time-of-day drive times.
- Least total driving, for now. Minimax only.
- Clustering dots.
- Anywhere outside the US, for now.
- Booking tee times inside fairway. The facility's own website handles that.
