# Attendify — Secure Attendance Tracking System
**Version 1.1 | B.Tech Software Engineering Lab | Team: Attendify | CSE-A, Semester IV**

---

## 📋 Project Overview
Attendify is a web-based attendance management and leave approval platform built for college environments, replacing manual paper-based processes with a secure, role-driven digital solution.

**Team:** Atharva, Vaibhav, Asheesh, Roshan, Saurabh

---

## ⚡ Quick Start (Run in 3 Steps)

### Step 1 — Prerequisites
Make sure you have Python 3.8+ installed:
```bash
python3 --version
```
Install Flask (the only dependency):
```bash
pip3 install flask
```
> **Note:** Flask includes Werkzeug for password hashing. No other packages needed.

---

### Step 2 — Initialize the Database
Run the setup script once to create the database with sample data:
```bash
python3 setup.py
```
This creates:
- 1 Admin account
- 2 Faculty accounts  
- 5 Student accounts
- 4 Courses with enrollments
- 14 days of sample attendance data

---

### Step 3 — Start the Application
```bash
python3 app.py
```
Then open your browser and go to: **http://localhost:5000**

---

## 🔐 Login Credentials

| Role    | Username       | Password      |
|---------|----------------|---------------|
| Admin   | `admin`        | `Admin@1234`  |
| Faculty | `atharva`      | `Faculty@123` |
| Faculty | `vaibhav`      | `Faculty@123` |
| Faculty | `asheesh`      | `Faculty@123` |
| Faculty | `roshan`      | `Faculty@123` |
| Faculty | `saurabh`      | `Faculty@123` |
| Student | `s001` to `s005` | `Student@123` |

---

## 🗂️ Project Structure

```
attendify/
├── app.py              ← Main Flask application (all routes & logic)
├── setup.py            ← Database initialization script (run once)
├── schema.sql          ← SQLite database schema
├── README.md           ← This file
├── instance/
│   └── attendify.db    ← SQLite database (auto-created by setup.py)
└── templates/
    ├── base.html           ← Master layout with sidebar & navigation
    ├── login.html          ← Login page
    ├── dashboard.html      ← Role-specific dashboard
    ├── mark_attendance.html   ← Faculty: mark attendance
    ├── view_attendance.html   ← Student: view own attendance
    ├── apply_leave.html       ← Student: apply for leave
    ├── my_leaves.html         ← Student: leave application history
    ├── manage_leaves.html     ← Faculty: approve/reject leaves
    ├── reports.html           ← Attendance reports + CSV export
    ├── admin_users.html       ← Admin: user list & search
    ├── create_user.html       ← Admin: create new user
    ├── edit_user.html         ← Admin: edit user details
    ├── admin_courses.html     ← Admin: course management
    ├── create_course.html     ← Admin: create new course
    ├── edit_course.html       ← Admin: edit course
    ├── enroll_students.html   ← Admin: manage enrollments & faculty
    └── audit_logs.html        ← Admin: system audit trail
```

---

## ✅ Implemented Features (All SRS Requirements)

### 🔒 Authentication & Access Control
- [x] REQ-1.1 to REQ-1.10: Login, RBAC, session timeout (30 min), bcrypt hashing, account lockout after 5 failures

### ✓ Attendance Marking (Faculty)
- [x] REQ-2.1 to REQ-2.12: Mark/edit attendance, auto-populate On Leave, 7-day warning, 24h edit window

### 📝 Leave Application (Student)
- [x] REQ-3.1 to REQ-3.8: Apply for leave, date validation, 10-char reason, Pending status, view history

### ✅ Leave Approval (Faculty)
- [x] REQ-4.1 to REQ-4.8: Review/approve/reject leaves, optional comment, audit trail, auto-update attendance

### 📊 Attendance Viewing (Student)
- [x] REQ-5.1 to REQ-5.6: View records, compute %, highlight below 66.67% in red, N/A for zero classes

### 📋 Attendance Reports
- [x] REQ-6.1 to REQ-6.7: Generate reports with filters, CSV export, "No data available" message

### 👥 User Management (Admin)
- [x] REQ-7.1 to REQ-7.10: Create/edit/deactivate users, unique username, immutable username, search/filter

### 🎓 Course & Enrollment Management (Admin)
- [x] REQ-8.1 to REQ-8.9: Create courses, assign faculty, enroll students, prevent duplicates

### ⚡ Non-Functional Requirements
- [x] REQ-NFR-7: Werkzeug PBKDF2 password hashing (bcrypt-equivalent)
- [x] REQ-NFR-9: 30-min session timeout
- [x] REQ-NFR-10: SQLite parameterized queries (SQL injection prevention)
- [x] REQ-NFR-12: Audit log of failed login attempts
- [x] REQ-NFR-13: Server-side RBAC enforcement
- [x] REQ-NFR-21: Full audit trail (login, attendance, leave decisions)
- [x] REQ-NFR-27 to REQ-NFR-30: Correct attendance formula, N/A edge case, duplicate prevention, 66.67% threshold

---

## 🏗️ Architecture

```
Browser (HTML/CSS/JS)
    ↕ HTTP
Flask Application Server (Python)
    ├── RBAC Middleware
    ├── Business Logic (attendance %, leave workflow)
    └── Parameterized DB queries
    ↕ SQLite
attendify.db (6 tables: users, courses, faculty_courses, enrollments, attendance_records, leave_requests, audit_logs)
```

**Design Pattern:** MVC (Model-View-Controller)  
**Database:** SQLite (normalized to 3NF)  
**Security:** PBKDF2 password hashing, session tokens, RBAC, audit logging

---

## 🔄 Re-initialize Database
To start fresh with clean sample data:
```bash
python3 setup.py
```

---

## 📌 Notes for Evaluators
- The attendance percentage formula is: `(Attended ÷ (Held − OnLeave)) × 100`
- Attendance below 66.67% is highlighted in red on all views
- All admin actions and authentication events are logged in the audit trail
- CSV export is available for all attendance reports
- The system uses SQLite (file-based, no server setup required) for easy evaluation
