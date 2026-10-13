export const MIN_ORIGIN_ROWS = 2;

export function canRemoveOrigin(rowCount, rowIndex) {
  return (
    Number.isInteger(rowCount) &&
    Number.isInteger(rowIndex) &&
    rowCount > MIN_ORIGIN_ROWS &&
    rowIndex >= MIN_ORIGIN_ROWS &&
    rowIndex < rowCount
  );
}

export function requiredOriginRows(rowCount) {
  const count = Number.isInteger(rowCount) && rowCount >= 0 ? rowCount : 0;
  return Math.max(0, MIN_ORIGIN_ROWS - count);
}

export function originLimit(configured, available) {
  const upperBound = Math.min(configured, available);
  return Math.max(MIN_ORIGIN_ROWS, upperBound);
}
