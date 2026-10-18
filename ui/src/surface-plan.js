// Work-coordinate planning only. This module never sends machine commands.
export function defaultSurfaceSettings(bounds) {
  return {columns: 3, rows: 3, clearance: 2, below: 1, distance: 1, feed: 20, area: {
    X: [...bounds.X], Y: [...bounds.Y]
  }};
}

export function surfaceRequest(bounds, settings) {
  const current = settings || defaultSurfaceSettings(bounds);
  const plan = createSurfacePlan(bounds, current);
  if (plan.error) return {error: plan.error};
  const params = Object.fromEntries(['clearance','below','distance','feed'].map(key => [key, Number(current[key] ?? {clearance:2,below:1,distance:1,feed:20}[key])]));
  if (Object.values(params).some(value => !Number.isFinite(value)) || params.clearance < 1 || params.clearance > 3 || params.below < 0.1 || params.below > 2 || params.clearance + params.below > 5 || params.distance < 0.1 || params.distance > 5 || params.feed < 10 || params.feed > 60) return {error:'Sprawdź parametry sondowania: prześwit 1–3 mm, zakres pod zerem 0,1–2 mm, pierwszy zjazd 0,1–5 mm, posuw 10–60 mm/min.'};
  return {columns:plan.columns, rows:plan.rows, area:plan.area, ...params};
}

export function surfaceMatches(map, jobId, settings, bounds) {
  if (!map?.id || map.job_id !== jobId || !bounds) return false;
  const current = settings || defaultSurfaceSettings(bounds);
  return Number(current.columns) === map.columns && Number(current.rows) === map.rows && ['X','Y'].every(axis => current.area[axis].every((value,index) => Number(value) === map.area?.[axis]?.[index]));
}

export function createSurfacePlan(bounds, settings) {
  const columns = Number(settings.columns);
  const rows = Number(settings.rows);
  if (![columns, rows].every(value => Number.isInteger(value) && value >= 2 && value <= 11)) {
    return {error: 'Wybierz od 2 do 11 punktów na każdej osi.'};
  }
  const area = {};
  for (const [axis, limit] of [['X', 300], ['Y', 180]]) {
    const original = bounds?.[axis];
    const values = settings.area?.[axis];
    if (!original?.every(Number.isFinite) || !values || values.some(value => value === '')) {
      return {error: 'Brak poprawnego zakresu X/Y w pliku.'};
    }
    const [low, high] = values.map(Number);
    if (![low, high].every(Number.isFinite) || low >= high || low < -limit || high > limit) {
      return {error: `Zakres ${axis} musi mieć dodatnią szerokość i mieścić się w ±${limit} mm.`};
    }
    // A future compensation map must cover every programmed move, not just
    // the interior of the copper. Do not quietly permit extrapolation.
    if (low > original[0] || high < original[1]) {
      return {error: `Plan musi obejmować cały zakres ${axis} z pliku. Sprawdź mocowania lub zmień program.`};
    }
    area[axis] = [low, high];
  }
  const points = [];
  for (let row = 0; row < rows; row++) {
    for (let column = 0; column < columns; column++) {
      const orderedColumn = row % 2 ? columns - 1 - column : column;
      points.push({
        number: points.length + 1,
        x: area.X[0] + orderedColumn * (area.X[1] - area.X[0]) / (columns - 1),
        y: area.Y[0] + row * (area.Y[1] - area.Y[0]) / (rows - 1)
      });
    }
  }
  return {area, points, columns, rows,
    spacingX: (area.X[1] - area.X[0]) / (columns - 1),
    spacingY: (area.Y[1] - area.Y[0]) / (rows - 1)};
}
