// Stock metadata can be edited while connected and idle. CAM still requires
// disconnection; active jobs, probes and unknown controller state stay locked.
export function canEditStock({known, active, busy, pending, cnc}) {
  return !!known && !active && !busy && !pending &&
    (!cnc.connected || (cnc.fresh === true && cnc.state === 'Idle'));
}
