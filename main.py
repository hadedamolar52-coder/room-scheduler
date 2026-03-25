import os
import sys
from flask import Flask, render_template, request, redirect, url_for

from google.auth.transport import requests as google_requests
from google.cloud import firestore
import google.oauth2.id_token

from bookings import (
    create_booking,
    list_user_bookings_all,
    list_user_bookings_for_room,
    parse_date_yyyy_mm_dd,
    parse_time_hhmm,
)
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
        rooms.append({"id": doc.id, "name": data.get("name", "")})
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

                else:
                    error_message = "Unknown form."

    rooms = _load_rooms()
    user_uid = _user_uid(claims) if claims else None

    filter_room_id = (request.args.get("bookings_room") or "").strip()
    my_bookings_all: list[dict] = []
    my_bookings_room: list[dict] = []
    if user_uid:
        my_bookings_all = list_user_bookings_all(db, user_uid)
        if filter_room_id:
            my_bookings_room = list_user_bookings_for_room(
                db, user_uid, filter_room_id
            )

    return render_template(
        "index.html",
        user_data=claims,
        error_message=error_message,
        rooms=rooms,
        my_bookings_all=my_bookings_all,
        my_bookings_room=my_bookings_room,
        filter_room_id=filter_room_id,
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080, debug=True)
