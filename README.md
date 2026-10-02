# TTC3018 Bot

Rebuildable configuration for a Raspberry Pi CNC monitoring host.
Current baseline: Raspberry Pi 5, Raspberry Pi Camera Rev 1.3 (OV5647),
DHT22 on GPIO17 and private Tailscale access.

- [Set up another Raspberry Pi](docs/development/setup.md)
- [Run checks and troubleshoot](docs/development/operations.md)
- [Verified hardware and software](docs/reference/baseline.md)
- [System boundaries and next components](docs/architecture/system.md)

The repository does not start or control the CNC machine. A loopback monitoring
service provides live camera video, DHT22 telemetry and read-only status/snapshot
endpoints through private Tailscale Serve. A CNC operator panel and CNC agent
integration are not implemented yet.
