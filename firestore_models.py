"""
Firestore data model for Room Scheduler.
Linking uses subcollections only (no composite index required).

Structure:
  - Room: top-level collection "rooms". Document id = room_id.
  - Day: subcollection under each room: rooms/{room_id}/days/{day_id}.
    One document per calendar day per room; day_id = date string (e.g. "2026-03-15").
  - Booking: subcollection under each day: rooms/{room_id}/days/{day_id}/bookings/{booking_id}.
    Each booking has start_time, end_time, user_uid, etc.

Relationships: Room -> zero or more Days -> zero or more Bookings.
We traverse by path (room_ref.collection("days").document(day_id).collection("bookings"))
so no index is needed to link documents.
"""

# Top-level collection for rooms.
ROOMS_COLLECTION = "rooms"

# Subcollection name under each room document (one doc per calendar day).
DAYS_SUBCOLLECTION = "days"

# Subcollection name under each day document.
BOOKINGS_SUBCOLLECTION = "bookings"
