from flask import Flask, render_template, request, jsonify, g, redirect, url_for, flash, send_file, session
import sqlite3
from datetime import datetime, timedelta
import random
from collections import defaultdict
import pandas as pd
from fpdf import FPDF
import io
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
DB_PATH = 'timetable.db'
DAYS = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT']
app.secret_key = 'your_very_secret_key_for_sessions'
app.permanent_session_lifetime = timedelta(days=30) # Added for "Remember Me"

# --- DATABASE HELPERS ---
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
        g._database = db
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        cur = db.cursor()

        cur.execute("PRAGMA table_info(courses)")
        columns = [row['name'] for row in cur.fetchall()]
        if 'classroom_id' not in columns:
            cur.execute("ALTER TABLE courses ADD COLUMN classroom_id INTEGER REFERENCES classrooms(classroom_id)")

        cur.executescript('''
            CREATE TABLE IF NOT EXISTS teachers (
                teacher_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS teacher_preferences (
                teacher_id INTEGER PRIMARY KEY,
                preference TEXT,
                FOREIGN KEY (teacher_id) REFERENCES teachers(teacher_id)
            );
            CREATE TABLE IF NOT EXISTS subjects (
                subject_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                code TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS classes (
                class_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                num_batches INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS classrooms (
                classroom_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                is_lab INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS courses (
                course_id INTEGER PRIMARY KEY AUTOINCREMENT,
                class_id INTEGER,
                subject_id INTEGER,
                teacher_id INTEGER,
                weekly_lectures INTEGER NOT NULL,
                is_lab INTEGER NOT NULL DEFAULT 0,
                classroom_id INTEGER,
                FOREIGN KEY (class_id) REFERENCES classes(class_id),
                FOREIGN KEY (subject_id) REFERENCES subjects(subject_id),
                FOREIGN KEY (teacher_id) REFERENCES teachers(teacher_id),
                FOREIGN KEY (classroom_id) REFERENCES classrooms(classroom_id)
            );
            CREATE TABLE IF NOT EXISTS timetable_slots (
                slot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                class_id INTEGER,
                day TEXT,
                time_start TEXT,
                time_end TEXT,
                course_id INTEGER,
                teacher_id INTEGER,
                classroom_id INTEGER,
                batch_number INTEGER,
                FOREIGN KEY (class_id) REFERENCES classes(class_id),
                FOREIGN KEY (course_id) REFERENCES courses(course_id),
                FOREIGN KEY (teacher_id) REFERENCES teachers(teacher_id),
                FOREIGN KEY (classroom_id) REFERENCES classrooms(classroom_id)
            );
            CREATE TABLE IF NOT EXISTS schedule_config (
                config_id INTEGER PRIMARY KEY AUTOINCREMENT,
                is_break INTEGER,
                start_time TEXT,
                end_time TEXT,
                break_name TEXT
            );
            CREATE TABLE IF NOT EXISTS batch_teacher_assignments (
                assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                class_id INTEGER NOT NULL,
                subject_id INTEGER NOT NULL,
                batch_number INTEGER NOT NULL,
                teacher_id INTEGER NOT NULL,
                FOREIGN KEY(class_id) REFERENCES classes(class_id),
                FOREIGN KEY(subject_id) REFERENCES subjects(subject_id),
                FOREIGN KEY(teacher_id) REFERENCES teachers(teacher_id),
                UNIQUE(class_id, subject_id, batch_number)
            );
            CREATE TABLE IF NOT EXISTS generation_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            );
        ''')
        cur.execute("INSERT OR IGNORE INTO generation_settings (key, value) VALUES ('practical_preference', 'none')")
        
        cur.execute("SELECT * FROM admins")
        if cur.fetchone() is None:
            cur.execute("INSERT INTO admins (username, password_hash) VALUES (?, ?)", 
                        ('admin', generate_password_hash('admin123')))
        
        db.commit()

# --- AUTHENTICATION ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_id' not in session:
            flash('You need to be logged in to access this page.', 'warning')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# --- TIMETABLE GENERATION & VALIDATION ---
def get_slot_times():
    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT * FROM schedule_config ORDER BY config_id')
    return cur.fetchall()

def generate_timetable():
    db = get_db()
    cur = db.cursor()
    cur.execute('DELETE FROM timetable_slots')
    db.commit()

    courses = cur.execute('''
        SELECT c.*, s.name as subject_name, cl.name as class_name, cl.num_batches 
        FROM courses c 
        JOIN subjects s ON c.subject_id = s.subject_id
        JOIN classes cl ON c.class_id = cl.class_id
    ''').fetchall()
    
    theory_rooms = [r for r in cur.execute('SELECT * FROM classrooms WHERE is_lab = 0').fetchall()]
    
    teacher_prefs = {row['teacher_id']: row['preference'] for row in cur.execute('SELECT * FROM teacher_preferences').fetchall()}
    
    batch_assignments = defaultdict(dict)
    for a in cur.execute('SELECT * FROM batch_teacher_assignments').fetchall():
        batch_assignments[(a['class_id'], a['subject_id'])][a['batch_number']] = a['teacher_id']

    SLOTS = get_slot_times()
    TEACHABLE_SLOTS = [s for s in SLOTS if s['is_break'] == 0]
    
    # --- IN-MEMORY GRID ---
    grid = {day: {slot['start_time']: {'teacher': None, 'classroom': None, 'batches': set()} for slot in TEACHABLE_SLOTS} for day in DAYS}

    # Helper to check the in-memory grid
    def is_block_free(day, start_slot_index, duration, teacher_id, classroom_id, class_id, batch_number=None):
        for i in range(duration):
            slot_time = TEACHABLE_SLOTS[start_slot_index + i]['start_time']
            slot_info = grid[day][slot_time]
            
            # Check teacher, classroom, and batch availability
            if slot_info['teacher'] == teacher_id: return False
            if slot_info['classroom'] == classroom_id: return False
            
            if batch_number: # Practical
                if batch_number in slot_info['batches']: return False # This batch is busy
                if f"class_{class_id}" in slot_info['batches']: return False # The whole class is busy
            else: # Theory
                if len(slot_info['batches']) > 0: return False # Any batch is busy
                
        return True

    # Helper to book a slot in the in-memory grid
    def book_block(day, start_slot_index, duration, teacher_id, classroom_id, class_id, batch_number=None):
        for i in range(duration):
            slot_time = TEACHABLE_SLOTS[start_slot_index + i]['start_time']
            grid[day][slot_time]['teacher'] = teacher_id
            grid[day][slot_time]['classroom'] = classroom_id
            if batch_number:
                grid[day][slot_time]['batches'].add(batch_number)
            else:
                grid[day][slot_time]['batches'].add(f"class_{class_id}")
    
    # --- Schedule Practicals First ---
    labs_to_schedule = []
    for course in courses:
        if course['is_lab']:
            for _ in range(course['weekly_lectures'] // 2):
                for batch in range(1, course['num_batches'] + 1):
                    teacher_id = batch_assignments.get((course['class_id'], course['subject_id']), {}).get(batch, course['teacher_id'])
                    labs_to_schedule.append({'course': course, 'batch': batch, 'teacher_id': teacher_id})
    
    random.shuffle(labs_to_schedule)

    for lab_session in labs_to_schedule:
        course, batch, teacher_id = lab_session['course'], lab_session['batch'], lab_session['teacher_id']
        lab_classroom = cur.execute('SELECT * FROM classrooms WHERE classroom_id = ?', (course['classroom_id'],)).fetchone()

        if not lab_classroom: continue
        
        placed = False
        for _ in range(200):
            day = random.choice(DAYS)
            slot_index = random.choice(range(len(TEACHABLE_SLOTS) - 1))
            
            if is_block_free(day, slot_index, 2, teacher_id, lab_classroom['classroom_id'], course['class_id'], batch):
                book_block(day, slot_index, 2, teacher_id, lab_classroom['classroom_id'], course['class_id'], batch)
                start_time = TEACHABLE_SLOTS[slot_index]['start_time']
                end_time = TEACHABLE_SLOTS[slot_index + 1]['end_time']
                cur.execute('INSERT INTO timetable_slots (class_id, day, time_start, time_end, course_id, teacher_id, classroom_id, batch_number) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                            (course['class_id'], day, start_time, end_time, course['course_id'], teacher_id, lab_classroom['classroom_id'], batch))
                placed = True
                break
        if not placed:
             print(f"Warning: Could not schedule lab for {course['subject_name']} Batch {batch}")

    # --- Schedule Theory Lectures ---
    lectures_to_schedule = []
    for course in courses:
        if not course['is_lab']:
            for _ in range(course['weekly_lectures']):
                lectures_to_schedule.append(course)
    
    random.shuffle(lectures_to_schedule)
    
    for lecture in lectures_to_schedule:
        placed = False
        teacher_id = lecture['teacher_id']
        
        for _ in range(100):
            day = random.choice(DAYS)
            slot_index = random.choice(range(len(TEACHABLE_SLOTS)))
            room = random.choice(theory_rooms)
            
            if is_block_free(day, slot_index, 1, teacher_id, room['classroom_id'], lecture['class_id']):
                book_block(day, slot_index, 1, teacher_id, room['classroom_id'], lecture['class_id'])
                start_time = TEACHABLE_SLOTS[slot_index]['start_time']
                end_time = TEACHABLE_SLOTS[slot_index]['end_time']
                cur.execute('INSERT INTO timetable_slots (class_id, day, time_start, time_end, course_id, teacher_id, classroom_id, batch_number) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)',
                            (lecture['class_id'], day, start_time, end_time, lecture['course_id'], teacher_id, room['classroom_id']))
                placed = True
                break
        if not placed:
            print(f"Warning: Could not schedule lecture for {lecture['subject_name']}")
            
    db.commit()


# --- ROUTES ---
@app.route('/manage', methods=['GET', 'POST'])
@login_required
def manage():
    db = get_db()
    cur = db.cursor()

    if request.method == 'POST':
        form_name = request.form.get('form_name')
        if form_name == 'add_teacher_form':
            name = request.form['teacher_name']
            preference = request.form['teacher_pref']
            try:
                db.execute('INSERT INTO teachers (name) VALUES (?)', (name,))
                if preference:
                    db.execute('INSERT OR IGNORE INTO teacher_preferences (teacher_id, preference) VALUES ((SELECT teacher_id FROM teachers WHERE name = ?), ?)', (name, preference))
                db.commit()
                flash(f'Teacher "{name}" added successfully!', 'success')
            except sqlite3.IntegrityError:
                flash(f'Error: Teacher "{name}" already exists.', 'error')
            return redirect(url_for('manage'))
        
        elif form_name == 'add_subject_form':
            name = request.form['subject_name']
            code = request.form['subject_code']
            try:
                db.execute('INSERT INTO subjects (name, code) VALUES (?, ?)', (name, code))
                db.commit()
                flash(f'Subject "{name}" added successfully!', 'success')
            except sqlite3.IntegrityError:
                flash(f'Error: Subject "{name}" already exists.', 'error')
            return redirect(url_for('manage'))

        elif form_name == 'add_class_form':
            name = request.form['class_name']
            num_batches = int(request.form.get('num_batches', 1))
            try:
                db.execute('INSERT INTO classes (name, num_batches) VALUES (?, ?)', (name, num_batches))
                db.commit()
                flash(f'Class "{name}" added successfully!', 'success')
            except sqlite3.IntegrityError:
                flash(f'Error: Class "{name}" already exists.', 'error')
            return redirect(url_for('manage'))

        elif form_name == 'add_classroom_form':
            name = request.form['classroom_name']
            is_lab = int(request.form['is_lab'])
            try:
                db.execute('INSERT INTO classrooms (name, is_lab) VALUES (?, ?)', (name, is_lab))
                db.commit()
                flash(f'Classroom "{name}" added successfully!', 'success')
            except sqlite3.IntegrityError:
                flash(f'Error: Classroom "{name}" already exists.', 'error')
            return redirect(url_for('manage'))

        elif form_name == 'add_course_form':
            class_id = request.form['course_class']
            subject_id = request.form['course_subject']
            teacher_id = request.form['course_teacher']
            weekly_lectures = request.form['weekly_lectures']
            is_lab = 1 if 'is_lab_checkbox' in request.form else 0
            classroom_id = request.form.get('lab_classroom') if is_lab else None
            try:
                db.execute('INSERT INTO courses (class_id, subject_id, teacher_id, weekly_lectures, is_lab, classroom_id) VALUES (?, ?, ?, ?, ?, ?)',
                           (class_id, subject_id, teacher_id, weekly_lectures, is_lab, classroom_id))
                db.commit()
                flash('Course assignment added successfully!', 'success')
            except sqlite3.IntegrityError:
                flash('Error: Course assignment already exists.', 'error')
            return redirect(url_for('manage'))
        
        elif form_name == 'batch_teacher_form':
            class_id = request.form.get('class_id')
            subject_id = request.form.get('subject_id')
            
            db.execute('DELETE FROM batch_teacher_assignments WHERE class_id = ? AND subject_id = ?', (class_id, subject_id))
            
            for key, teacher_id in request.form.items():
                if key.startswith('teacher_batch_'):
                    batch_number = key.replace('teacher_batch_', '')
                    if teacher_id:
                        db.execute('''
                            INSERT INTO batch_teacher_assignments (class_id, subject_id, batch_number, teacher_id)
                            VALUES (?, ?, ?, ?)
                        ''', (class_id, subject_id, batch_number, teacher_id))
            db.commit()
            flash('Batch-teacher assignments saved successfully!', 'success')
            return redirect(url_for('manage'))

        elif form_name == 'schedule_config_form':
            start_times = request.form.getlist('start_time')
            end_times = request.form.getlist('end_time')
            is_breaks = request.form.getlist('is_break')
            break_names = request.form.getlist('break_name')
            config_ids = request.form.getlist('config_id')
            
            db.execute('BEGIN TRANSACTION')
            try:
                current_ids_rows = db.execute('SELECT config_id FROM schedule_config').fetchall()
                current_ids = {row[0] for row in current_ids_rows}
                submitted_ids = {int(i) for i in config_ids if i}
                ids_to_delete = current_ids - submitted_ids
                
                if ids_to_delete:
                    db.execute(f'DELETE FROM schedule_config WHERE config_id IN ({",".join("?"*len(ids_to_delete))})', list(ids_to_delete))
                
                break_name_counter = 0
                for i in range(len(start_times)):
                    config_id = config_ids[i]
                    is_break = int(is_breaks[i])
                    start_time = start_times[i]
                    end_time = end_times[i]
                    
                    break_name = None
                    if is_break == 1: 
                        break_name = break_names[break_name_counter] if break_names[break_name_counter] else None
                        break_name_counter += 1

                    if config_id:
                        db.execute('UPDATE schedule_config SET is_break=?, start_time=?, end_time=?, break_name=? WHERE config_id=?',
                                   (is_break, start_time, end_time, break_name, config_id))
                    else:
                        db.execute('INSERT INTO schedule_config (is_break, start_time, end_time, break_name) VALUES (?, ?, ?, ?)',
                                   (is_break, start_time, end_time, break_name))
                
                db.commit()
                flash('Schedule configuration saved successfully!', 'success')
            except Exception as e:
                db.rollback()
                flash(f'Error saving schedule: {e}', 'error')
            return redirect(url_for('manage'))

        elif form_name == 'practical_pref_form':
            preference = request.form.get('practical_preference')
            db.execute("UPDATE generation_settings SET value = ? WHERE key = 'practical_preference'", (preference,))
            db.commit()
            flash('Practical session preference saved!', 'success')
            return redirect(url_for('manage'))

        elif form_name.startswith('delete_'):
            entity = form_name.replace('delete_', '').replace('_form', '')
            id_map = {
                'teacher': 'teacher_id',
                'subject': 'subject_id',
                'class': 'class_id',
                'classroom': 'classroom_id',
                'course': 'course_id'
            }
            column_id = id_map.get(entity)
            if column_id:
                try:
                    record_id = request.form[f'{entity}_id']
                    table_name = 'classes' if entity == 'class' else f'{entity}s'
                    db.execute(f'DELETE FROM {table_name} WHERE {column_id} = ?', (record_id,))
                    db.commit()
                    flash(f'{entity.capitalize()} deleted successfully!', 'success')
                except (sqlite3.IntegrityError, KeyError):
                    flash(f'Error: Cannot delete {entity} because it is in use by another record.', 'error')
            return redirect(url_for('manage'))

    # CORRECTED VALIDATION WARNING LOGIC
    warnings = []
    classes_list = cur.execute('SELECT * FROM classes').fetchall()
    for class_obj in classes_list:
        if class_obj['num_batches'] > 1:
            practicals_count = cur.execute('SELECT COUNT(DISTINCT subject_id) FROM courses WHERE class_id = ? AND is_lab = 1', (class_obj['class_id'],)).fetchone()[0]
            if class_obj['num_batches'] > practicals_count:
                 warnings.append(f"For class '{class_obj['name']}', the number of batches ({class_obj['num_batches']}) is greater than assigned practical subjects ({practicals_count}). Some batches will miss practicals.")

    teachers = cur.execute('SELECT teachers.*, teacher_preferences.preference FROM teachers LEFT JOIN teacher_preferences ON teachers.teacher_id = teacher_preferences.teacher_id').fetchall()
    subjects = cur.execute('SELECT * FROM subjects').fetchall()
    classrooms = cur.execute('SELECT * FROM classrooms').fetchall()
    courses = cur.execute('''
        SELECT c.*, t.name as teacher_name, sub.name as subject_name, cl.name as class_name, cl.num_batches
        FROM courses c 
        JOIN teachers t ON c.teacher_id = t.teacher_id 
        JOIN subjects sub ON c.subject_id = sub.subject_id
        JOIN classes cl ON c.class_id = cl.class_id
    ''').fetchall()
    
    batch_assignments = defaultdict(lambda: defaultdict(dict))
    assignments = cur.execute('''
        SELECT b.*, t.name as teacher_name 
        FROM batch_teacher_assignments b 
        JOIN teachers t ON b.teacher_id = t.teacher_id
    ''').fetchall()
    for a in assignments:
        batch_assignments[a['class_id']][a['subject_id']][a['batch_number']] = a['teacher_id']

    schedule_config = get_slot_times()
    practical_preference = cur.execute("SELECT value FROM generation_settings WHERE key = 'practical_preference'").fetchone()['value']
    lab_classrooms = cur.execute('SELECT * FROM classrooms WHERE is_lab = 1').fetchall()
    
    return render_template('manage.html', 
                           teachers=teachers, 
                           subjects=subjects, 
                           classes=classes_list, 
                           classrooms=classrooms, 
                           courses=courses, 
                           schedule_config=schedule_config,
                           warnings=warnings,
                           batch_assignments=batch_assignments,
                           practical_preference=practical_preference,
                           lab_classrooms=lab_classrooms)

@app.route('/')
def index():
    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT name, class_id FROM classes')
    classes = [dict(row) for row in cur.fetchall()]
    return render_template('index.html', classes=classes)

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if 'admin_id' in session:
        return redirect(url_for('manage'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        db = get_db()
        admin = db.execute('SELECT * FROM admins WHERE username = ?', (username,)).fetchone()

        if admin and check_password_hash(admin['password_hash'], password):
            session.clear()
            session['admin_id'] = admin['id']
            session['admin_username'] = admin['username']
            return redirect(url_for('manage'))
        else:
            flash('Invalid username or password.', 'danger')

    return render_template('login.html')

@app.route('/admin/logout')
def admin_logout():
    session.clear()
    flash('You have been successfully logged out.', 'success')
    return redirect(url_for('admin_login'))

@app.route('/api/timetable/generate', methods=['POST'])
@login_required
def api_generate():
    generate_timetable()
    return jsonify({'status': 'success', 'message': 'Timetable generated successfully!'})

@app.route('/api/timetables/<class_name>')
def api_get_timetable(class_name):
    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT class_id FROM classes WHERE name = ?', (class_name,))
    class_id_row = cur.fetchone()
    if class_id_row is None:
        return jsonify({'error': 'Class not found'}), 404
    class_id = class_id_row['class_id']
    
    SLOTS = get_slot_times()
    TEACHABLE_SLOTS = [s for s in SLOTS if s['is_break'] == 0]
    grid = {day: {slot['start_time']: [] for slot in TEACHABLE_SLOTS} for day in DAYS}
    
    slots_query = '''
        SELECT ts.*, t.name as teacher_name, s.name as subject_name, c.name as classroom_name, co.is_lab
        FROM timetable_slots ts
        JOIN courses co ON ts.course_id = co.course_id
        JOIN subjects s ON co.subject_id = s.subject_id
        JOIN teachers t ON ts.teacher_id = t.teacher_id
        JOIN classrooms c ON ts.classroom_id = c.classroom_id
        WHERE ts.class_id = ?
    '''
    cur.execute(slots_query, (class_id,))
    slots = cur.fetchall()
    
    for slot in slots:
        start_time = slot['time_start']
        day = slot['day']
        if day in grid and start_time in grid[day]:
            grid[day][start_time].append(dict(slot))
            
    cur.execute('SELECT teachers.teacher_id, teachers.name, teacher_preferences.preference FROM teachers LEFT JOIN teacher_preferences ON teachers.teacher_id = teacher_preferences.teacher_id')
    teachers = [dict(row) for row in cur.fetchall()]
    cur.execute('SELECT subject_id, name, code FROM subjects')
    subjects = [dict(row) for row in cur.fetchall()]
    cur.execute('SELECT classroom_id, name, is_lab FROM classrooms')
    classrooms = [dict(row) for row in cur.fetchall()]
    cur.execute('SELECT course_id, subject_id, teacher_id, is_lab FROM courses WHERE class_id = ?', (class_id,))
    courses = [dict(row) for row in cur.fetchall()]
    cur.execute('SELECT class_id, name FROM classes')
    classes = [dict(row) for row in cur.fetchall()]

    return jsonify({
        'grid': grid, 
        'days': DAYS, 
        'slots_full': [dict(s) for s in SLOTS],
        'options': {'teachers': teachers, 'subjects': subjects, 'classrooms': classrooms, 'courses': courses, 'classes': classes}
    })

@app.route('/api/timetable/update', methods=['POST'])
@login_required
def api_update():
    # This function remains unchanged
    pass

@app.route('/api/timetable/delete', methods=['POST'])
@login_required
def api_delete():
    # This function remains unchanged
    pass

@app.route('/api/export/pdf/<class_name>')
def export_timetable_pdf(class_name):
    # This function remains unchanged
    pass

@app.route('/api/export/excel/<class_name>')
def export_timetable_excel(class_name):
    # This function remains unchanged
    pass


if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True)