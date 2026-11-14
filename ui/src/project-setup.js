// Stock metadata and project CAM allow a connected idle controller.
// Active jobs, probes and unknown controller state stay locked.
export function canEditStock({known, active, busy, pending, cnc}) {
  return !!known && !active && !busy && !pending &&
    (!cnc.connected || (cnc.fresh === true && cnc.state === 'Idle'));
}
