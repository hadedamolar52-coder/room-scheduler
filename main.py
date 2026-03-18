import os
import sys
from flask import Flask, render_template, request, redirect, url_for
from google.auth.transport import requests as google_requests
from google.cloud import firestore
import google.oauth2.id_token
from firestore_models import ROOMS_COLLECTION

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


@app.route("/", methods=["GET", "POST"])
def root():
    id_token = request.cookies.get("token")
    claims = verify_firebase_token(id_token)
    error_message = None

    if request.method == "POST":
        if not claims:
            error_message = "You must be logged in to add a room."
        else:
            room_name = (request.form.get("room_name") or "").strip()
            if not room_name:
                error_message = "Room name is required."
            else:
                user_uid = (
                    claims.get("uid")
                    or claims.get("user_id")
                    or claims.get("sub")
                )
                if not user_uid:
                    error_message = "Unable to determine user id from login token."
                    return render_template(
                        "index.html",
                        user_data=claims,
                        error_message=error_message,
                        rooms=[],
                    ), 401

                
                room_ref = db.collection(ROOMS_COLLECTION).document()
                room_ref.set({
                    "name": room_name,
                    "created_by_uid": user_uid,
                    "created_at": firestore.SERVER_TIMESTAMP,
                })
                return redirect(url_for("root"))

   
    rooms_ref = db.collection(ROOMS_COLLECTION)
    rooms_docs = list(rooms_ref.stream())
    rooms = []
    for doc in rooms_docs:
        data = doc.to_dict()
        rooms.append({
            "id": doc.id,
            "name": data.get("name", ""),
        })

    return render_template(
        "index.html",
        user_data=claims,
        error_message=error_message,
        rooms=rooms,
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080, debug=True)
