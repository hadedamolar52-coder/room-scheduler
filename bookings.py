from __future__ import annotations
import re
from datetime import date, datetime
from typing import Any
from google.cloud import firestore
from firestore_models import BOOKINGS_SUBCOLLECTION, DAYS_SUBCOLLECTION, ROOMS_COLLECTION


DAY_MINUTES = 24 * 60

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_date_yyyy_mm_dd(value: str) -> date | None:
    value = (value or "").strip()
    if not _DATE_RE.match(value):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_time_hhmm(value: str) -> int | None:
    value = (value or "").strip()
    m = re.match(r"^(\d{1,2}):(\d{2})$", value)
    if not m:
        return None
    h, mm = int(m.group(1)), int(m.group(2))
    if not (0 <= h <= 23 and 0 <= mm <= 59):
        return None
    return h * 60 + mm


def format_hhmm(minutes: int) -> str:
    minutes = max(0, min(DAY_MINUTES - 1, minutes))
    h, m = divmod(minutes, 60)
    return f"{h:02d}:{m:02d}"


def intervals_overlap(
    start_a: int, end_a: int, start_b: int, end_b: int
) -> bool:
    return start_a < end_b and start_b < end_a


def _booking_dict(
    room_id: str,
    room_name: str,
    day_id: str,
    booking_id: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    start_m = int(data.get("start_minutes", 0))
    end_m = int(data.get("end_minutes", 0))
    return {
        "room_id": room_id,
        "room_name": room_name,
        "day_id": day_id,
        "booking_id": booking_id,
        "start_minutes": start_m,
        "end_minutes": end_m,
        "start_label": format_hhmm(start_m),
        "end_label": format_hhmm(end_m),
        "user_uid": data.get("user_uid", ""),
    }


def create_booking(
    db: firestore.Client,
    room_id: str,
    day_str: str,
    start_minutes: int,
    end_minutes: int,
    user_uid: str,
) -> tuple[bool, str | None]:
    if start_minutes < 0 or end_minutes > DAY_MINUTES or start_minutes >= end_minutes:
        return False, "Invalid time range (use HH:MM, start before end, same day)."

    room_ref = db.collection(ROOMS_COLLECTION).document(room_id)
    room_snap = room_ref.get()
    if not room_snap.exists:
        return False, "Room not found."

    day_id = day_str
    day_ref = room_ref.collection(DAYS_SUBCOLLECTION).document(day_id)
    bookings_ref = day_ref.collection(BOOKINGS_SUBCOLLECTION)

    # Ensure day document exists (links room -> day without an index).
    if not day_ref.get().exists:
        day_ref.set({"date": day_id})

    for b in bookings_ref.stream():
        d = b.to_dict() or {}
        s = int(d.get("start_minutes", -1))
        e = int(d.get("end_minutes", -1))
        if intervals_overlap(start_minutes, end_minutes, s, e):
            return False, "That time overlaps another booking for this room."

    booking_ref = bookings_ref.document()
    booking_ref.set(
        {
            "start_minutes": start_minutes,
            "end_minutes": end_minutes,
            "user_uid": user_uid,
            "created_at": firestore.SERVER_TIMESTAMP,
        }
    )
    return True, None


def get_booking(
    db: firestore.Client,
    room_id: str,
    day_id: str,
    booking_id: str,
) -> dict[str, Any] | None:
    ref = (
        db.collection(ROOMS_COLLECTION)
        .document(room_id)
        .collection(DAYS_SUBCOLLECTION)
        .document(day_id)
        .collection(BOOKINGS_SUBCOLLECTION)
        .document(booking_id)
    )
    snap = ref.get()
    if not snap.exists:
        return None
    data = snap.to_dict() or {}
    return {
        "booking_id": booking_id,
        **data,
    }


def update_booking(
    db: firestore.Client,
    room_id: str,
    day_id: str,
    booking_id: str,
    user_uid: str,
    start_minutes: int,
    end_minutes: int,
) -> tuple[bool, str | None]:

    if start_minutes < 0 or end_minutes > DAY_MINUTES or start_minutes >= end_minutes:
        return False, "Invalid time range (use HH:MM, start before end, same day)."

    booking_data = get_booking(db, room_id, day_id, booking_id)
    if booking_data is None:
        return False, "Booking not found."
    if booking_data.get("user_uid") != user_uid:
        return False, "You can only edit your own booking."

    room_ref = db.collection(ROOMS_COLLECTION).document(room_id)
    day_ref = room_ref.collection(DAYS_SUBCOLLECTION).document(day_id)
    bookings_ref = day_ref.collection(BOOKINGS_SUBCOLLECTION)

    for b in bookings_ref.stream():
        if b.id == booking_id:
            continue
        d = b.to_dict() or {}
        s = int(d.get("start_minutes", -1))
        e = int(d.get("end_minutes", -1))
        if intervals_overlap(start_minutes, end_minutes, s, e):
            return False, "That time overlaps another booking for this room."

    ref = bookings_ref.document(booking_id)
    ref.update(
        {
            "start_minutes": start_minutes,
            "end_minutes": end_minutes,
            "created_at": firestore.SERVER_TIMESTAMP,
        }
    )
    return True, None


def delete_booking(
    db: firestore.Client,
    room_id: str,
    day_id: str,
    booking_id: str,
    user_uid: str,
) -> tuple[bool, str | None]:
    if not room_id or not day_id or not booking_id:
        return False, "Missing booking reference."

    ref = (
        db.collection(ROOMS_COLLECTION)
        .document(room_id)
        .collection(DAYS_SUBCOLLECTION)
        .document(day_id)
        .collection(BOOKINGS_SUBCOLLECTION)
        .document(booking_id)
    )
    snap = ref.get()
    if not snap.exists:
        return False, "Booking not found."
    data = snap.to_dict() or {}
    if data.get("user_uid") != user_uid:
        return False, "You can only delete your own booking."
    ref.delete()
    return True, None


def list_user_bookings_all(
    db: firestore.Client, user_uid: str
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for room in db.collection(ROOMS_COLLECTION).stream():
        room_id = room.id
        room_name = (room.to_dict() or {}).get("name", "")
        for day_doc in room.reference.collection(DAYS_SUBCOLLECTION).stream():
            day_id = day_doc.id
            for b in day_doc.reference.collection(BOOKINGS_SUBCOLLECTION).stream():
                data = b.to_dict() or {}
                if data.get("user_uid") != user_uid:
                    continue
                out.append(_booking_dict(room_id, room_name, day_id, b.id, data))

    out.sort(key=lambda x: (x["day_id"], x["start_minutes"], x["room_name"]))
    return out


def list_user_bookings_for_room(
    db: firestore.Client, user_uid: str, room_id: str
) -> list[dict[str, Any]]:
    room_ref = db.collection(ROOMS_COLLECTION).document(room_id)
    room_snap = room_ref.get()
    if not room_snap.exists:
        return []
    room_name = (room_snap.to_dict() or {}).get("name", "")

    out: list[dict[str, Any]] = []
    for day_doc in room_ref.collection(DAYS_SUBCOLLECTION).stream():
        day_id = day_doc.id
        for b in day_doc.reference.collection(BOOKINGS_SUBCOLLECTION).stream():
            data = b.to_dict() or {}
            if data.get("user_uid") != user_uid:
                continue
            out.append(_booking_dict(room_id, room_name, day_id, b.id, data))

    out.sort(key=lambda x: (x["day_id"], x["start_minutes"]))
    return out


def list_bookings_for_day_all_rooms(
    db: firestore.Client, day_id: str
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for room in db.collection(ROOMS_COLLECTION).stream():
        room_id = room.id
        room_name = (room.to_dict() or {}).get("name", "")
        day_ref = room.reference.collection(DAYS_SUBCOLLECTION).document(day_id)
        day_snap = day_ref.get()
        if not day_snap.exists:
            continue
        for b in day_ref.collection(BOOKINGS_SUBCOLLECTION).stream():
            data = b.to_dict() or {}
            out.append(_booking_dict(room_id, room_name, day_id, b.id, data))

    out.sort(key=lambda x: (x["start_minutes"], x["room_name"]))
    return out


def list_all_bookings_for_room(
    db: firestore.Client, room_id: str
) -> list[dict[str, Any]]:
    room_ref = db.collection(ROOMS_COLLECTION).document(room_id)
    room_snap = room_ref.get()
    if not room_snap.exists:
        return []
    room_name = (room_snap.to_dict() or {}).get("name", "")

    out: list[dict[str, Any]] = []
    for day_doc in room_ref.collection(DAYS_SUBCOLLECTION).stream():
        day_id = day_doc.id
        for b in day_doc.reference.collection(BOOKINGS_SUBCOLLECTION).stream():
            data = b.to_dict() or {}
            out.append(_booking_dict(room_id, room_name, day_id, b.id, data))

    out.sort(key=lambda x: (x["day_id"], x["start_minutes"]))
    return out
