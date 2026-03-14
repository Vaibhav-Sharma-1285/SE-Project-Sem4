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
