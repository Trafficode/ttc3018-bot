// Resolve only a distance; selecting or editing a step never sends motion.
export function jogStep(selection, custom) {
  const text = selection === 'custom' ? String(custom).trim().replace(',', '.') : String(selection);
  if (!text) return null;
  const value = Number(text);
  return Number.isFinite(value) && value >= .01 && value <= 300 ? value : null;
}

export function jogAllowed(distance, axis, limits) {
  return distance !== null && Number.isFinite(limits?.[axis]) && distance <= limits[axis];
}
