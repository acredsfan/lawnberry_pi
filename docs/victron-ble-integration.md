# Victron SmartSolar BLE Integration

This guide describes how to source battery, solar, and load telemetry from a Victron SmartSolar charge controller using the [`victron-ble`](https://github.com/keshavdv/victron-ble) Instant Readout utility. The LawnBerry backend can merge this data with (or substitute it for) INA3221 shunt readings.

## 1. Install prerequisites

1. Ensure Bluetooth is enabled on the Pi and the SmartSolar controller is paired (VictronConnect → Instant Readout).  
2. Install the CLI and its dependencies (system Python requires `--break-system-packages`):

   ```bash
   python3 -m pip install --upgrade --break-system-packages victron-ble bleak dbus-fast
   ```

3. Apply the upstream resiliency patch (current victron-ble `0.9.2` assumes the BlueZ backend exposes `BLEDevice.rssi`). Run this once after installing/upgrading:

   ```bash
   python3 - <<'PY'
   import pathlib

   target = pathlib.Path('/usr/local/lib/python3.11/dist-packages/victron_ble/scanner.py')
   text = target.read_text(encoding='utf-8')
   if 'getattr(ble_device, "rssi", None)' not in text:
       text = text.replace(
           '"rssi": ble_device.rssi,',
           '"rssi": getattr(ble_device, "rssi", None),',
           1,
       )
       target.write_text(text, encoding='utf-8')
       print('Patched victron_ble scanner to guard missing rssi attribute.')
   else:
       print('victron_ble scanner already patched; no action taken.')
   PY
   ```

   Future victron-ble releases may include this guard; remove the snippet once upstream fixes the issue.

## 2. Collect the encryption key

The Instant Readout key is displayed in VictronConnect once you enable BLE for the controller. Record the 32-character hex key and the controller MAC address (format `EC:1A:…`).

You can validate the key from the CLI:

```bash
victron-ble read EC:1A:A8:DD:99:C2@<replace-with-instant-readout-key> | head -n 1
```

A successful read prints JSON containing `battery_voltage`, `battery_charging_current`, `solar_power`, and `external_device_load`.

## 3. Configure LawnBerry

Update `config/hardware.yaml` with the Victron block (values shown below are placeholders). Keep the placeholder for `encryption_key` in the tracked file so secrets never end up in Git history:

```yaml
victron:
  enabled: true
  device_id: "EC:1A:A8:DD:99:C2"          # controller MAC address
  encryption_key: "<replace-with-instant-readout-key>"
  # device_key: "EC:1A:A8:DD:99:C2@<replace-with-instant-readout-key>"
  cli_path: victron-ble
  adapter: null                            # optional, e.g. "hci1"
  prefer_battery: true                     # take battery V/I/P from Victron when available
  prefer_solar: true                       # take solar power/current from Victron when available
  prefer_load: true                        # take load current from Victron when available
```

Store the real key in the untracked override file `config/hardware.local.yaml` (created automatically by the repo tooling). Only values present in this file override the base configuration:

```yaml
victron:
    encryption_key: "<your-instant-readout-key>"
    # device_key: "EC:1A:A8:DD:99:C2@<your-instant-readout-key>"
```

Because `config/.gitignore` excludes `hardware.local.yaml`, the secret stays on the node while the placeholder remains safe to commit. If you prefer environment variables, set `LAWN_HARDWARE_LOCAL_PATH` to another YAML file path before starting the backend.

If you are phasing out the INA3221, you may also set `power_monitor: false` (or remove the `ina3221` block). The backend gracefully operates with Victron telemetry alone.

## 4. Restart backend services

Restart the backend to load the new configuration:

```bash
sudo systemctl restart lawnberry-backend.service
```

Monitor the log for SmartSolar frames:

```bash
journalctl -u lawnberry-backend.service -f | grep SmartSolar
```

## 5. Confirm dashboard telemetry

Once the backend is running, the `/api/telemetry` power block should contain:

- `battery_voltage` ~13–14 V (from Victron)  
- `battery_current` (positive while charging)  
- `solar_power` (watts)  
- `load_current` (amps drawn by external devices)

If both Victron and INA3221 are enabled, the preference flags control which source wins per channel; the backend will automatically fall back to the other source if the preferred reading is missing.

## 6. Troubleshooting

- **`victron-ble` hangs**: ensure the Instant Readout key is correct and that only one reader is active at a time. The backend captures a single JSON frame and terminates the CLI, so it should not leave lingering processes.
- **`victron-ble` crashes with `AttributeError: 'BLEDevice' object has no attribute 'rssi'`**: rerun the patch snippet in step 1 to guard the missing attribute.
- **No data after restart**: confirm the backend service user (`pi`) can access Bluetooth and that the key is readable from the active configuration (either the placeholder plus `config/hardware.local.yaml` or the file pointed to by `LAWN_HARDWARE_LOCAL_PATH`).

With this configuration, other developers only need the key and MAC address to replicate the SmartSolar integration.
