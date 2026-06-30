"""
GPSGate batch test — send status=true violations from DB for 10 selected devices.

All position/speed/time/altitude values come from each Violation row in the DB.
Run from project root:  python test_gpsgate.py
"""

import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "afdd.settings")
django.setup()

import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from datetime import timezone as _tz
from devices.models import Device, Violation

# ── Config ────────────────────────────────────────────────────────────────────
GPSGATE_URL   = "https://116.0.58.155/comGpsGate/protocols/gpsgate/"
GPSGATE_HOST  = "dfm.qict.com.pk"
PORTAL_BASE   = "https://afdd-portal.monit.tech/violations"
CONTRACTOR_ID = 56

UNIT_ID_PREFIX = "1234567"   # final unit id = prefix + device suffix

DEVICE_SUFFIXES = ["188", "920", "227", "535", "502", "632", "375", "807", "677", "658"]

MAX_VIOLATIONS_PER_DEVICE = 50    # cap per device
SEND = True                       # set False for dry-run preview only

# ── Text-slot mapping (matches client-defined text fields) ────────────────────
# Text1 = Severe Drowsiness        Text5 = Smoking
# Text2 = Yawning                  Text6 = Hands Away
# Text3 = Distraction              Text7 = Harsh Brake
# Text4 = Mobile                   Text8 = Harsh Acceleration
#                                  Text9 = Over Speeding
VIOLATION_TEXT_SLOT = {
    # Text1 — Severe Drowsiness (and aliases)
    "severe drowsiness":      1,
    "severe drowsy":          1,
    "drowsiness":             1,

    # Text2 — Yawning
    "yawning":                2,

    # Text3 — Distraction
    "distraction":            3,
    "distracted":             3,

    # Text4 — Mobile / Mobile Phone
    "mobile":                 4,
    "mobile phone":           4,
    "phone":                  4,

    # Text5 — Smoking
    "smoking":                5,

    # Text6 — Hands Away (off steering)
    "hands away":             6,
    "hands not on steering":  6,

    # Text7 — Harsh Brake
    "harsh brake":            7,
    "harsh braking":          7,

    # Text8 — Harsh Acceleration
    "harsh acceleration":     8,

    # Text9 — Over Speeding
    "over speeding":          9,
    "overspeeding":           9,
}


# ── Helpers ───────────────────────────────────────────────────────────────────
def to_nmea(degrees: float, is_lat: bool):
    abs_deg = abs(degrees)
    d = int(abs_deg)
    m = (abs_deg - d) * 60
    if is_lat:
        return f"{d:02d}{m:07.4f}", ("N" if degrees >= 0 else "S")
    return f"{d:03d}{m:07.4f}", ("E" if degrees >= 0 else "W")


def build_cmd(unit_id: str, v: Violation, vtype_title: str):
    """Build $FRCMD string using ONLY this violation's actual DB values."""
    title_key = vtype_title.strip().lower()
    if title_key not in VIOLATION_TEXT_SLOT:
        return None, None, f"unmapped type '{vtype_title}'"
    slot = VIOLATION_TEXT_SLOT[title_key]

    # Timestamp — must come from the violation row
    if not v.logged_at:
        return None, slot, "missing logged_at"
    logged_at = v.logged_at
    if logged_at.tzinfo is None:
        logged_at = logged_at.replace(tzinfo=_tz.utc)
    date_str   = logged_at.strftime("%d%m%y")
    time_str   = logged_at.strftime("%H%M%S.00")
    dt_display = logged_at.strftime("%Y-%m-%d %H:%M:%S UTC")

    # Position — straight from violation row
    if v.latitude is None or v.longitude is None:
        return None, slot, "missing lat/lon"
    lat = float(v.latitude)
    lon = float(v.longitude)
    alt = float(v.altitude) if v.altitude is not None else 0.0

    # Speed — straight from violation row (km/h)
    if v.speed is None:
        return None, slot, "missing speed"
    speed_kmh   = float(v.speed)
    speed_knots = round(speed_kmh / 1.852, 2)   # position field (knots)
    speed_ms    = round(speed_kmh / 3.6,   2)   # Speed input (m/s)

    valid = 1 if (lat != 0 and lon != 0) else 0
    lat_nmea, lat_hemi = to_nmea(lat, is_lat=True)
    lon_nmea, lon_hemi = to_nmea(lon, is_lat=False)

    portal_url = f"{PORTAL_BASE}/{CONTRACTOR_ID}/{v.id}"
    detail = (
        f"{vtype_title} | {dt_display} | "
        f"Speed: {speed_kmh} km/h | "
        f"Alt: {alt} m | "
        f"Lat: {lat} Lng: {lon} | "
        f"{portal_url}"
    )

    cmd = (
        f"$FRCMD,{unit_id},_SendMessage,,"
        f"{lat_nmea},{lat_hemi},"
        f"{lon_nmea},{lon_hemi},"
        f"{alt},{speed_knots},0.0,"           # alt from DB; heading not stored on Violation
        f"{date_str},{time_str},{valid},"
        f"Speed={speed_ms},Text{slot}={detail}"
    )
    return cmd, slot, None


# ── Resolve device suffix → full device UUID ──────────────────────────────────
print(f"Resolving {len(DEVICE_SUFFIXES)} device suffixes to UUIDs...")
suffix_to_uuid = {}
for suffix in DEVICE_SUFFIXES:
    dev = Device.objects.filter(uuid__endswith=suffix).first()
    if dev:
        suffix_to_uuid[suffix] = dev.uuid
        print(f"  {suffix:>4} → {dev.uuid}")
    else:
        print(f"  {suffix:>4} → NOT FOUND in DB")

if not suffix_to_uuid:
    print("\nNo devices matched. Exiting.")
    exit(1)

# ── Loop devices and send their true violations ───────────────────────────────
totals = {"sent_ok": 0, "sent_err": 0, "skipped": 0}
unmapped_types = set()

for suffix, device_uuid in suffix_to_uuid.items():
    unit_id = f"{UNIT_ID_PREFIX}{suffix}"

    violations = list(
        Violation.objects
        .select_related("violation_type_id")
        .filter(device_id=device_uuid, status="true")
        .order_by("-logged_at")[:MAX_VIOLATIONS_PER_DEVICE]
    )

    print(f"\n── Device {suffix} (uuid={device_uuid})  →  Unit {unit_id} ──")
    print(f"   {len(violations)} true violation(s) found")

    for v in violations:
        vtype_title = v.violation_type_id.title if v.violation_type_id_id else "Unknown"
        cmd, slot, err = build_cmd(unit_id, v, vtype_title)

        if cmd is None:
            print(f"   SKIP vio={v.id} type={vtype_title:<20} reason={err}")
            if err and err.startswith("unmapped"):
                unmapped_types.add(vtype_title)
            totals["skipped"] += 1
            continue

        if not SEND:
            print(f"   [DRY] vio={v.id} type={vtype_title:<20} slot=Text{slot} "
                  f"lat={v.latitude} lon={v.longitude} spd={v.speed} alt={v.altitude}")
            totals["skipped"] += 1
            continue

        try:
            resp = requests.get(
                GPSGATE_URL,
                params={"cmd": cmd},
                headers={"Host": GPSGATE_HOST},
                timeout=15,
                verify=False,
            )
            if "$FRRET" in resp.text:
                print(f"   OK   vio={v.id} type={vtype_title:<20} slot=Text{slot}")
                totals["sent_ok"] += 1
            else:
                print(f"   FAIL vio={v.id} http={resp.status_code} resp={resp.text[:80]}")
                totals["sent_err"] += 1
        except requests.exceptions.RequestException as e:
            print(f"   FAIL vio={v.id} error={e}")
            totals["sent_err"] += 1

# ── Summary ───────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print(f"DONE. sent_ok={totals['sent_ok']}  sent_err={totals['sent_err']}  skipped={totals['skipped']}")
if unmapped_types:
    print(f"Unmapped types (add to VIOLATION_TEXT_SLOT): {sorted(unmapped_types)}")
print("=" * 60)
