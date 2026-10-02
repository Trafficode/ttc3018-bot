# System boundaries

The repository owns host setup and monitoring. The operator owns physical work.
Solid arrows below represent implemented access; dotted links are planned.

```mermaid
flowchart LR
    Agent[Agent workstation] --> TS[Private Tailscale network]
    TS --> SSH[Restricted SSH access]
    TS --> Serve[Private Tailscale Serve port 8765]
    Serve --> Monitor[Loopback monitoring port 8766]
    Monitor --> Camera
    Monitor --> DHT
    SSH --> Scripts[Explicit repository checks]
    Scripts --> Camera[Camera Rev 1.3]
    Scripts --> DHT[DHT22 GPIO17]
    Operator[Local operator] -.-> Panel[Future CNC panel]
    Panel -.-> USB[Single USB connection owner]
    USB -.-> CNC[TTC3018 controller]
```

Implemented: setup script, version-locked Python environment, host diagnostics,
bounded sensor test, camera snapshot command and a persistent monitoring service.
The browser receives Motion JPEG (MJPEG), a sequence of JPEG images, at 960 x 540
and 8 frames per second. One `rpicam-vid` process serves all viewers. At most four
streams run simultaneously; slow clients receive the latest frame, not a queue.
One DHT22 worker reads every five seconds. Errors and sample ages remain visible.

The service listens only on `127.0.0.1:8766`. Tailscale Serve exposes port 8765
only within the private tailnet; there is no LAN listener or public Funnel.
Tailscale encrypts network transport even though the browser URL uses HTTP.
Tailnet access rules, not a separate application password, control access. Review
those rules before sharing the node or adding untrusted tailnet members.
There is no external web dependency, analytics, continuous disk recording or
historical sensor database. Latest values and one latest frame are held in memory.

Read-only application programming interface (API): `/api/status` and `/camera.jpg`.
No camera restart, GPIO selection, serial connection or machine command can be
requested over HTTP. Snapshot access uses the existing camera worker.

Pending: CNC sender, CNC operator panel and CNC agent integration. Monitoring
status explicitly reports CNC as not connected; USB enumeration is not a session.

Future agent access should favor compact structured status and on-demand images.
The operator can watch continuous video without sending each frame to a model.
A CNC adapter should use the single sender's API, never open a competing USB
connection. Starting motion or spindle operation remains operator-controlled.
