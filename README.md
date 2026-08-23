# MediBridge 🩺

> **Connected Care Platform — Hackathon MVP**

MediBridge is a Flask-based healthcare coordination platform designed to connect **patients, doctors, hospitals, pharmacy operations, delivery agents, and healthcare administrators** through one web application.

The project is built as a hackathon MVP and demonstrates an end-to-end healthcare workflow: symptom assessment → doctor discovery → appointment booking → consultation → prescriptions/reminders → pharmacy ordering → delivery verification → hospital capacity intelligence.

---

## ✨ Key Features

### 👤 Patient Portal
- Patient authentication and dashboard
- AI-assisted symptom assessment and triage
- First-aid guidance, urgency level, red flags, and doctor/specialty recommendations
- Doctor discovery with specialty, qualification, experience, hospital and venue information
- Appointment slot browsing and booking
- ₹200 demo consultation payment flow using UPI
- Appointment token/queue information
- Appointment cancellation
- Prescription viewing
- Medicine reminders and "mark as taken" tracking
- Online consultation room / guest-link generation
- Diagnostics/test catalogue and diagnostic order flow
- Pharmacy medicine catalogue
- Medicine ordering and order tracking
- NFC patient-card support
- Appointment check-in through NFC UID
- Emergency/healthcare information exposed through the application UI

### 🩺 Doctor / Clinician Portal
- Doctor authentication
- Doctor profile and professional information
- Appointment schedule
- Availability control for appointment slots
- View active appointments
- Start/end consultations
- Patient queue/token workflow
- Prescription creation
- Consultation room generation
- Patient-facing appointment state updates

### 🏥 Hospital Partner Portal
- Separate hospital authentication
- Hospital bed capacity dashboard
- Occupied/total bed reporting
- Regional capacity information
- Hospital data feeds the pandemic/risk intelligence system
- Multiple demo partner hospitals are pre-seeded

### 🔐 Admin Operations Console
- Patient overview
- NFC card registration
- NFC appointment check-in
- Patient pharmacy lookup using NFC UID
- Pharmacy inventory management/view
- Medicine order monitoring
- Delivery portal access
- NFC scan logs
- RFID/package scan logs
- Pandemic intelligence dashboard
- City/hospital capacity analysis
- Configurable hotspot and potential-hotspot occupancy thresholds

### 🚚 Delivery Agent Portal
- Dedicated delivery-agent authentication
- Medicine order delivery workflow
- Chipless-RFID package-tag scanning
- 6-digit OTP verification
- Delivery status confirmation
- Delivery/RFID activity logging

### 🧭 Pandemic Intelligence
- Regional/hospital capacity monitoring
- Occupancy-based risk classification
- 24-hour, 7-day and 30-day views
- Hotspot and potential-hotspot thresholds
- City and hospital drill-down
- Historical capacity/trend data
- Designed to support future hospital/government data integrations

---

## 🧠 AI Symptom Assistant

The symptom assistant has a **local rule-based assessment layer** that works without an external AI service.

It evaluates submitted symptoms and produces:
- A general impression
- Priority/urgency
- Immediate self-care / first-aid guidance
- Red-flag warnings
- Recommended doctors
- Recommended specialties

The application also supports an **optional OpenAI integration**. If `OPENAI_API_KEY` is configured, the backend attempts to generate a more natural-language triage response through the OpenAI Responses API. If the API is unavailable or fails, MediBridge automatically falls back to its built-in assessment response.

> **Important:** This is a demonstration/hackathon system, not a medical diagnostic tool. AI output must not be treated as a substitute for professional medical advice.

---

## 🏗️ Technology Stack

| Layer | Technology |
|---|---|
| Backend | Python |
| Web Framework | Flask 3.1.2 |
| Database | SQLite |
| Authentication | Flask sessions + Werkzeug password hashing |
| Frontend | HTML, CSS, JavaScript |
| API | Flask JSON endpoints |
| AI | Built-in rule-based triage + optional OpenAI Responses API |
| Payments | Demo UPI flow |
| NFC | UID-based simulation/integration workflow |
| RFID | Package-tag simulation/workflow |
| Maps | Frontend map-related configuration/visualization support |
| Runtime | Python 3.11+ recommended |

The repository intentionally keeps the MVP lightweight: the application has **no frontend framework build step** and requires only two Python packages from `requirements.txt`.

---

## 📁 Project Structure

```text
MediBridge/
│
├── mvp_city/
│   ├── app1.py
│   ├── requirements.txt
│   │
│   ├── templates/
│   │   ├── index.html
│   │   ├── login.html
│   │   ├── admin_login.html
│   │   └── admin.html
│   │
│   └── static/
│       ├── diagnostics.svg
│       ├── care.svg
│       ├── payment.svg
│       └── connect.svg
│
├── START_MEDIBRIDGE.bat
└── README.md
```

### Database

On first application startup, MediBridge creates:

```text
mvp_city/medibridge.db
```

The SQLite database is automatically initialized and populated with demo data.

The database contains tables for major application domains including:
- Users
- Doctors
- Appointments
- Appointment payments
- Doctor availability
- Symptom sessions
- Prescriptions
- Reminders
- Consultations
- Diagnostic tests/orders
- Pharmacy medicines/orders
- Delivery agents
- Hospital accounts
- Pandemic regions/history
- NFC cards/check-ins/logs
- RFID/package events

---

## 🚀 Quick Start — Windows

### Option 1: One-click startup

Double-click:

```text
START_MEDIBRIDGE.bat
```

The launcher:
1. Opens the project directory
2. Creates a local Python virtual environment if required
3. Installs dependencies
4. Starts the Flask server
5. Opens MediBridge in the browser

The default local URL is:

```text
http://127.0.0.1:5000
```

### Option 2: Manual startup

Open Command Prompt / PowerShell in the repository directory:

```bash
cd mvp_city
```

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it on Windows:

```bash
.venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Start the application:

```bash
python app1.py
```

Then open:

```text
http://127.0.0.1:5000
```

---

## 🔑 Demo Accounts

The application seeds demo accounts automatically.

### Patient

```text
Email: patient@medibridge.local
Password: aarav1
```

Second demo patient:

```text
Email: priya.singh@medibridge.local
Password: aarav1
```

### Doctors

```text
Email: doctor@medibridge.local
Password: doc1
```

```text
Email: arjun.nair@medibridge.local
Password: doc2
```

```text
Email: kavita.rao@medibridge.local
Password: doc3
```

```text
Email: rohan.verma@medibridge.local
Password: doc4
```

```text
Email: simran.kaur@medibridge.local
Password: doc5
```

### Admin

```text
Email: admin@medibridge.local
Password: admin123
```

### Delivery Agent

```text
Email: delivery@medibridge.local
Password: delivery123
```

### Hospital Partner

Hospital accounts use:

```text
Password: hospital123
```

Example:

```text
Email: citycare@medibridge.local
Password: hospital123
```

Other seeded hospital accounts include Fortis Mohali, Max Healthcare Chandigarh, Apollo Ludhiana, Ivy Hospital Jalandhar, and AIIMS Bathinda.

> **These credentials are intentionally hard-coded demo credentials for the hackathon MVP. Do not use them in production.**

---

## 🧪 Demo NFC UIDs

The seeded patients have demo NFC identifiers:

```text
Aarav Sharma
04:AA:BB:CC:DD:EE:01
```

```text
Priya Singh
04:AA:BB:CC:DD:EE:02
```

These can be used in the NFC simulator/admin workflow.

The MVP treats an NFC card primarily as an **identifier**. Clinical information remains in the MediBridge database rather than being stored directly on the card.

---

## 🔄 Recommended Demo Flow

For a hackathon presentation, the following sequence demonstrates the largest portion of the system:

### 1. Patient → Symptom Assessment

Log in as:

```text
patient@medibridge.local
```

Enter symptoms and submit the assessment.

Show:
- Triage result
- Priority
- First-aid guidance
- Red flags
- Recommended doctors/specialties

### 2. Patient → Doctor Discovery

Browse doctors and select a suitable clinician.

Show:
- Specialty
- Qualification
- Experience
- Hospital
- Consultation venue
- Available slots

### 3. Patient → Appointment

Select a slot.

The MVP uses a demo consultation fee of:

```text
₹200
```

Complete the simulated UPI payment flow and confirm the appointment.

### 4. Doctor → Consultation

Log in as the selected doctor.

Show:
- Appointment queue
- Token number
- Start consultation
- End consultation
- Prescription creation
- Consultation room workflow

### 5. Patient → Prescription & Reminders

Return to the patient portal and demonstrate:
- Prescription
- Medicine reminders
- Reminder completion

### 6. Patient → Pharmacy

Open the pharmacy workflow.

Demonstrate:
- Medicine catalogue
- Prescription-required medicine handling
- Order creation
- Order tracking

### 7. Admin → NFC

Open:

```text
/admin/login
```

Use the admin account and demonstrate:
- Patient NFC registration
- NFC check-in
- Pharmacy lookup
- Scan logs

Use:

```text
04:AA:BB:CC:DD:EE:01
```

for the seeded Aarav Sharma patient.

### 8. Delivery → RFID + OTP

Open the Delivery Agent portal.

Demonstrate:
1. Select an order
2. Scan/verify its RFID package tag
3. Complete OTP verification
4. Confirm delivery

### 9. Hospital → Pandemic Intelligence

Log in through the hospital portal.

Update aggregate:
- Total beds
- Occupied beds

Then open the Admin Pandemic Intelligence dashboard and demonstrate how capacity data contributes to regional risk classification.

---

## 🔌 Optional OpenAI Configuration

The application can run without an OpenAI API key.

To enable the optional enhanced natural-language symptom response, set:

### Windows Command Prompt

```bat
set OPENAI_API_KEY=your_api_key_here
```

Optional model override:

```bat
set OPENAI_MODEL=gpt-4.1-mini
```

Then start the application.

The default model configured by the application is:

```text
gpt-4.1-mini
```

If no API key is supplied, MediBridge continues using its built-in assessment logic.

> Never commit a real API key to GitHub. Use environment variables or a secret-management system.

---

## ⚙️ Environment Variables

| Variable | Purpose | Default |
|---|---|---|
| `MEDIBRIDGE_SECRET` | Flask session secret | Demo fallback value |
| `MEDIBRIDGE_UPI_ID` | Demo UPI identifier | `medibridge@upi` |
| `OPENAI_API_KEY` | Optional AI enhancement | Not set |
| `OPENAI_MODEL` | Optional OpenAI model | `gpt-4.1-mini` |

For a real deployment, all secrets and credentials should be replaced with secure environment-based configuration.

---

## 🌐 Important Routes

### Main Portals

| Route | Purpose |
|---|---|
| `/` | Main MediBridge application |
| `/login` | Patient / Doctor login |
| `/hospital/login` | Hospital Partner login |
| `/admin/login` | Admin login |
| `/delivery/login` | Delivery Agent login |
| `/hospital` | Hospital dashboard |
| `/admin` | Admin console |
| `/diagnostics` | Diagnostics interface |
| `/pharmacy` | Pharmacy interface |
| `/nfc` | NFC interface |
| `/join/<token>` | Consultation guest room |

### Major API Groups

```text
/api/analyse
/api/doctors
/api/appointment-slots
/api/doctor/schedule
/api/payments/*
/api/appointments/*
/api/prescriptions
/api/reminders/*
/api/consultations/*
/api/diagnostics/*
/api/pharmacy/*
/api/delivery/*
/api/hospitals
/api/pandemic/*
/api/nfc/*
/api/admin/*
```

---

## 🔐 Security Notes

This repository is a **hackathon MVP**, not a production healthcare system.

Before production deployment, the following must be addressed:

- Replace all demo credentials
- Replace the fallback Flask secret key
- Use HTTPS/TLS
- Add robust CSRF protection
- Add rate limiting and brute-force protection
- Use secure cookie configuration
- Add stronger session management
- Implement role-based authorization consistently across every endpoint
- Validate and sanitize all user input
- Use production-grade database infrastructure
- Encrypt sensitive healthcare data at rest and in transit
- Implement proper audit logging
- Add consent and data-retention controls
- Secure payment integration through a real payment provider
- Integrate real NFC/RFID hardware securely
- Add secure secret management
- Add proper backup/recovery procedures
- Perform penetration testing and dependency/security audits
- Ensure compliance with applicable healthcare and privacy regulations

---

## ⚠️ Medical Safety Disclaimer

MediBridge is a **prototype created for demonstration and hackathon purposes**.

The symptom assistant provides informational triage and first-aid guidance. It is **not a medical diagnosis system** and should not be relied upon for emergency decisions, prescription decisions, or treatment without professional medical evaluation.

For real-world deployment, medical workflows and AI outputs would require clinical validation, appropriate safeguards, human oversight, and regulatory/privacy compliance.

---

## 💳 Payment Disclaimer

The current appointment payment system is a **demo UPI workflow**.

The application:
- Generates a UPI payment URI
- Displays the demo consultation fee
- Accepts a user-entered UTR/reference
- Marks the demo payment as paid

It does **not** provide verified bank-side payment confirmation.

A production implementation should use a certified payment gateway and verify payment status server-side.

---

## 🏥 Pandemic Intelligence Disclaimer

The pandemic/risk intelligence module is designed to demonstrate how **aggregate hospital capacity data** could be transformed into regional early-warning signals.

The current MVP uses seeded/demo hospital information and synthetic trend data where applicable.

It should not be interpreted as an actual epidemiological prediction system.

A production implementation would require validated public-health datasets, epidemiological models, data governance, and appropriate health-authority partnerships.

---

## 🧩 Architecture Overview

```text
                         ┌──────────────────────┐
                         │      MediBridge      │
                         │     Flask Server     │
                         └──────────┬───────────┘
                                    │
              ┌─────────────────────┼─────────────────────┐
              │                     │                     │
        ┌─────▼─────┐         ┌─────▼─────┐        ┌─────▼─────┐
        │  Patient  │         │  Doctor   │        │  Admin    │
        │  Portal   │         │  Portal   │        │  Console  │
        └─────┬─────┘         └─────┬─────┘        └─────┬─────┘
              │                     │                     │
              └─────────────────────┼─────────────────────┘
                                    │
                         ┌──────────▼──────────┐
                         │      SQLite DB      │
                         │ Users / Appointments│
                         │ Pharmacy / Hospital │
                         │ NFC / RFID / Logs   │
                         └──────────┬──────────┘
                                    │
                 ┌──────────────────┼──────────────────┐
                 │                  │                  │
          ┌──────▼──────┐    ┌──────▼──────┐    ┌──────▼──────┐
          │   Hospital  │    │  Pharmacy   │    │  Delivery   │
          │   Portal    │    │  Workflow   │    │   Portal    │
          └──────┬──────┘    └─────────────┘    └──────┬──────┘
                 │                                      │
                 ▼                                      ▼
        Capacity / Risk Engine                    RFID + OTP
```

---

## 🛠️ Future Roadmap

### Phase 1 — MVP
- [x] Patient portal
- [x] Doctor portal
- [x] Admin portal
- [x] Hospital portal
- [x] Delivery portal
- [x] Symptom assistant
- [x] Appointments
- [x] Prescriptions
- [x] Reminders
- [x] Pharmacy
- [x] NFC workflow
- [x] RFID/OTP delivery workflow
- [x] Hospital capacity intelligence

### Phase 2 — Real Integrations
- [ ] Real NFC reader integration
- [ ] Real RFID hardware integration
- [ ] Production payment gateway
- [ ] Real video consultation infrastructure
- [ ] Real map/hospital APIs
- [ ] Hospital information-system integration
- [ ] Government/public-health data feeds
- [ ] Production notification service

### Phase 3 — Production Platform
- [ ] PostgreSQL / managed database
- [ ] Secure cloud deployment
- [ ] Containerization
- [ ] CI/CD
- [ ] Observability and monitoring
- [ ] Automated backups
- [ ] Strong RBAC and audit trails
- [ ] Security testing
- [ ] Clinical validation
- [ ] Privacy and regulatory compliance

---

## 🤝 Contributing

Contributions are welcome.

A typical development workflow:

```bash
git clone <your-repository-url>
cd <repository-name>
```

Create and activate a virtual environment:

```bash
python -m venv .venv
.venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r mvp_city/requirements.txt
```

Run the application:

```bash
cd mvp_city
python app1.py
```

Create a feature branch:

```bash
git checkout -b feature/your-feature
```

Make your changes, test the complete workflow, and open a pull request.

---

## 📜 License

No license has been specified for this MVP repository yet.

If this project is intended to be publicly reused or modified, add an appropriate license file such as `MIT`, `Apache-2.0`, or another license selected by the project owners.

---

## 👥 Team

**MediBridge — Cosmicathon 2026**

- Arjan Mittal
- Jival Sharma
- Kushaagra Mediratta
- Ishkaram Singh Gulati

---

## ⭐ Project Vision

> **MediBridge aims to bridge the gap between patients, doctors, hospitals, pharmacies, and healthcare operations through one connected digital healthcare ecosystem.**

Built as a hackathon MVP with a focus on **accessible care, connected workflows, intelligent assistance, and scalable healthcare coordination**.
