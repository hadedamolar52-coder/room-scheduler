from __future__ import annotations

from typing import Any

from google.cloud import firestore

from firestore_models import BOOKINGS_SUBCOLLECTION, DAYS_SUBCOLLECTION, ROOMS_COLLECTION


def delete_room_if_permitted(
    db: firestore.Client,
    room_id: str,
    user_uid: str,
) -> tuple[bool, str | None]:
    if not room_id:
        return False, "Missing room id."

    room_ref = db.collection(ROOMS_COLLECTION).document(room_id)
    room_snap = room_ref.get()
    if not room_snap.exists:
        return False, "Room not found."

    room_data: dict[str, Any] = room_snap.to_dict() or {}
    created_by_uid = room_data.get("created_by_uid")
    if created_by_uid != user_uid:
        return False, "You can only delete rooms you created."

    days = list(room_ref.collection(DAYS_SUBCOLLECTION).stream())
    for day_doc in days:
        bookings_ref = day_doc.reference.collection(BOOKINGS_SUBCOLLECTION)
        bookings_iter = bookings_ref.limit(1).stream()
        first_booking = next(bookings_iter, None)
        if first_booking is not None:
            return False, "You cannot delete a room that has bookings."

    for day_doc in days:
        day_doc.reference.delete()

    room_ref.delete()
    return True, None

