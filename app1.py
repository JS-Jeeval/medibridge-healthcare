from flask import Flask, render_template, render_template_string, request, jsonify, redirect, url_for, session
import sqlite3, os, json, secrets, socket, urllib.request, urllib.error
from datetime import datetime, date, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "medibridge.db")
app = Flask(__name__)
app.secret_key = os.environ.get("MEDIBRIDGE_SECRET", "hackathon-demo-secret-change-me")
UPI_ID = os.environ.get("MEDIBRIDGE_UPI_ID", "medibridge@upi")
CONSULTATION_FEE = 200.0
MINIMAL_PORTAL_CSS = """body{background:#f7f8f8!important;color:#111827!important} .wrap,.box,.panel,.shell,.app-shell{filter:none!important} .card,.box,.panel,.section,.product,.order,.table-wrap{border:1px solid #e5e7eb!important;border-radius:16px!important;box-shadow:0 8px 30px rgba(17,24,39,.05)!important} button,.btn{background:#0f9f8c!important;border-radius:11px!important;box-shadow:none!important} .secondary{background:#f3f4f6!important;color:#374151!important} input,select,textarea{border-color:#e5e7eb!important;border-radius:11px!important;background:#fff!important} a{color:#0b7568} h1,h2,h3{letter-spacing:-.3px} .muted{color:#6b7280!important}"""


def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_column(conn, table, column, definition):
    cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db():
    conn = db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('patient','doctor')), created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS admin_users(
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS doctors(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL UNIQUE,
        specialty TEXT NOT NULL, bio TEXT DEFAULT '',
        venue TEXT DEFAULT 'CityCare Hospital • Room 204',
        emergency_phone TEXT DEFAULT '',
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS appointments(
        id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL,
        doctor_id INTEGER NOT NULL, appointment_time TEXT NOT NULL,
        venue TEXT DEFAULT '', token_number INTEGER, status TEXT NOT NULL DEFAULT 'confirmed',
        notes TEXT DEFAULT '', started_at TEXT DEFAULT '', ended_at TEXT DEFAULT '', video_room TEXT DEFAULT '', created_at TEXT NOT NULL,
        consultation_fee REAL NOT NULL DEFAULT 200.0,
        FOREIGN KEY(patient_id) REFERENCES users(id), FOREIGN KEY(doctor_id) REFERENCES doctors(id)
    );
    CREATE TABLE IF NOT EXISTS appointment_payments(
        id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL,
        doctor_id INTEGER NOT NULL, appointment_time TEXT NOT NULL, amount REAL NOT NULL DEFAULT 200.0,
        method TEXT NOT NULL DEFAULT 'UPI', upi_id TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'pending', utr TEXT DEFAULT '',
        created_at TEXT NOT NULL, paid_at TEXT DEFAULT '',
        FOREIGN KEY(patient_id) REFERENCES users(id), FOREIGN KEY(doctor_id) REFERENCES doctors(id)
    );
    CREATE TABLE IF NOT EXISTS symptom_sessions(
        id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL,
        symptoms TEXT NOT NULL, duration TEXT NOT NULL, extra TEXT DEFAULT '',
        ai_response TEXT NOT NULL, created_at TEXT NOT NULL,
        FOREIGN KEY(patient_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS prescriptions(
        id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL,
        doctor_id INTEGER NOT NULL, diagnosis TEXT DEFAULT '', notes TEXT DEFAULT '',
        status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL,
        FOREIGN KEY(patient_id) REFERENCES users(id), FOREIGN KEY(doctor_id) REFERENCES doctors(id)
    );
    CREATE TABLE IF NOT EXISTS prescription_items(
        id INTEGER PRIMARY KEY AUTOINCREMENT, prescription_id INTEGER NOT NULL,
        medicine TEXT NOT NULL, dosage TEXT NOT NULL, frequency TEXT NOT NULL, duration TEXT NOT NULL,
        FOREIGN KEY(prescription_id) REFERENCES prescriptions(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS reminders(
        id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL,
        prescription_item_id INTEGER NOT NULL, reminder_time TEXT NOT NULL,
        taken INTEGER NOT NULL DEFAULT 0, reminder_date TEXT NOT NULL,
        FOREIGN KEY(patient_id) REFERENCES users(id), FOREIGN KEY(prescription_item_id) REFERENCES prescription_items(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS doctor_slots(
        id INTEGER PRIMARY KEY AUTOINCREMENT, doctor_id INTEGER NOT NULL,
        appointment_time TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'available',
        UNIQUE(doctor_id, appointment_time),
        FOREIGN KEY(doctor_id) REFERENCES doctors(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS pharmacy_medicines(
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT 'General', description TEXT DEFAULT '',
        price REAL NOT NULL DEFAULT 0, stock INTEGER NOT NULL DEFAULT 0,
        requires_prescription INTEGER NOT NULL DEFAULT 0, image_url TEXT DEFAULT '',
        active INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS medicine_orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL,
        total_amount REAL NOT NULL DEFAULT 0, delivery_address TEXT NOT NULL,
        phone TEXT DEFAULT '', payment_method TEXT NOT NULL DEFAULT 'Cash on Delivery',
        status TEXT NOT NULL DEFAULT 'placed', placed_at TEXT NOT NULL,
        FOREIGN KEY(patient_id) REFERENCES users(id)
    );
    CREATE TABLE IF NOT EXISTS medicine_order_items(
        id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL,
        medicine_id INTEGER NOT NULL, medicine_name TEXT NOT NULL,
        quantity INTEGER NOT NULL, unit_price REAL NOT NULL,
        FOREIGN KEY(order_id) REFERENCES medicine_orders(id) ON DELETE CASCADE,
        FOREIGN KEY(medicine_id) REFERENCES pharmacy_medicines(id)
    );
    CREATE TABLE IF NOT EXISTS delivery_tracking(
        id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL UNIQUE,
        courier_name TEXT DEFAULT 'MediBridge Delivery', tracking_code TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Order placed', eta TEXT DEFAULT '',
        updated_at TEXT NOT NULL,
        FOREIGN KEY(order_id) REFERENCES medicine_orders(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS delivery_rfid(
        id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL UNIQUE,
        tag_uid TEXT NOT NULL,
        sealed_at TEXT NOT NULL,
        dispatch_scanned INTEGER NOT NULL DEFAULT 0, dispatch_scanned_at TEXT DEFAULT '',
        delivery_scanned INTEGER NOT NULL DEFAULT 0, delivery_scanned_at TEXT DEFAULT '',
        last_scan_result TEXT DEFAULT '',
        FOREIGN KEY(order_id) REFERENCES medicine_orders(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS rfid_scan_log(
        id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL,
        event TEXT NOT NULL, scanned_uid TEXT NOT NULL, result TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(order_id) REFERENCES medicine_orders(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS nfc_scan_log(
        id INTEGER PRIMARY KEY AUTOINCREMENT, uid TEXT NOT NULL, context TEXT NOT NULL,
        patient_id INTEGER, result TEXT NOT NULL, note TEXT DEFAULT '', created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS delivery_agents(
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
        phone TEXT DEFAULT '', created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS delivery_otp(
        id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL,
        otp_code TEXT NOT NULL, generated_at TEXT NOT NULL, expires_at TEXT NOT NULL,
        verified INTEGER NOT NULL DEFAULT 0, verified_at TEXT DEFAULT '',
        attempts INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY(order_id) REFERENCES medicine_orders(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS diagnostic_tests(
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, category TEXT NOT NULL DEFAULT 'General',
        description TEXT DEFAULT '', price REAL NOT NULL DEFAULT 0, turnaround TEXT DEFAULT '24 hours',
        home_collection INTEGER NOT NULL DEFAULT 1, active INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS diagnostic_orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL, test_id INTEGER NOT NULL,
        collection_type TEXT NOT NULL DEFAULT 'Home collection', collection_address TEXT DEFAULT '',
        preferred_date TEXT NOT NULL, preferred_time TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Booked',
        amount REAL NOT NULL DEFAULT 0, payment_method TEXT NOT NULL DEFAULT 'Pay at lab', created_at TEXT NOT NULL,
        FOREIGN KEY(patient_id) REFERENCES users(id), FOREIGN KEY(test_id) REFERENCES diagnostic_tests(id)
    );
    CREATE TABLE IF NOT EXISTS diagnostic_labs(
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, venue TEXT NOT NULL,
        capacity INTEGER NOT NULL DEFAULT 1, active INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS diagnostic_reservations(
        id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL UNIQUE, lab_id INTEGER NOT NULL,
        reservation_date TEXT NOT NULL, reservation_time TEXT NOT NULL, token_number INTEGER NOT NULL DEFAULT 1,
        status TEXT NOT NULL DEFAULT 'Reserved', created_at TEXT NOT NULL,
        FOREIGN KEY(order_id) REFERENCES diagnostic_orders(id) ON DELETE CASCADE,
        FOREIGN KEY(lab_id) REFERENCES diagnostic_labs(id)
    );
    CREATE TABLE IF NOT EXISTS pandemic_regions(
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
        state TEXT NOT NULL DEFAULT 'Punjab', city TEXT NOT NULL,
        lat REAL NOT NULL, lng REAL NOT NULL, total_beds INTEGER NOT NULL,
        occupied_beds INTEGER NOT NULL, history_json TEXT NOT NULL DEFAULT '[]',
        updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS hospital_accounts(
        id INTEGER PRIMARY KEY AUTOINCREMENT, hospital_name TEXT NOT NULL UNIQUE,
        email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, region TEXT NOT NULL,
        contact_person TEXT DEFAULT '', created_at TEXT NOT NULL
    );
    """)
    ensure_column(conn, "delivery_rfid", "agent_id", "INTEGER")
    # NFC Smart Patient Card: UID lives on the existing patient (users) row — it is only an
    # identifier used to look up the patient, never a place to store medical data. Check-in
    # state lives on the existing appointments row.
    ensure_column(conn, "users", "nfc_uid", "TEXT DEFAULT ''")
    ensure_column(conn, "appointments", "checked_in", "INTEGER NOT NULL DEFAULT 0")
    ensure_column(conn, "appointments", "checked_in_at", "TEXT DEFAULT ''")
    # Safe migration for older MediBridge databases.
    ensure_column(conn, "doctors", "venue", "TEXT DEFAULT 'CityCare Hospital • Room 204'")
    ensure_column(conn, "doctors", "emergency_phone", "TEXT DEFAULT ''")
    ensure_column(conn, "doctors", "qualification", "TEXT DEFAULT ''")
    ensure_column(conn, "doctors", "experience_years", "INTEGER DEFAULT 0")
    ensure_column(conn, "doctors", "hospitals", "TEXT DEFAULT ''")
    ensure_column(conn, "appointments", "venue", "TEXT DEFAULT ''")
    ensure_column(conn, "appointments", "token_number", "INTEGER")
    ensure_column(conn, "appointments", "started_at", "TEXT DEFAULT ''")
    ensure_column(conn, "appointments", "ended_at", "TEXT DEFAULT ''")
    ensure_column(conn, "appointments", "video_room", "TEXT DEFAULT ''")
    ensure_column(conn, "appointments", "guest_token", "TEXT DEFAULT ''")
    ensure_column(conn, "appointments", "consultation_fee", "REAL NOT NULL DEFAULT 200.0")
    ensure_column(conn, "appointments", "payment_id", "INTEGER")
    ensure_column(conn, "appointments", "payment_status", "TEXT NOT NULL DEFAULT 'pending'")
    ensure_column(conn, "appointments", "payment_method", "TEXT DEFAULT 'UPI'")
    ensure_column(conn, "hospital_accounts", "lat", "REAL DEFAULT 0")
    ensure_column(conn, "hospital_accounts", "lng", "REAL DEFAULT 0")
    ensure_column(conn, "hospital_accounts", "total_beds", "INTEGER DEFAULT 100")
    ensure_column(conn, "hospital_accounts", "occupied_beds", "INTEGER DEFAULT 50")
    ensure_column(conn, "hospital_accounts", "history_json", "TEXT DEFAULT '[]'")
    ensure_column(conn, "hospital_accounts", "updated_at", "TEXT DEFAULT ''")

    now = datetime.now().isoformat(timespec="seconds")
    if conn.execute("SELECT COUNT(*) c FROM diagnostic_labs").fetchone()["c"] == 0:
        conn.execute("INSERT INTO diagnostic_labs(name,venue,capacity) VALUES(?,?,?)", ("MediBridge Partner Lab", "CityCare Hospital · Diagnostics Wing", 1))

    if conn.execute("SELECT COUNT(*) c FROM diagnostic_tests").fetchone()["c"] == 0:
        tests = [
            ("Complete Blood Count (CBC)","Blood Test","Screens haemoglobin, white cells and platelets.",350,"24 hours"),
            ("Blood Glucose — Fasting","Diabetes","Fasting blood sugar test.",120,"Same day"),
            ("HbA1c","Diabetes","Average blood glucose over the previous 2–3 months.",450,"24 hours"),
            ("Lipid Profile","Heart Health","Cholesterol and triglyceride screening.",650,"24 hours"),
            ("Liver Function Test (LFT)","Organ Health","Common liver enzyme and protein panel.",700,"24 hours"),
            ("Thyroid Profile (T3/T4/TSH)","Hormones","Basic thyroid screening panel.",550,"24 hours"),
        ]
        conn.executemany("INSERT INTO diagnostic_tests(name,category,description,price,turnaround) VALUES(?,?,?,?,?)", tests)

    # Pandemic command-centre demo data. These are SYNTHETIC values for the hackathon MVP;
    # production deployment should replace them with signed hospital/government feeds.
    if conn.execute("SELECT COUNT(*) c FROM pandemic_regions").fetchone()["c"] == 0:
        regions = [
            ("Patiala","Punjab","Patiala",30.3398,76.3869,100,88),
            ("Ludhiana","Punjab","Ludhiana",30.9010,75.8573,140,105),
            ("Amritsar","Punjab","Amritsar",31.6340,74.8723,120,72),
            ("SAS Nagar / Mohali","Punjab","Mohali",30.7046,76.7179,110,79),
            ("Chandigarh","Chandigarh","Chandigarh",30.7333,76.7794,160,61),
            ("Bathinda","Punjab","Bathinda",30.2110,74.9455,90,48),
            ("Jalandhar","Punjab","Jalandhar",31.3260,75.5762,115,69),
        ]
        for name,state,city,lat,lng,beds,occupied in regions:
            hist=[]
            # Synthetic 30-day trajectory ending at the current occupancy.
            start=max(5,occupied-int(beds*.10))
            for d in range(30):
                frac=d/29 if d else 0
                val=round(start+(occupied-start)*frac + ((d%5)-2)*1.2)
                val=max(0,min(beds,val))
                hist.append({"days_ago":29-d,"occupied":val,"ts":(datetime.now()-timedelta(days=29-d)).isoformat(timespec="seconds")})
            conn.execute("INSERT INTO pandemic_regions(name,state,city,lat,lng,total_beds,occupied_beds,history_json,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                         (name,state,city,lat,lng,beds,occupied,json.dumps(hist),now))
    # Separate admin portal account: pharmacy operations and NFC (patient card) operations live here.
    if conn.execute("SELECT COUNT(*) c FROM admin_users").fetchone()["c"] == 0:
        conn.execute("INSERT INTO admin_users(name,email,password_hash,created_at) VALUES(?,?,?,?)",
                     ("MediBridge Admin", "admin@medibridge.local", generate_password_hash("admin123"), now))
    conn.execute("UPDATE admin_users SET password_hash=? WHERE email=?", (generate_password_hash("admin123"), "admin@medibridge.local"))
    # Demo delivery agent account for the standalone Delivery portal.
    if conn.execute("SELECT COUNT(*) c FROM delivery_agents").fetchone()["c"] == 0:
        conn.execute("INSERT INTO delivery_agents(name,email,password_hash,phone,created_at) VALUES(?,?,?,?,?)",
                     ("Ramesh Kumar", "delivery@medibridge.local", generate_password_hash("delivery123"), "9876543210", now))
    conn.execute("UPDATE delivery_agents SET password_hash=? WHERE email=?", (generate_password_hash("delivery123"), "delivery@medibridge.local"))
    DEMO_CARD_PATIENT = "04:AA:BB:CC:DD:EE:01"   # demo patient's NFC card UID — used by the /nfc simulator out of the box
    DEMO_CARD_PATIENT2 = "04:AA:BB:CC:DD:EE:02"
    if conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"] == 0:
        ph = generate_password_hash("aarav1")
        conn.execute("INSERT INTO users(name,email,password_hash,role,nfc_uid,created_at) VALUES(?,?,?,?,?,?)",
                     ("Aarav Sharma", "patient@medibridge.local", ph, "patient", DEMO_CARD_PATIENT, now))
        conn.execute("INSERT INTO users(name,email,password_hash,role,nfc_uid,created_at) VALUES(?,?,?,?,?,?)",
                     ("Priya Singh", "priya.singh@medibridge.local", ph, "patient", DEMO_CARD_PATIENT2, now))
        DOCTOR_SEED = [
            ("Dr. Meera Sharma", "doctor@medibridge.local", "doc1", "General Medicine",
             "Primary care and general medical consultation.",
             "MBBS, MD (General Medicine)", 10, "CityCare Hospital (2016–present) · Fortis Hospital (2013–2016)",
             "CityCare Hospital • Room 204"),
            ("Dr. Arjun Nair", "arjun.nair@medibridge.local", "doc2", "Cardiologist (Heart)",
             "Heart health, blood pressure and cardiac consultation.",
             "MBBS, MD, DM (Cardiology)", 14, "Apollo Hospital (2018–present) · AIIMS Delhi (2011–2018)",
             "CityCare Hospital • Room 108"),
            ("Dr. Kavita Rao", "kavita.rao@medibridge.local", "doc3", "Neurologist (Brain)",
             "Headaches, nerve and brain-related conditions.",
             "MBBS, MD, DM (Neurology)", 11, "Max Healthcare (2019–present) · Manipal Hospital (2014–2019)",
             "CityCare Hospital • Room 305"),
            ("Dr. Rohan Verma", "rohan.verma@medibridge.local", "doc4", "Orthopedic (Bones)",
             "Bone, joint, fracture and sports-injury care.",
             "MBBS, MS (Orthopaedics)", 9, "Fortis Hospital (2020–present) · Medanta Hospital (2016–2020)",
             "CityCare Hospital • Room 112"),
            ("Dr. Simran Kaur", "simran.kaur@medibridge.local", "doc5", "Dentist",
             "Dental checkups, cavities and oral surgery.",
             "BDS, MDS (Dental Surgery)", 7, "Clove Dental (2021–present) · Apollo White Dental (2018–2021)",
             "CityCare Hospital • Room 210"),
        ]
        for name, email, doctor_password, specialty, bio, qualification, exp_years, hospitals, venue in DOCTOR_SEED:
            conn.execute("INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",
                         (name, email, generate_password_hash(doctor_password), "doctor", now))
            duser = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()["id"]
            conn.execute("""INSERT INTO doctors(user_id,specialty,bio,venue,emergency_phone,qualification,experience_years,hospitals)
                            VALUES(?,?,?,?,?,?,?,?)""",
                         (duser, specialty, bio, venue, "", qualification, exp_years, hospitals))
        # Demo appointment for today so the NFC check-in simulator has something to find immediately.
        patient_id = conn.execute("SELECT id FROM users WHERE email='patient@medibridge.local'").fetchone()["id"]
        gp = conn.execute("SELECT id,venue FROM doctors WHERE user_id=(SELECT id FROM users WHERE email='doctor@medibridge.local')").fetchone()
        today_slot = date.today().isoformat() + "T11:00"
        conn.execute("""INSERT INTO appointments(patient_id,doctor_id,appointment_time,venue,token_number,status,created_at)
                        VALUES(?,?,?,?,?, 'confirmed', ?)""", (patient_id, gp["id"], today_slot, gp["venue"], 1, now))
    else:
        # Populate venue for older records.
        conn.execute("UPDATE doctors SET venue='CityCare Hospital • Room 204' WHERE venue IS NULL OR venue=''")
        # Back-fill a demo NFC card on the seeded patient for existing databases (safe no-op if already set).
        conn.execute("UPDATE users SET nfc_uid=? WHERE email='patient@medibridge.local' AND (nfc_uid IS NULL OR nfc_uid='')",
                     (DEMO_CARD_PATIENT,))
    if conn.execute("SELECT COUNT(*) c FROM pharmacy_medicines").fetchone()["c"] == 0:
        conn.executemany(
            "INSERT INTO pharmacy_medicines(name,category,description,price,stock,requires_prescription) VALUES(?,?,?,?,?,?)",
            [
                ("Paracetamol 500 mg","Pain & Fever","OTC pain/fever relief. Follow the pack label.",30.0,100,0),
                ("ORS Sachets","Hydration","Oral rehydration salts for fluid replacement.",20.0,100,0),
                ("Antacid Tablets","Digestive Care","For occasional acidity/heartburn relief.",45.0,60,0),
                ("Vitamin C Tablets","Vitamins","Demo wellness product.",80.0,50,0),
                ("Amoxicillin 500 mg","Prescription","Antibiotic — prescription verification required.",120.0,20,1),
                ("MediBridge Sanitizer 50 ml","Hygiene","Optional sanitizer add-on with medicine orders.",5.0,500,0)
            ])
    conn.execute("UPDATE pharmacy_medicines SET name=?, description=? WHERE name=?",("Amoxicillin 500 mg","Antibiotic — prescription verification required.","Prescription Medicine"))
    # Ensure optional sanitizer exists even when upgrading an older demo database.
    conn.execute("INSERT OR IGNORE INTO pharmacy_medicines(name,category,description,price,stock,requires_prescription,active) VALUES(?,?,?,?,?,?,1)", ("MediBridge Sanitizer 50 ml","Hygiene","Optional sanitizer add-on with medicine orders.",5.0,500,0))
    # Reset demo credentials on every startup so all seeded doctors can log in.
    conn.execute("UPDATE users SET password_hash=? WHERE role='patient'", (generate_password_hash("aarav1"),))
    for email, pwd in [("doctor@medibridge.local","doc1"),("arjun.nair@medibridge.local","doc2"),("kavita.rao@medibridge.local","doc3"),("rohan.verma@medibridge.local","doc4"),("simran.kaur@medibridge.local","doc5")]:
        conn.execute("UPDATE users SET password_hash=? WHERE email=?", (generate_password_hash(pwd), email))
    # Legacy appointments from the previous MVP were already booked without a payment step.
    # Mark them paid and attach a demo payment record so the upgrade does not break existing demos.
    conn.execute("UPDATE appointments SET payment_status='paid', payment_method='UPI' WHERE payment_status IS NULL OR payment_status='pending'")
    legacy = conn.execute("SELECT a.id,a.patient_id,a.doctor_id,a.appointment_time,a.consultation_fee FROM appointments a LEFT JOIN appointment_payments p ON p.id=a.payment_id WHERE a.payment_status='paid' AND p.id IS NULL").fetchall()
    for a in legacy:
        conn.execute("INSERT INTO appointment_payments(patient_id,doctor_id,appointment_time,amount,method,upi_id,status,utr,created_at,paid_at) VALUES(?,?,?,?,?,'','paid','LEGACY-DEMO',?,?)", (a['patient_id'],a['doctor_id'],a['appointment_time'],a['consultation_fee'] or CONSULTATION_FEE,'UPI',now,now))
        pid=conn.execute("SELECT last_insert_rowid() id").fetchone()['id']
        conn.execute("UPDATE appointments SET payment_id=? WHERE id=?",(pid,a['id']))
    ensure_doctor_library(conn, now)
    ensure_hospital_accounts(conn, now)
    conn.commit(); conn.close()



# ---------------- Chipless RFID + doorstep OTP delivery verification ----------------
# No physical reader here — this simulates the workflow the real system uses: a chipless
# RFID code (a unique pattern PRINTED on the package label at packing time — no embedded
# chip) is bound to the order, "scanned" once at courier hand-off (dispatch), and scanned
# again by the delivery agent's handheld scanner at the customer's doorstep. A tag match
# alone does NOT mark the order Delivered — it only unlocks a 6-digit OTP that is issued to
# the CUSTOMER's own MediBridge app. The delivery agent must then get that OTP from the
# customer and enter it (within a 2-minute window) on the Delivery portal before the order
# is confirmed Delivered. This keeps possession of the OTP itself off the agent's device.
OTP_VALIDITY_SECONDS = 120

def gen_tag_uid():
    # Printed chipless-RFID pattern code, e.g. RFID-8F3A9C21 — not a chip UID.
    return "RFID-" + secrets.token_hex(4).upper()

def gen_otp():
    return f"{secrets.randbelow(1000000):06d}"

def get_or_seal_tag(conn, order_id):
    row = conn.execute("SELECT * FROM delivery_rfid WHERE order_id=?", (order_id,)).fetchone()
    if row: return row
    now = datetime.now().isoformat(timespec="seconds")
    uid = gen_tag_uid()
    conn.execute("""INSERT INTO delivery_rfid(order_id,tag_uid,sealed_at) VALUES(?,?,?)""", (order_id, uid, now))
    conn.execute("""INSERT INTO rfid_scan_log(order_id,event,scanned_uid,result,created_at)
                    VALUES(?,?,?,?,?)""", (order_id, "seal", uid, "sealed", now))
    return conn.execute("SELECT * FROM delivery_rfid WHERE order_id=?", (order_id,)).fetchone()

def mark_dispatch_scan(conn, order_id):
    tag = get_or_seal_tag(conn, order_id)
    if tag["dispatch_scanned"]: return tag
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute("UPDATE delivery_rfid SET dispatch_scanned=1,dispatch_scanned_at=? WHERE order_id=?", (now, order_id))
    conn.execute("""INSERT INTO rfid_scan_log(order_id,event,scanned_uid,result,created_at)
                    VALUES(?,?,?,?,?)""", (order_id, "dispatch", tag["tag_uid"], "match", now))
    return conn.execute("SELECT * FROM delivery_rfid WHERE order_id=?", (order_id,)).fetchone()

def rfid_payload(tag):
    if not tag: return None
    x = dict(tag)
    return x

def active_otp(conn, order_id):
    """Most recent OTP row issued for this order, if any."""
    return conn.execute("SELECT * FROM delivery_otp WHERE order_id=? ORDER BY id DESC LIMIT 1", (order_id,)).fetchone()

def otp_is_live(otp_row):
    if not otp_row or otp_row["verified"]: return False
    return datetime.now() <= datetime.fromisoformat(otp_row["expires_at"])

def issue_delivery_otp(conn, order_id):
    """Called only after a successful chipless-RFID tag match at the doorstep."""
    now = datetime.now()
    code = gen_otp()
    expires = (now + timedelta(seconds=OTP_VALIDITY_SECONDS)).isoformat(timespec="seconds")
    conn.execute("INSERT INTO delivery_otp(order_id,otp_code,generated_at,expires_at) VALUES(?,?,?,?)",
                 (order_id, code, now.isoformat(timespec="seconds"), expires))
    conn.execute("""INSERT INTO rfid_scan_log(order_id,event,scanned_uid,result,created_at)
                    VALUES(?,?,?,?,?)""", (order_id, "otp_issued", "******", "sent_to_customer", now.isoformat(timespec="seconds")))
    return conn.execute("SELECT * FROM delivery_otp WHERE order_id=? ORDER BY id DESC LIMIT 1", (order_id,)).fetchone()


# ---------------- NFC Smart Patient Card ----------------
# One shared code path resolves a scanned UID to a patient — a real hardware reader and the
# on-screen simulator both end up calling exactly this. The UID is only ever used as a lookup
# key into the existing patient/appointment/prescription/order tables; nothing clinical is
# ever written to or read from the card itself.
def norm_uid(uid):
    return (uid or "").strip().upper()

def find_patient_by_uid(conn, uid):
    uid = norm_uid(uid)
    if not uid: return None
    return conn.execute("SELECT * FROM users WHERE role='patient' AND nfc_uid=?", (uid,)).fetchone()

def log_nfc_scan(conn, uid, context, patient_id, result, note=""):
    conn.execute("""INSERT INTO nfc_scan_log(uid,context,patient_id,result,note,created_at)
                    VALUES(?,?,?,?,?,?)""",
                 (norm_uid(uid), context, patient_id, result, note, datetime.now().isoformat(timespec="seconds")))

def patient_public(u):
    return {"id": u["id"], "name": u["name"], "email": u["email"], "nfc_uid": u["nfc_uid"]}




def ensure_doctor_library(conn, now):
    """Expand the demo doctor network without disturbing existing accounts."""
    library = [
        ("Dr. Nisha Kapoor","nisha.kapoor@medibridge.local","ent1","ENT Specialist","Ear, nose and throat care including sinus, throat, ear pain and voice complaints.","MBBS, MS (ENT)",12,"Fortis Hospital · Max Hospital","Fortis Hospital • ENT 204"),
        ("Dr. Vivek Sethi","vivek.sethi@medibridge.local","ent2","ENT Specialist","ENT consultation for sore throat, sinus congestion, ear blockage and hearing concerns.","MBBS, DLO, MS (ENT)",9,"Apollo Hospitals · Ivy Hospital","Apollo Hospital • ENT 3"),
        ("Dr. Ritu Malhotra","ritu.malhotra@medibridge.local","ent3","ENT Specialist","Pediatric and adult ENT, allergies, tonsils and recurrent sinus problems.","MBBS, MS (ENT)",15,"Max Healthcare · Fortis Hospital","Max Healthcare • ENT 12"),
        ("Dr. Karan Bedi","karan.bedi@medibridge.local","ent4","ENT Specialist","Voice, throat, ear infections and balance-related ENT care.","MBBS, MS (ENT)",8,"DMC Hospital · Fortis Hospital","DMC Hospital • ENT 7"),
        ("Dr. Aditi Mehra","aditi.mehra@medibridge.local","physio1","Physiotherapist","Musculoskeletal rehabilitation, back pain, posture and mobility recovery.","BPT, MPT (Orthopaedics)",8,"Fortis Hospital · SPS Hospital","Fortis Hospital • Rehab 101"),
        ("Dr. Rahul Chawla","rahul.chawla@medibridge.local","physio2","Physiotherapist","Sports injuries, joint stiffness, muscle pain and rehabilitation plans.","BPT, MPT (Sports)",11,"Apollo Hospitals · Ivy Hospital","Apollo Hospital • Rehab 6"),
        ("Dr. Simran Gill","simran.gill@medibridge.local","physio3","Physiotherapist","Neck pain, shoulder pain, arthritis support and functional rehabilitation.","BPT, MPT (Neuro)",7,"Max Healthcare · Manipal Hospital","Max Healthcare • Rehab 14"),
        ("Dr. Manav Arora","manav.arora@medibridge.local","physio4","Physiotherapist","Post-operative and neurological rehabilitation, mobility and gait training.","BPT, MPT (Neuro)",13,"AIIMS Bathinda · Fortis Hospital","AIIMS Bathinda • Rehab 2"),
        ("Dr. Pooja Bansal","pooja.bansal@medibridge.local","derm1","Dermatologist","Acne, rashes, allergies and common skin conditions.","MBBS, MD (Dermatology)",10,"Fortis Hospital · Max Hospital","Fortis Hospital • Skin 11"),
        ("Dr. Sameer Joshi","sameer.joshi@medibridge.local","pulmo1","Pulmonologist","Cough, breathing complaints, asthma and respiratory assessment.","MBBS, MD, DM (Pulmonary Medicine)",16,"Apollo Hospitals · Fortis Hospital","Apollo Hospital • Pulmonary 8"),
        ("Dr. Neha Suri","neha.suri@medibridge.local","gastro1","Gastroenterologist","Stomach pain, nausea, vomiting, reflux and digestive disorders.","MBBS, MD, DM (Gastroenterology)",13,"Max Healthcare · Fortis Hospital","Max Healthcare • GI 4"),
        ("Dr. Harpreet Singh","harpreet.singh@medibridge.local","peds1","Pediatrician","Fever, cough, infections and general child health.","MBBS, MD (Pediatrics)",14,"Fortis Hospital · Ivy Hospital","Ivy Hospital • Pediatrics 9"),
        ("Dr. Ananya Rao","ananya.rao@medibridge.local","gyne1","Gynecologist","Women's health, menstrual concerns and routine gynecology.","MBBS, MS (OBGYN)",12,"Max Healthcare · Apollo Hospitals","Max Healthcare • Women 5"),
        ("Dr. Dev Khanna","dev.khanna@medibridge.local","gen2","General Medicine","Fever, fatigue, infections and common adult health complaints.","MBBS, MD (Medicine)",12,"Fortis Hospital · CityCare Hospital","CityCare Hospital • Room 116"),
        ("Dr. Isha Verma","isha.verma@medibridge.local","gen3","General Medicine","General primary care, preventive health and common acute symptoms.","MBBS, MD (Medicine)",7,"Ivy Hospital · CityCare Hospital","Ivy Hospital • Room 208"),
        ("Dr. Mohit Tandon","mohit.tandon@medibridge.local","ortho2","Orthopedic (Bones)","Back pain, joint pain, sports injuries and mobility concerns.","MBBS, MS (Orthopaedics)",15,"Max Healthcare · Fortis Hospital","Max Healthcare • Ortho 18"),
        ("Dr. Priyanka Shah","priyanka.shah@medibridge.local","card2","Cardiologist (Heart)","Blood pressure, palpitations and heart-health consultation.","MBBS, MD, DM (Cardiology)",13,"Apollo Hospitals · Fortis Hospital","Apollo Hospital • Cardiology 4"),
        ("Dr. Adil Khan","adil.khan@medibridge.local","neuro2","Neurologist (Brain)","Headache, dizziness, nerve symptoms and neurological assessment.","MBBS, MD, DM (Neurology)",10,"Max Healthcare · DMC Hospital","Max Healthcare • Neuro 6"),
        ("Dr. Rhea Anand","rhea.anand@medibridge.local","dent2","Dentist","Dental pain, cavities, gum problems and oral health.","BDS, MDS","9","Clove Dental · Apollo White Dental","Clove Dental • Clinic 8"),
        ("Dr. Tarun Mehta","tarun.mehta@medibridge.local","dent3","Dentist","Dental checkups, wisdom teeth and restorative dental care.","BDS, MDS","11","Apollo White Dental · Fortis Dental","Apollo White Dental • Clinic 4"),
    ]
    for name,email,pwd,specialty,bio,qual,exp,hospitals,venue in library:
        if conn.execute("SELECT 1 FROM users WHERE email=?",(email,)).fetchone():
            continue
        conn.execute("INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",(name,email,generate_password_hash(pwd),"doctor",now))
        uid=conn.execute("SELECT id FROM users WHERE email=?",(email,)).fetchone()["id"]
        conn.execute("INSERT INTO doctors(user_id,specialty,bio,venue,emergency_phone,qualification,experience_years,hospitals) VALUES(?,?,?,?,?,?,?,?)",(uid,specialty,bio,venue,"",qual,int(exp),hospitals))


def ensure_hospital_accounts(conn, now):
    hospitals=[
      ("CityCare Hospital","citycare@medibridge.local","hospital123","Patiala","Dr. Meera Khanna",30.3398,76.3869,100,88),
      ("Fortis Hospital Mohali","fortis.mohali@medibridge.local","hospital123","SAS Nagar / Mohali","Operations Desk",30.7046,76.7179,110,79),
      ("Max Healthcare Chandigarh","max.chd@medibridge.local","hospital123","Chandigarh","Bed Management Desk",30.7333,76.7794,160,61),
      ("Apollo Hospital Ludhiana","apollo.ludhiana@medibridge.local","hospital123","Ludhiana","Hospital Operations",30.9010,75.8573,140,105),
      ("Ivy Hospital Jalandhar","ivy.jalandhar@medibridge.local","hospital123","Jalandhar","Capacity Desk",31.3260,75.5762,115,69),
      ("Fortis Amritsar","fortis.amritsar@medibridge.local","hospital123","Amritsar","Capacity Desk",31.6340,74.8723,120,72),
      ("AIIMS Bathinda","aiims.bathinda@medibridge.local","hospital123","Bathinda","Capacity Desk",30.2110,74.9455,90,48),
    ]
    for h,email,pwd,region,contact,lat,lng,beds,occupied in hospitals:
        row=conn.execute("SELECT id FROM hospital_accounts WHERE email=?",(email,)).fetchone()
        if not row:
            conn.execute("INSERT INTO hospital_accounts(hospital_name,email,password_hash,region,contact_person,created_at,lat,lng,total_beds,occupied_beds,history_json,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(h,email,generate_password_hash(pwd),region,contact,now,lat,lng,beds,occupied,json.dumps([]),now))
        else:
            conn.execute("UPDATE hospital_accounts SET password_hash=?,lat=?,lng=?,total_beds=CASE WHEN total_beds IS NULL OR total_beds=0 THEN ? ELSE total_beds END,occupied_beds=CASE WHEN occupied_beds IS NULL THEN ? ELSE occupied_beds END,updated_at=? WHERE email=?",(generate_password_hash(pwd),lat,lng,beds,occupied,now,email))

def current_user():
    if "user_id" not in session: return None
    conn = db(); u = conn.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone(); conn.close()
    return u

def current_admin():
    if "admin_id" not in session: return None
    conn=db(); a=conn.execute("SELECT * FROM admin_users WHERE id=?",(session["admin_id"],)).fetchone(); conn.close(); return a

def current_agent():
    if "agent_id" not in session: return None
    conn=db(); ag=conn.execute("SELECT * FROM delivery_agents WHERE id=?",(session["agent_id"],)).fetchone(); conn.close(); return ag


def ai_assess(symptoms, duration, extra):
    """Rule-based demo decision support with distinct, symptom-specific guidance.
    It deliberately avoids autonomous diagnosis/prescribing and gives general OTC information only.
    """
    s = {x.strip().lower() for x in symptoms}
    red_flags = ["Difficulty breathing or severe chest pain", "Fainting, confusion, seizure, or sudden severe weakness", "Severe or rapidly worsening symptoms", "Heavy/uncontrolled bleeding or a serious allergic reaction"]
    impression = "Your symptoms can have several causes. The pattern below is meant to help you decide what to discuss with a clinician."
    questions = ["When did the symptoms begin?", "Are they improving, worsening, or unchanged?"]
    priority = "Routine doctor consultation"
    first_aid = ["Rest and avoid strenuous activity.", "Drink fluids regularly if you can tolerate them.", "Track how the symptoms change over the next few hours."]
    relief = ["For pain or fever, an over-the-counter paracetamol/acetaminophen product may help some people who can normally take it; follow the package label and ask a pharmacist if unsure."]

    if "shortness of breath" in s:
        impression = "Breathing difficulty needs more caution than many routine symptoms, especially if it is new or worsening."
        priority = "Urgent medical assessment recommended"
        first_aid = ["Stop exertion and sit upright in a comfortable position.", "Avoid smoke and other airway irritants.", "Do not drive yourself if you are significantly short of breath."]
        relief = ["Do not rely on a new over-the-counter medicine to treat unexplained breathing difficulty. Seek medical assessment."]
        questions = ["Did the breathing difficulty start suddenly?", "Do you also have chest pain, fainting, blue lips, or severe wheezing?"]
    elif "chest pain" in s:
        impression = "Chest pain has many possible causes and some are emergencies."
        priority = "Urgent medical assessment recommended"
        first_aid = ["Stop activity and rest.", "If symptoms are severe, sudden, or associated with breathing difficulty or fainting, seek emergency help now."]
        relief = ["Avoid self-treating unexplained chest pain with new medicines; seek professional assessment."]
        questions = ["Is the pain severe, sudden, or spreading to the arm, jaw, back, or shoulder?", "Any sweating, fainting, or breathing difficulty?"]
    elif "fever" in s and "cough" in s and "sore throat" in s:
        impression = "Fever, cough and sore throat can occur with common respiratory infections, but symptoms alone cannot identify the cause."
        first_aid = ["Rest and drink fluids regularly.", "Warm fluids or honey may soothe a cough for people older than 1 year.", "Avoid smoke and close contact with others while feverish."]
        relief = ["Paracetamol/acetaminophen may help fever or discomfort when normally safe; follow the package label.", "Throat lozenges or warm fluids may temporarily soothe throat discomfort."]
        questions = ["What is the highest temperature recorded?", "Any breathing difficulty or chest pain?"]
        priority = "Doctor review recommended"
    elif "fever" in s and "headache" in s:
        impression = "Fever with headache has several possible causes. Severity, duration and associated symptoms are important."
        first_aid = ["Rest in a quiet, comfortable environment.", "Drink fluids regularly if tolerated.", "Monitor temperature and whether the headache is getting worse."]
        relief = ["Paracetamol/acetaminophen may help fever or headache when normally safe; follow the package label and avoid duplicate products containing it."]
        questions = ["How severe is the headache?", "Any unusual confusion, fainting, neck stiffness, repeated vomiting, or vision changes?"]
        priority = "Doctor review recommended"
    elif "stomach pain" in s and ("vomiting" in s or "nausea" in s):
        impression = "Abdominal discomfort with nausea or vomiting can have many causes; hydration and severity are important to monitor."
        first_aid = ["Take small, frequent sips of water or oral rehydration fluids if tolerated.", "Avoid heavy or greasy meals until you feel better.", "Rest and monitor the location and severity of the pain."]
        relief = ["Avoid starting new medicines for unexplained abdominal pain without advice from a pharmacist or clinician."]
        questions = ["Where exactly is the pain and how severe is it?", "Can you keep fluids down? Any blood in vomit or stool?"]
        priority = "Doctor review recommended"
    elif "vomiting" in s:
        impression = "Vomiting can quickly lead to dehydration, especially when frequent."
        first_aid = ["Take small sips of water or oral rehydration fluid frequently.", "Avoid large meals immediately after vomiting; restart light foods gradually if tolerated.", "Watch for dizziness, very low urine output, or inability to keep fluids down."]
        relief = ["Do not start anti-vomiting medicines without checking with a pharmacist or clinician, especially for children."]
        questions = ["How often have you vomited?", "Are you able to keep any fluids down?"]
    elif "dizziness" in s:
        impression = "Dizziness can come from dehydration, low blood pressure, medication effects and other causes."
        first_aid = ["Sit or lie down until the sensation passes to reduce fall risk.", "Drink fluids if dehydration may be contributing.", "Stand up slowly and avoid driving while dizzy."]
        relief = ["There is no single suitable OTC medicine for unexplained dizziness; identifying the cause is more important."]
        questions = ["Does the room feel like it is spinning or do you feel faint?", "Did it start after standing up, missing a meal, or taking a medicine?"]
    elif "runny nose" in s and "cough" in s:
        impression = "Runny nose and cough commonly occur with viral upper-respiratory illnesses, allergies, or irritation."
        first_aid = ["Rest and drink fluids.", "Use saline nasal spray or a gentle saline rinse if appropriate.", "Avoid smoke, dust and other irritants."]
        relief = ["Warm fluids can soothe cough or throat irritation.", "Ask a pharmacist about an OTC option if congestion is bothersome, especially if you take other medicines."]
        questions = ["Any fever or breathing difficulty?", "How long have the symptoms lasted?"]
    elif "body ache" in s and "fatigue" in s:
        impression = "Body aches with fatigue can occur with infections, poor sleep, dehydration and other causes."
        first_aid = ["Prioritise rest and sleep.", "Drink fluids and eat regular, light meals if tolerated.", "Monitor for fever or symptoms that are rapidly worsening."]
        relief = ["Paracetamol/acetaminophen may help aches for people who can normally take it; follow the package label."]
        questions = ["Any fever, cough, sore throat, or other new symptoms?", "How long has the fatigue lasted?"]
    elif "headache" in s:
        impression = "A headache can be related to dehydration, sleep, stress, illness or other causes."
        first_aid = ["Rest somewhere quiet and comfortable.", "Drink water if you may be dehydrated.", "Reduce bright screens or other triggers if they make the headache worse."]
        relief = ["Paracetamol/acetaminophen may help some headaches when normally safe; follow the package label."]
        questions = ["Is this a new or unusually severe headache?", "Any weakness, confusion, vision changes, fainting, or repeated vomiting?"]
    elif "sore throat" in s:
        impression = "A sore throat can have infectious or non-infectious causes; the presence of fever and breathing difficulty changes urgency."
        first_aid = ["Warm fluids can soothe irritation.", "Avoid smoke and other irritants.", "Rest your voice and stay hydrated."]
        relief = ["Throat lozenges may provide temporary comfort. Paracetamol/acetaminophen may help pain when normally safe; follow the label."]
        questions = ["Any fever, difficulty swallowing, or breathing difficulty?", "How long has the sore throat lasted?"]
    elif "nausea" in s:
        impression = "Nausea has many possible triggers including illness, dehydration, food-related problems and medicines."
        first_aid = ["Take small sips of water or oral fluids.", "Try small, bland meals if you feel able to eat.", "Avoid strong smells and heavy meals if they worsen nausea."]
        relief = ["Check with a pharmacist before using an anti-nausea medicine, especially if you take other medicines or have other conditions."]
        questions = ["Are you vomiting or able to keep fluids down?", "Did the nausea begin after food, travel, or a new medicine?"]
    elif "fatigue" in s:
        impression = "Fatigue can have many causes, including sleep disruption, stress, dehydration, infection and other conditions."
        first_aid = ["Prioritise regular sleep and hydration.", "Eat regular balanced meals if possible.", "Avoid overexertion until you understand the cause."]
        relief = ["There is no universal OTC medicine for fatigue; persistent or unexplained fatigue deserves medical review."]
        questions = ["How long has the fatigue been present?", "Any fever, weight change, breathlessness, dizziness, or sleep problems?"]

    return {"impression": impression, "questions": questions, "priority": priority,
            "first_aid": first_aid, "relief_options": relief, "red_flags": red_flags,
            "safety": "AI guidance is informational, not a diagnosis or prescription. Medicine suggestions are general OTC information only; follow the package label and seek professional advice when unsure. Doctors remain responsible for diagnosis and treatment.",
            "symptoms": symptoms, "duration": duration, "extra": extra}

def slot_dates():
    # Show a full week of the doctor's appointment schedule.
    today = date.today()
    return [(today + timedelta(days=i)).isoformat() for i in range(1, 8)]


def schedule_for_doctor(doctor_id):
    times = ["09:00", "12:00", "14:00", "17:00", "21:00", "00:00"]
    conn = db()
    rows = []
    for ds in slot_dates():
        for t in times:
            when = f"{ds}T{t}"
            override = conn.execute("SELECT status FROM doctor_slots WHERE doctor_id=? AND appointment_time=?", (doctor_id, when)).fetchone()
            booking = conn.execute("SELECT id,token_number,status FROM appointments WHERE doctor_id=? AND appointment_time=? AND status NOT IN ('cancelled','completed')", (doctor_id, when)).fetchone()
            status = "booked" if booking else (override["status"] if override else "available")
            rows.append({"doctor_id": doctor_id, "date": ds, "time": t, "appointment_time": when,
                         "status": status, "booked": bool(booking), "token_number": booking["token_number"] if booking else None})
    conn.close(); return rows

def appointment_payload(row):
    x = dict(row)
    if x.get("appointment_time"):
        try:
            dt = datetime.fromisoformat(x["appointment_time"])
            x["date"] = dt.date().isoformat(); x["time"] = dt.strftime("%I:%M %p")
        except ValueError:
            x["date"] = x["appointment_time"]; x["time"] = x["appointment_time"]
    return x


@app.route("/")
def index():
    if current_admin(): return redirect(url_for("admin_dashboard"))
    u = current_user()
    if not u: return redirect(url_for("login"))
    return render_template("index.html", user=u)

@app.route("/hospital/login", methods=["GET", "POST"])
def hospital_login():
    if request.method=="POST":
        email=request.form["email"].strip().lower(); password=request.form["password"]
        conn=db(); h=conn.execute("SELECT * FROM hospital_accounts WHERE email=?",(email,)).fetchone(); conn.close()
        if h and check_password_hash(h["password_hash"],password):
            session.clear(); session["hospital_id"]=h["id"]; return redirect(url_for("hospital_dashboard"))
        return render_template_string(HOSPITAL_LOGIN_HTML.replace("</style>", MINIMAL_PORTAL_CSS+"</style>"),error="Invalid hospital email or password.")
    return render_template_string(HOSPITAL_LOGIN_HTML.replace("</style>", MINIMAL_PORTAL_CSS+"</style>"),error=None)

@app.get("/hospital/logout")
def hospital_logout(): session.pop("hospital_id",None); return redirect(url_for("hospital_login"))

@app.get("/hospital")
def hospital_dashboard():
    if not session.get("hospital_id"): return redirect(url_for("hospital_login"))
    conn=db(); h=conn.execute("SELECT * FROM hospital_accounts WHERE id=?",(session["hospital_id"],)).fetchone(); r=conn.execute("SELECT * FROM pandemic_regions WHERE name=? OR city=? LIMIT 1",(h["region"],h["region"])).fetchone(); conn.close()
    return render_template_string(HOSPITAL_HTML.replace("</style>", MINIMAL_PORTAL_CSS+"</style>"),h=h,region=r)

@app.post("/api/hospital/occupancy")
def hospital_occupancy_update():
    if not session.get("hospital_id"): return jsonify(error="Hospital login required"),403
    data=request.get_json() or {}; beds=int(data.get("total_beds",0)); occupied=int(data.get("occupied_beds",0))
    if beds<=0 or occupied<0 or occupied>beds: return jsonify(error="Enter valid bed numbers."),400
    conn=db(); h=conn.execute("SELECT * FROM hospital_accounts WHERE id=?",(session["hospital_id"],)).fetchone(); r=conn.execute("SELECT * FROM pandemic_regions WHERE name=? OR city=? LIMIT 1",(h["region"],h["region"])).fetchone()
    if not r: conn.close(); return jsonify(error="No mapped region found."),404
    now=datetime.now().isoformat(timespec="seconds")
    hist=json.loads(h["history_json"] or "[]"); hist.append({"days_ago":0,"occupied":occupied,"ts":now}); hist=hist[-30:]
    conn.execute("UPDATE hospital_accounts SET total_beds=?,occupied_beds=?,history_json=?,updated_at=? WHERE id=?",(beds,occupied,json.dumps(hist),now,h["id"]))
    hs=conn.execute("SELECT total_beds,occupied_beds FROM hospital_accounts WHERE region=?",(h["region"],)).fetchall()
    city_beds=sum(int(x["total_beds"] or 0) for x in hs); city_occ=sum(int(x["occupied_beds"] or 0) for x in hs)
    conn.execute("UPDATE pandemic_regions SET total_beds=?,occupied_beds=?,updated_at=? WHERE id=?",(max(1,city_beds),city_occ,now,r["id"]))
    conn.commit(); conn.close(); return jsonify(ok=True,occupancy_pct=round(occupied/beds*100,1))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower(); password = request.form["password"]
        conn = db(); u = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone(); conn.close()
        if u and check_password_hash(u["password_hash"], password):
            session.pop("admin_id", None); session["user_id"] = u["id"]; return redirect(url_for("index"))
        return render_template("login.html", error="Invalid email or password.")
    return render_template("login.html")

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        email=request.form["email"].strip().lower(); password=request.form["password"]
        conn=db(); a=conn.execute("SELECT * FROM admin_users WHERE email=?",(email,)).fetchone(); conn.close()
        if a and check_password_hash(a["password_hash"],password):
            session.pop("user_id",None); session["admin_id"]=a["id"]; return redirect(url_for("admin_dashboard"))
        return render_template("admin_login.html", error="Invalid admin email or password.")
    return render_template("admin_login.html")

@app.route("/admin")
def admin_dashboard():
    a=current_admin()
    if not a:return redirect(url_for("admin_login"))
    return render_template("admin.html", admin=a)

@app.route("/logout")
def logout():
    was_admin=bool(session.get("admin_id")); session.clear(); return redirect(url_for("admin_login" if was_admin else "login"))

@app.get("/admin/logout")
def admin_logout():
    session.clear(); return redirect(url_for("admin_login"))

@app.route("/delivery/login", methods=["GET", "POST"])
def delivery_login():
    if request.method == "POST":
        email = request.form["email"].strip().lower(); password = request.form["password"]
        conn = db(); ag = conn.execute("SELECT * FROM delivery_agents WHERE email=?", (email,)).fetchone(); conn.close()
        if ag and check_password_hash(ag["password_hash"], password):
            session.pop("user_id", None); session.pop("admin_id", None); session["agent_id"] = ag["id"]
            return redirect(url_for("delivery_dashboard"))
        return render_delivery_login(error="Invalid delivery-agent email or password.")
    return render_delivery_login()

def render_delivery_login(error=None):
    template = os.path.join(BASE, "templates", "delivery_login.html")
    return render_template("delivery_login.html", error=error) if os.path.exists(template) \
        else render_template_string(DELIVERY_LOGIN_HTML.replace("</style>", MINIMAL_PORTAL_CSS+"</style>"), error=error)

@app.get("/delivery/logout")
def delivery_logout():
    session.pop("agent_id", None); return redirect(url_for("delivery_login"))

@app.get("/delivery")
def delivery_dashboard():
    ag = current_agent()
    if not ag: return redirect(url_for("delivery_login"))
    template = os.path.join(BASE, "templates", "delivery.html")
    return render_template("delivery.html", agent=ag) if os.path.exists(template) \
        else render_template_string(DELIVERY_HTML.replace("</style>", MINIMAL_PORTAL_CSS+"</style>"), agent=ag)


def recommend_doctors(symptoms):
    s={x.strip().lower() for x in symptoms}
    specialties=set()
    if s & {"sore throat","runny nose","ear pain","sinus congestion","voice change"}: specialties.add("ENT Specialist")
    if s & {"body ache","back pain","joint pain","neck pain","shoulder pain","muscle pain","dizziness"}: specialties.add("Physiotherapist")
    if s & {"tooth pain","gum pain","dental pain"}: specialties.add("Dentist")
    if s & {"cough","shortness of breath","wheezing"}: specialties.add("Pulmonologist")
    if s & {"stomach pain","nausea","vomiting"}: specialties.add("Gastroenterologist")
    if s & {"headache","dizziness","fainting"}: specialties.add("Neurologist (Brain)")
    if s & {"chest pain","palpitations"}: specialties.add("Cardiologist (Heart)")
    if s & {"fever","fatigue"}: specialties.add("General Medicine")
    if not specialties: specialties.add("General Medicine")
    conn=db(); q="""SELECT d.id,u.name,d.specialty,d.qualification,d.experience_years,d.hospitals,d.venue,d.bio FROM doctors d JOIN users u ON u.id=d.user_id WHERE d.specialty IN ({}) ORDER BY d.experience_years DESC,u.name""".format(','.join('?'*len(specialties)))
    rows=conn.execute(q,tuple(specialties)).fetchall(); conn.close()
    return [dict(r) for r in rows]

@app.post("/api/analyse")
def analyse():
    u = current_user()
    if not u or u["role"] != "patient": return jsonify(error="Patient login required"), 403
    data = request.get_json() or {}; symptoms = data.get("symptoms", []); duration = data.get("duration", ""); extra = data.get("extra", "")
    if not symptoms: return jsonify(error="Select at least one symptom"), 400
    result = ai_assess(symptoms, duration, extra)
    api_key=os.environ.get("OPENAI_API_KEY")
    if api_key:
        try:
            prompt=f"Provide a practical, concise medical triage response for symptoms: {', '.join(symptoms)}. Duration: {duration}. Extra details: {extra}. Do not diagnose with certainty or prescribe. Include likely possibilities, self-care, urgency, and red flags in one coherent answer."
            payload=json.dumps({"model":os.environ.get("OPENAI_MODEL","gpt-4.1-mini"),"input":prompt}).encode()
            req=urllib.request.Request("https://api.openai.com/v1/responses",data=payload,headers={"Authorization":"Bearer "+api_key,"Content-Type":"application/json"})
            raw=json.loads(urllib.request.urlopen(req,timeout=15).read().decode())
            text=raw.get("output_text")
            if text: result["full_answer"]=text
        except Exception: pass
    if "full_answer" not in result:
        result["full_answer"]=f"Based on {', '.join(symptoms)} for {duration or 'an unspecified duration'}, {result['impression']} Priority: {result['priority']}. What you can do now: " + " ".join(result['first_aid']) + " Warning signs needing urgent care: " + "; ".join(result['red_flags'])
    result["recommended_doctors"] = recommend_doctors(symptoms)
    result["recommended_specialties"] = sorted({d["specialty"] for d in result["recommended_doctors"]})
    conn = db(); conn.execute("INSERT INTO symptom_sessions(patient_id,symptoms,duration,extra,ai_response,created_at) VALUES(?,?,?,?,?,?)",
                             (u["id"], ", ".join(symptoms), duration, extra, json.dumps(result), datetime.now().isoformat(timespec="seconds")))
    conn.commit(); conn.close(); return jsonify(result)

@app.get("/api/doctors")
def doctors():
    conn = db(); rows = conn.execute("""SELECT d.id,d.user_id,u.name,d.specialty,d.bio,d.venue,d.emergency_phone,
        d.qualification,d.experience_years,d.hospitals FROM doctors d JOIN users u ON u.id=d.user_id ORDER BY u.name""").fetchall(); conn.close()
    return jsonify([dict(x) for x in rows])

@app.get("/api/appointment-slots")
def appointment_slots():
    specialty=(request.args.get("specialty") or "").strip()
    hospital=(request.args.get("hospital") or "").strip()
    doctor_id=request.args.get("doctor_id")
    conn = db(); docs = conn.execute("""SELECT d.id AS id, u.name AS name, d.venue AS venue, d.specialty AS specialty,
        d.qualification AS qualification, d.experience_years AS experience_years, d.hospitals AS hospitals
        FROM doctors d JOIN users u ON u.id=d.user_id ORDER BY u.name""").fetchall(); conn.close()
    docs=[d for d in docs if (not specialty or d["specialty"]==specialty) and (not hospital or hospital.lower() in (d["hospitals"] or "").lower()) and (not doctor_id or str(d["id"])==str(doctor_id))]
    out=[]
    for d in docs:
        for x in schedule_for_doctor(d["id"]):
            x.update({"doctor_name":d["name"], "venue":d["venue"], "specialty":d["specialty"],
                      "qualification":d["qualification"], "experience_years":d["experience_years"], "hospitals":d["hospitals"]})
            out.append(x)
    return jsonify(out)

@app.get("/api/doctor/schedule")
def doctor_schedule():
    u=current_user()
    if not u or u["role"]!="doctor": return jsonify(error="Doctor login required"),403
    conn=db(); d=conn.execute("SELECT id FROM doctors WHERE user_id=?",(u["id"],)).fetchone(); conn.close()
    return jsonify(schedule_for_doctor(d["id"]))

@app.post("/api/doctor/schedule/toggle")
def toggle_doctor_slot():
    u=current_user()
    if not u or u["role"]!="doctor": return jsonify(error="Doctor login required"),403
    data=request.get_json() or {}; when=data.get("appointment_time")
    if not when: return jsonify(error="Appointment time required"),400
    conn=db(); d=conn.execute("SELECT id FROM doctors WHERE user_id=?",(u["id"],)).fetchone()
    booking=conn.execute("SELECT id FROM appointments WHERE doctor_id=? AND appointment_time=? AND status NOT IN ('cancelled','completed')",(d["id"],when)).fetchone()
    if booking: conn.close(); return jsonify(error="Booked slots cannot be marked unavailable."),409
    cur=conn.execute("SELECT status FROM doctor_slots WHERE doctor_id=? AND appointment_time=?",(d["id"],when)).fetchone()
    new_status="unavailable" if not cur or cur["status"]=="available" else "available"
    conn.execute("INSERT INTO doctor_slots(doctor_id,appointment_time,status) VALUES(?,?,?) ON CONFLICT(doctor_id,appointment_time) DO UPDATE SET status=excluded.status",(d["id"],when,new_status))
    conn.commit(); conn.close(); return jsonify(ok=True,status=new_status)

@app.post("/api/payments/create")
def create_appointment_payment():
    u=current_user()
    if not u or u["role"]!="patient": return jsonify(error="Patient login required"),403
    data=request.get_json() or {}; doctor_id=data.get("doctor_id"); when=data.get("appointment_time")
    if not doctor_id or not when: return jsonify(error="Doctor and time required"),400
    conn=db(); doctor=conn.execute("SELECT * FROM doctors WHERE id=?",(doctor_id,)).fetchone()
    if not doctor: conn.close(); return jsonify(error="Doctor not found"),404
    try:
        dt=datetime.fromisoformat(when)
        if dt.strftime("%H:%M") not in {"09:00","12:00","14:00","17:00","21:00","00:00"}: raise ValueError
    except Exception:
        conn.close(); return jsonify(error="Please choose one of the available clinic-window slots."),400
    active=conn.execute("SELECT id FROM appointments WHERE patient_id=? AND status NOT IN ('cancelled','completed')",(u["id"],)).fetchall()
    if active:
        conn.close(); return jsonify(error="You already have an active appointment. Cancel or complete it before booking another."),409
    exists=conn.execute("SELECT id FROM appointments WHERE doctor_id=? AND appointment_time=? AND status NOT IN ('cancelled','completed')",(doctor_id,when)).fetchone()
    if exists: conn.close(); return jsonify(error="That slot is already booked."),409
    blocked=conn.execute("SELECT status FROM doctor_slots WHERE doctor_id=? AND appointment_time=?",(doctor_id,when)).fetchone()
    if blocked and blocked["status"]!="available": conn.close(); return jsonify(error="That slot is currently unavailable."),409
    payment=conn.execute("SELECT * FROM appointment_payments WHERE patient_id=? AND doctor_id=? AND appointment_time=? AND status='pending' ORDER BY id DESC LIMIT 1",(u["id"],doctor_id,when)).fetchone()
    if not payment:
        now=datetime.now().isoformat(timespec="seconds")
        conn.execute("INSERT INTO appointment_payments(patient_id,doctor_id,appointment_time,amount,method,upi_id,status,created_at) VALUES(?,?,?,?,?,?, 'pending',?)",(u["id"],doctor_id,when,CONSULTATION_FEE,'UPI',UPI_ID,now))
        payment=conn.execute("SELECT * FROM appointment_payments WHERE id=?",(conn.execute("SELECT last_insert_rowid() id").fetchone()["id"],)).fetchone()
    conn.commit(); conn.close()
    from urllib.parse import quote
    upi_uri=f"upi://pay?pa={quote(UPI_ID)}&pn={quote('MediBridge')}&am={CONSULTATION_FEE:.2f}&cu=INR&tn={quote('MediBridge consultation')}"
    return jsonify(ok=True,payment_id=payment["id"],amount=CONSULTATION_FEE,upi_id=UPI_ID,upi_uri=upi_uri)

@app.post("/api/payments/<int:payment_id>/confirm")
def confirm_appointment_payment(payment_id):
    u=current_user()
    if not u or u["role"]!="patient": return jsonify(error="Patient login required"),403
    data=request.get_json() or {}; utr=(data.get("utr") or "").strip()
    if len(utr)<4: return jsonify(error="Enter the UPI transaction reference / UTR after payment."),400
    conn=db(); p=conn.execute("SELECT * FROM appointment_payments WHERE id=? AND patient_id=?",(payment_id,u["id"])).fetchone()
    if not p: conn.close(); return jsonify(error="Payment session not found."),404
    if p["status"]=="paid": conn.close(); return jsonify(ok=True,payment_id=payment_id,status="paid")
    now=datetime.now().isoformat(timespec="seconds")
    conn.execute("UPDATE appointment_payments SET status='paid',utr=?,paid_at=? WHERE id=?",(utr,now,payment_id))
    conn.commit(); conn.close(); return jsonify(ok=True,payment_id=payment_id,status="paid",utr=utr)

@app.post("/api/appointments")
def appointment():
    u = current_user()
    if not u or u["role"] != "patient": return jsonify(error="Patient login required"), 403
    data=request.get_json() or {}; doctor_id=data.get("doctor_id"); when=data.get("appointment_time"); payment_id=data.get("payment_id")
    if not doctor_id or not when: return jsonify(error="Doctor and time required"),400
    if not payment_id: return jsonify(error="UPI payment is required before booking the consultation.",payment_required=True),402
    conn=db(); doctor=conn.execute("SELECT * FROM doctors WHERE id=?",(doctor_id,)).fetchone()
    if not doctor: conn.close(); return jsonify(error="Doctor not found"),404
    payment=conn.execute("SELECT * FROM appointment_payments WHERE id=? AND patient_id=? AND doctor_id=? AND appointment_time=?",(payment_id,u["id"],doctor_id,when)).fetchone()
    if not payment or payment["status"]!="paid" or float(payment["amount"] or 0)!=CONSULTATION_FEE:
        conn.close(); return jsonify(error="Complete the ₹200 UPI payment before booking this consultation.",payment_required=True),402
    try:
        if datetime.fromisoformat(when).strftime("%H:%M") not in {"09:00","12:00","14:00","17:00","21:00","00:00"}: raise ValueError
    except Exception:
        conn.close(); return jsonify(error="Please choose one of the available clinic-window slots."),400
    active_patient=conn.execute("SELECT * FROM appointments WHERE patient_id=? AND status NOT IN ('cancelled','completed') ORDER BY appointment_time",(u["id"],)).fetchall()
    if active_patient:
        same=next((row for row in active_patient if row["doctor_id"]==int(doctor_id) and row["appointment_time"]==when),None)
        if same:
            row=conn.execute("SELECT a.*,du.name doctor_name,d.specialty,d.emergency_phone FROM appointments a JOIN doctors d ON d.id=a.doctor_id JOIN users du ON du.id=d.user_id WHERE a.id=?",(same["id"],)).fetchone()
            payload=appointment_payload(row); conn.close()
            return jsonify(ok=True,already_booked=True,message="This appointment is already booked.",token_number=same["token_number"],venue=same["venue"],consultation_fee=CONSULTATION_FEE,appointment=payload)
        conn.close(); return jsonify(error="You already have an active appointment. Cancel or complete it before booking another."),409
    exists=conn.execute("SELECT id FROM appointments WHERE doctor_id=? AND appointment_time=? AND status NOT IN ('cancelled','completed')",(doctor_id,when)).fetchone()
    if exists: conn.close(); return jsonify(error="That slot is already booked."),409
    blocked=conn.execute("SELECT status FROM doctor_slots WHERE doctor_id=? AND appointment_time=?",(doctor_id,when)).fetchone()
    if blocked and blocked["status"]!="available": conn.close(); return jsonify(error="That slot is currently unavailable."),409
    day=when[:10]
    token=(conn.execute("SELECT COALESCE(MAX(token_number),0)+1 n FROM appointments WHERE doctor_id=? AND substr(appointment_time,1,10)=?",(doctor_id,day)).fetchone()["n"])
    now=datetime.now().isoformat(timespec="seconds")
    conn.execute("INSERT INTO appointments(patient_id,doctor_id,appointment_time,venue,token_number,status,created_at,consultation_fee,payment_id,payment_status,payment_method) VALUES(?,?,?,?,?,'confirmed',?,?,?,?,?)",(u["id"],doctor_id,when,doctor["venue"],token,now,CONSULTATION_FEE,payment_id,"paid","UPI"))
    new_id=conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    row=conn.execute("SELECT a.*,du.name doctor_name,d.specialty,d.emergency_phone FROM appointments a JOIN doctors d ON d.id=a.doctor_id JOIN users du ON du.id=d.user_id WHERE a.id=?",(new_id,)).fetchone()
    payload=appointment_payload(row); conn.commit(); conn.close()
    return jsonify(ok=True,message="Payment received. Appointment booked.",token_number=token,venue=doctor["venue"],consultation_fee=CONSULTATION_FEE,payment_status="paid",appointment=payload)

@app.post("/api/appointments/<int:aid>/cancel")
def cancel_appointment(aid):
    u=current_user()
    if not u:return jsonify(error="Login required"),401
    conn=db()
    if u["role"]=="patient": cur=conn.execute("UPDATE appointments SET status='cancelled' WHERE id=? AND patient_id=? AND status IN ('confirmed','waiting')",(aid,u["id"]))
    elif u["role"]=="doctor":
        doc=conn.execute("SELECT id FROM doctors WHERE user_id=?",(u["id"],)).fetchone()
        if not doc: conn.close(); return jsonify(error="Doctor profile not found"),404
        cur=conn.execute("UPDATE appointments SET status='cancelled' WHERE id=? AND doctor_id=? AND status IN ('confirmed','waiting')",(aid,doc["id"]))
    else:
        conn.close(); return jsonify(error="Only the patient or assigned doctor can cancel this appointment"),403
    ok=cur.rowcount>0
    if ok:
        row=conn.execute("SELECT doctor_id,appointment_time FROM appointments WHERE id=?",(aid,)).fetchone()
        if row:
            conn.execute("UPDATE doctor_slots SET status='available' WHERE doctor_id=? AND appointment_time=?",(row["doctor_id"],row["appointment_time"]))
    conn.commit(); conn.close()
    return jsonify(ok=ok, message="Appointment cancelled" if ok else "Appointment cannot be cancelled in its current state")

@app.get("/api/live-state")
def live_state():
    """Authoritative, on-demand user state derived directly from the database."""
    u=current_user()
    if not u: return jsonify(error="Login required"),401
    conn=db(); now=datetime.now().isoformat(timespec="seconds")
    if u["role"]=="patient":
        rows=conn.execute("SELECT a.*,du.name doctor_name FROM appointments a JOIN doctors d ON d.id=a.doctor_id JOIN users du ON du.id=d.user_id WHERE a.patient_id=? ORDER BY CASE a.status WHEN 'in_progress' THEN 0 WHEN 'waiting' THEN 1 WHEN 'confirmed' THEN 2 ELSE 3 END,a.appointment_time",(u["id"],)).fetchall()
        active=next((r for r in rows if r["status"] in ("confirmed","waiting","in_progress")),None)
        state={"in_progress":"IN CONSULTATION","waiting":"WAITING FOR CONSULTATION","confirmed":"APPOINTMENT CONFIRMED"}.get(active["status"],"AVAILABLE / NO ACTIVE APPOINTMENT") if active else "AVAILABLE / NO ACTIVE APPOINTMENT"
        payload={"state":state,"active_appointment":appointment_payload(active) if active else None}
    else:
        doc=conn.execute("SELECT id FROM doctors WHERE user_id=?",(u["id"],)).fetchone()
        active=conn.execute("SELECT a.*,pu.name patient_name FROM appointments a JOIN users pu ON pu.id=a.patient_id WHERE a.doctor_id=? AND a.status='in_progress' ORDER BY a.started_at DESC LIMIT 1",(doc["id"],)).fetchone()
        waiting=conn.execute("SELECT COUNT(*) n FROM appointments WHERE doctor_id=? AND status IN ('confirmed','waiting')",(doc["id"],)).fetchone()["n"]
        state="IN CONSULTATION" if active else ("PATIENTS WAITING" if waiting else "AVAILABLE")
        payload={"state":state,"active_appointment":appointment_payload(active) if active else None,"waiting_patients":waiting}
    conn.close(); return jsonify(ok=True,verified_at=now,role=u["role"],**payload)

@app.get("/api/appointments")
def appointments():
    u=current_user()
    if not u:return jsonify(error="Login required"),401
    conn=db()
    if u["role"]=="patient":
        rows=conn.execute("""SELECT a.*,du.name doctor_name,d.specialty,d.emergency_phone FROM appointments a
            JOIN doctors d ON d.id=a.doctor_id JOIN users du ON du.id=d.user_id WHERE a.patient_id=? ORDER BY a.appointment_time""",(u["id"],)).fetchall()
    else:
        rows=conn.execute("""SELECT a.*,pu.name patient_name,pu.email patient_email FROM appointments a JOIN users pu ON pu.id=a.patient_id
            WHERE a.doctor_id=(SELECT id FROM doctors WHERE user_id=?) ORDER BY a.appointment_time""",(u["id"],)).fetchall()
    out=[appointment_payload(r) for r in rows]; conn.close(); return jsonify(out)

@app.get("/api/appointments/active")
def active_appointments():
    u=current_user()
    if not u or u["role"]!="patient": return jsonify(error="Patient login required"),403
    conn=db()
    rows=conn.execute("""SELECT a.*,du.name doctor_name,d.specialty FROM appointments a
        JOIN doctors d ON d.id=a.doctor_id JOIN users du ON du.id=d.user_id
        WHERE a.patient_id=? AND a.status IN ('confirmed','waiting','in_progress')
        ORDER BY a.appointment_time""",(u["id"],)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.get("/api/queue/<int:appointment_id>")
def queue(appointment_id):
    u=current_user()
    if not u:return jsonify(error="Login required"),401
    conn=db(); a=conn.execute("SELECT * FROM appointments WHERE id=?",(appointment_id,)).fetchone()
    if not a: conn.close(); return jsonify(error="Appointment not found"),404
    if a["payment_status"] != "paid": conn.close(); return jsonify(error="Consultation cannot start until the ₹200 UPI fee is paid."),402
    day=a["appointment_time"][:10]
    rows=conn.execute("""SELECT a.token_number,a.status,pu.name patient_name FROM appointments a JOIN users pu ON pu.id=a.patient_id
        WHERE a.doctor_id=? AND substr(a.appointment_time,1,10)=? AND a.status NOT IN ('cancelled','completed') ORDER BY a.token_number""",(a["doctor_id"],day)).fetchall()
    current=conn.execute("SELECT token_number FROM appointments WHERE doctor_id=? AND substr(appointment_time,1,10)=? AND status='in_progress' ORDER BY token_number LIMIT 1",(a["doctor_id"],day)).fetchone()
    ahead=conn.execute("SELECT COUNT(*) n FROM appointments WHERE doctor_id=? AND substr(appointment_time,1,10)=? AND token_number<? AND status IN ('confirmed','waiting')",(a["doctor_id"],day,a["token_number"])).fetchone()["n"]
    conn.close(); return jsonify(current_token=current["token_number"] if current else None, your_token=a["token_number"], ahead=ahead, queue=[dict(r) for r in rows])

@app.post("/api/appointments/<int:aid>/start")
def start_appointment(aid):
    u=current_user()
    if not u or u["role"]!="doctor": return jsonify(error="Doctor login required"),403
    conn=db(); doc=conn.execute("SELECT id FROM doctors WHERE user_id=?",(u["id"],)).fetchone()
    if not doc: conn.close(); return jsonify(error="Doctor profile not found"),404
    a=conn.execute("SELECT * FROM appointments WHERE id=? AND doctor_id=?",(aid,doc["id"])).fetchone()
    if not a: conn.close(); return jsonify(error="Appointment not found"),404
    day=a["appointment_time"][:10]
    active=conn.execute("SELECT id FROM appointments WHERE doctor_id=? AND substr(appointment_time,1,10)=? AND status='in_progress'",(doc["id"],day)).fetchone()
    if active and active["id"]!=aid: conn.close(); return jsonify(error="End the current appointment before starting another."),409
    conn.execute("UPDATE appointments SET status='in_progress',started_at=? WHERE id=?",(datetime.now().isoformat(timespec="seconds"),aid)); conn.commit(); conn.close(); return jsonify(ok=True)

@app.post("/api/appointments/<int:aid>/end")
def end_appointment(aid):
    u=current_user()
    if not u or u["role"]!="doctor":return jsonify(error="Doctor login required"),403
    conn=db(); doc=conn.execute("SELECT id FROM doctors WHERE user_id=?",(u["id"],)).fetchone(); cur=conn.execute("UPDATE appointments SET status='completed',ended_at=? WHERE id=? AND doctor_id=?",(datetime.now().isoformat(timespec="seconds"),aid,doc["id"])); conn.commit(); conn.close(); return jsonify(ok=cur.rowcount>0)

@app.post("/api/doctor/profile")
def doctor_profile():
    u=current_user()
    if not u or u["role"]!="doctor":return jsonify(error="Doctor login required"),403
    data=request.get_json() or {}; venue=data.get("venue","").strip(); phone=data.get("emergency_phone","").strip()
    conn=db(); doc=conn.execute("SELECT id FROM doctors WHERE user_id=?",(u["id"],)).fetchone()
    conn.execute("UPDATE doctors SET venue=?, emergency_phone=? WHERE id=?",(venue,phone,doc["id"])); conn.commit(); conn.close(); return jsonify(ok=True)

@app.get("/api/prescriptions")
def prescriptions():
    u=current_user()
    if not u:return jsonify(error="Login required"),401
    conn=db()
    if u["role"]=="patient":
        rows=conn.execute("SELECT p.*,du.name doctor_name,d.emergency_phone FROM prescriptions p JOIN doctors d ON d.id=p.doctor_id JOIN users du ON du.id=d.user_id WHERE p.patient_id=? ORDER BY p.id DESC",(u["id"],)).fetchall()
    else:
        rows=conn.execute("SELECT p.*,pu.name patient_name FROM prescriptions p JOIN users pu ON pu.id=p.patient_id WHERE p.doctor_id=(SELECT id FROM doctors WHERE user_id=?) ORDER BY p.id DESC",(u["id"],)).fetchall()
    out=[]
    for r in rows:
        x=dict(r); x["items"]=[dict(i) for i in conn.execute("SELECT * FROM prescription_items WHERE prescription_id=?",(r["id"],)).fetchall()]; out.append(x)
    conn.close(); return jsonify(out)

@app.post("/api/prescriptions")
def create_prescription():
    u=current_user()
    if not u or u["role"]!="doctor":return jsonify(error="Doctor login required"),403
    data=request.get_json() or {}; patient_id=data.get("patient_id"); items=data.get("items",[])
    if not patient_id or not items:return jsonify(error="Patient and medicine items required"),400
    conn=db(); doctor=conn.execute("SELECT id FROM doctors WHERE user_id=?",(u["id"],)).fetchone()
    if not doctor:conn.close();return jsonify(error="Doctor profile missing"),400
    cur=conn.execute("INSERT INTO prescriptions(patient_id,doctor_id,diagnosis,notes,created_at) VALUES(?,?,?,?,?)",(patient_id,doctor["id"],data.get("diagnosis",""),data.get("notes",""),datetime.now().isoformat(timespec="seconds")))
    pid=cur.lastrowid
    for i in items:
        if not all(i.get(k) for k in ("medicine","dosage","frequency","duration")): conn.close(); return jsonify(error="Complete all medicine fields"),400
        conn.execute("INSERT INTO prescription_items(prescription_id,medicine,dosage,frequency,duration) VALUES(?,?,?,?,?)",(pid,i["medicine"],i["dosage"],i["frequency"],i["duration"]))
    conn.commit();conn.close();return jsonify(ok=True,prescription_id=pid)

@app.post("/api/reminders")
def create_reminder():
    u=current_user()
    if not u or u["role"]!="patient":return jsonify(error="Patient login required"),403
    data=request.get_json() or {}; conn=db(); item=conn.execute("SELECT pi.id FROM prescription_items pi JOIN prescriptions p ON p.id=pi.prescription_id WHERE pi.id=? AND p.patient_id=?",(data.get("prescription_item_id"),u["id"])).fetchone()
    if not item:conn.close();return jsonify(error="Prescription item not found"),404
    conn.execute("INSERT INTO reminders(patient_id,prescription_item_id,reminder_time,taken,reminder_date) VALUES(?,?,?,?,?)",(u["id"],item["id"],data["reminder_time"],0,data.get("reminder_date",date.today().isoformat())))
    conn.commit();conn.close();return jsonify(ok=True)

@app.get("/api/reminders")
def reminders():
    u=current_user()
    if not u:return jsonify(error="Login required"),401
    conn=db(); rows=conn.execute("SELECT r.*,pi.medicine,pi.dosage,pi.frequency,pi.duration FROM reminders r JOIN prescription_items pi ON pi.id=r.prescription_item_id WHERE r.patient_id=? ORDER BY r.reminder_date,r.reminder_time",(u["id"],)).fetchall(); conn.close(); return jsonify([dict(x) for x in rows])

@app.post("/api/reminders/<int:rid>/taken")
def taken(rid):
    u=current_user()
    if not u:return jsonify(error="Login required"),401
    conn=db(); cur=conn.execute("UPDATE reminders SET taken=1 WHERE id=? AND patient_id=?",(rid,u["id"])); conn.commit();conn.close();return jsonify(ok=cur.rowcount>0)

@app.post("/api/consultations/<int:aid>/guest-link")
def consultation_guest_link(aid):
    """Create/retrieve a non-login guest link for an in-progress consultation."""
    u=current_user()
    if not u:return jsonify(error="Login required to create a guest link"),401
    conn=db(); a=conn.execute("SELECT * FROM appointments WHERE id=?",(aid,)).fetchone()
    if not a: conn.close(); return jsonify(error="Appointment not found"),404
    allowed = a["patient_id"]==u["id"]
    if u["role"]=="doctor":
        doc=conn.execute("SELECT id FROM doctors WHERE user_id=?",(u["id"],)).fetchone()
        allowed = bool(doc and a["doctor_id"]==doc["id"])
    if not allowed: conn.close(); return jsonify(error="You do not have access to this consultation"),403
    if a["status"]!="in_progress": conn.close(); return jsonify(error="Start the appointment first"),409
    room=a["video_room"] or f"medibridge-{aid}-{secrets.token_urlsafe(10)}"
    token=a["guest_token"] or secrets.token_urlsafe(32)
    conn.execute("UPDATE appointments SET video_room=?, guest_token=? WHERE id=?",(room,token,aid))
    conn.commit(); conn.close()
    return jsonify(url=url_for("guest_consultation", token=token, _external=True), room=room)

@app.get("/join/<token>")
def guest_consultation(token):
    """No-login consultation entry point. The opaque token is the only credential."""
    conn=db(); a=conn.execute("SELECT id,video_room,status FROM appointments WHERE guest_token=?",(token,)).fetchone(); conn.close()
    if not a:
        return render_template_string("""
        <!doctype html><meta name="viewport" content="width=device-width,initial-scale=1">
        <title>MediBridge · Link unavailable</title>
        <body style="font-family:Segoe UI,Arial;background:#f5f8fa;display:grid;place-items:center;min-height:100vh">
        <div style="background:white;padding:32px;border-radius:18px;max-width:460px;box-shadow:0 16px 40px #0b1f2a18">
        <h2>Consultation link unavailable</h2><p style="color:#687a83">This link is invalid or has been revoked.</p></div></body>"""),404
    if a["status"]!="in_progress":
        return render_template_string("""
        <!doctype html><meta name="viewport" content="width=device-width,initial-scale=1">
        <title>MediBridge · Waiting</title>
        <body style="font-family:Segoe UI,Arial;background:#f5f8fa;display:grid;place-items:center;min-height:100vh">
        <div style="background:white;padding:32px;border-radius:18px;max-width:520px;box-shadow:0 16px 40px #0b1f2a18">
        <h2>Consultation is not live yet</h2><p style="color:#687a83">Ask the doctor to start the appointment, then open this same link again.</p></div></body>"""),409
    return render_template_string("""<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'><title>MediBridge Consultation</title><style>html,body{margin:0;height:100%;background:#071a24;font-family:Arial,sans-serif}#meet{height:100vh;width:100vw}</style></head><body><div id='meet'></div><script src='https://meet.jit.si/external_api.js'></script><script>const api=new JitsiMeetExternalAPI('meet.jit.si',{room:{{ room|tojson }},parentNode:document.getElementById('meet'),width:'100%',height:'100%',configOverwrite:{prejoinPageEnabled:true,disableDeepLinking:true},interfaceConfigOverwrite:{MOBILE_APP_PROMO:false,SHOW_JITSI_WATERMARK:false}});api.addEventListener('readyToClose',()=>{window.close()});</script></body></html>""",room=a['video_room'])

@app.post("/api/consultations/<int:aid>/room")
def consultation_room(aid):
    """Create or retrieve a private Jitsi room for an in-progress appointment."""
    u=current_user()
    if not u:return jsonify(error="Login required"),401
    conn=db(); a=conn.execute("SELECT * FROM appointments WHERE id=?",(aid,)).fetchone()
    if not a: conn.close(); return jsonify(error="Appointment not found"),404
    allowed = a["patient_id"]==u["id"]
    if u["role"]=="doctor":
        doc=conn.execute("SELECT id FROM doctors WHERE user_id=?",(u["id"],)).fetchone()
        allowed = bool(doc and a["doctor_id"]==doc["id"])
    if not allowed: conn.close(); return jsonify(error="You do not have access to this consultation"),403
    if a["status"]!="in_progress": conn.close(); return jsonify(error="Consultation is available only while the appointment is in progress"),409
    room=a["video_room"] or f"medibridge-{aid}-{secrets.token_urlsafe(10)}"
    if not a["video_room"]:
        conn.execute("UPDATE appointments SET video_room=? WHERE id=?",(room,aid)); conn.commit()
    conn.close(); return jsonify(room=room, url=f"https://meet.jit.si/{room}")


# ---------------- Diagnostics MVP ----------------
@app.get("/diagnostics")
def diagnostics_page():
    u=current_user()
    if not u: return redirect(url_for("login"))
    return redirect(url_for("index")+"#diagnostics")

@app.get("/api/diagnostics/tests")
def diagnostics_tests():
    conn=db(); rows=conn.execute("SELECT id,name,category,description,price,turnaround,home_collection FROM diagnostic_tests WHERE active=1 ORDER BY category,name").fetchall(); conn.close()
    return jsonify([dict(r) for r in rows])

@app.get("/api/diagnostics/orders")
def diagnostics_orders():
    u=current_user()
    if not u or u["role"]!="patient": return jsonify(error="Patient login required"),403
    conn=db(); rows=conn.execute("""SELECT o.*,t.name test_name,t.category,t.turnaround,
        r.id reservation_id,r.token_number,r.reservation_date,r.reservation_time,r.status reservation_status,
        l.name lab_name,l.venue lab_venue
        FROM diagnostic_orders o JOIN diagnostic_tests t ON t.id=o.test_id
        LEFT JOIN diagnostic_reservations r ON r.order_id=o.id
        LEFT JOIN diagnostic_labs l ON l.id=r.lab_id
        WHERE o.patient_id=? ORDER BY o.id DESC""",(u["id"],)).fetchall(); conn.close()
    return jsonify([dict(r) for r in rows])

@app.get("/api/diagnostics/labs")
def diagnostics_labs():
    u=current_user()
    if not u or u["role"]!="patient": return jsonify(error="Patient login required"),403
    conn=db(); labs=conn.execute("SELECT * FROM diagnostic_labs WHERE active=1 ORDER BY name").fetchall(); conn.close()
    return jsonify([dict(x) for x in labs])

@app.get("/api/diagnostics/slots")
def diagnostics_slots():
    u=current_user()
    if not u or u["role"]!="patient": return jsonify(error="Patient login required"),403
    d=(request.args.get("date") or "").strip(); lab_id=int(request.args.get("lab_id") or 1)
    if not d: return jsonify(error="Date required"),400
    conn=db(); taken={r[0] for r in conn.execute("SELECT reservation_time FROM diagnostic_reservations WHERE lab_id=? AND reservation_date=? AND status='Reserved'",(lab_id,d)).fetchall()}; conn.close()
    slots=[]
    for h in range(8,18):
        for m in (0,30):
            t=f"{h:02d}:{m:02d}"
            slots.append({"time":t,"available":t not in taken})
    return jsonify(slots)

@app.post("/api/diagnostics/orders")
def create_diagnostic_order():
    u=current_user()
    if not u or u["role"]!="patient": return jsonify(error="Patient login required"),403
    data=request.get_json() or {}
    try: test_id=int(data.get("test_id"))
    except (TypeError,ValueError): return jsonify(error="Select a diagnostic test."),400
    preferred_date=(data.get("preferred_date") or "").strip(); preferred_time=(data.get("preferred_time") or "").strip()
    collection_type=(data.get("collection_type") or "Home collection").strip(); address=(data.get("collection_address") or "").strip()
    if not preferred_date or not preferred_time: return jsonify(error="Choose a preferred date and time."),400
    if collection_type not in {"Home collection","At diagnostic centre"}: return jsonify(error="Invalid collection type."),400
    if collection_type=="Home collection" and not address: return jsonify(error="Enter the home collection address."),400
    conn=db(); test=conn.execute("SELECT * FROM diagnostic_tests WHERE id=? AND active=1",(test_id,)).fetchone()
    if not test: conn.close(); return jsonify(error="Diagnostic test not found."),404
    now=datetime.now().isoformat(timespec="seconds")
    if collection_type=="At diagnostic centre":
        lab=conn.execute("SELECT * FROM diagnostic_labs WHERE active=1 ORDER BY id LIMIT 1").fetchone()
        if not lab: conn.close(); return jsonify(error="No partner lab is currently available."),409
        existing=conn.execute("SELECT id FROM diagnostic_reservations WHERE lab_id=? AND reservation_date=? AND reservation_time=? AND status='Reserved'",(lab["id"],preferred_date,preferred_time)).fetchone()
        if existing: conn.close(); return jsonify(error="That lab slot is already reserved. Please choose another time."),409
    cur=conn.execute("""INSERT INTO diagnostic_orders(patient_id,test_id,collection_type,collection_address,preferred_date,preferred_time,status,amount,payment_method,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",(u["id"],test_id,collection_type,address,preferred_date,preferred_time,"Reserved" if collection_type=="At diagnostic centre" else "Booked",float(test["price"]),"Pay at collection",now))
    oid=cur.lastrowid; token=None; lab_name=None; lab_venue=None
    if collection_type=="At diagnostic centre":
        conn.execute("INSERT INTO diagnostic_reservations(order_id,lab_id,reservation_date,reservation_time,token_number,status,created_at) VALUES(?,?,?,?,?,?,?)",(oid,lab["id"],preferred_date,preferred_time,1,"Reserved",now))
        token=1; lab_name=lab["name"]; lab_venue=lab["venue"]
    conn.commit(); conn.close()
    return jsonify(ok=True,order_id=oid,test_name=test["name"],amount=float(test["price"]),status="Reserved" if collection_type=="At diagnostic centre" else "Booked",collection_type=collection_type,preferred_date=preferred_date,preferred_time=preferred_time,token_number=token,lab_name=lab_name,lab_venue=lab_venue)

# ---------------- Pharmacy + medicine delivery MVP ----------------
@app.get("/pharmacy")
def pharmacy_panel():
    u=current_user()
    if not u: return redirect(url_for("login"))
    template=os.path.join(BASE,"templates","pharmacy.html")
    return render_template("pharmacy.html",user=u) if os.path.exists(template) else render_template_string(PHARMACY_HTML.replace("</style>", MINIMAL_PORTAL_CSS+"</style>"),user=u)

@app.get("/api/pharmacy/medicines")
def pharmacy_medicines():
    conn=db()
    rows=conn.execute("""SELECT id,name,category,description,price,stock,requires_prescription,image_url
                         FROM pharmacy_medicines WHERE active=1 ORDER BY category,name""").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.post("/api/pharmacy/orders")
def create_medicine_order():
    u=current_user()
    if not u or u["role"]!="patient": return jsonify(error="Patient login required"),403
    data=request.get_json() or {}; items=data.get("items") or []
    address=(data.get("delivery_address") or "").strip()
    phone=(data.get("phone") or "").strip()
    payment=(data.get("payment_method") or "Cash on Delivery").strip()
    if not items or not address: return jsonify(error="Add at least one medicine and a delivery address."),400
    allowed_payment={"UPI","Debit Card","Cash on Delivery"}
    if payment not in allowed_payment: return jsonify(error="Unsupported payment method."),400
    if payment=="UPI" and not (data.get("upi_id") or "").strip(): return jsonify(error="Enter a valid UPI ID."),400
    if payment=="Debit Card":
        card="".join(c for c in (data.get("card_number") or "") if c.isdigit())
        if len(card) < 12 or not (data.get("card_holder") or data.get("holder") or "").strip(): return jsonify(error="Enter valid debit card details."),400
    # Optional hygiene add-on is accepted by the UI, but must be explicitly selected.
    sanitizer_added = bool(data.get("sanitizer_added", False))
    conn=db()
    try:
        checked=[]; total=0.0
        for item in items:
            mid=int(item.get("medicine_id")); qty=int(item.get("quantity",1))
            if qty<1 or qty>20: raise ValueError("Quantity must be between 1 and 20.")
            med=conn.execute("SELECT * FROM pharmacy_medicines WHERE id=? AND active=1",(mid,)).fetchone()
            if not med: raise ValueError("Medicine not found.")
            if med["stock"]<qty: raise ValueError(f"Only {med['stock']} unit(s) available for {med['name']}.")
            if med["requires_prescription"]: raise ValueError(f"{med['name']} requires prescription verification.")
            checked.append((med,qty)); total+=float(med["price"])*qty
        if sanitizer_added:
            if total < 10: raise ValueError("Sanitizer can be added only when medicines worth at least ₹10 are in the cart.")
            san=conn.execute("SELECT * FROM pharmacy_medicines WHERE name=? AND active=1",("MediBridge Sanitizer 50 ml",)).fetchone()
            if not san or san["stock"] < 1: raise ValueError("Sanitizer is currently unavailable.")
            checked.append((san,1)); total += float(san["price"])
        now=datetime.now().isoformat(timespec="seconds")
        cur=conn.execute("""INSERT INTO medicine_orders
            (patient_id,total_amount,delivery_address,phone,payment_method,status,placed_at)
            VALUES(?,?,?,?,?,?,?)""",(u["id"],total,address,phone,payment,"paid" if payment in ("UPI","Debit Card") else "placed",now))
        oid=cur.lastrowid
        for med,qty in checked:
            conn.execute("""INSERT INTO medicine_order_items
                (order_id,medicine_id,medicine_name,quantity,unit_price) VALUES(?,?,?,?,?)""",
                (oid,med["id"],med["name"],qty,med["price"]))
            conn.execute("UPDATE pharmacy_medicines SET stock=stock-? WHERE id=?",(qty,med["id"]))
        tracking=f"MB{datetime.now().strftime('%y%m%d')}{oid:04d}"
        eta=(date.today()+timedelta(days=2)).isoformat()
        conn.execute("""INSERT INTO delivery_tracking
            (order_id,tracking_code,status,eta,updated_at) VALUES(?,?,?,?,?)""",
            (oid,tracking,"Order placed",eta,now))
        conn.commit()
        return jsonify(ok=True,order_id=oid,tracking_code=tracking,status="Order placed",eta=eta,total_amount=round(total,2),sanitizer_added=sanitizer_added)
    except (ValueError,TypeError) as e:
        conn.rollback(); return jsonify(error=str(e)),400
    finally: conn.close()

@app.get("/pharmacy/bill/<int:order_id>")
def pharmacy_bill(order_id):
    u=current_user()
    if not u or u["role"]!="patient": return redirect(url_for("login"))
    conn=db(); o=conn.execute("SELECT o.*,t.tracking_code,t.status delivery_status,t.eta FROM medicine_orders o LEFT JOIN delivery_tracking t ON t.order_id=o.id WHERE o.id=? AND o.patient_id=?",(order_id,u["id"])).fetchone()
    if not o: conn.close(); return "Bill not found",404
    items=conn.execute("SELECT * FROM medicine_order_items WHERE order_id=? ORDER BY id",(order_id,)).fetchall(); conn.close()
    rows=''.join(f'<tr><td>{esc_html(i["medicine_name"])}</td><td>{i["quantity"]}</td><td>₹{float(i["unit_price"]):.2f}</td><td>₹{float(i["unit_price"])*i["quantity"]:.2f}</td></tr>' for i in items)
    return render_template_string(BILL_HTML,user=u,order=dict(o),items=rows)

@app.get("/api/pharmacy/orders")
def pharmacy_orders():
    u=current_user()
    if not u or u["role"]!="patient": return jsonify(error="Patient login required"),403
    conn=db()
    rows=conn.execute("""SELECT o.*,t.tracking_code,t.courier_name,t.status AS delivery_status,t.eta,t.updated_at
                         FROM medicine_orders o LEFT JOIN delivery_tracking t ON t.order_id=o.id
                         WHERE o.patient_id=? ORDER BY o.id DESC""",(u["id"],)).fetchall()
    out=[]
    for r in rows:
        x=dict(r)
        x["items"]=[dict(i) for i in conn.execute(
            "SELECT medicine_name,quantity,unit_price FROM medicine_order_items WHERE order_id=?",(r["id"],)
        ).fetchall()]
        tag=conn.execute("SELECT * FROM delivery_rfid WHERE order_id=?",(r["id"],)).fetchone()
        x["rfid"]=rfid_payload(tag)
        out.append(x)
    conn.close(); return jsonify(out)

@app.get("/api/pharmacy/orders/<int:order_id>/track")
def track_medicine_order(order_id):
    u=current_user()
    if not u:return jsonify(error="Login required"),401
    conn=db()
    r=conn.execute("""SELECT o.id,o.total_amount,o.delivery_address,o.phone,o.payment_method,o.placed_at,
                             t.tracking_code,t.courier_name,t.status,t.eta,t.updated_at
                      FROM medicine_orders o JOIN delivery_tracking t ON t.order_id=o.id
                      WHERE o.id=? AND o.patient_id=?""",(order_id,u["id"])).fetchone()
    conn.close()
    return jsonify(dict(r)) if r else (jsonify(error="Order not found"),404)

@app.post("/api/pharmacy/orders/<int:order_id>/demo-status")
def demo_delivery_status(order_id):
    u=current_user()
    if not u or u["role"]!="patient":return jsonify(error="Patient login required"),403
    # Auto-progress only covers warehouse/courier stages. "Delivered" is deliberately NOT
    # reachable from here — it requires the delivery agent to scan the chipless-RFID tag
    # AND enter the customer's OTP via the Delivery portal, so a package can't be
    # "marked delivered" without proof of a real doorstep handoff.
    stages=["Order placed","Packed","Out for delivery"]
    conn=db()
    r=conn.execute("""SELECT t.status FROM delivery_tracking t JOIN medicine_orders o ON o.id=t.order_id
                      WHERE t.order_id=? AND o.patient_id=?""",(order_id,u["id"])).fetchone()
    if not r: conn.close(); return jsonify(error="Order not found"),404
    cur=r["status"]
    nxt=stages[min(stages.index(cur)+1,len(stages)-1)] if cur in stages else cur
    now=datetime.now().isoformat(timespec="seconds")
    if nxt!=cur:
        conn.execute("UPDATE delivery_tracking SET status=?,updated_at=? WHERE order_id=?",(nxt,now,order_id))
        conn.execute("UPDATE medicine_orders SET status=? WHERE id=?",(nxt.lower().replace(" ","_"),order_id))
        if nxt=="Packed": get_or_seal_tag(conn,order_id)          # tag bound to package at packing
        elif nxt=="Out for delivery": mark_dispatch_scan(conn,order_id)  # scanned at courier hand-off
    conn.commit()
    tag=conn.execute("SELECT * FROM delivery_rfid WHERE order_id=?",(order_id,)).fetchone()
    conn.close();return jsonify(ok=True,status=nxt,updated_at=now,rfid=rfid_payload(tag))

@app.get("/api/pharmacy/orders/<int:order_id>/rfid")
def get_order_rfid(order_id):
    u=current_user()
    if not u:return jsonify(error="Login required"),401
    conn=db()
    owner=conn.execute("SELECT patient_id FROM medicine_orders WHERE id=?",(order_id,)).fetchone()
    if not owner or (u["role"]=="patient" and owner["patient_id"]!=u["id"]):
        conn.close(); return jsonify(error="Order not found"),404
    tag=conn.execute("SELECT * FROM delivery_rfid WHERE order_id=?",(order_id,)).fetchone()
    log=conn.execute("SELECT event,result,created_at FROM rfid_scan_log WHERE order_id=? ORDER BY id",(order_id,)).fetchall()
    conn.close()
    if not tag: return jsonify(error="Package not yet sealed with a tag"),404
    return jsonify(rfid=rfid_payload(tag), log=[dict(x) for x in log])

@app.get("/api/pharmacy/orders/<int:order_id>/otp")
def patient_get_otp(order_id):
    """Polled by the patient's Pharmacy page while an order is 'Out for delivery'. Only the
    order's own patient can ever see this OTP — that's the whole point: the delivery agent
    never sees it, the customer reads it out (or shows it) to the agent in person."""
    u=current_user()
    if not u or u["role"]!="patient": return jsonify(error="Patient login required"),403
    conn=db()
    owner=conn.execute("SELECT patient_id FROM medicine_orders WHERE id=?",(order_id,)).fetchone()
    if not owner or owner["patient_id"]!=u["id"]:
        conn.close(); return jsonify(error="Order not found"),404
    otp=active_otp(conn,order_id)
    conn.close()
    if not otp or not otp_is_live(otp):
        return jsonify(active=False)
    remaining=max(0,int((datetime.fromisoformat(otp["expires_at"])-datetime.now()).total_seconds()))
    return jsonify(active=True,otp=otp["otp_code"],expires_in=remaining)

@app.get("/api/delivery/orders")
def delivery_orders():
    ag=current_agent()
    if not ag: return jsonify(error="Delivery login required"),403
    conn=db()
    rows=conn.execute("""SELECT o.id,o.total_amount,o.delivery_address,o.phone,pu.name patient_name,
        t.status delivery_status,t.tracking_code
        FROM medicine_orders o JOIN users pu ON pu.id=o.patient_id JOIN delivery_tracking t ON t.order_id=o.id
        WHERE t.status IN ('Out for delivery','Delivered') ORDER BY o.id DESC LIMIT 40""").fetchall()
    out=[]
    for r in rows:
        x=dict(r)
        tag=conn.execute("SELECT * FROM delivery_rfid WHERE order_id=?",(r["id"],)).fetchone()
        x["rfid"]=rfid_payload(tag)
        otp=active_otp(conn,r["id"])
        x["otp_pending"]=bool(otp and otp_is_live(otp))
        out.append(x)
    conn.close(); return jsonify(out)

@app.post("/api/delivery/orders/<int:order_id>/scan-rfid")
def delivery_scan_rfid(order_id):
    """Delivery agent's handheld scanner reads the printed chipless-RFID code on the package
    at the customer's doorstep. A match does NOT mark the order Delivered by itself — it only
    triggers a 6-digit OTP (2-minute validity) sent to the customer's own MediBridge app."""
    ag=current_agent()
    if not ag: return jsonify(error="Delivery login required"),403
    data=request.get_json() or {}
    scanned_uid=norm_uid(data.get("uid"))
    if not scanned_uid: return jsonify(error="Scan the package tag first."),400
    conn=db()
    order=conn.execute("SELECT * FROM medicine_orders WHERE id=?",(order_id,)).fetchone()
    if not order: conn.close(); return jsonify(error="Order not found."),404
    tag=conn.execute("SELECT * FROM delivery_rfid WHERE order_id=?",(order_id,)).fetchone()
    dstatus=conn.execute("SELECT status FROM delivery_tracking WHERE order_id=?",(order_id,)).fetchone()
    if not tag or not dstatus or dstatus["status"]!="Out for delivery":
        conn.close(); return jsonify(ok=False,error="Package is not out for delivery yet — nothing to scan."),400
    now=datetime.now().isoformat(timespec="seconds")
    if scanned_uid != norm_uid(tag["tag_uid"]):
        conn.execute("""INSERT INTO rfid_scan_log(order_id,event,scanned_uid,result,created_at)
                        VALUES(?,?,?,?,?)""",(order_id,"delivery",scanned_uid,"mismatch",now))
        conn.execute("UPDATE delivery_rfid SET last_scan_result=? WHERE order_id=?",("mismatch",order_id))
        conn.commit(); conn.close()
        return jsonify(ok=False,result="mismatch",scanned_uid=scanned_uid,expected_uid=tag["tag_uid"],
                       message="Tag mismatch — this is not the sealed package for this order."),409
    conn.execute("""UPDATE delivery_rfid SET delivery_scanned=1,delivery_scanned_at=?,last_scan_result=?,agent_id=?
                    WHERE order_id=?""",(now,"match",ag["id"],order_id))
    conn.execute("""INSERT INTO rfid_scan_log(order_id,event,scanned_uid,result,created_at)
                    VALUES(?,?,?,?,?)""",(order_id,"delivery",tag["tag_uid"],"match",now))
    issue_delivery_otp(conn,order_id)
    conn.commit()
    tag=conn.execute("SELECT * FROM delivery_rfid WHERE order_id=?",(order_id,)).fetchone()
    conn.close()
    return jsonify(ok=True,result="match",
                   message="Tag verified. A 6-digit OTP has been sent to the customer's app — ask them for it.",
                   otp_expires_in=OTP_VALIDITY_SECONDS,rfid=rfid_payload(tag))

@app.post("/api/delivery/orders/<int:order_id>/verify-otp")
def delivery_verify_otp(order_id):
    """Delivery agent enters the OTP the customer gave them. Correct + not expired -> Delivered."""
    ag=current_agent()
    if not ag: return jsonify(error="Delivery login required"),403
    data=request.get_json() or {}
    code=(data.get("otp") or "").strip()
    if not code: return jsonify(error="Enter the OTP the customer gave you."),400
    conn=db()
    order=conn.execute("SELECT * FROM medicine_orders WHERE id=?",(order_id,)).fetchone()
    if not order: conn.close(); return jsonify(error="Order not found."),404
    otp=active_otp(conn,order_id)
    if not otp:
        conn.close(); return jsonify(ok=False,error="No OTP has been issued yet — scan the package tag first."),400
    if otp["verified"]:
        conn.close(); return jsonify(ok=False,error="This order is already delivered."),400
    if datetime.now() > datetime.fromisoformat(otp["expires_at"]):
        conn.close()
        return jsonify(ok=False,result="expired",
                       message="OTP expired (2-minute limit). Re-scan the package tag to send a new one."),410
    conn.execute("UPDATE delivery_otp SET attempts=attempts+1 WHERE id=?",(otp["id"],))
    if code != otp["otp_code"]:
        conn.commit(); conn.close()
        return jsonify(ok=False,result="wrong_otp",message="Incorrect OTP. Ask the customer to re-check it."),409
    now=datetime.now().isoformat(timespec="seconds")
    conn.execute("UPDATE delivery_otp SET verified=1,verified_at=? WHERE id=?",(now,otp["id"]))
    conn.execute("UPDATE delivery_tracking SET status='Delivered',updated_at=? WHERE order_id=?",(now,order_id))
    conn.execute("UPDATE medicine_orders SET status='delivered' WHERE id=?",(order_id,))
    conn.execute("""INSERT INTO rfid_scan_log(order_id,event,scanned_uid,result,created_at)
                    VALUES(?,?,?,?,?)""",(order_id,"otp_verify","******","delivered",now))
    conn.commit()
    tag=conn.execute("SELECT * FROM delivery_rfid WHERE order_id=?",(order_id,)).fetchone()
    conn.close()
    return jsonify(ok=True,result="delivered",status="Delivered",updated_at=now,rfid=rfid_payload(tag))


def esc_html(v):
    return str(v or '').replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;')

BILL_HTML="""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>MediBridge Digital Bill</title><style>body{font-family:Inter,Segoe UI,Arial,sans-serif;background:#f4f8f9;color:#17313d;margin:0}.bill{max-width:760px;margin:35px auto;background:#fff;border-radius:20px;padding:32px;box-shadow:0 18px 45px rgba(11,31,42,.1)}.head{display:flex;justify-content:space-between;gap:20px;border-bottom:2px solid #e3ecef;padding-bottom:18px}.brand{font-size:28px;font-weight:900;color:#0b1f2a}.muted{color:#72838c;font-size:12px;line-height:1.5}.items{width:100%;border-collapse:collapse;margin-top:24px}.items th,.items td{text-align:left;padding:11px;border-bottom:1px solid #e3ecef}.items th{font-size:11px;text-transform:uppercase;color:#72838c}.total{text-align:right;font-size:22px;font-weight:900;margin-top:18px}.actions{display:flex;gap:10px;margin-top:24px}.btn{border:0;border-radius:11px;padding:11px 16px;background:#16a38f;color:#fff;font-weight:800;cursor:pointer;text-decoration:none}.secondary{background:#edf4f5;color:#23515b}@media print{body{background:#fff}.bill{box-shadow:none;margin:0;max-width:none}.actions{display:none}}</style></head><body><div class='bill'><div class='head'><div><div class='brand'>MediBridge</div><div class='muted'>Digital medicine bill</div></div><div style='text-align:right'><b>Invoice #{{ order.id }}</b><div class='muted'>{{ order.placed_at }}</div><div class='muted'>{{ order.tracking_code or '' }}</div></div></div><p><b>Patient:</b> {{ user['name'] }}<br><span class='muted'>{{ user['email'] }}</span></p><table class='items'><tr><th>Medicine / item</th><th>Qty</th><th>Unit price</th><th>Amount</th></tr>{{ items|safe }}</table><div class='total'>Total: ₹{{ '%.2f'|format(order.total_amount) }}</div><div class='muted' style='margin-top:12px'>Payment: {{ order.payment_method }} · Delivery: {{ order.delivery_status or order.status }}</div><div class='actions'><button class='btn' onclick='window.print()'>🖨 Print / Save PDF</button><a class='btn secondary' href='/pharmacy'>← Back to Pharmacy</a></div></div></body></html>"""

PHARMACY_HTML="""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>MediBridge Pharmacy</title><style>
:root{--navy:#0b1f2a;--teal:#16a38f;--mint:#dff7f1;--bg:#f5f8fa;--text:#17313d;--muted:#72838c;--line:#dfe9ed;--shadow:0 12px 30px rgba(11,31,42,.07)}
*{box-sizing:border-box}body{font-family:Inter,Segoe UI,Arial,sans-serif;margin:0;background:var(--bg);color:var(--text)}
.wrap{max-width:1180px;margin:auto;padding:30px 26px 60px}
.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:22px;gap:14px}
.top h1{margin:0;font-size:27px;letter-spacing:-.5px}.back{color:var(--teal);text-decoration:none;font-weight:700;font-size:14px;white-space:nowrap}
.freebar{display:flex;align-items:center;gap:8px;background:var(--mint);color:#116d61;font-weight:700;font-size:13px;padding:10px 16px;border-radius:14px;margin-bottom:22px}
.layout{display:grid;grid-template-columns:1fr 340px;gap:20px;align-items:start}
.card{background:#fff;border:1px solid var(--line);border-radius:18px;padding:20px;box-shadow:var(--shadow)}
.card h2{margin:0 0 16px;font-size:18px}
.catalog{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:14px}
.med{border:1px solid var(--line);border-radius:15px;padding:16px;display:flex;flex-direction:column;gap:8px;background:#fbfdfe}
.med .icon{font-size:22px}.med h3{margin:0;font-size:15px;line-height:1.3}
.tag{display:inline-block;padding:4px 9px;border-radius:20px;background:#eef5f6;color:#47717b;font-size:11px;font-weight:700;width:fit-content}
.desc{color:var(--muted);font-size:12.5px;line-height:1.5;min-height:34px}
.price{font-weight:800;font-size:17px;color:var(--navy)}
.stock{font-size:11.5px;color:var(--muted)}.stock.low{color:#b5651d}
.rxnote{font-size:11.5px;color:#8b3030;background:#fff0f0;border-radius:9px;padding:6px 8px}
.qtyrow{display:flex;align-items:center;justify-content:space-between;margin-top:auto;gap:8px}
.stepper{display:flex;align-items:center;border:1px solid var(--line);border-radius:10px;overflow:hidden}
.stepper button{width:30px;height:30px;border:0;background:#f2f6f7;color:var(--navy);font-weight:800;cursor:pointer}
.stepper span{width:28px;text-align:center;font-weight:700;font-size:13px}
.addbtn{border:0;border-radius:10px;padding:9px 12px;background:var(--teal);color:#fff;font-weight:700;font-size:12.5px;cursor:pointer;white-space:nowrap}
.addbtn:disabled{background:#dfe6e8;color:#93a1a6;cursor:not-allowed}
.cartcard{position:sticky;top:20px}
.cartline{display:flex;justify-content:space-between;gap:8px;padding:9px 0;border-bottom:1px solid var(--line);font-size:13px}
.cartline:last-child{border-bottom:0}.cartline .rm{color:#b33;cursor:pointer;font-size:12px;background:none;border:0;padding:0}
.empty-cart{color:var(--muted);font-size:13px;padding:6px 0}
label.f{font-size:12px;color:var(--muted);display:block;margin:10px 0 4px}
input,select{width:100%;box-sizing:border-box;padding:11px;border:1px solid var(--line);border-radius:10px;background:#fbfdfe;font-size:13.5px}
.totalrow{display:flex;justify-content:space-between;align-items:center;margin:14px 0;font-weight:800;font-size:16px}
.placebtn{width:100%;border:0;border-radius:11px;padding:12px;background:var(--teal);color:#fff;font-weight:800;cursor:pointer;font-size:14px}
.placebtn:disabled{background:#dfe6e8;color:#93a1a6;cursor:not-allowed}
.orders{margin-top:20px}
.order{border:1px solid var(--line);border-radius:16px;padding:17px;margin-bottom:14px}
.order .head{display:flex;justify-content:space-between;flex-wrap:wrap;gap:6px;align-items:baseline}
.order .items{color:var(--muted);font-size:12.5px;margin:6px 0 14px}
.tracker{position:relative;margin:26px 4px 10px}
.tracker .line{position:absolute;top:11px;left:0;right:0;height:4px;background:#eef1f3;border-radius:2px}
.tracker .fill{position:absolute;top:11px;left:0;height:4px;background:var(--teal);border-radius:2px;transition:width .8s ease}
.tracker .nodes{display:flex;justify-content:space-between;position:relative}
.tracker .node{display:flex;flex-direction:column;align-items:center;gap:6px;width:70px}
.tracker .dot{width:24px;height:24px;border-radius:50%;background:#eef1f3;border:3px solid #fff;box-shadow:0 0 0 1px #eef1f3;display:grid;place-items:center;font-size:11px;transition:.3s}
.tracker .dot.on{background:var(--teal);box-shadow:0 0 0 1px var(--teal)}
.tracker .lbl{font-size:10.5px;color:var(--muted);text-align:center}.tracker .lbl.on{color:var(--navy);font-weight:700}
.truck{position:absolute;top:-16px;font-size:18px;transition:left .8s ease;transform:translateX(-50%)}
.orderfoot{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-top:10px;font-size:12px;color:var(--muted)}
.livebtn{border:0;border-radius:10px;padding:8px 13px;background:var(--navy);color:#fff;font-weight:700;font-size:12px;cursor:pointer}
.livebtn:disabled{background:#c9d2d6;cursor:not-allowed}
.livebtn.playing{background:var(--teal)}
.rfidbox{margin-top:16px;border:1px dashed var(--line);border-radius:14px;padding:14px;background:#fbfdfe}
.rfidhead{display:flex;align-items:center;gap:8px;font-weight:800;font-size:12.5px;color:var(--navy)}
.taguid{font-family:'Courier New',monospace;font-weight:700;letter-spacing:.5px;background:#eef5f6;color:#2c545c;border-radius:8px;padding:2px 7px;font-size:12px}
.custody{display:flex;flex-wrap:wrap;gap:10px;margin-top:10px}
.custep{display:flex;align-items:center;gap:6px;font-size:11.5px;color:var(--muted);background:#f2f6f7;border-radius:20px;padding:5px 10px}
.custep.on{color:#116d61;background:var(--mint);font-weight:700}
.nfcpanel{margin-top:12px;border-top:1px solid var(--line);padding-top:12px;display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap}
.nfcbtn{display:flex;align-items:center;gap:8px;border:0;border-radius:10px;padding:9px 14px;background:var(--navy);color:#fff;font-weight:800;cursor:pointer;font-size:12.5px}
.nfcbtn .pulse{width:9px;height:9px;border-radius:50%;background:#5ce0c6;box-shadow:0 0 0 0 rgba(92,224,198,.7);animation:pulse 1.4s infinite}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(92,224,198,.6)}70%{box-shadow:0 0 0 8px rgba(92,224,198,0)}100%{box-shadow:0 0 0 0 rgba(92,224,198,0)}}
.tamperlink{background:none;border:0;color:#b5651d;font-size:11px;cursor:pointer;text-decoration:underline}
.scanmsg{font-size:12px;border-radius:9px;padding:8px 10px;margin-top:10px}
.scanmsg.ok{background:#e9f9f0;color:#116d3c}.scanmsg.fail{background:#fdecec;color:#a12727}
.scanning{opacity:.65;pointer-events:none}
@media(max-width:820px){.layout{grid-template-columns:1fr}.cartcard{position:static}}
</style></head><body><div class='wrap'>
<div class='top'><div><h1>🛒 Pharmacy</h1><div class='muted' style='font-size:13px;margin-top:3px'>Order medicines and track delivery, right from MediBridge.</div></div><a class='back' href='/'>← Back to MediBridge</a></div>
<div class='freebar'>🚚 Free delivery on every order</div>
<div class='layout'>
<div class='card'><h2>Medicine store</h2><div id='catalog' class='catalog'>Loading…</div></div>
<div class='card cartcard'><h2>Your cart</h2><div id='cartlines'><div class='empty-cart'>Your cart is empty.</div></div><label class='f' id='sanitizerWrap' style='display:none'><input type='checkbox' id='sanitizer' onchange='renderCart()' style='width:auto;margin-right:8px'> Add MediBridge sanitizer (₹5) with medicines worth ₹10+</label>
<div class='totalrow'><span>Total</span><span id='total'>₹0.00</span></div>
<label class='f'>Delivery address</label><input id='address' placeholder='House no., street, city'>
<label class='f'>Phone number</label><input id='phone' placeholder='10-digit phone number'>
<label class='f'>Payment method</label><select id='payment' onchange='paymentFields()'><option>UPI</option><option>Debit Card</option><option>Cash on Delivery</option></select><div id='payFields'><label class='f'>UPI ID</label><input id='upi' placeholder='name@bank'></div>
<button class='placebtn' id='placeBtn' onclick='placeOrder()' disabled>Place order</button></div>
</div>
<div class='card orders'><h2>My medicine buying history</h2><div id='orders'>Loading…</div></div>
</div>
<script>
let meds=[],cart={};const $=x=>document.getElementById(x);
const ICONS={"Pain & Fever":"🌡️","Hydration":"💧","Digestive Care":"🩺","Vitamins":"🍊","Prescription":"📋"};
const STAGES=[{k:'Order placed',i:'📦'},{k:'Packed',i:'📦'},{k:'Out for delivery',i:'🚚'},{k:'Delivered',i:'✅'}];
let liveTimers={};
function esc(s){return String(s??'').replace(/[&<>'\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','\"':'&quot;'}[c]))}
async function load(){meds=await(await fetch('/api/pharmacy/medicines')).json();renderCatalog();renderCart();orders()}
function renderCatalog(){$('catalog').innerHTML=meds.map(m=>{let qty=cart[m.id]||0,low=m.stock>0&&m.stock<10;
return `<div class='med'><div class='icon'>${ICONS[m.category]||'💊'}</div><span class='tag'>${esc(m.category)}</span><h3>${esc(m.name)}</h3><div class='desc'>${esc(m.description)}</div>
<div class='price'>₹${Number(m.price).toFixed(2)}</div><div class='stock ${low?'low':''}'>${m.stock<1?'Out of stock':low?`Only ${m.stock} left`:m.stock+' in stock'}</div>
${m.requires_prescription?`<div class='rxnote'>⚕️ Prescription required</div>`:`<div class='qtyrow'>${qty>0?`<div class='stepper'><button onclick='changeQty(${m.id},-1)'>−</button><span>${qty}</span><button onclick='changeQty(${m.id},1)'>+</button></div>`:`<span></span>`}
<button class='addbtn' ${m.stock<1?'disabled':''} onclick='changeQty(${m.id},1)'>${qty>0?'Add more':'Add to cart'}</button></div>`}</div>`}).join('')}
function changeQty(id,d){let m=meds.find(x=>x.id===id);let q=(cart[id]||0)+d;if(q<=0){delete cart[id]}else if(q<=Math.min(20,m.stock)){cart[id]=q}renderCatalog();renderCart()}
function paymentFields(){let p=$('payment').value;$('payFields').innerHTML=p==='UPI'?`<label class='f'>UPI ID</label><input id='upi' placeholder='name@bank'>`:p==='Debit Card'?`<label class='f'>Cardholder name</label><input id='holder'><label class='f'>Debit card number</label><input id='card' inputmode='numeric' maxlength='19' placeholder='1234 5678 9012 3456'>`:''}
function renderCart(){let ids=Object.keys(cart);let n=0;
$('cartlines').innerHTML=ids.length?ids.map(id=>{let m=meds.find(x=>x.id==id),line=m.price*cart[id];n+=line;
return `<div class='cartline'><span>${esc(m.name)} × ${cart[id]}</span><span>₹${line.toFixed(2)} <button class='rm' onclick='changeQty(${id},-cart[${id}])'>remove</button></span></div>`}).join(''):`<div class='empty-cart'>Your cart is empty. Add a medicine to get started.</div>`;
let sanitizer=$('sanitizer')?.checked && n>=10; if($('sanitizerWrap')) $('sanitizerWrap').style.display=n>=10?'block':'none'; if(n<10&&$('sanitizer')) $('sanitizer').checked=false; if(sanitizer)n+=5; $('total').textContent='₹'+n.toFixed(2);$('placeBtn').disabled=!ids.length}
async function placeOrder(){let items=Object.entries(cart).map(([medicine_id,quantity])=>({medicine_id:Number(medicine_id),quantity}));if(!items.length)return;
if(!$('address').value.trim()){alert('Add a delivery address.');return}
let r=await fetch('/api/pharmacy/orders',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({items,delivery_address:$('address').value,phone:$('phone').value,payment_method:$('payment').value,sanitizer_added:!!$('sanitizer')?.checked,upi_id:$('upi')?.value||'',card_holder:$('holder')?.value||'',card_number:$('card')?.value||''})});
let x=await r.json();if(!r.ok)return alert(x.error||'Could not place order');cart={};if($('sanitizer'))$('sanitizer').checked=false;renderCatalog();renderCart();load();$('orders').scrollIntoView({behavior:'smooth'})}
async function orders(){let xs=await(await fetch('/api/pharmacy/orders')).json();if(!xs.length){$('orders').innerHTML=\"<div class='muted'>No medicine orders yet — your purchases will appear here.</div>\";return}
$('orders').innerHTML=xs.map(o=>{let st=o.delivery_status||o.status||'Order placed';return renderOrder(o,st)}).join('')}
function rfidBox(o,st){let tag=o.rfid;
if(!tag)return `<div class='rfidbox'><div class='rfidhead'>🏷️ Chipless RFID package tag</div><div class='muted' style='font-size:11.5px;margin-top:4px'>A tag will be printed on your package once the pharmacy packs your order.</div></div>`;
let steps=[{on:true,lbl:'🏷️ Tag printed on package'},{on:!!tag.dispatch_scanned,lbl:'📡 Scanned at courier pickup'},{on:!!tag.delivery_scanned,lbl:'✅ Scanned by delivery agent'}];
let otpPanel='';
if(st==='Out for delivery'&&tag.delivery_scanned){
otpPanel=`<div class='nfcpanel' id='otpbox-${o.id}'><div class='muted' style='font-size:11.5px'>Checking for your delivery OTP…</div></div>`;
}else if(st==='Out for delivery'){
otpPanel=`<div class='nfcpanel'><div style='font-size:11.5px;color:var(--muted);max-width:320px'>When your delivery agent reaches your address and scans the chipless RFID tag on the package, a 6-digit OTP will appear here — read it out to the agent to confirm delivery. It's valid for 2 minutes.</div></div>`;
}else if(st==='Delivered'){
otpPanel=`<div class='nfcpanel'><div class='scanmsg ok' style='margin-top:0'>✅ Delivered — verified by chipless RFID scan + OTP. Tag <span class='taguid'>${esc(tag.tag_uid)}</span>.</div></div>`;
}
return `<div class='rfidbox'><div class='rfidhead'>🏷️ Chipless RFID tag <span class='taguid'>${esc(tag.tag_uid)}</span></div>
<div class='custody'>${steps.map(s=>`<div class='custep ${s.on?'on':''}'>${s.lbl}</div>`).join('')}</div>${otpPanel}</div>`}
function renderOrder(o,st){let ix=Math.max(0,STAGES.findIndex(s=>s.k===st));let pct=(ix/(STAGES.length-1))*100;let done=st==='Delivered';
let liveDisabled=done||st==='Out for delivery';
return `<div class='order' id='order-${o.id}'><div class='head'><b>Order #${o.id}</b><span class='muted'>${esc(o.tracking_code||'')}</span><b>₹${Number(o.total_amount).toFixed(2)}</b></div>
<div class='items'>${o.items.map(i=>`${esc(i.medicine_name)} × ${i.quantity}`).join(', ')}</div><div style='margin-top:8px'><a class='btn secondary' style='text-decoration:none;padding:7px 10px;font-size:12px' href='/pharmacy/bill/${o.id}' target='_blank'>🧾 Digital bill</a></div>
<div class='tracker'><div class='truck' style='left:${pct}%'>${done?'✅':'🚚'}</div><div class='line'></div><div class='fill' style='width:${pct}%'></div>
<div class='nodes'>${STAGES.map((s,i)=>`<div class='node'><div class='dot ${i<=ix?'on':''}'>${i<=ix?'✓':''}</div><div class='lbl ${i<=ix?'on':''}'>${s.k}</div></div>`).join('')}</div></div>
<div class='orderfoot'><span>🚚 Free delivery · Courier: ${esc(o.courier_name||'MediBridge Delivery')} · ETA: ${esc(o.eta||'—')}</span>
<button class='livebtn' id='live-${o.id}' onclick='toggleLive(${o.id})' ${liveDisabled?'disabled':''}>${done?'Delivered':st==='Out for delivery'?'Awaiting agent scan':'▶ Simulate live tracking'}</button></div>
${rfidBox(o,st)}</div>`}
async function toggleLive(id){let btn=$('live-'+id);if(liveTimers[id]){clearInterval(liveTimers[id]);delete liveTimers[id];btn.textContent='▶ Simulate live tracking';btn.classList.remove('playing');return}
btn.textContent='⏸ Tracking live…';btn.classList.add('playing');
liveTimers[id]=setInterval(async()=>{let r=await fetch(`/api/pharmacy/orders/${id}/demo-status`,{method:'POST'});let x=await r.json();
let xs=await(await fetch('/api/pharmacy/orders')).json();let o=xs.find(y=>y.id===id);if(o)document.getElementById('order-'+id).outerHTML=renderOrder(o,x.status);
if(x.status==='Out for delivery')startOtpPoll(id);
if(x.status==='Out for delivery'||x.status==='Delivered'){clearInterval(liveTimers[id]);delete liveTimers[id]}else{let b=$('live-'+id);if(b){b.textContent='⏸ Tracking live…';b.classList.add('playing')}}},1800)}
let otpTimers={};
function startOtpPoll(id){if(otpTimers[id])return;
otpTimers[id]=setInterval(async()=>{let box=$('otpbox-'+id);if(!box){clearInterval(otpTimers[id]);delete otpTimers[id];return}
let r=await fetch(`/api/pharmacy/orders/${id}/otp`);let x=await r.json();
if(!x.active){box.innerHTML=`<div class='muted' style='font-size:11.5px'>Waiting for the delivery agent to scan your package…</div>`;return}
box.innerHTML=`<div style='text-align:center'><div class='muted' style='font-size:11px;margin-bottom:4px'>Give this OTP to your delivery agent</div>
<div style='font-family:Courier New,monospace;font-weight:800;font-size:26px;letter-spacing:4px;color:var(--navy)'>${esc(x.otp)}</div>
<div class='muted' style='font-size:11px;margin-top:2px'>Expires in ${Math.floor(x.expires_in/60)}:${String(x.expires_in%60).padStart(2,'0')}</div></div>`;
},1000)}
// Background poll: catches status changes made independently by the delivery agent's app
// (different login/device), and starts the OTP countdown as soon as a tag scan lands.
setInterval(async()=>{
let xs=await(await fetch('/api/pharmacy/orders')).json();
xs.forEach(o=>{let st=o.delivery_status||o.status||'Order placed';let card=document.getElementById('order-'+o.id);
if(!card)return;
let currentlyDelivered=card.querySelector('.livebtn')&&card.querySelector('.livebtn').textContent==='Delivered';
let needsOtpBox=st==='Out for delivery'&&o.rfid&&o.rfid.delivery_scanned&&!$('otpbox-'+o.id);
let justDelivered=st==='Delivered'&&!currentlyDelivered;
if(needsOtpBox||justDelivered){card.outerHTML=renderOrder(o,st);if(st==='Out for delivery')startOtpPoll(o.id)}})},3000);
load();
</script></body></html>"""

NFC_HTML="""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>MediBridge · NFC Smart Patient Card</title><style>
:root{--navy:#0b1f2a;--teal:#16a38f;--mint:#dff7f1;--bg:#f5f8fa;--text:#17313d;--muted:#72838c;--line:#dfe9ed;--shadow:0 12px 30px rgba(11,31,42,.07)}
*{box-sizing:border-box}body{font-family:Inter,Segoe UI,Arial,sans-serif;margin:0;background:var(--bg);color:var(--text)}
.wrap{max-width:1180px;margin:auto;padding:30px 26px 60px}
.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:22px;gap:14px;flex-wrap:wrap}
.top h1{margin:0;font-size:27px;letter-spacing:-.5px}.back{color:var(--teal);text-decoration:none;font-weight:700;font-size:14px;white-space:nowrap}
.freebar{display:flex;align-items:center;gap:8px;background:var(--mint);color:#116d61;font-weight:700;font-size:13px;padding:10px 16px;border-radius:14px;margin-bottom:22px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}
.card{background:#fff;border:1px solid var(--line);border-radius:18px;padding:20px;box-shadow:var(--shadow);margin-bottom:20px}
.card h2{margin:0 0 4px;font-size:17px}.card .sub{color:var(--muted);font-size:12px;margin-bottom:14px}
label.f{font-size:12px;color:var(--muted);display:block;margin:10px 0 4px}
input,select{width:100%;box-sizing:border-box;padding:11px;border:1px solid var(--line);border-radius:10px;background:#fbfdfe;font-size:13.5px;font-family:inherit}
.uidinput{font-family:'Courier New',monospace;font-weight:700;letter-spacing:.5px}
.row{display:flex;gap:10px;align-items:end}.row>div{flex:1}
.btn{border:0;border-radius:10px;padding:11px 16px;background:var(--teal);color:#fff;font-weight:800;cursor:pointer;font-size:13px;white-space:nowrap}
.btn.navy{background:var(--navy)}.btn.ghost{background:#f2f6f7;color:var(--navy)}
.btn:disabled{background:#dfe6e8;color:#93a1a6;cursor:not-allowed}
.hint{font-size:11px;color:var(--muted);margin-top:8px;line-height:1.5}
.result{margin-top:14px;border-radius:12px;padding:12px 14px;font-size:13px;display:none}
.result.ok{display:block;background:#e9f9f0;color:#116d3c}.result.fail{display:block;background:#fdecec;color:#a12727}
.result.info{display:block;background:#eef5f6;color:#2c545c}
.taguid{font-family:'Courier New',monospace;font-weight:700;background:#00000010;border-radius:6px;padding:1px 6px}
.tbl{width:100%;border-collapse:collapse;margin-top:10px;font-size:12.5px}
.tbl th{text-align:left;color:var(--muted);font-weight:700;font-size:11px;padding:6px 8px;border-bottom:1px solid var(--line)}
.tbl td{padding:8px;border-bottom:1px solid var(--line)}
.pill{display:inline-block;padding:3px 9px;border-radius:20px;font-size:11px;font-weight:700}
.pill.yes{background:var(--mint);color:#116d61}.pill.no{background:#f2f6f7;color:#8a9aa1}
.rxblock{border:1px solid var(--line);border-radius:12px;padding:10px 12px;margin-top:8px;font-size:12.5px}
.rxblock b{font-size:13px}
@media(max-width:900px){.grid{grid-template-columns:1fr}.row{flex-direction:column;align-items:stretch}}
</style></head><body><div class='wrap'>
<div class='top'><div><h1>📶 NFC Smart Patient Card</h1><div class='muted' style='font-size:13px;margin-top:3px'>Tap (or simulate) a card to identify a patient across MediBridge — staff console.</div></div><a class='back' href='/'>← Back to MediBridge</a></div>
<div class='freebar'>🪪 The card only ever carries a UID. No medical data is stored on it — every scan looks the patient up in MediBridge's existing records.</div>
<div class='grid'>

<div class='card'>
<h2>🆕 Register a card</h2><div class='sub'>Admin/front-desk: link a physical (or simulated) card UID to a patient.</div>
<label class='f'>Patient</label><select id='regPatient'></select>
<label class='f'>Card UID</label>
<div class='row'><div><input id='regUid' class='uidinput' placeholder='Tap card, or type a test UID' onkeydown='if(event.key==="Enter")registerCard()'></div>
<button class='btn navy' onclick='registerCard()'>Register</button></div>
<div class='hint'>A real reader in USB-keyboard (HID) mode can tap into this exact field — it types the UID then Enter, same as a barcode scanner. Simulation and hardware share this one input and one backend endpoint.</div>
<div id='regResult' class='result'></div>
</div>

<div class='card'>
<h2>✅ Appointment check-in</h2><div class='sub'>Tap a patient's card to check them in for today's appointment.</div>
<div class='row'><div><input id='ciUid' class='uidinput' placeholder='Card UID' onkeydown='if(event.key==="Enter")scan("checkin")'></div>
<button class='btn' onclick='scan("checkin")'>📡 Simulate scan</button></div>
<div id='ciResult' class='result'></div>
<div class='sub' style='margin-top:16px'>Today's appointments</div>
<table class='tbl'><thead><tr><th>Token</th><th>Patient</th><th>Time</th><th>Checked in</th></tr></thead><tbody id='ciTable'></tbody></table>
</div>

<div class='card'>
<h2>💊 Pharmacy lookup</h2><div class='sub'>Tap a patient's card to pull up their prescriptions and orders.</div>
<div class='row'><div><input id='phUid' class='uidinput' placeholder='Card UID' onkeydown='if(event.key==="Enter")scan("pharmacy")'></div>
<button class='btn' onclick='scan("pharmacy")'>📡 Simulate scan</button></div>
<div id='phResult' class='result'></div>
<div id='phData'></div>
</div>

<div class='card'>
<h2>🚚 Delivery portal</h2><div class='sub'>Package chipless-RFID scanning and OTP delivery confirmation now happen on the separate Delivery agent portal, not here.</div>
<a class='btn navy' style='display:inline-block;text-decoration:none' href='/delivery/login'>Open Delivery portal →</a>
</div>

</div>
</div>
<script>
const $=x=>document.getElementById(x);
function esc(s){return String(s??'').replace(/[&<>'\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','\"':'&quot;'}[c]))}
async function loadPatients(){let ps=await(await fetch('/api/patients')).json();
$('regPatient').innerHTML=ps.map(p=>`<option value='${p.id}'>${esc(p.name)} — ${esc(p.email)}${p.nfc_uid?' (card on file)':''}</option>`).join('')}
async function registerCard(){let patient_id=$('regPatient').value,uid=$('regUid').value.trim();if(!uid)return;
let r=await fetch('/api/nfc/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({patient_id,uid})});
let x=await r.json();let box=$('regResult');
if(r.ok){box.className='result ok';box.innerHTML=`✅ Card <span class='taguid'>${esc(x.uid)}</span> linked.`;$('regUid').value='';loadPatients()}
else{box.className='result fail';box.innerHTML=`⚠️ ${esc(x.error||'Could not register card')}`}}
async function scan(context){let uidBox=context==='checkin'?$('ciUid'):$('phUid');let uid=uidBox.value.trim();if(!uid)return;
let r=await fetch('/api/nfc/scan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({uid,context})});
let x=await r.json();
if(context==='checkin'){let box=$('ciResult');
if(!r.ok||!x.ok){box.className='result fail';box.innerHTML=`⚠️ ${esc(x.message||x.error||'Card not recognised')}`}
else{let a=x.appointment;box.className='result '+(x.result==='already_checked_in'?'info':'ok');
box.innerHTML=`${x.result==='already_checked_in'?'ℹ️ Already':'✅'} checked in: <b>${esc(x.patient.name)}</b> — token #${a.token_number} with ${esc(a.doctor_name)} at ${esc(a.time)}, ${esc(a.venue||'')}`}
loadCheckins()}
else{let box=$('phResult');
if(!r.ok||!x.ok){box.className='result fail';box.innerHTML=`⚠️ ${esc(x.message||x.error||'Card not recognised')}`;$('phData').innerHTML='';return}
box.className='result ok';box.innerHTML=`✅ Identified: <b>${esc(x.patient.name)}</b> (${esc(x.patient.email)})`;
let rx=x.prescriptions||[],ords=x.orders||[];
$('phData').innerHTML=(rx.length?`<div class='sub' style='margin-top:14px'>Prescriptions</div>`+rx.map(p=>`<div class='rxblock'><b>${esc(p.diagnosis||'Prescription')}</b> — Dr. ${esc(p.doctor_name)}<br>${p.items.map(i=>`${esc(i.medicine)} · ${esc(i.dosage)} · ${esc(i.frequency)} · ${esc(i.duration)}`).join('<br>')}</div>`).join(''):`<div class='sub' style='margin-top:14px'>No prescriptions on file.</div>`)
+(ords.length?`<div class='sub' style='margin-top:14px'>Pharmacy orders</div>`+ords.map(o=>`<div class='rxblock'>Order #${o.id} · ₹${Number(o.total_amount).toFixed(2)} · <span class='pill ${o.delivery_status==='Delivered'?'yes':'no'}'>${esc(o.delivery_status||o.status||'placed')}</span><br>${o.items.map(i=>`${esc(i.medicine_name)} × ${i.quantity}`).join(', ')}</div>`).join(''):'')}}
async function loadCheckins(){let rows=await(await fetch('/api/nfc/checkins-today')).json();
$('ciTable').innerHTML=rows.length?rows.map(a=>`<tr><td>#${a.token_number}</td><td>${esc(a.patient_name||'')}</td><td>${esc(a.time)}</td><td>${a.checked_in?`<span class='pill yes'>✓ ${esc((a.checked_in_at||'').slice(11,16))}</span>`:`<span class='pill no'>Not yet</span>`}</td></tr>`).join(''):`<tr><td colspan='4' class='muted'>No appointments today.</td></tr>`}
loadPatients();loadCheckins();
</script></body></html>"""

DELIVERY_LOGIN_HTML="""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>MediBridge · Delivery Login</title><style>
:root{--navy:#0b1f2a;--teal:#16a38f;--mint:#dff7f1;--bg:#f5f8fa;--text:#17313d;--muted:#72838c;--line:#dfe9ed;--shadow:0 12px 30px rgba(11,31,42,.07)}
*{box-sizing:border-box}body{font-family:Inter,Segoe UI,Arial,sans-serif;margin:0;background:var(--bg);color:var(--text);display:flex;align-items:center;justify-content:center;min-height:100vh}
.card{background:#fff;border:1px solid var(--line);border-radius:18px;padding:32px;box-shadow:var(--shadow);width:100%;max-width:360px}
.card h1{margin:0 0 4px;font-size:22px}.card .sub{color:var(--muted);font-size:12.5px;margin-bottom:20px}
label{font-size:12px;color:var(--muted);display:block;margin:12px 0 4px}
input{width:100%;box-sizing:border-box;padding:11px;border:1px solid var(--line);border-radius:10px;background:#fbfdfe;font-size:13.5px;font-family:inherit}
button{width:100%;margin-top:18px;border:0;border-radius:10px;padding:12px;background:var(--navy);color:#fff;font-weight:800;cursor:pointer;font-size:14px}
.err{background:#fdecec;color:#a12727;border-radius:10px;padding:9px 12px;font-size:12.5px;margin-top:14px}
.hint{font-size:11px;color:var(--muted);margin-top:16px;line-height:1.5}
.back{display:block;text-align:center;margin-top:14px;color:var(--teal);text-decoration:none;font-weight:700;font-size:12.5px}
</style></head><body>
<form class='card' method='post'>
<h1>🚚 Delivery Login</h1><div class='sub'>Agent portal — chipless RFID scan &amp; OTP delivery confirmation.</div>
<label>Email</label><input name='email' type='email' required placeholder='delivery@medibridge.local'>
<label>Password</label><input name='password' type='password' required placeholder='••••••••'>
<button type='submit'>Log in</button>
{% if error %}<div class='err'>{{ error }}</div>{% endif %}

<a class='back' href='/'>← Back to MediBridge</a>
</form>
</body></html>"""

DELIVERY_HTML="""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>MediBridge · Delivery</title><style>
:root{--navy:#0b1f2a;--teal:#16a38f;--mint:#dff7f1;--bg:#f5f8fa;--text:#17313d;--muted:#72838c;--line:#dfe9ed;--shadow:0 12px 30px rgba(11,31,42,.07)}
*{box-sizing:border-box}body{font-family:Inter,Segoe UI,Arial,sans-serif;margin:0;background:var(--bg);color:var(--text)}
.wrap{max-width:720px;margin:auto;padding:26px 20px 60px}
.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:18px;gap:10px}
.top h1{margin:0;font-size:23px}.top .who{font-size:12.5px;color:var(--muted)}
.logout{color:var(--teal);text-decoration:none;font-weight:700;font-size:13px}
.card{background:#fff;border:1px solid var(--line);border-radius:18px;padding:18px;box-shadow:var(--shadow);margin-bottom:16px}
.card h3{margin:0 0 2px;font-size:16px}.addr{font-size:12.5px;color:var(--muted);margin:4px 0 10px}
.pill{display:inline-block;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700}
.pill.out{background:#fff4e0;color:#8a5a00}.pill.done{background:var(--mint);color:#116d61}
.row{display:flex;gap:8px;margin-top:10px}.row input{flex:1;box-sizing:border-box;padding:10px;border:1px solid var(--line);border-radius:9px;font-size:13.5px;font-family:'Courier New',monospace;font-weight:700}
.row button{border:0;border-radius:9px;padding:10px 14px;background:var(--navy);color:#fff;font-weight:800;cursor:pointer;font-size:12.5px;white-space:nowrap}
.row button:disabled{background:#dfe6e8;color:#93a1a6;cursor:not-allowed}
.msg{margin-top:10px;border-radius:9px;padding:8px 10px;font-size:12.5px;display:none}
.msg.ok{display:block;background:#e9f9f0;color:#116d3c}.msg.fail{display:block;background:#fdecec;color:#a12727}.msg.info{display:block;background:#eef5f6;color:#2c545c}
.step{font-size:11.5px;color:var(--muted);margin-top:4px}
.empty{color:var(--muted);font-size:13px;text-align:center;padding:30px 0}
</style></head><body><div class='wrap'>
<div class='top'><div><h1>🚚 Delivery</h1><div class='who'>Logged in as {{ agent['name'] }}</div></div><a class='logout' href='/delivery/logout'>Log out</a></div>
<div id='list'>Loading…</div>
</div>
<script>
const $=x=>document.getElementById(x);
function esc(s){return String(s??'').replace(/[&<>'\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','\"':'&quot;'}[c]))}
async function load(){let xs=await(await fetch('/api/delivery/orders')).json();
if(!xs.length){$('list').innerHTML="<div class='empty'>No orders out for delivery right now.</div>";return}
$('list').innerHTML=xs.map(o=>card(o)).join('')}
function card(o){let done=o.delivery_status==='Delivered';let tag=o.rfid;
let scanStep=tag&&tag.delivery_scanned?`<div class='step'>✅ Package tag scanned — ${o.otp_pending?'OTP sent to customer, awaiting entry':'OTP already used'}</div>`:`<div class='step'>Scan the chipless RFID tag printed on the package first.</div>`;
return `<div class='card' id='card-${o.id}'>
<h3>Order #${o.id} · ₹${Number(o.total_amount).toFixed(2)}</h3>
<div class='addr'>${esc(o.patient_name)} · ${esc(o.delivery_address)}${o.phone?' · '+esc(o.phone):''}</div>
<span class='pill ${done?'done':'out'}'>${done?'✅ Delivered':'🚚 Out for delivery'}</span>
${scanStep}
${done?'':`
<div class='row'><input id='rfid-${o.id}' placeholder='Scan / type chipless RFID tag' onkeydown='if(event.key==="Enter")scanTag(${o.id})'>
<button onclick='scanTag(${o.id})'>📡 Scan tag</button></div>
<div class='row'><input id='otp-${o.id}' placeholder='6-digit OTP from customer' maxlength='6' ${tag&&tag.delivery_scanned?'':'disabled'} onkeydown='if(event.key==="Enter")verifyOtp(${o.id})'>
<button onclick='verifyOtp(${o.id})' ${tag&&tag.delivery_scanned?'':'disabled'}>✅ Confirm delivery</button></div>
<div class='msg' id='msg-${o.id}'></div>`}
</div>`}
async function scanTag(id){let uid=$('rfid-'+id).value.trim();if(!uid)return;
let r=await fetch(`/api/delivery/orders/${id}/scan-rfid`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({uid})});
let x=await r.json();let box=$('msg-'+id);
if(x.ok){box.className='msg ok';box.innerHTML=`✅ ${esc(x.message)}`;load()}
else{box.className='msg fail';box.innerHTML=`⚠️ ${esc(x.message||x.error||'Scan failed')}`}}
async function verifyOtp(id){let otp=$('otp-'+id).value.trim();if(!otp)return;
let r=await fetch(`/api/delivery/orders/${id}/verify-otp`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({otp})});
let x=await r.json();let box=$('msg-'+id);
if(x.ok){box.className='msg ok';box.innerHTML='✅ Order marked Delivered.';load()}
else{box.className='msg fail';box.innerHTML=`⚠️ ${esc(x.message||x.error||'Verification failed')}`}}
load();setInterval(load,8000);
</script></body></html>"""

@app.get("/api/hospitals")
def hospitals():
    # No paid Places API is required in the free-map MVP. The emergency page
    # uses an OpenStreetMap-backed map/search view for nearby hospitals.
    return jsonify([])

def _pandemic_payload(row, days=7, hotspot=85, potential=70):
    hist=json.loads(row["history_json"] or "[]")
    cutoff=max(0,30-days)
    period=[h for h in hist if int(h.get("days_ago",0)) < days] or hist
    vals=[int(h.get("occupied",row["occupied_beds"])) for h in period]
    current=int(row["occupied_beds"]); beds=max(1,int(row["total_beds"]))
    pct=current/beds*100; avg=sum(vals)/len(vals)/beds*100; peak=max(vals)/beds*100
    old=vals[0] if vals else current
    trend=(current-old)/max(1,beds)*100
    risk="hotspot" if pct>=hotspot else ("potential" if pct>=potential or trend>=5 else "safe")
    return {"id":row["id"],"name":row["name"],"state":row["state"],"city":row["city"],"lat":row["lat"],"lng":row["lng"],"total_beds":beds,"occupied_beds":current,"occupancy_pct":round(pct,1),"period_avg_pct":round(avg,1),"period_peak_pct":round(peak,1),"trend_pct":round(trend,1),"risk":risk,"updated_at":row["updated_at"]}

@app.get("/api/pandemic/risk")
def pandemic_risk():
    # Patients get regional public-health guidance only; no patient-level health data is exposed.
    days=max(1,min(30,int(request.args.get("days",7))))
    hotspot=max(50,min(100,float(request.args.get("hotspot",85))))
    potential=max(30,min(hotspot-1,float(request.args.get("potential",70))))
    conn=db(); rows=conn.execute("SELECT * FROM pandemic_regions ORDER BY name").fetchall(); hospitals=conn.execute("SELECT h.*, r.city AS city_name FROM hospital_accounts h LEFT JOIN pandemic_regions r ON r.name=h.region OR r.city=h.region ORDER BY city_name,hospital_name").fetchall(); conn.close()
    out=[]
    for r in rows:
        payload=_pandemic_payload(r,days,hotspot,potential)
        zones=[]
        for h in hospitals:
            if h["city_name"] != r["city"]: continue
            beds=max(1,int(h["total_beds"] or 1)); occ=int(h["occupied_beds"] or 0); pct=occ/beds*100
            risk="hotspot" if pct>=hotspot else ("potential" if pct>=potential else "safe")
            zones.append({"id":h["id"],"hospital_name":h["hospital_name"],"region":h["region"],"total_beds":beds,"occupied_beds":occ,"availability":max(0,beds-occ),"occupancy_pct":round(pct,1),"risk":risk,"updated_at":h["updated_at"]})
        payload["city"]=r["city"]; payload["state"]=r["state"]; payload["hospitals"]=zones
        out.append(payload)
    return jsonify(period_days=days,hotspot_limit=hotspot,potential_limit=potential,regions=out)

@app.get("/api/admin/pandemic/regions")
def admin_pandemic_regions():
    if not current_admin(): return jsonify(error="Admin login required"),403
    days=max(1,min(30,int(request.args.get("days",7))))
    hotspot=max(50,min(100,float(request.args.get("hotspot",85))))
    potential=max(30,min(hotspot-1,float(request.args.get("potential",70))))
    conn=db(); rows=conn.execute("SELECT * FROM pandemic_regions ORDER BY name").fetchall(); conn.close()
    data=[_pandemic_payload(r,days,hotspot,potential) for r in rows]
    return jsonify(period_days=days,hotspot_limit=hotspot,potential_limit=potential,regions=data,source_note="Synthetic hackathon demo data — replace with hospital/government feeds in production.")

@app.get("/api/admin/pandemic/cities")
def admin_pandemic_cities():
    if not current_admin(): return jsonify(error="Admin login required"),403
    days=max(1,min(30,int(request.args.get("days",7))))
    hotspot=max(50,min(100,float(request.args.get("hotspot",85))))
    potential=max(30,min(hotspot-1,float(request.args.get("potential",70))))
    conn=db()
    regions=conn.execute("SELECT * FROM pandemic_regions ORDER BY city").fetchall()
    hospitals=conn.execute("SELECT h.*, r.city AS city_name, r.state AS state_name FROM hospital_accounts h LEFT JOIN pandemic_regions r ON r.name=h.region OR r.city=h.region ORDER BY city_name,hospital_name").fetchall()
    conn.close()
    out=[]
    for r in regions:
        rh=_pandemic_payload(r,days,hotspot,potential); hs=[]
        for h in hospitals:
            if h["city_name"] != r["city"]: continue
            beds=max(1,int(h["total_beds"] or 1)); occ=int(h["occupied_beds"] or 0); pct=occ/beds*100
            hist=json.loads(h["history_json"] or "[]"); period=[x for x in hist if int(x.get("days_ago",0)) < days] or hist; vals=[int(x.get("occupied",occ)) for x in period] or [occ]
            peak=max(vals)/beds*100; trend=(occ-vals[0])/beds*100
            risk="hotspot" if pct>=hotspot else ("potential" if pct>=potential or trend>=5 else "safe")
            hs.append({"id":h["id"],"hospital_name":h["hospital_name"],"region":h["region"],"lat":h["lat"],"lng":h["lng"],"total_beds":beds,"occupied_beds":occ,"availability":max(0,beds-occ),"occupancy_pct":round(pct,1),"period_peak_pct":round(peak,1),"trend_pct":round(trend,1),"risk":risk,"updated_at":h["updated_at"]})
        if not hs:
            hs=[{"id":f"region-{r['id']}","hospital_name":"Regional aggregate","region":r["name"],"lat":r["lat"],"lng":r["lng"],"total_beds":rh["total_beds"],"occupied_beds":rh["occupied_beds"],"availability":max(0,rh["total_beds"]-rh["occupied_beds"]),"occupancy_pct":rh["occupancy_pct"],"period_peak_pct":rh["period_peak_pct"],"trend_pct":rh["trend_pct"],"risk":rh["risk"],"updated_at":rh["updated_at"]}]
        out.append({"id":r["id"],"city":r["city"],"state":r["state"],"lat":r["lat"],"lng":r["lng"],"total_beds":rh["total_beds"],"occupied_beds":rh["occupied_beds"],"availability":max(0,rh["total_beds"]-rh["occupied_beds"]),"occupancy_pct":rh["occupancy_pct"],"period_peak_pct":rh["period_peak_pct"],"trend_pct":rh["trend_pct"],"risk":rh["risk"],"hospitals":hs})
    return jsonify(period_days=days,hotspot_limit=hotspot,potential_limit=potential,cities=out)

@app.get("/api/admin/pandemic/history/<int:region_id>")
def admin_pandemic_history(region_id):
    if not current_admin(): return jsonify(error="Admin login required"),403
    conn=db(); row=conn.execute("SELECT * FROM pandemic_regions WHERE id=?",(region_id,)).fetchone(); conn.close()
    if not row: return jsonify(error="Region not found"),404
    return jsonify(region=_pandemic_payload(row,30),history=json.loads(row["history_json"] or "[]"))

@app.get("/api/maps/config")
def maps_config():
    # Maps are rendered with Leaflet + OpenStreetMap in the browser, so the MVP
    # does not require a paid Google Maps key. Attribution is shown on the map.
    return jsonify(provider="OpenStreetMap",library="Leaflet",requires_key=False)

@app.get("/api/patients")
def patients():
    u=current_user(); a=current_admin()
    if not ((u and u["role"]=="doctor") or a): return jsonify(error="Staff access required"),403
    conn=db()
    if a: rows=conn.execute("SELECT id,name,email,nfc_uid FROM users WHERE role='patient' ORDER BY name").fetchall()
    else: rows=conn.execute("SELECT id,name,email FROM users WHERE role='patient' ORDER BY name").fetchall()
    conn.close(); return jsonify([dict(x) for x in rows])


# ---------------- NFC Smart Patient Card: registration + scan endpoints ----------------
@app.post("/api/nfc/register")
def nfc_register():
    # Card issuance is a front-desk/staff action; reuses the doctor role since this project
    # has no separate admin role. "Admin selects patient -> scans NFC -> UID is saved."
    if not current_admin(): return jsonify(error="Admin login required"),403
    data=request.get_json() or {}
    patient_id=data.get("patient_id"); uid=norm_uid(data.get("uid"))
    if not patient_id or not uid: return jsonify(error="Patient and card UID are required."),400
    conn=db()
    patient=conn.execute("SELECT * FROM users WHERE id=? AND role='patient'",(patient_id,)).fetchone()
    if not patient: conn.close(); return jsonify(error="Patient not found."),404
    clash=conn.execute("SELECT id,name FROM users WHERE role='patient' AND nfc_uid=? AND id!=?",(uid,patient_id)).fetchone()
    if clash: conn.close(); return jsonify(error=f"This card is already registered to {clash['name']}."),409
    conn.execute("UPDATE users SET nfc_uid=? WHERE id=?",(uid,patient_id))
    log_nfc_scan(conn,uid,"register",patient_id,"registered",note=f"linked to {patient['name']}")
    conn.commit(); conn.close()
    return jsonify(ok=True,patient_id=patient_id,uid=uid)

@app.post("/api/nfc/scan")
def nfc_scan():
    """The single entry point both the physical reader and the on-screen simulator call.
    A hardware reader in USB-HID mode just needs to land the UID text into the same input
    the simulator uses and submit it — no separate hardware code path exists."""
    if not current_admin(): return jsonify(error="Admin login required"),403
    data=request.get_json() or {}
    uid=norm_uid(data.get("uid")); context=(data.get("context") or "identify").strip()
    if not uid: return jsonify(error="No UID received from card/simulator."),400
    conn=db()
    patient=find_patient_by_uid(conn,uid)
    if not patient:
        log_nfc_scan(conn,uid,context,None,"unknown_card"); conn.commit(); conn.close()
        return jsonify(ok=False,result="unknown_card",message="This card is not registered to any patient."),404

    if context=="checkin":
        today=date.today().isoformat()
        appt=conn.execute("""SELECT a.*,du.name doctor_name,d.specialty,d.venue FROM appointments a
            JOIN doctors d ON d.id=a.doctor_id JOIN users du ON du.id=d.user_id
            WHERE a.patient_id=? AND substr(a.appointment_time,1,10)=? AND a.status NOT IN ('cancelled','completed')
            ORDER BY a.appointment_time LIMIT 1""",(patient["id"],today)).fetchone()
        if not appt:
            log_nfc_scan(conn,uid,context,patient["id"],"no_appointment"); conn.commit(); conn.close()
            return jsonify(ok=False,result="no_appointment",patient=patient_public(patient),
                           message=f"{patient['name']} has no appointment scheduled today."),404
        already=bool(appt["checked_in"])
        now=datetime.now().isoformat(timespec="seconds")
        if not already:
            conn.execute("UPDATE appointments SET checked_in=1,checked_in_at=? WHERE id=?",(now,appt["id"]))
            log_nfc_scan(conn,uid,context,patient["id"],"checked_in",note=f"appointment #{appt['id']}")
        else:
            log_nfc_scan(conn,uid,context,patient["id"],"already_checked_in")
        conn.commit()
        appt=conn.execute("""SELECT a.*,du.name doctor_name,d.specialty,d.venue FROM appointments a
            JOIN doctors d ON d.id=a.doctor_id JOIN users du ON du.id=d.user_id WHERE a.id=?""",(appt["id"],)).fetchone()
        conn.close()
        return jsonify(ok=True,result="already_checked_in" if already else "checked_in",
                       patient=patient_public(patient),appointment=appointment_payload(appt))

    if context=="pharmacy":
        rx_rows=conn.execute("""SELECT p.*,du.name doctor_name FROM prescriptions p JOIN doctors d ON d.id=p.doctor_id
            JOIN users du ON du.id=d.user_id WHERE p.patient_id=? ORDER BY p.id DESC LIMIT 10""",(patient["id"],)).fetchall()
        prescriptions=[]
        for r in rx_rows:
            x=dict(r); x["items"]=[dict(i) for i in conn.execute(
                "SELECT * FROM prescription_items WHERE prescription_id=?",(r["id"],)).fetchall()]
            prescriptions.append(x)
        order_rows=conn.execute("""SELECT o.*,t.tracking_code,t.status delivery_status,t.eta FROM medicine_orders o
            LEFT JOIN delivery_tracking t ON t.order_id=o.id WHERE o.patient_id=? ORDER BY o.id DESC LIMIT 10""",(patient["id"],)).fetchall()
        orders=[]
        for r in order_rows:
            x=dict(r); x["items"]=[dict(i) for i in conn.execute(
                "SELECT medicine_name,quantity,unit_price FROM medicine_order_items WHERE order_id=?",(r["id"],)).fetchall()]
            orders.append(x)
        log_nfc_scan(conn,uid,context,patient["id"],"pharmacy_lookup")
        conn.commit(); conn.close()
        return jsonify(ok=True,result="pharmacy_lookup",patient=patient_public(patient),
                       prescriptions=prescriptions,orders=orders)

    # default: identify — just confirm who the card belongs to, no records pulled.
    log_nfc_scan(conn,uid,"identify",patient["id"],"identified")
    conn.commit(); conn.close()
    return jsonify(ok=True,result="identified",patient=patient_public(patient))

@app.get("/api/nfc/checkins-today")
def nfc_checkins_today():
    if not current_admin(): return jsonify(error="Admin login required"),403
    conn=db(); today=date.today().isoformat()
    rows=conn.execute("""SELECT a.*,pu.name patient_name FROM appointments a JOIN users pu ON pu.id=a.patient_id
        WHERE substr(a.appointment_time,1,10)=? AND a.status NOT IN ('cancelled','completed')
        ORDER BY a.checked_in DESC,a.appointment_time""",(today,)).fetchall()
    conn.close(); return jsonify([appointment_payload(r) for r in rows])

@app.get("/api/admin/live-state")
def admin_live_state():
    if not current_admin(): return jsonify(error="Admin login required"),403
    conn=db();
    active=conn.execute("SELECT COUNT(*) n FROM appointments WHERE status='in_progress'").fetchone()["n"]
    waiting=conn.execute("SELECT COUNT(*) n FROM appointments WHERE status IN ('confirmed','waiting')").fetchone()["n"]
    patients=conn.execute("SELECT COUNT(*) n FROM users WHERE role='patient'").fetchone()["n"]
    doctors=conn.execute("SELECT COUNT(*) n FROM users WHERE role='doctor'").fetchone()["n"]
    conn.close(); return jsonify(ok=True,state="PLATFORM LIVE",active_consultations=active,waiting_appointments=waiting,registered_patients=patients,registered_doctors=doctors,verified_at=datetime.now().isoformat(timespec="seconds"))

@app.get("/api/admin/overview")
def admin_overview():
    if not current_admin(): return jsonify(error="Admin login required"),403
    conn=db()
    patients=conn.execute("SELECT COUNT(*) n FROM users WHERE role='patient'").fetchone()["n"]
    cards=conn.execute("SELECT COUNT(*) n FROM users WHERE role='patient' AND COALESCE(nfc_uid,'')!=''").fetchone()["n"]
    orders=conn.execute("SELECT COUNT(*) n FROM medicine_orders").fetchone()["n"]
    delivered=conn.execute("SELECT COUNT(*) n FROM medicine_orders WHERE status='delivered'").fetchone()["n"]
    pending=conn.execute("SELECT COUNT(*) n FROM medicine_orders WHERE status!='delivered'").fetchone()["n"]
    stock=conn.execute("SELECT COALESCE(SUM(stock),0) n FROM pharmacy_medicines WHERE active=1").fetchone()["n"]
    conn.close(); return jsonify(patients=patients,cards=cards,orders=orders,delivered=delivered,pending=pending,stock=stock)

@app.get("/api/admin/orders")
def admin_orders():
    if not current_admin(): return jsonify(error="Admin login required"),403
    conn=db(); rows=conn.execute("""SELECT o.id,o.total_amount,o.status,o.placed_at,pu.name patient_name,pu.email patient_email,
        t.tracking_code,t.courier_name,t.status delivery_status,t.eta,r.tag_uid,r.dispatch_scanned,r.delivery_scanned
        FROM medicine_orders o JOIN users pu ON pu.id=o.patient_id LEFT JOIN delivery_tracking t ON t.order_id=o.id
        LEFT JOIN delivery_rfid r ON r.order_id=o.id ORDER BY o.id DESC""").fetchall()
    out=[]
    for r in rows:
        x=dict(r); x["items"]=[dict(i) for i in conn.execute("SELECT medicine_name,quantity,unit_price FROM medicine_order_items WHERE order_id=?",(r["id"],)).fetchall()]; out.append(x)
    conn.close(); return jsonify(out)

@app.get("/api/admin/inventory")
def admin_inventory():
    if not current_admin(): return jsonify(error="Admin login required"),403
    conn=db(); rows=conn.execute("SELECT id,name,category,price,stock,requires_prescription,active FROM pharmacy_medicines ORDER BY category,name").fetchall(); conn.close(); return jsonify([dict(x) for x in rows])

@app.get("/api/admin/nfc/logs")
def admin_nfc_logs():
    if not current_admin(): return jsonify(error="Admin login required"),403
    conn=db(); rows=conn.execute("""SELECT l.*,u.name patient_name,u.email patient_email FROM nfc_scan_log l
        LEFT JOIN users u ON u.id=l.patient_id ORDER BY l.id DESC LIMIT 50""").fetchall(); conn.close(); return jsonify([dict(x) for x in rows])

@app.get("/api/admin/rfid/logs")
def admin_rfid_logs():
    if not current_admin(): return jsonify(error="Admin login required"),403
    conn=db(); rows=conn.execute("""SELECT l.*,o.patient_id,pu.name patient_name FROM rfid_scan_log l
        JOIN medicine_orders o ON o.id=l.order_id JOIN users pu ON pu.id=o.patient_id ORDER BY l.id DESC LIMIT 50""").fetchall(); conn.close(); return jsonify([dict(x) for x in rows])

@app.get("/nfc")
def nfc_console():
    if not current_admin(): return redirect(url_for("admin_login"))
    return redirect(url_for("admin_dashboard"))


HOSPITAL_LOGIN_HTML="""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>MediBridge · Hospital Portal</title><style>*{box-sizing:border-box}body{margin:0;font-family:Inter,Segoe UI,Arial,sans-serif;background:radial-gradient(circle at 15% 10%,#d8fff2 0,#effbf8 28%,transparent 48%),linear-gradient(135deg,#f8fffd,#f5f8fb);min-height:100vh;display:grid;place-items:center;color:#172a3a}.box{width:min(470px,92vw);background:rgba(255,255,255,.97);border:1px solid #dcebe7;border-radius:28px;padding:34px;box-shadow:0 30px 80px rgba(31,55,79,.12)}.logo{font-size:32px;font-weight:950}.tag{color:#0f8a78;font-size:11px;font-weight:900;letter-spacing:1.2px;margin:5px 0 24px}.badge{background:#effbf7;border:1px solid #cbeee3;border-radius:16px;padding:14px;font-size:12px;line-height:1.5;margin-bottom:20px}label{font-size:12px;color:#6d7f8d;font-weight:700}input{width:100%;padding:13px;box-sizing:border-box;margin:6px 0 15px;border:1px solid #dfe8ec;border-radius:13px;outline:none}input:focus{border-color:#75cbbd;box-shadow:0 0 0 4px rgba(15,138,120,.08)}button{width:100%;padding:14px;border:0;border-radius:13px;background:linear-gradient(135deg,#0f8a78,#16a38f);color:#fff;font-weight:900;cursor:pointer;box-shadow:0 8px 20px rgba(15,138,120,.2)}.err{background:#fff0f0;color:#9b3030;padding:11px;border-radius:11px;font-size:12px;margin-bottom:14px}a{display:block;text-align:center;color:#167f73;text-decoration:none;font-size:12px;font-weight:800;margin-top:14px}</style></head><body><div class='box'><div class='logo'>MediBridge</div><div class='tag'>HOSPITAL PARTNER PORTAL</div><div class='badge'>🏥 <b>Secure partner access</b><br>Update aggregate bed capacity and occupancy for the regional pandemic intelligence system.</div>{% if error %}<div class='err'>{{error}}</div>{% endif %}<form method='post'><label>Hospital email</label><input name='email' type='email' placeholder='hospital@medibridge.local' required><label>Password</label><input name='password' type='password' placeholder='Enter password' required><button>Enter Hospital Console →</button></form><a href='/login'>← Patient / Doctor login</a><a href='/admin/login'>Admin operations portal →</a></div></body></html>"""

HOSPITAL_HTML="""<!doctype html><html><head><meta name='viewport' content='width=device-width,initial-scale=1'><title>MediBridge · Hospital Console</title><style>body{margin:0;font-family:Segoe UI,Arial;background:#f4f8fa;color:#16303d}.wrap{max-width:980px;margin:auto;padding:28px}.top{display:flex;justify-content:space-between;align-items:center}.card{background:#fff;border:1px solid #dfe8ec;border-radius:20px;padding:22px;margin-top:18px;box-shadow:0 14px 35px #0b1f2a0d}.metric{font-size:34px;font-weight:850;color:#126b60}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.muted{color:#687a83;font-size:13px;line-height:1.5}input{padding:12px;border:1px solid #dfe8ec;border-radius:11px;width:100%;box-sizing:border-box}button{padding:12px 16px;border:0;border-radius:11px;background:#126b60;color:#fff;font-weight:800;cursor:pointer}.logout{color:#126b60;text-decoration:none;font-weight:800;font-size:12px}@media(max-width:700px){.grid{grid-template-columns:1fr}}</style></head><body><div class='wrap'><div class='top'><div><h1>🏥 {{h['hospital_name']}}</h1><div class='muted'>Hospital Partner Console · {{h['region']}}</div></div><a class='logout' href='/hospital/logout'>Logout</a></div><div class='grid'><div class='card'><div class='muted'>Total beds</div><div class='metric' id='beds'>{{region['total_beds'] if region else '—'}}</div></div><div class='card'><div class='muted'>Occupied beds</div><div class='metric' id='occ'>{{region['occupied_beds'] if region else '—'}}</div></div><div class='card'><div class='muted'>Current occupancy</div><div class='metric' id='pct'>{{round(region['occupied_beds']/region['total_beds']*100,1) if region else '—'}}%</div></div></div><div class='card'><h2>Update regional capacity</h2><p class='muted'>Only aggregate capacity is shared with MediBridge. No patient records are transmitted.</p><form id='f'><label>Total beds</label><br><input id='b' type='number' min='1' value='{{region['total_beds'] if region else 100}}'><br><br><label>Occupied beds</label><br><input id='o' type='number' min='0' value='{{region['occupied_beds'] if region else 50}}'><br><br><button>Publish occupancy</button></form><div id='msg' class='muted' style='margin-top:12px'></div></div></div><script>f.onsubmit=async e=>{e.preventDefault();let r=await fetch('/api/hospital/occupancy',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({total_beds:+b.value,occupied_beds:+o.value})});let x=await r.json();if(!r.ok){msg.textContent=x.error;return}beds.textContent=b.value;occ.textContent=o.value;pct.textContent=x.occupancy_pct+'%';msg.textContent='✓ Occupancy sent to MediBridge command centre.'}</script></body></html>"""


if __name__ == "__main__":
    init_db(); print("MediBridge running at http://127.0.0.1:5000"); app.run(host="0.0.0.0",port=5000,debug=True)
