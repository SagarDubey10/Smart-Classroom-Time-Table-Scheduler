from flask import Flask, render_template, request, jsonify, g, redirect, url_for, flash, send_file
import sqlite3
from datetime import datetime
import random
from collections import defaultdict
import pandas as pd
from fpdf import FPDF
import io

app = Flask(__name__)
DB_PATH = 'timetable.db'
DAYS = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT']
app.secret_key = 'your_secret_key_here'

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
                FOREIGN KEY (class_id) REFERENCES classes(class_id),
                FOREIGN KEY (subject_id) REFERENCES subjects(subject_id),
                FOREIGN KEY (teacher_id) REFERENCES teachers(teacher_id)
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
        ''')
        db.commit()

def seed_sample_data():
    db = get_db()
    cur = db.cursor()
    cur.executescript('''
        DELETE FROM timetable_slots;
        DELETE FROM courses;
        DELETE FROM classrooms;
        DELETE FROM subjects;
        DELETE FROM classes;
        DELETE FROM teacher_preferences;
        DELETE FROM teachers;
        DELETE FROM schedule_config;
        DELETE FROM batch_teacher_assignments;
    ''')
    
    config = [
        (0, '10:30 AM', '11:30 AM', None),
        (0, '11:30 AM', '12:30 PM', None),
        (0, '12:30 PM', '01:30 PM', None),
        (1, '01:30 PM', '02:15 PM', 'Lunch Break'),
        (0, '02:15 PM', '03:15 PM', None),
        (1, '03:15 PM', '03:30 PM', 'Short Break'),
        (0, '03:30 PM', '04:30 PM', None),
        (0, '04:30 PM', '05:30 PM', None)
    ]
    cur.executemany('INSERT INTO schedule_config (is_break, start_time, end_time, break_name) VALUES (?, ?, ?, ?)', config)
    
    teachers = [('Prof. Ghule',), ('Prof. Bhosle',), ('Prof. Pingle',), ('Dr. Deshmukh',), ('Ms. Shaikh',)]
    cur.executemany('INSERT INTO teachers (name) VALUES (?)', teachers)
    teacher_ids = {row['name']: row['teacher_id'] for row in cur.execute('SELECT teacher_id, name FROM teachers').fetchall()}
    subjects = [('Data Structures', 'CS201'), ('Operating Systems', 'CS202'), ('Database Systems', 'CS301'), ('Programming Lab', 'CSL201'), ('Networks Lab', 'CSL301')]
    cur.executemany('INSERT INTO subjects (name, code) VALUES (?, ?)', subjects)
    subject_ids = {row['code']: row['subject_id'] for row in cur.execute('SELECT subject_id, code FROM subjects').fetchall()}
    classes = [('TE-B1', 2), ('TE-B2', 2), ('BE-A', 1)]
    cur.executemany('INSERT INTO classes (name, num_batches) VALUES (?, ?)', classes)
    class_ids = {row['name']: row['class_id'] for row in cur.execute('SELECT class_id, name FROM classes').fetchall()}
    classrooms = [('CR-1', 0), ('CR-2', 0), ('LAB-1', 1), ('LAB-2', 1)]
    cur.executemany('INSERT INTO classrooms (name, is_lab) VALUES (?, ?)', classrooms)
    courses = [
        (class_ids['TE-B1'], subject_ids['CS201'], teacher_ids['Prof. Ghule'], 3, 0),
        (class_ids['TE-B1'], subject_ids['CS202'], teacher_ids['Prof. Bhosle'], 3, 0),
        (class_ids['TE-B1'], subject_ids['CSL201'], teacher_ids['Prof. Pingle'], 2, 1), 
        (class_ids['TE-B2'], subject_ids['CS301'], teacher_ids['Dr. Deshmukh'], 3, 0),
        (class_ids['TE-B2'], subject_ids['CSL301'], teacher_ids['Ms. Shaikh'], 2, 1),
        (class_ids['BE-A'], subject_ids['CS301'], teacher_ids['Prof. Ghule'], 4, 0)
    ]
    cur.executemany('INSERT INTO courses (class_id, subject_id, teacher_id, weekly_lectures, is_lab) VALUES (?, ?, ?, ?, ?)', courses)
    teacher_prefs = [
        (teacher_ids['Prof. Pingle'], 'morning'),
        (teacher_ids['Ms. Shaikh'], 'morning'),
        (teacher_ids['Prof. Bhosle'], 'afternoon')
    ]
    cur.executemany('INSERT OR REPLACE INTO teacher_preferences (teacher_id, preference) VALUES (?, ?)', teacher_prefs)

    db.commit()

# --- TIMETABLE GENERATION & VALIDATION ---
def get_slot_times():
    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT * FROM schedule_config ORDER BY config_id')
    return cur.fetchall()

def is_slot_available(day, time_start, time_end, teacher_id, classroom_id, class_id, batch_number=None):
    db = get_db()
    cur = db.cursor()
    # Teacher availability
    cur.execute('SELECT 1 FROM timetable_slots WHERE teacher_id = ? AND day = ? AND NOT (time_end <= ? OR time_start >= ?)', (teacher_id, day, time_start, time_end))
    if cur.fetchone(): return False
    # Classroom availability
    cur.execute('SELECT 1 FROM timetable_slots WHERE classroom_id = ? AND day = ? AND NOT (time_end <= ? OR time_start >= ?)', (classroom_id, day, time_start, time_end))
    if cur.fetchone(): return False
    # Class/Batch availability
    if batch_number:
        # Check for this specific batch
        cur.execute('SELECT 1 FROM timetable_slots WHERE class_id = ? AND batch_number = ? AND day = ? AND NOT (time_end <= ? OR time_start >= ?)', (class_id, batch_number, day, time_start, time_end))
        if cur.fetchone(): return False
        
        # Also check if there's a theory lecture for the whole class at the same time
        cur.execute('SELECT 1 FROM timetable_slots WHERE class_id = ? AND batch_number IS NULL AND day = ? AND NOT (time_end <= ? OR time_start >= ?)', (class_id, day, time_start, time_end))
        if cur.fetchone(): return False
    else: # This is a theory lecture
        # Check if the whole class has a theory lecture
        cur.execute('SELECT 1 FROM timetable_slots WHERE class_id = ? AND batch_number IS NULL AND day = ? AND NOT (time_end <= ? OR time_start >= ?)', (class_id, day, time_start, time_end))
        if cur.fetchone(): return False
        # Check if ANY batch of the class has a lab
        cur.execute('SELECT 1 FROM timetable_slots WHERE class_id = ? AND batch_number IS NOT NULL AND day = ? AND NOT (time_end <= ? OR time_start >= ?)', (class_id, day, time_start, time_end))
        if cur.fetchone(): return False
    return True

def schedule_session(course, day, start_slot_index, duration, classroom, batch_number=None, teacher_id=None):
    SLOTS = get_slot_times()
    TEACHABLE_SLOTS = [(i, s) for i, s in enumerate(SLOTS) if not s['is_break']]
    db = get_db()
    cur = db.cursor()

    if start_slot_index + duration > len(TEACHABLE_SLOTS): return False
    
    start_time_idx = TEACHABLE_SLOTS[start_slot_index][0]
    end_time_idx = TEACHABLE_SLOTS[start_slot_index + duration - 1][0]
    start_time = SLOTS[start_time_idx]['start_time']
    end_time = SLOTS[end_time_idx]['end_time']
    
    # Use provided teacher_id if available (for batch labs), otherwise use course default
    final_teacher_id = teacher_id if teacher_id is not None else course['teacher_id']

    if is_slot_available(day, start_time, end_time, final_teacher_id, classroom['classroom_id'], course['class_id'], batch_number):
        cur.execute('''
            INSERT INTO timetable_slots (class_id, day, time_start, time_end, course_id, teacher_id, classroom_id, batch_number)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (course['class_id'], day, start_time, end_time, course['course_id'], final_teacher_id, classroom['classroom_id'], batch_number))
        return True
    return False

def generate_timetable():
    db = get_db()
    cur = db.cursor()
    cur.execute('DELETE FROM timetable_slots')
    db.commit()

    courses = cur.execute('''
        SELECT c.*, s.name as subject_name, cl.num_batches 
        FROM courses c 
        JOIN subjects s ON c.subject_id = s.subject_id
        JOIN classes cl ON c.class_id = cl.class_id
    ''').fetchall()
    
    classrooms = cur.execute('SELECT * FROM classrooms').fetchall()
    lab_rooms = [r for r in classrooms if r['is_lab']]
    theory_rooms = [r for r in classrooms if not r['is_lab']]
    
    teacher_prefs = {row['teacher_id']: row['preference'] for row in cur.execute('SELECT * FROM teacher_preferences').fetchall()}
    
    # Fetch batch-teacher assignments
    batch_assignments = defaultdict(dict)
    assignments = cur.execute('SELECT * FROM batch_teacher_assignments').fetchall()
    for a in assignments:
        batch_assignments[(a['class_id'], a['subject_id'])][a['batch_number']] = a['teacher_id']

    SLOTS = get_slot_times()
    TEACHABLE_SLOTS = [(i, s) for i, s in enumerate(SLOTS) if not s['is_break']]
    
    # --- New Batch Scheduling Logic for Labs ---
    labs_to_schedule = []
    for course in courses:
        if course['is_lab']:
            for _ in range(course['weekly_lectures'] // 2): # Each lab is 2 hours
                for batch in range(1, course['num_batches'] + 1):
                    teacher_id = batch_assignments.get((course['class_id'], course['subject_id']), {}).get(batch, course['teacher_id'])
                    labs_to_schedule.append({'course': course, 'batch': batch, 'teacher_id': teacher_id})
    
    random.shuffle(labs_to_schedule)

    for lab_session in labs_to_schedule:
        course = lab_session['course']
        batch = lab_session['batch']
        teacher_id = lab_session['teacher_id']
        
        placed = False
        for _ in range(200): # More attempts to find a slot
            day = random.choice(DAYS)
            i = random.randrange(len(TEACHABLE_SLOTS) - 1)
            room = random.choice(lab_rooms)
            if schedule_session(course, day, i, 2, room, batch, teacher_id):
                placed = True
                break
        if not placed:
            print(f"Warning: Could not schedule lab for {course['subject_name']} Batch {batch}")


    # --- Scheduling Theory Lectures ---
    lectures_to_schedule = []
    for course in courses:
        if not course['is_lab']:
            for _ in range(course['weekly_lectures']):
                lectures_to_schedule.append(course)
    
    random.shuffle(lectures_to_schedule)
    
    for lecture in lectures_to_schedule:
        placed = False
        teacher_id = lecture['teacher_id']
        teacher_pref = teacher_prefs.get(teacher_id)
        
        for _ in range(100): # Attempt to place each lecture
            day = random.choice(DAYS)
            
            slots_to_try = list(range(len(TEACHABLE_SLOTS)))
            random.shuffle(slots_to_try)
            
            if teacher_pref == 'morning':
                slots_to_try.sort(key=lambda i: i > 2)
            elif teacher_pref == 'afternoon':
                slots_to_try.sort(key=lambda i: i <= 2)
            
            i = random.choice(slots_to_try)

            if not theory_rooms: continue
            room = random.choice(theory_rooms)
            if schedule_session(lecture, day, i, 1, room):
                placed = True
                break
        if not placed:
            print(f"Warning: Could not schedule lecture for {lecture['subject_name']}")

            
    db.commit()

def validate_change(slot_id, day, time_start, time_end, teacher_id, classroom_id, class_id):
    db = get_db()
    cur = db.cursor()
    
    query = 'SELECT 1 FROM timetable_slots WHERE teacher_id = ? AND day = ? AND NOT (? >= time_end OR ? <= time_start)'
    params = (teacher_id, day, time_start, time_end)
    if slot_id:
        query += ' AND slot_id != ?'
        params += (slot_id,)
    cur.execute(query, params)
    if cur.fetchone():
        return False, 'Error: The selected teacher is already assigned to another class at this time.'

    query = 'SELECT 1 FROM timetable_slots WHERE classroom_id = ? AND day = ? AND NOT (? >= time_end OR ? <= time_start)'
    params = (classroom_id, day, time_start, time_end)
    if slot_id:
        query += ' AND slot_id != ?'
        params += (slot_id,)
    cur.execute(query, params)
    if cur.fetchone():
        return False, 'Error: The selected classroom is already occupied at this time.'

    query = 'SELECT 1 FROM timetable_slots WHERE class_id = ? AND day = ? AND NOT (? >= time_end OR ? <= time_start)'
    params = (class_id, day, time_start, time_end)
    if slot_id:
        query += ' AND slot_id != ?'
        params += (slot_id,)
    cur.execute(query, params)
    if cur.fetchone():
        return False, 'Error: The class already has a lecture at this time.'

    return True, 'OK'

# --- ROUTES ---
@app.route('/')
def index():
    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT name, class_id FROM classes')
    classes = [dict(row) for row in cur.fetchall()]
    return render_template('index.html', classes=classes)

@app.route('/manage', methods=['GET', 'POST'])
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
            is_lab = int(request.form.get('is_lab_checkbox') == 'on')
            try:
                db.execute('INSERT INTO courses (class_id, subject_id, teacher_id, weekly_lectures, is_lab) VALUES (?, ?, ?, ?, ?)',
                           (class_id, subject_id, teacher_id, weekly_lectures, is_lab))
                db.commit()
                flash('Course assignment added successfully!', 'success')
            except sqlite3.IntegrityError:
                flash('Error: Course assignment already exists.', 'error')
            return redirect(url_for('manage'))
        
        elif form_name == 'batch_teacher_form':
            class_id = request.form.get('class_id')
            subject_id = request.form.get('subject_id')
            
            # Delete existing assignments for this class/subject
            db.execute('DELETE FROM batch_teacher_assignments WHERE class_id = ? AND subject_id = ?', (class_id, subject_id))
            
            # Add new assignments
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
                # Delete removed slots
                current_ids_rows = db.execute('SELECT config_id FROM schedule_config').fetchall()
                current_ids = {row[0] for row in current_ids_rows}
                submitted_ids = {int(i) for i in config_ids if i}
                ids_to_delete = current_ids - submitted_ids
                
                if ids_to_delete:
                    db.execute(f'DELETE FROM schedule_config WHERE config_id IN ({",".join("?"*len(ids_to_delete))})', list(ids_to_delete))
                
                # Update existing and insert new slots
                break_name_counter = 0
                for i in range(len(start_times)):
                    config_id = config_ids[i]
                    is_break = int(is_breaks[i])
                    start_time = start_times[i]
                    end_time = end_times[i]
                    
                    break_name = None
                    if is_break:
                        break_name = break_names[break_name_counter] if break_names[break_name_counter] else None
                        break_name_counter += 1

                    if config_id: # Update existing
                        db.execute('UPDATE schedule_config SET is_break=?, start_time=?, end_time=?, break_name=? WHERE config_id=?',
                                   (is_break, start_time, end_time, break_name, config_id))
                    else: # Insert new
                        db.execute('INSERT INTO schedule_config (is_break, start_time, end_time, break_name) VALUES (?, ?, ?, ?)',
                                   (is_break, start_time, end_time, break_name))
                
                db.commit()
                flash('Schedule configuration saved successfully!', 'success')
            except Exception as e:
                db.rollback()
                flash(f'Error saving schedule: {e}', 'error')
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
                    
                    if entity == 'class':
                        table_name = 'classes'
                    else:
                        table_name = f'{entity}s'

                    db.execute(f'DELETE FROM {table_name} WHERE {column_id} = ?', (record_id,))
                    db.commit()
                    flash(f'{entity.capitalize()} deleted successfully!', 'success')
                except (sqlite3.IntegrityError, KeyError):
                    flash(f'Error: Cannot delete {entity} because it is in use by another record.', 'error')
            return redirect(url_for('manage'))

    # Validation for batches vs practicals
    warnings = []
    classes_list = cur.execute('SELECT * FROM classes').fetchall()
    for class_obj in classes_list:
        num_batches = class_obj['num_batches']
        if num_batches > 1:
            practicals_count = cur.execute('SELECT COUNT(*) FROM courses WHERE class_id = ? AND is_lab = 1', (class_obj['class_id'],)).fetchone()[0]
            if practicals_count > 0 and num_batches > practicals_count:
                 warnings.append(f"For class '{class_obj['name']}', the number of batches ({num_batches}) is greater than the number of assigned practicals ({practicals_count}). Some batches may miss practicals.")

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
    
    # Fetch existing batch-teacher assignments
    batch_assignments = defaultdict(lambda: defaultdict(dict))
    assignments = cur.execute('''
        SELECT b.*, t.name as teacher_name 
        FROM batch_teacher_assignments b 
        JOIN teachers t ON b.teacher_id = t.teacher_id
    ''').fetchall()
    for a in assignments:
        batch_assignments[a['class_id']][a['subject_id']][a['batch_number']] = a['teacher_id']

    schedule_config = get_slot_times()
    
    return render_template('manage.html', 
                           teachers=teachers, 
                           subjects=subjects, 
                           classes=classes_list, 
                           classrooms=classrooms, 
                           courses=courses, 
                           schedule_config=schedule_config,
                           warnings=warnings,
                           batch_assignments=batch_assignments)

@app.route('/api/timetable/generate', methods=['POST'])
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
    TEACHABLE_SLOTS = [s for s in SLOTS if not s['is_break']]
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
        grid[slot['day']][slot['time_start']].append(dict(slot))
            
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
def api_update():
    data = request.json
    slot_id = data.get('slot_id')
    
    db = get_db()
    cur = db.cursor()
    
    cur.execute('SELECT course_id, is_lab FROM courses WHERE subject_id = ? AND teacher_id = ? AND class_id = ?', 
                (data['subject_id'], data['teacher_id'], data['class_id']))
    course = cur.fetchone()

    if not course:
        return jsonify({'status': 'error', 'message': 'This teacher is not assigned to teach this subject for this class.'}), 400

    course_id = course['course_id']
    
    valid, message = validate_change(
        slot_id, 
        data['day'], 
        data['time_start'], 
        data['time_end'], 
        data['teacher_id'], 
        data['classroom_id'],
        data['class_id']
    )

    if not valid:
        return jsonify({'status': 'error', 'message': message}), 400

    try:
        if slot_id:
            cur.execute('''
                UPDATE timetable_slots 
                SET day = ?, time_start = ?, time_end = ?, teacher_id = ?, classroom_id = ?, course_id = ?
                WHERE slot_id = ?
            ''', (data['day'], data['time_start'], data['time_end'], data['teacher_id'], data['classroom_id'], course_id, slot_id))
        else:
            cur.execute('''
                INSERT INTO timetable_slots (class_id, day, time_start, time_end, teacher_id, classroom_id, course_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (data['class_id'], data['day'], data['time_start'], data['time_end'], data['teacher_id'], data['classroom_id'], course_id))
        db.commit()
        return jsonify({'status': 'success', 'message': 'Timetable updated successfully.'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/timetable/delete', methods=['POST'])
def api_delete():
    data = request.json
    slot_id = data.get('slot_id')

    if not slot_id:
        return jsonify({'status': 'error', 'message': 'Invalid slot ID provided.'}), 400

    db = get_db()
    cur = db.cursor()

    try:
        cur.execute('DELETE FROM timetable_slots WHERE slot_id = ?', (slot_id,))
        db.commit()
        if cur.rowcount == 0:
            return jsonify({'status': 'error', 'message': 'Slot not found.'}), 404
        return jsonify({'status': 'success', 'message': 'Slot deleted successfully.'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

def get_timetable_data_for_export(class_name):
    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT class_id FROM classes WHERE name = ?', (class_name,))
    class_id_row = cur.fetchone()
    if not class_id_row:
        return None, None
    class_id = class_id_row['class_id']

    slots_full = get_slot_times()
    teachable_slots = [s for s in slots_full if not s['is_break']]
    grid = {day: {slot['start_time']: [] for slot in teachable_slots} for day in DAYS}

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
        grid[slot['day']][slot['time_start']].append(dict(slot))
    
    return grid, slots_full

@app.route('/api/export/pdf/<class_name>')
def export_timetable_pdf(class_name):
    grid, slots_full = get_timetable_data_for_export(class_name)
    if grid is None:
        return "Class not found", 404
    
    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_font('Arial', 'B', 16)
    pdf.cell(0, 10, f'Timetable for {class_name}', 0, 1, 'C')
    pdf.ln(5)

    pdf.set_font('Arial', 'B', 10)
    col_width = (pdf.w - 20) / (len(DAYS) + 1)
    
    pdf.cell(col_width, 10, 'Time', 1, 0, 'C')
    for day in DAYS:
        pdf.cell(col_width, 10, day, 1, 0, 'C')
    pdf.ln()

    pdf.set_font('Arial', '', 8)
    for slot in slots_full:
        time_formatted = f"{slot['start_time']} - {slot['end_time']}"
        if slot['is_break']:
            row_height = 10
            pdf.cell(col_width, row_height, time_formatted, 1, 0, 'C')
            pdf.cell(col_width * len(DAYS), row_height, slot['break_name'], 1, 1, 'C')
        else:
            max_lines = 1
            for day in DAYS:
                cell_data_array = grid[day][slot['start_time']]
                if cell_data_array:
                    max_lines = max(max_lines, sum([len(d['subject_name'].split('\n')) + 2 for d in cell_data_array]))
            
            row_height = max_lines * 4
            if max_lines == 1 : row_height = 10
            
            y_before = pdf.get_y()
            x_before = pdf.get_x()

            pdf.multi_cell(col_width, row_height, time_formatted, 1, 'C')
            
            x_after_time = x_before + col_width
            pdf.set_y(y_before)

            for day in DAYS:
                pdf.set_x(x_after_time)
                cell_data_array = grid[day][slot['start_time']]
                text = ""
                if cell_data_array:
                    text = "\n\n".join([f"{d['subject_name']}\n({d['teacher_name']})\n@{d['classroom_name']}" for d in cell_data_array])
                
                pdf.multi_cell(col_width, row_height, text, 1, 'C')
                x_after_time += col_width
                pdf.set_y(y_before)

            pdf.set_y(y_before + row_height)
    
    pdf_bytes = pdf.output(dest='S').encode('latin-1')
    buffer = io.BytesIO(pdf_bytes)
    buffer.seek(0)

    return send_file(buffer, as_attachment=True, download_name=f'{class_name}_timetable.pdf', mimetype='application/pdf')

@app.route('/api/export/excel/<class_name>')
def export_timetable_excel(class_name):
    grid, slots_full = get_timetable_data_for_export(class_name)
    if grid is None:
        return "Class not found", 404

    df_data = {'Time': [f"{s['start_time']} - {s['end_time']}" for s in slots_full]}
    for day in DAYS:
        day_column = []
        for slot in slots_full:
            if slot['is_break']:
                day_column.append(slot['break_name'])
            else:
                cell_data_array = grid[day][slot['start_time']]
                if cell_data_array:
                    day_column.append("\n".join([f"{d['subject_name']} ({d['teacher_name']}) @{d['classroom_name']}" for d in cell_data_array]))
                else:
                    day_column.append("")
        df_data[day] = day_column
    
    df = pd.DataFrame(df_data)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Timetable')
        worksheet = writer.sheets['Timetable']
        for idx, col in enumerate(df):
            series = df[col]
            max_len = max((series.astype(str).map(len).max(), len(str(series.name)))) + 2
            worksheet.set_column(idx, idx, max_len)

    output.seek(0)
    
    return send_file(output, as_attachment=True, download_name=f'{class_name}_timetable.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

if __name__ == '__main__':
    with app.app_context():
        init_db()
        seed_sample_data()
    app.run(debug=True)