# Printcam Setup: ustreamer MJPEG to Mainsail + Frigate

## Goal

Replace crowsnest on each printer's Raspberry Pi with a standalone ustreamer service that serves the Nocturne USB camera's MJPEG stream directly. Mainsail/Fluidd connects to the local stream. Frigate pulls from each Pi for recording and AI failure detection.

The Nocturne cameras (Sonix/Microdia UVC 1.0) output MJPEG only — they do not support H.264. ustreamer passes through the native MJPEG frames with near-zero CPU overhead since no transcoding occurs.

### Architecture

```
[Pi: Doomcube]   ustreamer :8080 ──MJPEG──▶ Mainsail/Fluidd (local)
[Pi: VCore 3.1]  ustreamer :8080 ──MJPEG──▶ Mainsail/Fluidd (local)
[Pi: K3]         ustreamer :8080 ──MJPEG──▶ Mainsail/Fluidd (local)
[Pi: BabyBelt]   ustreamer :8080 ──MJPEG──▶ Mainsail/Fluidd (local)
                       ▲
                       └──── Frigate (192.168.30.3) pulls MJPEG from each Pi
                             └── recording, timelapse, AI failure detection
```

---

## Target Printers

| Printer     | Hostname             | Notes                                    |
|-------------|----------------------|------------------------------------------|
| Doomcube    | doomcube.local       | Enclosed, 60°C chamber, CAN bus toolhead |
| VCore 3.1   | vcore.local          | AWD, Octopus Max EZ, HappyHare MMU      |
| K3          | k3.local             | Annex K3, Kalico                         |
| BabyBelt    | babybelt.local       | Kalico, SKR Mini E3 V3                   |

Skip any printer that doesn't have a Nocturne camera installed yet.

---

## Prerequisites

- SSH access to each printer Pi
- Nocturne camera plugged into a USB port on the Pi
- Crowsnest currently running (will be disabled, not uninstalled)
- Frigate NVR running on 192.168.30.3 with go2rtc (check: `http://192.168.30.3:1984`)

---

## Step-by-Step Setup (repeat per printer)

### 1. Identify the camera device

SSH into the Pi and confirm the Nocturne is detected:

```bash
v4l2-ctl --list-devices
```

Note the `/dev/videoN` path. The Nocturne may register multiple device nodes — find the one that supports MJPEG:

```bash
v4l2-ctl --list-formats-ext -d /dev/video0
```

Look for `Motion-JPEG` (MJPEG) at 1280x720 or higher. If not listed on `/dev/video0`, try `/dev/video2` or other nodes.

### 2. Create udev rule for stable device naming

USB device numbering can change across reboots. Create a persistent symlink:

```bash
# Find camera vendor/product IDs
udevadm info --name=/dev/video0 --attribute-walk | grep -E "idVendor|idProduct"
```

Create the rule (replace `XXXX` and `YYYY` with actual IDs from above):

```bash
sudo tee /etc/udev/rules.d/99-nocturne.rules > /dev/null <<'EOF'
SUBSYSTEM=="video4linux", ATTRS{idVendor}=="XXXX", ATTRS{idProduct}=="YYYY", ATTR{index}=="0", SYMLINK+="nocturne", TAG+="systemd"
EOF
sudo udevadm control --reload-rules
sudo udevadm trigger
```

Verify the symlink exists:

```bash
ls -la /dev/nocturne
```

`TAG+="systemd"` exposes the device as a systemd unit (`dev-nocturne.device`), which lets the service wait for the camera before starting.

### 3. Install ustreamer

Check if ustreamer is available via apt:

```bash
apt-cache show ustreamer
```

If available:

```bash
sudo apt install -y ustreamer
```

If not in apt, build from source:

```bash
sudo apt install -y build-essential libevent-dev libjpeg-dev libbsd-dev
cd /tmp
git clone --depth=1 https://github.com/pikvm/ustreamer.git
cd ustreamer
make -j$(nproc)
sudo cp ustreamer /usr/local/bin/
cd /tmp && rm -rf ustreamer
```

Verify:

```bash
ustreamer --version
```

### 4. Stop and disable crowsnest

```bash
sudo systemctl stop crowsnest
sudo systemctl disable crowsnest
```

Verify it's stopped:

```bash
sudo systemctl status crowsnest
```

Do NOT uninstall crowsnest — just disable it for rollback capability.

### 5. Create service user

```bash
sudo useradd -r -s /bin/false printcam
sudo usermod -aG video printcam
```

### 6. Create the ustreamer service

```bash
sudo tee /etc/systemd/system/printcam.service > /dev/null <<'EOF'
[Unit]
Description=Printcam ustreamer MJPEG service
BindsTo=dev-nocturne.device
After=dev-nocturne.device

[Service]
ExecStart=/usr/local/bin/ustreamer \
  --device=/dev/nocturne \
  --host=0.0.0.0 \
  --port=8080 \
  --format=MJPEG \
  --resolution=1280x720 \
  --desired-fps=15
Restart=on-failure
RestartSec=10
StartLimitIntervalSec=0
User=printcam
SupplementaryGroups=video

[Install]
WantedBy=multi-user.target
EOF
```

**Key details:**

- `--format=MJPEG` — grabs MJPEG frames directly from the Nocturne (native format, no conversion)
- `--resolution=1280x720` — 720p is a good balance of quality and bandwidth
- `--desired-fps=15` — 15fps is plenty for monitoring a print
- `--host=0.0.0.0` — listen on all interfaces (needed for Frigate to pull the stream)
- `BindsTo=dev-nocturne.device` — service stops if camera is unplugged, restarts when it reappears
- `StartLimitIntervalSec=0` — never give up retrying

If ustreamer was installed via apt instead of built from source, change the `ExecStart` path to `/usr/bin/ustreamer`.

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable printcam
sudo systemctl start printcam
```

### 7. Verify the stream

Check service status:

```bash
sudo systemctl status printcam
journalctl -u printcam -f
```

Open a browser and navigate to `http://HOSTNAME:8080/?action=stream` — you should see a live MJPEG stream. Also check the snapshot endpoint: `http://HOSTNAME:8080/?action=snapshot`.

### 8. Configure Moonraker webcam

Add the following to `moonraker.conf` (already done in this repo — just verify it's present after syncing config):

```ini
[webcam nocturne]
location: printer
icon: mdiPrinter3d
enabled: True
service: mjpegstreamer-adaptive
target_fps: 15
stream_url: /webcam/?action=stream
snapshot_url: /webcam/?action=snapshot
```

Mainsail/Fluidd will auto-detect the webcam from this Moonraker config. The `/webcam/` path relies on nginx proxying to port 8080 — this is the standard Mainsail/crowsnest nginx config. Verify it's intact after disabling crowsnest:

```bash
curl -s http://localhost/webcam/?action=snapshot -o /dev/null -w "%{http_code}"
# Should return 200 if nginx proxy and ustreamer are both working
```

---

## Frigate Configuration (on 192.168.30.3)

### go2rtc streams

Add to your Frigate config (`frigate.yml` or `go2rtc.yml`):

```yaml
go2rtc:
  streams:
    doomcube_printcam: "http://doomcube.local:8080/?action=stream"
    vcore_printcam: "http://vcore.local:8080/?action=stream"
    k3_printcam: "http://k3.local:8080/?action=stream"
    babybelt_printcam: "http://babybelt.local:8080/?action=stream"
```

go2rtc pulls the MJPEG stream from each Pi and makes it available as WebRTC for low-latency viewing in the Frigate UI.

**CPU note:** Since these are MJPEG sources, go2rtc must transcode to H.264 for Frigate's record and detect roles. This uses CPU on the Frigate host (not the Pi). For four simultaneous streams, enable hardware-accelerated transcoding if the Frigate host supports it:

```yaml
go2rtc:
  streams:
    k3_printcam: "ffmpeg:http://k3.local:8080/?action=stream#video=h264#hardware"
```

### Frigate cameras

```yaml
cameras:
  doomcube_printcam:
    ffmpeg:
      inputs:
        - path: rtsp://127.0.0.1:8554/doomcube_printcam
          input_args: preset-rtsp-restream
          roles:
            - record
            - detect
    detect:
      enabled: false
      width: 1280
      height: 720
      fps: 5
    record:
      enabled: false

  vcore_printcam:
    ffmpeg:
      inputs:
        - path: rtsp://127.0.0.1:8554/vcore_printcam
          input_args: preset-rtsp-restream
          roles:
            - record
            - detect
    detect:
      enabled: false
      width: 1280
      height: 720
      fps: 5
    record:
      enabled: false

  # Add k3_printcam, babybelt_printcam as cameras come online
```

**Notes:**

- `preset-rtsp-restream` — correct Frigate preset for local go2rtc restreams
- Detect at 1280x720 @ 5fps — Frigate's detection model operates at 320x320, so higher res wastes compute
- Recording will be toggled on/off by HA automation when printing

---

## Troubleshooting

### Camera not found

```bash
ls /dev/video*
v4l2-ctl --list-devices
```

The Nocturne may register multiple device nodes. Try each with `v4l2-ctl --list-formats-ext -d /dev/videoN` until you find the one with MJPEG support.

### Stream starts then dies

Check logs:

```bash
journalctl -u printcam -f
```

Common causes:
- Wrong device — verify `/dev/nocturne` symlink points to the correct node
- Camera doesn't support 1280x720 in MJPEG — try 640x480 (`--resolution=640x480`)
- Crowsnest still holding the camera — confirm it's stopped (`systemctl status crowsnest`)
- Permission denied — verify `printcam` user is in the `video` group

### Service stopped retrying

If systemd gave up (shouldn't happen with `StartLimitIntervalSec=0`, but check):

```bash
systemctl status printcam
# If "start limit hit":
sudo systemctl reset-failed printcam
sudo systemctl start printcam
```

### High CPU usage

ustreamer in MJPEG passthrough should use <2% CPU. If CPU is high:
- Verify `--format=MJPEG` is set (without it, ustreamer may capture in YUYV and convert to MJPEG in software)
- Reduce resolution or framerate
- Check for other processes accessing the camera simultaneously

### USB bandwidth issues

If the Pi has other USB devices (MCU serial, Beacon probe, etc.) and the stream is choppy, reduce resolution to 640x480 or framerate to 10fps. USB bandwidth on the Pi is shared across all ports.

---

## Rollback

If anything goes wrong, revert ALL systems touched:

```bash
# Pi service layer
sudo systemctl stop printcam
sudo systemctl disable printcam
sudo systemctl enable crowsnest
sudo systemctl start crowsnest

# Remove the [webcam nocturne] section from moonraker.conf, then:
sudo systemctl restart moonraker
```

If Frigate was configured, also remove the go2rtc stream and camera entries for this printer.

---

## Post-Setup Checklist

Per printer:

- [ ] Nocturne camera identified, MJPEG node confirmed
- [ ] udev rule created (`/dev/nocturne` symlink with `TAG+="systemd"`)
- [ ] ustreamer installed (apt or built from source)
- [ ] Crowsnest stopped and disabled
- [ ] Service user `printcam` created with video group
- [ ] `printcam.service` installed, enabled, and running
- [ ] Stream visible at `http://HOSTNAME:8080/?action=stream`
- [ ] Moonraker `[webcam nocturne]` section present
- [ ] Mainsail/Fluidd webcam widget working

Frigate side (once, on 192.168.30.3):

- [ ] go2rtc streams configured with MJPEG pull URLs for each printer
- [ ] Frigate cameras configured with `preset-rtsp-restream` and detect role
- [ ] Frigate receiving streams (check Frigate UI)
