export function probeSettings(cnc) {
  return {max_descent_mm:10,xy_feed_mm_min:100,travel_clearance_mm:3,z_feed_mm_min:20,...cnc.probe_settings};
}

export function probeDistanceLimit(cnc, localLimit=10) {
  return Math.min(probeSettings(cnc).max_descent_mm, localLimit);
}

export const probeNumber=value=>Number(value).toLocaleString('pl-PL',{maximumFractionDigits:4});
