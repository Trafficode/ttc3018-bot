# TTC3018 Bot

Rebuildable configuration for a Raspberry Pi CNC monitoring host.
Current baseline: Raspberry Pi 5, Raspberry Pi Camera Rev 1.3 (OV5647),
DHT22 on GPIO17 and private Tailscale access.

- [Set up another Raspberry Pi](docs/development/setup.md)
- [Run checks and troubleshoot](docs/development/operations.md)
- [Verified hardware and software](docs/reference/baseline.md)
- [System boundaries and next components](docs/architecture/system.md)

PiloMill provides camera video, environmental telemetry and explicit manual CNC
controls through private Tailscale Serve. The operator connects USB, jogs, sets
material zero and controls the spindle. There is no automatic USB reconnect,
homing, probing, unlock or job execution. File streaming is not implemented yet.
See the operations guide for the first supervised test.
