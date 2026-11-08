// Pure millimetre geometry; never sends commands or claims measured accuracy.
export function toolDiameter(tip, angle, depth) {
  if (![tip, angle, depth].every(Number.isFinite) || tip < .01 || tip > .5 || angle < 10 || angle > 90 || depth < .01 || depth > .3) return NaN;
  return tip + 2 * depth * Math.tan(angle * Math.PI / 360);
}

export function serviceGeometry(config) {
  const {tip, angle, depth, width} = config;
  const model = config.calibration?.model;
  if (model && (depth < model.min_depth - 1e-9 || depth > model.max_depth + 1e-9)) return {error:`Profil: zagłębienie ${model.min_depth}–${model.max_depth} mm. Poza tym zakresem wykonaj nowe pomiary.`};
  const diameter = model ? model.intercept_mm + model.slope * depth : toolDiameter(tip, angle, depth);
  if (model && diameter <= 0) return {error:'Profil przewiduje niedodatnią szerokość rowka dla tego zagłębienia. Popraw pomiar lub zagłębienie.'};
  if (!Number.isFinite(diameter) || !Number.isFinite(width) || width < .2 || width > 2) return {error:'Frez: końcówka 0,01–0,5 mm, kąt 10–90°. Pasek: 0,2–2 mm; zagłębienie: 0,01–0,3 mm.'};
  const half = (width + diameter) / 2;
  if (3.3 + half + diameter / 2 > 4.9 + 1e-9 || 3.3 - half - 1 - diameter < .1 - 1e-9 || 1 - diameter < .1 - 1e-9) return {error:'Próbka nie mieści się w polu 12 × 5 mm. Zmniejsz pasek lub zagłębienie.'};
  return {diameter, strip:width};
}
