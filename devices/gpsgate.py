"""
GPSGate Generic Protocol integration.

Sends a confirmed violation event to the GPSGate server whenever a violation
belonging to contractor user_id=56 (DP World Karachi) is annotated as "true".

GPSGate Generic Protocol URL format (GET):
  https://hostname:port/comGpsGate/protocols/gpsgate/
    ?cmd=$FRCMD,{IMEI},_SendMessage,,{lat_nmea},{N|S},{lon_nmea},{E|W},
         {alt},{speed_knots},{heading},{DDMMYY},{hhmmss.dd},{valid},{inputs}

Custom inputs are appended as comma-separated key=value pairs:
  Speed (m/s), Text1-Text30 (string)
"""

import logging
import requests
from datetime import timezone as _tz

logger = logging.getLogger(__name__)

GPSGATE_URL        = "https://dfm.qict.com.pk:443/comGpsGate/protocols/gpsgate/"
PORTAL_BASE        = "https://afdd-portal.monit.tech/violations"
CONTRACTOR_USER_ID = 56

# ViolationType.title (lower) → Text field slot number
VIOLATION_TEXT_SLOT: dict[str, int] = {
    "severe drowsiness":  1,
    "yawning":            2,
    "distraction":        3,
    "mobile phone":       4,
    "mobile":             4,
    "smoking":            5,
    "hands away":         6,
    "harsh brake":        7,
    "harsh braking":      7,
    "harsh acceleration": 8,
    "over speeding":      9,
}


def _to_nmea(degrees: float, is_lat: bool) -> tuple[str, str]:
    """Convert decimal degrees → NMEA DDMM.mmmm + hemisphere char."""
    abs_deg = abs(degrees)
    d = int(abs_deg)
    m = (abs_deg - d) * 60
    if is_lat:
        return f"{d:02d}{m:07.4f}", ("N" if degrees >= 0 else "S")
    return f"{d:03d}{m:07.4f}", ("E" if degrees >= 0 else "W")


def _text_slot(title: str) -> int:
    return VIOLATION_TEXT_SLOT.get(title.strip().lower(), 9)


def send_violation_event(violation) -> None:
    """
    Fire a GPSGate _SendMessage for a confirmed violation.
    Called in a daemon thread from ViolationViewSet.partial_update so it
    never blocks the HTTP response.
    """
    try:
        vtype_title = (
            violation.violation_type_id.title
            if violation.violation_type_id_id
            else "Unknown"
        )
        slot = _text_slot(vtype_title)

        # Unit ID — device UUID as sent to GPSGate
        unit_id = str(violation.device_id or "1234567890")

        # Portal deep-link for the annotator/client
        contractor_id = violation.user_id or CONTRACTOR_USER_ID
        portal_url = f"{PORTAL_BASE}/{contractor_id}/{violation.id}"

        # Timestamps (UTC)
        logged_at = violation.logged_at
        if logged_at and logged_at.tzinfo is None:
            logged_at = logged_at.replace(tzinfo=_tz.utc)

        date_str    = logged_at.strftime("%d%m%y")      if logged_at else "010101"
        time_str    = logged_at.strftime("%H%M%S.00")   if logged_at else "000000.00"
        dt_display  = logged_at.strftime("%Y-%m-%d %H:%M:%S UTC") if logged_at else ""

        # Position
        lat       = float(violation.latitude  or 0)
        lon       = float(violation.longitude or 0)
        speed_kmh = float(violation.speed or 0)
        speed_knots = round(speed_kmh / 1.852, 2)   # main position field (knots)
        speed_ms    = round(speed_kmh / 3.6,   2)   # Speed input (m/s)
        valid = 1 if (lat != 0 and lon != 0) else 0

        lat_nmea, lat_hemi = _to_nmea(lat, is_lat=True)
        lon_nmea, lon_hemi = _to_nmea(lon, is_lat=False)

        # Text field: violation name + all key details + portal URL
        detail = (
            f"{vtype_title} | {dt_display} | "
            f"Speed: {speed_kmh} km/h | "
            f"Lat: {lat} Lng: {lon} | "
            f"{portal_url}"
        )

        # Full $FRCMD command string
        cmd = (
            f"$FRCMD,{unit_id},_SendMessage,,"
            f"{lat_nmea},{lat_hemi},"
            f"{lon_nmea},{lon_hemi},"
            f"0.0,{speed_knots},0.0,"
            f"{date_str},{time_str},{valid},"
            f"Speed={speed_ms},Text{slot}={detail}"
        )

        resp = requests.get(
            GPSGATE_URL,
            params={"cmd": cmd},
            timeout=10,
            verify=False,
        )
        resp.raise_for_status()
        logger.info(
            "GPSGate event sent: violation=%s type=%s slot=Text%s http=%s",
            violation.id, vtype_title, slot, resp.status_code,
        )

    except Exception as exc:
        logger.warning(
            "GPSGate event failed: violation=%s error=%s",
            getattr(violation, "id", "?"), exc,
        )
