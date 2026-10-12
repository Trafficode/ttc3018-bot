# Bark Beetle

Rebuildable configuration for a Raspberry Pi CNC monitoring host.
Current baseline: Raspberry Pi 5, Raspberry Pi Camera Rev 1.3 (OV5647),
DHT22 on GPIO17 and private Tailscale access.

- [Set up another Raspberry Pi](docs/development/setup.md)
- [Run checks and troubleshoot](docs/development/operations.md)
- [Verified hardware and software](docs/reference/baseline.md)
- [System boundaries and next components](docs/architecture/system.md)
- [Build and operate the component-based panel](docs/development/operator-ui.md)
- [Plan PCB surface measurements](docs/development/surface-plan.md)
- [10 mm PCB starter coupon and CAM files](docs/reference/pcb-cnc-coupon-10mm-cam.md)
- [40 mm PCB reference coupon](docs/reference/pcb-cnc-coupon-40mm.md)

Bark Beetle provides camera video, environmental telemetry and explicit manual CNC
controls through private Tailscale Serve. The operator connects USB, jogs, sets
material zero and controls the spindle. There is no automatic USB reconnect,
homing, probing or unlock. File jobs support explicitly started linear GRBL
programs; see [file jobs and limits](docs/development/file-jobs.md).
See the operations guide for the first supervised test.
