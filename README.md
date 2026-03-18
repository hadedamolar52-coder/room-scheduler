# Room Scheduler (Assignment 1)

Google App Engine (Python 3) application with Firebase Authentication and Firestore.

## Group 1 (this setup)

- Login/logout via Firebase (same pattern as official App Engine + Firebase examples; `firebase-login.js`).
- Firestore documents: **Room**, **Day**, **Booking** — linked by subcollections (no index).
- Add-room form and list of rooms.

## Before you run

1. **Firebase**  
   - Create a Firebase project and enable Email/Password and Google sign-in.  
   - In Firebase Console → Project settings → General, copy your app’s config snippet.  
   - In `templates/index.html`, replace the `firebaseConfig` object with your snippet (apiKey, authDomain, projectId, etc.).

2. **Firestore database name**  
   - In `app.yaml`, set `FIRESTORE_DATABASE` to your student number, e.g. `A1-1234567`.  
   - Create a Firestore database in Firebase Console with that exact database ID (if using a second database).

3. **Local run**  
   Use **Python 3.12** (App Engine runtime; 3.14 is not supported by protobuf/Firestore).  
   ```bash
   python3.12 -m venv venv
   source venv/bin/activate   # or venv\Scripts\activate on Windows
   pip install -r requirements.txt
   # If you previously set a service-account JSON, it will override gcloud ADC:
   unset GOOGLE_APPLICATION_CREDENTIALS
   python main.py
   ```  
   Open http://127.0.0.1:8080

4. **Git**  
   Use a local git repo only (no remote). Make at least 7 commits before submission.

## Project layout

- `main.py` — Flask app, token verification, routes.
- `firestore_models.py` — Collection/subcollection names and model description.
- `templates/index.html` — Main page (login UI, room list, add-room form).
- `static/firebase-login.js` — Firebase UI and token cookie (required by assignment).
- `app.yaml` — App Engine config.
- `requirements.txt` — Python dependencies (SDK-only; no extra libraries).
