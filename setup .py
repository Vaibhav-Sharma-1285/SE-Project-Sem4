"""
Attendify — Database Initialization Script
Run once: python setup.py
"""
import sqlite3, os, datetime, random
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), 'instance', 'attendify.db')
os.makedirs(os.path.join(os.path.dirname(__file__), 'instance'), exist_ok=True)

if os.path.exists(DB_PATH):
    os.remove(DB_PATH)
    print("Removed old database.")

conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA foreign_keys = ON")

# ── CREATE TABLES ─────────────────────────────────────────────────────────────
conn.executescript("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('ADMIN','FACULTY','STUDENT')),
    batch TEXT DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS courses (
    course_id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_code TEXT UNIQUE NOT NULL,
    course_name TEXT NOT NULL,
    credits INTEGER NOT NULL CHECK(credits > 0)
);
CREATE TABLE IF NOT EXISTS faculty_courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    faculty_id INTEGER NOT NULL REFERENCES users(user_id),
    course_id INTEGER NOT NULL REFERENCES courses(course_id),
    UNIQUE(faculty_id, course_id)
);
CREATE TABLE IF NOT EXISTS enrollments (
    enrollment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES users(user_id),
    course_id INTEGER NOT NULL REFERENCES courses(course_id),
    semester INTEGER NOT NULL DEFAULT 4,
    enrolled_on DATE NOT NULL DEFAULT (date('now')),
    UNIQUE(student_id, course_id, semester)
);
CREATE TABLE IF NOT EXISTS attendance_records (
    record_id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL REFERENCES courses(course_id),
    student_id INTEGER NOT NULL REFERENCES users(user_id),
    marked_by INTEGER NOT NULL REFERENCES users(user_id),
    attendance_date DATE NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('PRESENT','ABSENT','ON_LEAVE')),
    created_at DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at DATETIME NOT NULL,
    UNIQUE(student_id, course_id, attendance_date)
);
CREATE TABLE IF NOT EXISTS leave_requests (
    leave_id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES users(user_id),
    course_id INTEGER NOT NULL REFERENCES courses(course_id),
    from_date DATE NOT NULL,
    to_date DATE NOT NULL CHECK(to_date >= from_date),
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','APPROVED','REJECTED')),
    reviewed_by INTEGER REFERENCES users(user_id),
    faculty_comment TEXT,
    submitted_at DATETIME NOT NULL DEFAULT (datetime('now')),
    reviewed_at DATETIME
);
CREATE TABLE IF NOT EXISTS audit_logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(user_id),
    action TEXT NOT NULL,
    details TEXT,
    ip_address TEXT NOT NULL DEFAULT '127.0.0.1',
    timestamp DATETIME NOT NULL DEFAULT (datetime('now'))
);
""")

# ── HELPER ────────────────────────────────────────────────────────────────────
def add_user(username, password, full_name, email, role, batch=''):
    pw = generate_password_hash(password)
    conn.execute(
        "INSERT INTO users (username,password_hash,full_name,email,role,batch) VALUES (?,?,?,?,?,?)",
        (username, pw, full_name, email, role, batch)
    )

# ── ADMIN ─────────────────────────────────────────────────────────────────────
print("\nCreating Admin...")
add_user('admin', 'Admin@1234', 'System Administrator', 'admin@attendify.edu', 'ADMIN')

# ── FACULTY ───────────────────────────────────────────────────────────────────
print("Creating Faculty...")
add_user('prof1', 'Prof@1234', 'Professor 1', 'prof1@attendify.edu', 'FACULTY')
add_user('prof2', 'Prof@1234', 'Professor 2', 'prof2@attendify.edu', 'FACULTY')
add_user('prof3', 'Prof@1234', 'Professor 3', 'prof3@attendify.edu', 'FACULTY')
add_user('prof4', 'Prof@1234', 'Professor 4', 'prof4@attendify.edu', 'FACULTY')
add_user('prof5', 'Prof@1234', 'Professor 5', 'prof5@attendify.edu', 'FACULTY')
conn.commit()

# ── STUDENTS ──────────────────────────────────────────────────────────────────
print("Creating Students...")
add_user('vaibhav',  'Student@1234', 'Vaibhav Sharma', 'vaibhav@attendify.edu',  'STUDENT', 'CSE-A 2024')
add_user('atharva',  'Student@1234', 'Atharva Verma',  'atharva@attendify.edu',  'STUDENT', 'CSE-A 2024')
add_user('asheesh',  'Student@1234', 'Asheesh Kumar',  'asheesh@attendify.edu',  'STUDENT', 'CSE-A 2024')
add_user('roshan',   'Student@1234', 'Roshan Verma',   'roshan@attendify.edu',   'STUDENT', 'CSE-A 2024')
add_user('saurabh',  'Student@1234', 'Saurabh Kumar',  'saurabh@attendify.edu',  'STUDENT', 'CSE-A 2024')
conn.commit()

# ── COURSES ───────────────────────────────────────────────────────────────────
print("Creating Courses...")
conn.executemany(
    "INSERT INTO courses (course_code, course_name, credits) VALUES (?,?,?)",
    [
        ('SE401',  'Software Engineering',              4),
        ('OS402',  'Operating System',                  4),
        ('CSA403', 'Computer System Architecture',      3),
        ('FDA404', 'Fundamental of Data Analytics',     3),
        ('CE405',  'Cryptography Essentials',           3),
    ]
)
conn.commit()

# Fetch IDs
def uid(username):
    return conn.execute("SELECT user_id FROM users WHERE username=?", (username,)).fetchone()[0]

def cid(code):
    return conn.execute("SELECT course_id FROM courses WHERE course_code=?", (code,)).fetchone()[0]

# ── FACULTY → COURSE ASSIGNMENT (1 each) ──────────────────────────────────────
print("Assigning Faculty to Courses...")
conn.executemany(
    "INSERT INTO faculty_courses (faculty_id, course_id) VALUES (?,?)",
    [
        (uid('prof1'), cid('SE401')),
        (uid('prof2'), cid('OS402')),
        (uid('prof3'), cid('CSA403')),
        (uid('prof4'), cid('FDA404')),
        (uid('prof5'), cid('CE405')),
    ]
)
conn.commit()

# ── STUDENT ENROLLMENTS ───────────────────────────────────────────────────────
print("Enrolling Students...")
all_students    = ['vaibhav', 'atharva', 'asheesh', 'roshan', 'saurabh']
common_courses  = ['SE401', 'OS402', 'CSA403']          # all 5 students
fda_students    = ['vaibhav', 'asheesh', 'saurabh']     # Fundamental of Data Analytics
crypto_students = ['roshan', 'atharva']                  # Cryptography Essentials

for s in all_students:
    for c in common_courses:
        conn.execute(
            "INSERT INTO enrollments (student_id, course_id, semester) VALUES (?,?,4)",
            (uid(s), cid(c))
        )
for s in fda_students:
    conn.execute(
        "INSERT INTO enrollments (student_id, course_id, semester) VALUES (?,?,4)",
        (uid(s), cid('FDA404'))
    )
for s in crypto_students:
    conn.execute(
        "INSERT INTO enrollments (student_id, course_id, semester) VALUES (?,?,4)",
        (uid(s), cid('CE405'))
    )
conn.commit()

# ── GENERATE DATES (Jan 1 – Mar 27, 2026, no Sundays) ────────────────────────
print("Generating attendance dates...")
start = datetime.date(2026, 1, 1)
end   = datetime.date(2026, 3, 27)
dates = []
cur   = start
while cur <= end:
    if cur.weekday() != 6:   # 6 = Sunday
        dates.append(cur)
    cur += datetime.timedelta(days=1)
print(f"  Total teaching days: {len(dates)}")

# ── LEAVE REQUESTS (approved) ─────────────────────────────────────────────────
# Each student gets 2-3 approved leave periods spread across the semester
print("Creating leave requests...")
random.seed(99)

leave_periods = [
    # (student, course_code, from_date, to_date, reason)
    ('vaibhav', 'SE401',  '2026-01-15', '2026-01-16', 'Medical emergency at home'),
    ('vaibhav', 'OS402',  '2026-02-10', '2026-02-11', 'Family function attendance'),
    ('atharva', 'SE401',  '2026-01-20', '2026-01-21', 'Medical appointment required'),
    ('atharva', 'CE405',  '2026-02-18', '2026-02-19', 'Intercollege sports event'),
    ('asheesh', 'OS402',  '2026-01-27', '2026-01-28', 'Fever and medical treatment'),
    ('asheesh', 'FDA404', '2026-02-25', '2026-02-26', 'Family emergency situation'),
    ('roshan',  'SE401',  '2026-02-03', '2026-02-04', 'Medical checkup and rest'),
    ('roshan',  'CE405',  '2026-03-05', '2026-03-06', 'College fest participation'),
    ('saurabh', 'CSA403', '2026-01-22', '2026-01-23', 'Medical leave due to illness'),
    ('saurabh', 'FDA404', '2026-03-10', '2026-03-11', 'Family function out of town'),
]

# Faculty who reviews leaves for each course
course_faculty = {
    'SE401':  'prof1', 'OS402':  'prof2', 'CSA403': 'prof3',
    'FDA404': 'prof4', 'CE405':  'prof5',
}

for s, course, fd, td, reason in leave_periods:
    # Check if course is in student's enrollment
    enrolled = conn.execute(
        "SELECT 1 FROM enrollments WHERE student_id=? AND course_id=?",
        (uid(s), cid(course))
    ).fetchone()
    if not enrolled:
        continue
    reviewer = uid(course_faculty[course])
    conn.execute(
        """INSERT INTO leave_requests
           (student_id, course_id, from_date, to_date, reason, status, reviewed_by, faculty_comment, reviewed_at)
           VALUES (?,?,?,?,?,'APPROVED',?,?,datetime('now'))""",
        (uid(s), cid(course), fd, td, reason, reviewer, 'Approved. Take care.')
    )
conn.commit()

# Build a set of approved leave dates per (student, course)
approved_leaves = {}
rows = conn.execute(
    "SELECT student_id, course_id, from_date, to_date FROM leave_requests WHERE status='APPROVED'"
).fetchall()
for row in rows:
    key = (row[0], row[1])
    fd  = datetime.date.fromisoformat(row[2])
    td  = datetime.date.fromisoformat(row[3])
    d   = fd
    while d <= td:
        approved_leaves.setdefault(key, set()).add(d)
        d += datetime.timedelta(days=1)

# ── SYNTHETIC ATTENDANCE ──────────────────────────────────────────────────────
print("Seeding attendance records...")
random.seed(42)

# Build enrollment map: student → list of course_ids
enrollment_map = {}
for s in all_students:
    rows = conn.execute(
        "SELECT course_id FROM enrollments WHERE student_id=?", (uid(s),)
    ).fetchall()
    enrollment_map[s] = [r[0] for r in rows]

records_added = 0
for date in dates:
    for s in all_students:
        for course_id in enrollment_map[s]:
            # Faculty who marks this course
            fac = conn.execute(
                "SELECT faculty_id FROM faculty_courses WHERE course_id=?", (course_id,)
            ).fetchone()[0]

            key = (uid(s), course_id)
            if key in approved_leaves and date in approved_leaves[key]:
                status = 'ON_LEAVE'
            else:
                # ~82% present, ~18% absent — realistic university attendance
                status = random.choices(
                    ['PRESENT', 'ABSENT'],
                    weights=[82, 18]
                )[0]

            try:
                conn.execute(
                    """INSERT INTO attendance_records
                       (course_id, student_id, marked_by, attendance_date, status, updated_at)
                       VALUES (?,?,?,?,?,datetime('now'))""",
                    (course_id, uid(s), fac, date.isoformat(), status)
                )
                records_added += 1
            except:
                pass

conn.commit()
print(f"  Attendance records added: {records_added}")

# ── PRINT CREDENTIALS ─────────────────────────────────────────────────────────
print("\n✅ Database initialized successfully!")
print("\n─── LOGIN CREDENTIALS ───────────────────────────────────────────")
print("  ADMIN")
print("    admin        / Admin@1234")
print()
print("  FACULTY")
print("    prof1        / Prof@1234   → Software Engineering")
print("    prof2        / Prof@1234   → Operating System")
print("    prof3        / Prof@1234   → Computer System Architecture")
print("    prof4        / Prof@1234   → Fundamental of Data Analytics")
print("    prof5        / Prof@1234   → Cryptography Essentials")
print()
print("  STUDENTS")
print("    vaibhav      / Student@1234  → Vaibhav Sharma")
print("    atharva      / Student@1234  → Atharva Verma")
print("    asheesh      / Student@1234  → Asheesh Kumar")
print("    roshan       / Student@1234  → Roshan Verma")
print("    saurabh      / Student@1234  → Saurabh Kumar")
print("─────────────────────────────────────────────────────────────────")
print("\nRun the app: python app.py  →  http://localhost:5000\n")
conn.close()
