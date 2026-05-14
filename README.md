# SwasthyaSetu — Real-Time Hospital Availability Platform

A full-stack Flask web application for smart healthcare management with real-time hospital bed booking, ambulance tracking, emergency alerts, and hospital service management.

**Tagline:** Real-Time Hospital Availability Platform

---

## Features

- Role-based dashboards: Admin, Hospital, Patient
- Hospital bed availability management (Normal, Emergency, ICU)
- **Ambulance booking + live tracking** with Leaflet.js maps (no API key needed)
- **Public Emergency Alert** page (no login required)
- 15 medical services management (MRI, CT Scan, Sonography, X-Ray, Ventilator, ICU, Emergency Ward, Blood Bank, Pharmacy, OPD, Dialysis, Maternity, Cardiology, Orthopedics, Neurology)
- QR Code on booking confirmation (client-side, qrcode.js)
- Chart.js dashboards with live stats
- Email notifications (Flask-Mail) — fully logged in DB even if SMTP fails
- Beautiful Bootstrap 5 + Animate.css UI with left-side dynamic sidebar
- Mobile responsive (off-canvas sidebar on small screens)

---

## Setup Instructions (Windows 11 + VSCode)

### Step 1 — Open project folder in VSCode

```
code SwasthyaSetu
```

### Step 2 — Open VSCode Terminal (Ctrl + `) and create venv

```bash
python -m venv venv
```

### Step 3 — Activate the virtual environment

```bash
venv\Scripts\activate
```

### Step 4 — Install dependencies

```bash
pip install -r requirements.txt
```

### Step 5 — Run the application

```bash
python app.py
```

### Step 6 — Open the app in your browser

Visit: <http://localhost:5000>

---

## Default Login Credentials (auto-seeded on first run)

### Admin
- **Email:** `admin@swasthyasetu.com`
- **Password:** `admin123`

### Demo Hospital (City Care Hospital — pre-approved)
- **Email:** `citycare@swasthyasetu.com`
- **Password:** `hospital123`

### Demo Patient
- **Email:** `patient@swasthyasetu.com`
- **Password:** `patient123`

---

## macOS / Linux Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

---

## Tech Stack

| Layer        | Tech                                         |
|--------------|----------------------------------------------|
| Backend      | Flask 3, Flask-SQLAlchemy, Flask-Login, Flask-Bcrypt, Flask-Mail, Flask-WTF |
| Database     | SQLite (auto-created in `instance/healthcare.db`) |
| Frontend     | Bootstrap 5, Jinja2, Animate.css, Vanilla JS, AJAX |
| Maps         | Leaflet.js + OpenStreetMap (free, no API key)|
| Charts       | Chart.js                                     |
| QR Codes     | qrcode.js (client-side)                      |
| Icons        | Bootstrap Icons, Font Awesome 6              |

---

## Project Structure

```
SwasthyaSetu/
├── app.py                  # Main Flask application (all models + routes)
├── requirements.txt
├── .env                    # Environment variables (edit SMTP creds)
├── README.md
├── .vscode/
│   ├── settings.json
│   └── launch.json
├── instance/               # SQLite DB lives here (auto-created)
├── static/
│   ├── css/                # main.css, sidebar.css, dashboard.css
│   ├── js/                 # main.js, sidebar.js, tracking.js, charts.js
│   ├── uploads/            # Site logos
│   └── hospital_logos/     # Hospital logos & images
└── templates/
    ├── base.html           # Master layout with left sidebar
    ├── index.html, login.html, emergency.html, ...
    ├── admin/              # Admin panel pages
    ├── hospital/           # Hospital panel pages
    ├── patient/            # Patient panel pages
    └── errors/             # 404, 500
```

---

## Demo Mode Notes

The app runs entirely in **demo mode** for the ambulance tracking module:

- Admin can manually update an ambulance's latitude, longitude, status, and ETA from the Admin Panel → Manage Ambulances → Update Location.
- Patients see the ambulance move on a Leaflet map (polling every 10s via AJAX `/api/ambulance/<id>/status`).
- No real GPS or Google Maps required.

All external API dependencies are removed — the app is 100% self-contained.

---

## License

© 2025 SwasthyaSetu. All rights reserved.
