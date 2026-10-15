export function unproject(x, y, state) {
  if (state === "AK") return [72 - (y - 435) / 6, (x - 25) / 4.5 - 180];
  if (state === "HI") return [23 - (y - 490) / 19, (x - 250) / 19 - 161];
  const rad = Math.PI / 180;
  const n = (Math.sin(29.5 * rad) + Math.sin(45.5 * rad)) / 2;
  const c = Math.cos(29.5 * rad) ** 2 + 2 * n * Math.sin(29.5 * rad);
  const rho0 = Math.sqrt(c - 2 * n * Math.sin(38 * rad)) / n;
  const px = (x - 510) / 1100,
    py = rho0 + (y - 270) / 1100;
  const rho = Math.hypot(px, py);
  return [
    Math.asin((c - (rho * n) ** 2) / (2 * n)) / rad,
    Math.atan2(px, py) / n / rad - 96,
  ];
}
export function shapeRings(shape) {
  return shape.d
    .split("M")
    .filter(Boolean)
    .map((part) =>
      [...part.matchAll(/(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)/g)].map((m) =>
        unproject(Number(m[1]), Number(m[2]), shape.state),
      ),
    );
}
