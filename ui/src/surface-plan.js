// Work-coordinate planning only. This module never sends machine commands.
export function surfaceHeights(map) {
  const samples = map?.samples || [];
  const near = (a, b) => Math.abs(a - b) < 0.00001;
  const origin = samples.find(point => near(point.x, 0) && near(point.y, 0));
  let baseline = origin?.z;
  let source = origin ? 'measured' : null;
  if (baseline === undefined && map?.reference_xy?.every(value => near(value, 0))) {
    baseline = 0;
    source = 'reference';
  }
  // Interpolate only inside the map, using already measured neighbours.
  if (baseline === undefined && map?.area && map.columns >= 2 && map.rows >= 2) {
    const axes = ['X', 'Y'].map((axis, index) => {
      const [low, high] = map.area[axis];
      if (low > 0 || high < 0) return null;
      const count = index ? map.rows : map.columns;
      const step = (high - low) / (count - 1);
      const cell = Math.min(count - 2, Math.floor(-low / step));
      const fraction = (-low - cell * step) / step;
      return [[low + cell * step, 1 - fraction], [low + (cell + 1) * step, fraction]];
    });
    if (axes.every(Boolean)) {
      let height = 0, complete = true;
      for (const [x, wx] of axes[0]) for (const [y, wy] of axes[1]) {
        if (wx * wy < 1e-10) continue;
        const point = samples.find(item => near(item.x, x) && near(item.y, y));
        if (!point) complete = false;
        else height += point.z * wx * wy;
      }
      if (complete) {baseline = height; source = 'interpolated';}
    }
  }
  const values = baseline === undefined ? [] : samples.map(point => ({...point, delta: point.z - baseline}));
  return {source, values, min: values.length ? Math.min(...values.map(point => point.delta)) : null,
    max: values.length ? Math.max(...values.map(point => point.delta)) : null};
}

export function defaultSurfaceSettings(bounds) {
  // Single-point zero retracts to Z=1. Leave 0.5 mm of search margin below
  // that nominal surface; the operator confirms the full bounded travel.
  return {columns: 3, rows: 3, clearance: 2, below: 1, distance: 1.5, feed: 20, area: {
    X: [...bounds.X], Y: [...bounds.Y]
  }};
}

export function surfaceRequest(bounds, settings) {
  const current = settings || defaultSurfaceSettings(bounds);
  const plan = createSurfacePlan(bounds, current);
  if (plan.error) return {error: plan.error};
  const params = Object.fromEntries(['clearance','below','distance','feed'].map(key => [key, Number(current[key] ?? {clearance:2,below:1,distance:1.5,feed:20}[key])]));
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
