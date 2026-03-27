from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, make_response
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, os, csv, io, datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = 'attendify-secret-key-2026-se-lab'
app.permanent_session_lifetime = datetime.timedelta(minutes=30)

DB_PATH = os.path.join(os.path.dirname(__file__), 'instance', 'attendify.db')

#DB HELPERS

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    db = get_db()
    db.executescript(open(os.path.join(os.path.dirname(__file__), 'schema.sql')).read())
    db.commit()
    db.close()

#AUTH DECORATORS

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to continue.', 'warning')
            return redirect(url_for('login'))
        # Session timeout check
        last = session.get('last_activity')
        if last:
            elapsed = (datetime.datetime.now() - datetime.datetime.fromisoformat(last)).seconds
            if elapsed > 1800:
                session.clear()
                flash('Session expired. Please log in again.', 'warning')
                return redirect(url_for('login'))
        session['last_activity'] = datetime.datetime.now().isoformat()
        return f(*args, **kwargs)
    return decorated

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if session.get('role') not in roles:
                flash('Access denied.', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated
    return decorator

#AUDIT LOGGING

def log_action(user_id, action, details='', ip=''):
    db = get_db()
    db.execute(
        "INSERT INTO audit_logs (user_id, action, details, ip_address) VALUES (?,?,?,?)",
        (user_id, action, details, ip or request.remote_addr)
    )
    db.commit()
    db.close()

#ROUTES: AUTH

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET','POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username','').strip()
        password = request.form.get('password','')
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()

        if user is None or not check_password_hash(user['password_hash'], password):
            # Track failed attempts
            fails = session.get('login_fails', {})
            fails[username] = fails.get(username, 0) + 1
            session['login_fails'] = fails
            log_action(None, 'LOGIN_FAIL', f'username={username}', request.remote_addr)
            if fails[username] >= 5:
                flash('Account temporarily locked after 5 failed attempts. Try again in 15 minutes.', 'danger')
            else:
                flash('Invalid username or password.', 'danger')
            db.close()
            return render_template('login.html')

        if not user['is_active']:
            flash('Your account has been deactivated. Contact the administrator.', 'danger')
            db.close()
            return render_template('login.html')

        # Clear fail counter on success
        fails = session.get('login_fails', {})
        fails.pop(username, None)
        session.clear()
        session['login_fails'] = fails
        session['user_id'] = user['user_id']
        session['username'] = user['username']
        session['full_name'] = user['full_name']
        session['role'] = user['role']
        session['last_activity'] = datetime.datetime.now().isoformat()
        session.permanent = True
        log_action(user['user_id'], 'LOGIN', f'role={user["role"]}', request.remote_addr)
        db.close()
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    uid = session.get('user_id')
    if uid:
        log_action(uid, 'LOGOUT', '', request.remote_addr)
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    role = session['role']
    db = get_db()
    data = {}
    if role == 'ADMIN':
        data['total_users'] = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        data['total_courses'] = db.execute("SELECT COUNT(*) FROM courses").fetchone()[0]
        data['total_students'] = db.execute("SELECT COUNT(*) FROM users WHERE role='STUDENT'").fetchone()[0]
        data['total_faculty'] = db.execute("SELECT COUNT(*) FROM users WHERE role='FACULTY'").fetchone()[0]
        data['pending_leaves'] = db.execute("SELECT COUNT(*) FROM leave_requests WHERE status='PENDING'").fetchone()[0]
        data['recent_logs'] = db.execute(
            "SELECT al.*, u.full_name FROM audit_logs al LEFT JOIN users u ON al.user_id=u.user_id ORDER BY al.timestamp DESC LIMIT 8"
        ).fetchall()
    elif role == 'FACULTY':
        data['my_courses'] = db.execute(
            "SELECT c.* FROM courses c JOIN faculty_courses fc ON c.course_id=fc.course_id WHERE fc.faculty_id=?",
            (session['user_id'],)
        ).fetchall()
        data['pending_leaves'] = db.execute(
            """SELECT lr.*, u.full_name as student_name, c.course_name
               FROM leave_requests lr
               JOIN users u ON lr.student_id=u.user_id
               JOIN courses c ON lr.course_id=c.course_id
               JOIN faculty_courses fc ON lr.course_id=fc.course_id
               WHERE fc.faculty_id=? AND lr.status='PENDING'""",
            (session['user_id'],)
        ).fetchall()
        data['today_classes'] = len(data['my_courses'])
    elif role == 'STUDENT':
        courses = db.execute(
            "SELECT c.* FROM courses c JOIN enrollments e ON c.course_id=e.course_id WHERE e.student_id=?",
            (session['user_id'],)
        ).fetchall()
        attendance_data = []
        for c in courses:
            held = db.execute(
                "SELECT COUNT(DISTINCT attendance_date) FROM attendance_records WHERE course_id=? AND student_id=?",
                (c['course_id'], session['user_id'])
            ).fetchone()[0]
            leave = db.execute(
                "SELECT COUNT(*) FROM attendance_records WHERE course_id=? AND student_id=? AND status='ON_LEAVE'",
                (c['course_id'], session['user_id'])
            ).fetchone()[0]
            attended = db.execute(
                "SELECT COUNT(*) FROM attendance_records WHERE course_id=? AND student_id=? AND status='PRESENT'",
                (c['course_id'], session['user_id'])
            ).fetchone()[0]
            effective = held - leave
            pct = round((attended / effective) * 100, 2) if effective > 0 else None
            attendance_data.append({'course': c, 'held': held, 'attended': attended, 'leave': leave, 'pct': pct})
        data['attendance_data'] = attendance_data
        data['pending_leaves'] = db.execute(
            "SELECT COUNT(*) FROM leave_requests WHERE student_id=? AND status='PENDING'",
            (session['user_id'],)
        ).fetchone()[0]
    db.close()
    return render_template('dashboard.html', data=data)

#ROUTES: ATTENDANCE (FACULTY)

@app.route('/attendance/mark', methods=['GET','POST'])
@login_required
@role_required('FACULTY','ADMIN')
def mark_attendance():
    db = get_db()
    if session['role'] == 'ADMIN':
        courses = db.execute("SELECT * FROM courses").fetchall()
    else:
        courses = db.execute(
            "SELECT c.* FROM courses c JOIN faculty_courses fc ON c.course_id=fc.course_id WHERE fc.faculty_id=?",
            (session['user_id'],)
        ).fetchall()

    if request.method == 'POST':
        course_id = request.form.get('course_id')
        att_date = request.form.get('att_date')
        statuses = request.form.getlist('status')
        student_ids = request.form.getlist('student_id')

        if not course_id or not att_date:
            flash('Please select a course and date.', 'danger')
            db.close()
            return redirect(url_for('mark_attendance'))

        if len(statuses) != len(student_ids) or len(student_ids) == 0:
            flash('Please mark attendance for all students.', 'danger')
            db.close()
            return redirect(url_for('mark_attendance'))

        # Check 7-day warning
        att_dt = datetime.date.fromisoformat(att_date)
        days_old = (datetime.date.today() - att_dt).days
        if days_old > 7:
            flash(f'Warning: You are marking attendance for a date {days_old} days in the past.', 'warning')

        errors = []
        for sid, status in zip(student_ids, statuses):
            existing = db.execute(
                "SELECT record_id FROM attendance_records WHERE student_id=? AND course_id=? AND attendance_date=?",
                (sid, course_id, att_date)
            ).fetchone()
            if existing:
                # Update within 24h
                rec = db.execute("SELECT created_at FROM attendance_records WHERE record_id=?", (existing['record_id'],)).fetchone()
                created = datetime.datetime.fromisoformat(rec['created_at'])
                if (datetime.datetime.now() - created).seconds > 86400 and session['role'] != 'ADMIN':
                    errors.append(f'Cannot edit attendance older than 24h for student {sid}.')
                    continue
                db.execute(
                    "UPDATE attendance_records SET status=?, marked_by=?, updated_at=datetime('now') WHERE record_id=?",
                    (status, session['user_id'], existing['record_id'])
                )
            else:
                db.execute(
                    "INSERT INTO attendance_records (course_id, student_id, marked_by, attendance_date, status, updated_at) VALUES (?,?,?,?,?,datetime('now'))",
                    (course_id, sid, session['user_id'], att_date, status)
                )
        db.commit()
        log_action(session['user_id'], 'MARK_ATTENDANCE', f'course={course_id} date={att_date}')
        if errors:
            for e in errors:
                flash(e, 'warning')
        flash('Attendance recorded successfully.', 'success')
        db.close()
        return redirect(url_for('mark_attendance'))

    selected_course = request.args.get('course_id')
    selected_date = request.args.get('att_date', datetime.date.today().isoformat())
    students = []
    existing_records = {}

    if selected_course:
        students = db.execute(
            """SELECT u.user_id, u.full_name, u.username, u.batch FROM users u
               JOIN enrollments e ON u.user_id=e.student_id
               WHERE e.course_id=? AND u.is_active=1 ORDER BY u.full_name""",
            (selected_course,)
        ).fetchall()
        recs = db.execute(
            "SELECT student_id, status FROM attendance_records WHERE course_id=? AND attendance_date=?",
            (selected_course, selected_date)
        ).fetchall()
        existing_records = {r['student_id']: r['status'] for r in recs}
        # Get approved leaves for auto-populate
        leaves = db.execute(
            """SELECT student_id FROM leave_requests
               WHERE course_id=? AND status='APPROVED' AND from_date<=? AND to_date>=?""",
            (selected_course, selected_date, selected_date)
        ).fetchall()
        for lv in leaves:
            if lv['student_id'] not in existing_records:
                existing_records[lv['student_id']] = 'ON_LEAVE'

    db.close()
    return render_template('mark_attendance.html', courses=courses,
                           selected_course=selected_course, selected_date=selected_date,
                           students=students, existing_records=existing_records)

@app.route('/attendance/view')
@login_required
@role_required('STUDENT')
def view_attendance():
    db = get_db()
    courses = db.execute(
        "SELECT c.* FROM courses c JOIN enrollments e ON c.course_id=e.course_id WHERE e.student_id=?",
        (session['user_id'],)
    ).fetchall()
    selected = request.args.get('course_id')
    records = []
    summary = None
    if selected:
        records = db.execute(
            "SELECT * FROM attendance_records WHERE student_id=? AND course_id=? ORDER BY attendance_date DESC",
            (session['user_id'], selected)
        ).fetchall()
        held = db.execute(
            "SELECT COUNT(DISTINCT attendance_date) FROM attendance_records WHERE course_id=? AND student_id=?",
            (selected, session['user_id'])
        ).fetchone()[0]
        leave = db.execute(
            "SELECT COUNT(*) FROM attendance_records WHERE course_id=? AND student_id=? AND status='ON_LEAVE'",
            (selected, session['user_id'])
        ).fetchone()[0]
        attended = db.execute(
            "SELECT COUNT(*) FROM attendance_records WHERE course_id=? AND student_id=? AND status='PRESENT'",
            (selected, session['user_id'])
        ).fetchone()[0]
        effective = held - leave
        pct = round((attended / effective) * 100, 2) if effective > 0 else None
        summary = {'held': held, 'attended': attended, 'leave': leave, 'pct': pct}
    db.close()
    return render_template('view_attendance.html', courses=courses,
                           selected=selected, records=records, summary=summary)

#ROUTES: LEAVE

@app.route('/leave/apply', methods=['GET','POST'])
@login_required
@role_required('STUDENT')
def apply_leave():
    db = get_db()
    courses = db.execute(
        "SELECT c.* FROM courses c JOIN enrollments e ON c.course_id=e.course_id WHERE e.student_id=?",
        (session['user_id'],)
    ).fetchall()
    if request.method == 'POST':
        course_id = request.form.get('course_id')
        from_date = request.form.get('from_date')
        to_date = request.form.get('to_date')
        reason = request.form.get('reason','').strip()
        if from_date > to_date:
            flash('From Date cannot be after To Date.', 'danger')
        elif len(reason) < 10:
            flash('Reason must be at least 10 characters.', 'danger')
        else:
            db.execute(
                "INSERT INTO leave_requests (student_id, course_id, from_date, to_date, reason) VALUES (?,?,?,?,?)",
                (session['user_id'], course_id, from_date, to_date, reason)
            )
            db.commit()
            log_action(session['user_id'], 'APPLY_LEAVE', f'course={course_id}')
            flash('Leave application submitted successfully.', 'success')
            db.close()
            return redirect(url_for('my_leaves'))
    db.close()
    return render_template('apply_leave.html', courses=courses)

@app.route('/leave/my')
@login_required
@role_required('STUDENT')
def my_leaves():
    db = get_db()
    leaves = db.execute(
        """SELECT lr.*, c.course_name, u.full_name as faculty_name
           FROM leave_requests lr
           JOIN courses c ON lr.course_id=c.course_id
           LEFT JOIN users u ON lr.reviewed_by=u.user_id
           WHERE lr.student_id=? ORDER BY lr.submitted_at DESC""",
        (session['user_id'],)
    ).fetchall()
    db.close()
    return render_template('my_leaves.html', leaves=leaves)

@app.route('/leave/manage')
@login_required
@role_required('FACULTY','ADMIN')
def manage_leaves():
    db = get_db()
    if session['role'] == 'ADMIN':
        leaves = db.execute(
            """SELECT lr.*, u.full_name as student_name, c.course_name
               FROM leave_requests lr
               JOIN users u ON lr.student_id=u.user_id
               JOIN courses c ON lr.course_id=c.course_id
               WHERE lr.status='PENDING' ORDER BY lr.submitted_at DESC"""
        ).fetchall()
    else:
        leaves = db.execute(
            """SELECT lr.*, u.full_name as student_name, c.course_name
               FROM leave_requests lr
               JOIN users u ON lr.student_id=u.user_id
               JOIN courses c ON lr.course_id=c.course_id
               JOIN faculty_courses fc ON lr.course_id=fc.course_id
               WHERE fc.faculty_id=? AND lr.status='PENDING'
               ORDER BY lr.submitted_at DESC""",
            (session['user_id'],)
        ).fetchall()
    db.close()
    return render_template('manage_leaves.html', leaves=leaves)

@app.route('/leave/action/<int:leave_id>', methods=['POST'])
@login_required
@role_required('FACULTY','ADMIN')
def leave_action(leave_id):
    action = request.form.get('action')
    comment = request.form.get('comment','')
    status = 'APPROVED' if action == 'approve' else 'REJECTED'
    db = get_db()
    leave = db.execute("SELECT * FROM leave_requests WHERE leave_id=?", (leave_id,)).fetchone()
    if not leave:
        flash('Leave request not found.', 'danger')
        db.close()
        return redirect(url_for('manage_leaves'))
    db.execute(
        """UPDATE leave_requests SET status=?, reviewed_by=?, faculty_comment=?,
           reviewed_at=datetime('now') WHERE leave_id=?""",
        (status, session['user_id'], comment, leave_id)
    )
    # Auto-update attendance if approved
    if status == 'APPROVED':
        from_d = datetime.date.fromisoformat(leave['from_date'])
        to_d = datetime.date.fromisoformat(leave['to_date'])
        cur = from_d
        while cur <= to_d:
            existing = db.execute(
                "SELECT record_id FROM attendance_records WHERE student_id=? AND course_id=? AND attendance_date=?",
                (leave['student_id'], leave['course_id'], cur.isoformat())
            ).fetchone()
            if existing:
                db.execute("UPDATE attendance_records SET status='ON_LEAVE', updated_at=datetime('now') WHERE record_id=?",
                           (existing['record_id'],))
            cur += datetime.timedelta(days=1)
    db.commit()
    log_action(session['user_id'], f'LEAVE_{status}', f'leave_id={leave_id}')
    flash(f'Leave application {status.lower()}.', 'success')
    db.close()
    return redirect(url_for('manage_leaves'))

#ROUTES: REPORTS

@app.route('/reports', methods=['GET'])
@login_required
@role_required('FACULTY','ADMIN')
def reports():
    db = get_db()
    if session['role'] == 'ADMIN':
        courses = db.execute("SELECT * FROM courses").fetchall()
    else:
        courses = db.execute(
            "SELECT c.* FROM courses c JOIN faculty_courses fc ON c.course_id=fc.course_id WHERE fc.faculty_id=?",
            (session['user_id'],)
        ).fetchall()
    course_id = request.args.get('course_id')
    from_date = request.args.get('from_date','')
    to_date = request.args.get('to_date','')
    report_data = []
    if course_id:
        query = """
            SELECT u.user_id, u.username as roll_no, u.full_name,
                   COUNT(CASE WHEN ar.status='PRESENT' THEN 1 END) as attended,
                   COUNT(CASE WHEN ar.status='ON_LEAVE' THEN 1 END) as on_leave,
                   COUNT(ar.record_id) as held
            FROM users u
            JOIN enrollments e ON u.user_id=e.student_id AND e.course_id=?
            LEFT JOIN attendance_records ar ON ar.student_id=u.user_id AND ar.course_id=?
        """
        params = [course_id, course_id]
        if from_date:
            query += " AND ar.attendance_date >= ?"
            params.append(from_date)
        if to_date:
            query += " AND ar.attendance_date <= ?"
            params.append(to_date)
        query += " GROUP BY u.user_id ORDER BY u.username"
        rows = db.execute(query, params).fetchall()
        for r in rows:
            effective = r['held'] - r['on_leave']
            pct = round((r['attended'] / effective) * 100, 2) if effective > 0 else None
            report_data.append({
                'roll_no': r['roll_no'],
                'full_name': r['full_name'],
                'held': r['held'],
                'attended': r['attended'],
                'on_leave': r['on_leave'],
                'pct': pct
            })
    db.close()
    return render_template('reports.html', courses=courses, report_data=report_data,
                           course_id=course_id, from_date=from_date, to_date=to_date)

@app.route('/reports/export')
@login_required
@role_required('FACULTY','ADMIN')
def export_report():
    db = get_db()
    course_id = request.args.get('course_id')
    from_date = request.args.get('from_date','')
    to_date = request.args.get('to_date','')
    if not course_id:
        flash('No course selected.', 'danger')
        return redirect(url_for('reports'))
    query = """
        SELECT u.username as roll_no, u.full_name,
               COUNT(CASE WHEN ar.status='PRESENT' THEN 1 END) as attended,
               COUNT(CASE WHEN ar.status='ON_LEAVE' THEN 1 END) as on_leave,
               COUNT(ar.record_id) as held
        FROM users u
        JOIN enrollments e ON u.user_id=e.student_id AND e.course_id=?
        LEFT JOIN attendance_records ar ON ar.student_id=u.user_id AND ar.course_id=?
    """
    params = [course_id, course_id]
    if from_date:
        query += " AND ar.attendance_date >= ?"
        params.append(from_date)
    if to_date:
        query += " AND ar.attendance_date <= ?"
        params.append(to_date)
    query += " GROUP BY u.user_id ORDER BY u.username"
    rows = db.execute(query, params).fetchall()
    course = db.execute("SELECT course_name FROM courses WHERE course_id=?", (course_id,)).fetchone()
    db.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Roll No', 'Full Name', 'Classes Held', 'Classes Attended', 'On Leave', 'Attendance %'])
    for r in rows:
        effective = r['held'] - r['on_leave']
        pct = round((r['attended'] / effective) * 100, 2) if effective > 0 else 'N/A'
        writer.writerow([r['roll_no'], r['full_name'], r['held'], r['attended'], r['on_leave'], pct])
    output.seek(0)
    resp = make_response(output.getvalue())
    resp.headers['Content-Disposition'] = f'attachment; filename=attendance_{course["course_name"].replace(" ","_")}.csv'
    resp.headers['Content-Type'] = 'text/csv'
    return resp

#ROUTES: USER MANAGEMENT (ADMIN)

@app.route('/admin/users')
@login_required
@role_required('ADMIN')
def admin_users():
    db = get_db()
    role_filter = request.args.get('role','')
    status_filter = request.args.get('status','')
    search = request.args.get('search','')
    q = "SELECT * FROM users WHERE 1=1"
    params = []
    if role_filter:
        q += " AND role=?"; params.append(role_filter)
    if status_filter == 'active':
        q += " AND is_active=1"
    elif status_filter == 'inactive':
        q += " AND is_active=0"
    if search:
        q += " AND (full_name LIKE ? OR username LIKE ?)"
        params += [f'%{search}%', f'%{search}%']
    q += " ORDER BY full_name"
    users = db.execute(q, params).fetchall()
    db.close()
    return render_template('admin_users.html', users=users,
                           role_filter=role_filter, status_filter=status_filter, search=search)

@app.route('/admin/users/create', methods=['GET','POST'])
@login_required
@role_required('ADMIN')
def create_user():
    if request.method == 'POST':
        username = request.form.get('username','').strip()
        full_name = request.form.get('full_name','').strip()
        email = request.form.get('email','').strip()
        role = request.form.get('role','').strip()
        password = request.form.get('password','')
        batch = request.form.get('batch','').strip()
        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'danger')
            return render_template('create_user.html')
        if '@' not in email or '.' not in email.split('@')[-1]:
            flash('Invalid email format.', 'danger')
            return render_template('create_user.html')
        db = get_db()
        existing = db.execute("SELECT user_id FROM users WHERE username=?", (username,)).fetchone()
        if existing:
            flash('Username already exists.', 'danger')
            db.close()
            return render_template('create_user.html')
        pw_hash = generate_password_hash(password)
        db.execute(
            "INSERT INTO users (username, password_hash, full_name, email, role, batch) VALUES (?,?,?,?,?,?)",
            (username, pw_hash, full_name, email, role, batch)
        )
        db.commit()
        log_action(session['user_id'], 'CREATE_USER', f'username={username} role={role}')
        flash(f'User "{username}" created successfully.', 'success')
        db.close()
        return redirect(url_for('admin_users'))
    return render_template('create_user.html')

@app.route('/admin/users/edit/<int:user_id>', methods=['GET','POST'])
@login_required
@role_required('ADMIN')
def edit_user(user_id):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not user:
        flash('User not found.', 'danger')
        db.close()
        return redirect(url_for('admin_users'))
    if request.method == 'POST':
        full_name = request.form.get('full_name','').strip()
        email = request.form.get('email','').strip()
        role = request.form.get('role','').strip()
        batch = request.form.get('batch','').strip()
        db.execute("UPDATE users SET full_name=?, email=?, role=?, batch=? WHERE user_id=?",
                   (full_name, email, role, batch, user_id))
        db.commit()
        log_action(session['user_id'], 'EDIT_USER', f'user_id={user_id}')
        flash('User updated successfully.', 'success')
        db.close()
        return redirect(url_for('admin_users'))
    db.close()
    return render_template('edit_user.html', user=user)

@app.route('/admin/users/toggle/<int:user_id>', methods=['POST'])
@login_required
@role_required('ADMIN')
def toggle_user(user_id):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    new_status = 0 if user['is_active'] else 1
    db.execute("UPDATE users SET is_active=? WHERE user_id=?", (new_status, user_id))
    db.commit()
    action = 'ACTIVATE_USER' if new_status else 'DEACTIVATE_USER'
    log_action(session['user_id'], action, f'user_id={user_id}')
    flash(f'User {"activated" if new_status else "deactivated"} successfully.', 'success')
    db.close()
    return redirect(url_for('admin_users'))

#ROUTES: COURSE MANAGEMENT (ADMIN)

@app.route('/admin/courses')
@login_required
@role_required('ADMIN')
def admin_courses():
    db = get_db()
    courses = db.execute("SELECT * FROM courses ORDER BY course_code").fetchall()
    db.close()
    return render_template('admin_courses.html', courses=courses)

@app.route('/admin/courses/create', methods=['GET','POST'])
@login_required
@role_required('ADMIN')
def create_course():
    if request.method == 'POST':
        code = request.form.get('course_code','').strip().upper()
        name = request.form.get('course_name','').strip()
        credits = request.form.get('credits', 0)
        db = get_db()
        existing = db.execute("SELECT course_id FROM courses WHERE course_code=?", (code,)).fetchone()
        if existing:
            flash('Course code already exists.', 'danger')
            db.close()
            return render_template('create_course.html')
        db.execute("INSERT INTO courses (course_code, course_name, credits) VALUES (?,?,?)",
                   (code, name, credits))
        db.commit()
        log_action(session['user_id'], 'CREATE_COURSE', f'code={code}')
        flash(f'Course "{name}" created successfully.', 'success')
        db.close()
        return redirect(url_for('admin_courses'))
    return render_template('create_course.html')

@app.route('/admin/courses/delete/<int:course_id>', methods=['POST'])
@login_required
@role_required('ADMIN')
def delete_course(course_id):
    db = get_db()
    # REQ-8.9: Cannot delete course with existing attendance records
    att_count = db.execute(
        "SELECT COUNT(*) FROM attendance_records WHERE course_id=?", (course_id,)
    ).fetchone()[0]
    if att_count > 0:
        flash(f'Cannot delete this course — it has {att_count} existing attendance records. Remove all attendance data first.', 'danger')
        db.close()
        return redirect(url_for('admin_courses'))
    course = db.execute("SELECT course_name FROM courses WHERE course_id=?", (course_id,)).fetchone()
    if not course:
        flash('Course not found.', 'danger')
        db.close()
        return redirect(url_for('admin_courses'))
    # Also remove enrollments and faculty assignments first
    db.execute("DELETE FROM enrollments WHERE course_id=?", (course_id,))
    db.execute("DELETE FROM faculty_courses WHERE course_id=?", (course_id,))
    db.execute("DELETE FROM courses WHERE course_id=?", (course_id,))
    db.commit()
    log_action(session['user_id'], 'DELETE_COURSE', f'course={course["course_name"]}')
    flash(f'Course "{course["course_name"]}" deleted successfully.', 'success')
    db.close()
    return redirect(url_for('admin_courses'))

@app.route('/admin/courses/edit/<int:course_id>', methods=['GET','POST'])
@login_required
@role_required('ADMIN')
def edit_course(course_id):
    db = get_db()
    course = db.execute("SELECT * FROM courses WHERE course_id=?", (course_id,)).fetchone()
    if request.method == 'POST':
        name = request.form.get('course_name','').strip()
        credits = request.form.get('credits', 0)
        db.execute("UPDATE courses SET course_name=?, credits=? WHERE course_id=?", (name, credits, course_id))
        db.commit()
        flash('Course updated.', 'success')
        db.close()
        return redirect(url_for('admin_courses'))
    db.close()
    return render_template('edit_course.html', course=course)

@app.route('/admin/courses/enroll/<int:course_id>', methods=['GET','POST'])
@login_required
@role_required('ADMIN')
def enroll_students(course_id):
    db = get_db()
    course = db.execute("SELECT * FROM courses WHERE course_id=?", (course_id,)).fetchone()
    enrolled = db.execute(
        "SELECT u.* FROM users u JOIN enrollments e ON u.user_id=e.student_id WHERE e.course_id=? AND u.role='STUDENT'",
        (course_id,)
    ).fetchall()
    enrolled_ids = [e['user_id'] for e in enrolled]
    all_students = db.execute("SELECT * FROM users WHERE role='STUDENT' AND is_active=1 ORDER BY full_name").fetchall()
    faculty_list = db.execute("SELECT * FROM users WHERE role='FACULTY' AND is_active=1 ORDER BY full_name").fetchall()
    assigned_faculty = db.execute(
        "SELECT faculty_id FROM faculty_courses WHERE course_id=?", (course_id,)
    ).fetchall()
    assigned_ids = [f['faculty_id'] for f in assigned_faculty]

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'enroll':
            student_ids = request.form.getlist('student_ids')
            semester = request.form.get('semester', 4)
            for sid in student_ids:
                try:
                    db.execute("INSERT INTO enrollments (student_id, course_id, semester) VALUES (?,?,?)",
                               (sid, course_id, semester))
                except: pass
            db.commit()
            flash('Students enrolled.', 'success')
        elif action == 'unenroll':
            sid = request.form.get('student_id')
            db.execute("DELETE FROM enrollments WHERE student_id=? AND course_id=?", (sid, course_id))
            db.commit()
            flash('Student removed from course.', 'success')
        elif action == 'assign_faculty':
            fid = request.form.get('faculty_id')
            try:
                db.execute("INSERT INTO faculty_courses (faculty_id, course_id) VALUES (?,?)", (fid, course_id))
                db.commit()
                flash('Faculty assigned.', 'success')
            except:
                flash('Faculty already assigned.', 'warning')
        elif action == 'unassign_faculty':
            fid = request.form.get('faculty_id')
            db.execute("DELETE FROM faculty_courses WHERE faculty_id=? AND course_id=?", (fid, course_id))
            db.commit()
            flash('Faculty removed.', 'success')
        db.close()
        return redirect(url_for('enroll_students', course_id=course_id))
    db.close()
    return render_template('enroll_students.html', course=course, enrolled=enrolled,
                           all_students=all_students, enrolled_ids=enrolled_ids,
                           faculty_list=faculty_list, assigned_ids=assigned_ids)

@app.route('/admin/logs')
@login_required
@role_required('ADMIN')
def audit_logs():
    db = get_db()
    logs = db.execute(
        "SELECT al.*, u.full_name FROM audit_logs al LEFT JOIN users u ON al.user_id=u.user_id ORDER BY al.timestamp DESC LIMIT 200"
    ).fetchall()
    db.close()
    return render_template('audit_logs.html', logs=logs)

@app.context_processor
def inject_now():
    return {'now': datetime.datetime.now().strftime('%d %b %Y, %H:%M')}

if __name__ == '__main__':
    os.makedirs(os.path.join(os.path.dirname(__file__), 'instance'), exist_ok=True)
    if not os.path.exists(DB_PATH):
        init_db()
    app.run(debug=True, port=5000)
