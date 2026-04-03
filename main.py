import os
import sys
from datetime import date, timedelta
from flask import Flask, render_template, request, redirect, url_for

from google.auth.transport import requests as google_requests
from google.cloud import firestore
import google.oauth2.id_token

from bookings import (
    create_booking,
    delete_booking,
    list_all_bookings_for_room,
    list_bookings_for_day_all_rooms,
    list_user_bookings_all,
    list_user_bookings_for_room,
    parse_date_yyyy_mm_dd,
    parse_time_hhmm,
    update_booking,
    get_booking,
    format_hhmm,
)
from rooms import delete_room_if_permitted
from firestore_models import ROOMS_COLLECTION

if sys.version_info >= (3, 14):
    sys.exit("Use Python 3.12 for this project (see README).")

firebase_request_adapter = google_requests.Request()

db = firestore.Client(
    database=os.environ.get("FIRESTORE_DATABASE", "a1-20260001")
)

app = Flask(__name__)


def verify_firebase_token(id_token: str | None) -> dict | None:
    if not id_token:
        return None
    try:
        return google.oauth2.id_token.verify_firebase_token(
            id_token, firebase_request_adapter
        )
    except ValueError:
        return None


def _user_uid(claims: dict) -> str | None:
    return claims.get("uid") or claims.get("user_id") or claims.get("sub")


def _load_rooms() -> list[dict]:
    rooms_ref = db.collection(ROOMS_COLLECTION)
    rooms_docs = list(rooms_ref.stream())
    rooms: list[dict] = []
    for doc in rooms_docs:
        data = doc.to_dict() or {}
        rooms.append(
            {
                "id": doc.id,
                "name": data.get("name", ""),
                "created_by_uid": data.get("created_by_uid", ""),
            }
        )
    rooms.sort(key=lambda r: (r["name"].lower(), r["id"]))
    return rooms


@app.route("/", methods=["GET", "POST"])
def root():
    id_token = request.cookies.get("token")
    claims = verify_firebase_token(id_token)
    error_message = None

    if request.method == "POST":
        if not claims:
            error_message = "You must be logged in."
        else:
            user_uid = _user_uid(claims)
            if not user_uid:
                error_message = "Unable to determine user id from login token."
            else:
                form_type = (request.form.get("form_type") or "").strip()

                if form_type == "add_room":
                    room_name = (request.form.get("room_name") or "").strip()
                    if not room_name:
                        error_message = "Room name is required."
                    else:
                        existing = (
                            db.collection(ROOMS_COLLECTION)
                            .where("name", "==", room_name)
                            .limit(1)
                            .stream()
                        )
                        if next(existing, None) is not None:
                            error_message = "A room with that name already exists."
                        else:
                            room_ref = db.collection(ROOMS_COLLECTION).document()
                            room_ref.set(
                                {
                                    "name": room_name,
                                    "created_by_uid": user_uid,
                                    "created_at": firestore.SERVER_TIMESTAMP,
                                }
                            )
                            return redirect(url_for("root"))

                elif form_type == "book_room":
                    room_id = (request.form.get("booking_room_id") or "").strip()
                    day_raw = (request.form.get("booking_date") or "").strip()
                    start_s = (request.form.get("start_time") or "").strip()
                    end_s = (request.form.get("end_time") or "").strip()

                    if not room_id:
                        error_message = "Select a room to book."
                    else:
                        d = parse_date_yyyy_mm_dd(day_raw)
                        if d is None:
                            error_message = "Booking date must be YYYY-MM-DD."
                        else:
                            day_str = d.isoformat()
                            sm = parse_time_hhmm(start_s)
                            em = parse_time_hhmm(end_s)
                            if sm is None or em is None:
                                error_message = (
                                    "Start and end times must be HH:MM (24h)."
                                )
                            else:
                                ok, err = create_booking(
                                    db, room_id, day_str, sm, em, user_uid
                                )
                                if not ok:
                                    error_message = (
                                        err or "Could not create booking."
                                    )
                                else:
                                    return redirect(url_for("root"))

                elif form_type == "delete_booking":
                    room_id = (request.form.get("room_id") or "").strip()
                    day_id = (request.form.get("day_id") or "").strip()
                    booking_id = (request.form.get("booking_id") or "").strip()
                    return_room = (
                        request.form.get("return_bookings_room") or ""
                    ).strip()
                    ok, err = delete_booking(
                        db, room_id, day_id, booking_id, user_uid
                    )
                    if not ok:
                        error_message = err or "Could not delete booking."
                    elif return_room:
                        return redirect(
                            url_for("root", bookings_room=return_room)
                        )
                    else:
                        return redirect(url_for("root"))

                elif form_type == "delete_room":
                    room_id = (request.form.get("room_id") or "").strip()
                    ok, err = delete_room_if_permitted(db, room_id, user_uid)
                    if not ok:
                        error_message = err or "Could not delete room."
                    else:
                        return redirect(url_for("root"))

                else:
                    error_message = "Unknown form."

    rooms = _load_rooms()
    user_uid = _user_uid(claims) if claims else None

    filter_room_id = (request.args.get("bookings_room") or "").strip()
    day_filter = (request.args.get("day_filter") or "").strip()
    day_filter_bookings: list[dict] = []
    my_bookings_all: list[dict] = []
    my_bookings_room: list[dict] = []
    if user_uid:
        my_bookings_all = list_user_bookings_all(db, user_uid)
        if filter_room_id:
            my_bookings_room = list_user_bookings_for_room(
                db, user_uid, filter_room_id
            )
    if day_filter:
        parsed_day = parse_date_yyyy_mm_dd(day_filter)
        if parsed_day is None:
            error_message = "Day filter must be YYYY-MM-DD."
            day_filter = ""
        else:
            day_filter = parsed_day.isoformat()
            day_filter_bookings = list_bookings_for_day_all_rooms(
                db, day_filter
            )

    return render_template(
        "index.html",
        user_data=claims,
        error_message=error_message,
        rooms=rooms,
        my_bookings_all=my_bookings_all,
        my_bookings_room=my_bookings_room,
        filter_room_id=filter_room_id,
        day_filter=day_filter,
        day_filter_bookings=day_filter_bookings,
        current_user_uid=user_uid,
    )


@app.route("/room/<room_id>", methods=["GET"])
def room_detail(room_id: str):
    id_token = request.cookies.get("token")
    claims = verify_firebase_token(id_token)

    room_ref = db.collection(ROOMS_COLLECTION).document(room_id)
    room_snap = room_ref.get()
    if not room_snap.exists:
        return redirect(url_for("root"))

    room_data = room_snap.to_dict() or {}
    room_name = room_data.get("name", "")
    bookings = list_all_bookings_for_room(db, room_id)
    occupancy_next_5_days: list[dict] = []

    earliest_free_slot: dict | None = None
    window_start = 9 * 60
    window_end = 18 * 60
    window_total = window_end - window_start  # 540 minutes
    today = date.today()

    calendar_hours: list[dict] = []
    calendar_next_5_days: list[dict] = []
    for h_start in range(window_start, window_end, 60):
        h_end = min(h_start + 60, window_end)
        calendar_hours.append(
            {
                "start_minutes": h_start,
                "end_minutes": h_end,
                "label": f"{format_hhmm(h_start)}-{format_hhmm(h_end)}",
            }
        )

    for offset in range(5):
        day = today + timedelta(days=offset)
        day_id = day.isoformat()
        booked_minutes = 0

        day_bookings = [b for b in bookings if b.get("day_id") == day_id]

        intervals: list[tuple[int, int]] = []
        for b in day_bookings:
            start_m = int(b.get("start_minutes", 0))
            end_m = int(b.get("end_minutes", 0))
            overlap_start = max(start_m, window_start)
            overlap_end = min(end_m, window_end)
            if overlap_end > overlap_start:
                booked_minutes += overlap_end - overlap_start
                intervals.append((overlap_start, overlap_end))

        occupancy_pct = round((booked_minutes / window_total) * 100, 2)
        occupancy_next_5_days.append(
            {
                "day_id": day_id,
                "booked_minutes": booked_minutes,
                "occupancy_pct": occupancy_pct,
            }
        )

        intervals.sort(key=lambda x: (x[0], x[1]))
        merged: list[tuple[int, int]] = []
        for s, e in intervals:
            if not merged or s > merged[-1][1]:
                merged.append((s, e))
            else:
                merged[-1] = (merged[-1][0], max(merged[-1][1], e))

        pointer = window_start
        free_start: int | None = None
        free_end: int | None = None
        for s, e in merged:
            if s > pointer:
                free_start = pointer
                free_end = s
                break
            pointer = max(pointer, e)

        if free_start is None and pointer < window_end:
            free_start = pointer
            free_end = window_end

        if (
            earliest_free_slot is None
            and free_start is not None
            and free_end is not None
            and free_start < free_end
        ):
            earliest_free_slot = {
                "day_id": day_id,
                "start_minutes": free_start,
                "end_minutes": free_end,
                "start_label": format_hhmm(free_start),
                "end_label": format_hhmm(free_end),
            }

        calendar_slots: list[dict] = []
        for slot in calendar_hours:
            s = int(slot["start_minutes"])
            e = int(slot["end_minutes"])
            cell_label = ""
            for b in day_bookings:
                start_m = int(b.get("start_minutes", 0))
                end_m = int(b.get("end_minutes", 0))
                if end_m <= s or start_m >= e:
                    continue
                overlap_s = max(start_m, s)
                overlap_e = min(end_m, e)
                if overlap_e > overlap_s:
                    cell_label = f"{format_hhmm(overlap_s)}-{format_hhmm(overlap_e)}"
                break
            calendar_slots.append(
                {
                    "start_minutes": s,
                    "end_minutes": e,
                    "label": cell_label,
                }
            )

        calendar_next_5_days.append(
            {
                "day_id": day_id,
                "slots": calendar_slots,
            }
        )

    return render_template(
        "room_detail.html",
        user_data=claims,
        room_id=room_id,
        room_name=room_name,
        room_bookings=bookings,
        occupancy_next_5_days=occupancy_next_5_days,
        earliest_free_slot=earliest_free_slot,
        calendar_hours=calendar_hours,
        calendar_next_5_days=calendar_next_5_days,
    )


@app.route("/booking/edit", methods=["GET", "POST"])
def edit_booking():
    id_token = request.cookies.get("token")
    claims = verify_firebase_token(id_token)

    if not claims:
        return redirect(url_for("root"))

    user_uid = _user_uid(claims)
    if not user_uid:
        return redirect(url_for("root"))

    if request.method == "GET":
        room_id = (request.args.get("room_id") or "").strip()
        day_id = (request.args.get("day_id") or "").strip()
        booking_id = (request.args.get("booking_id") or "").strip()
        return_room = (request.args.get("return_bookings_room") or "").strip()

        if not room_id or not day_id or not booking_id:
            return redirect(url_for("root"))

        booking = get_booking(db, room_id, day_id, booking_id)
        if booking is None or booking.get("user_uid") != user_uid:
            return redirect(url_for("root"))

        start_minutes = int(booking.get("start_minutes", 0))
        end_minutes = int(booking.get("end_minutes", 0))

        room_name = ""
        room_snap = db.collection(ROOMS_COLLECTION).document(room_id).get()
        if room_snap.exists:
            room_name = (room_snap.to_dict() or {}).get("name", "")

        return render_template(
            "edit_booking.html",
            user_data=claims,
            error_message=None,
            room_id=room_id,
            room_name=room_name,
            day_id=day_id,
            booking_id=booking_id,
            start_time=format_hhmm(start_minutes),
            end_time=format_hhmm(end_minutes),
            return_bookings_room=return_room,
            bookings_room_query=return_room,
        )

    room_id = (request.form.get("room_id") or "").strip()
    day_id = (request.form.get("day_id") or "").strip()
    booking_id = (request.form.get("booking_id") or "").strip()
    return_room = (request.form.get("return_bookings_room") or "").strip()

    if not room_id or not day_id or not booking_id:
        return redirect(url_for("root"))

    start_s = (request.form.get("start_time") or "").strip()
    end_s = (request.form.get("end_time") or "").strip()

    sm = parse_time_hhmm(start_s)
    em = parse_time_hhmm(end_s)
    if sm is None or em is None:
        booking = get_booking(db, room_id, day_id, booking_id)
        start_minutes = int((booking or {}).get("start_minutes", 0))
        end_minutes = int((booking or {}).get("end_minutes", 0))
        return render_template(
            "edit_booking.html",
            user_data=claims,
            error_message="Start and end times must be HH:MM (24h).",
            room_id=room_id,
            room_name=(db.collection(ROOMS_COLLECTION).document(room_id).get().to_dict() or {}).get("name", ""),
            day_id=day_id,
            booking_id=booking_id,
            start_time=format_hhmm(start_minutes),
            end_time=format_hhmm(end_minutes),
            return_bookings_room=return_room,
            bookings_room_query=return_room,
        )

    ok, err = update_booking(
        db, room_id, day_id, booking_id, user_uid, sm, em
    )
    if not ok:
        booking = get_booking(db, room_id, day_id, booking_id)
        start_minutes = int((booking or {}).get("start_minutes", 0))
        end_minutes = int((booking or {}).get("end_minutes", 0))
        return render_template(
            "edit_booking.html",
            user_data=claims,
            error_message=err or "Could not update booking.",
            room_id=room_id,
            room_name=(db.collection(ROOMS_COLLECTION).document(room_id).get().to_dict() or {}).get("name", ""),
            day_id=day_id,
            booking_id=booking_id,
            start_time=format_hhmm(start_minutes),
            end_time=format_hhmm(end_minutes),
            return_bookings_room=return_room,
            bookings_room_query=return_room,
        )

    if return_room:
        return redirect(url_for("root", bookings_room=return_room))
    return redirect(url_for("root"))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080, debug=True)
