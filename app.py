from flask import Flask, render_template, request, jsonify, g, redirect, url_for
import sqlite3
from datetime import datetime, timedelta
import random
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
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
                name TEXT NOT NULL UNIQUE
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
                FOREIGN KEY (class_id) REFERENCES classes(class_id),
                FOREIGN KEY (course_id) REFERENCES courses(course_id),
                FOREIGN KEY (teacher_id) REFERENCES teachers(teacher_id),
                FOREIGN KEY (classroom_id) REFERENCES classrooms(classroom_id)
            );
            CREATE TABLE IF NOT EXISTS schedule_config (
                config_id INTEGER PRIMARY KEY,
                is_break INTEGER,
                start_time TEXT,
                end_time TEXT,
                break_name TEXT
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
    ''')
    
    cur.execute('SELECT COUNT(*) FROM schedule_config')
    if cur.fetchone()[0] == 0:
        config = [
            (1, 0, '10:30 AM', '11:30 AM', None),
            (2, 0, '11:30 AM', '12:30 PM', None),
            (3, 0, '12:30 PM', '01:30 PM', None),
            (4, 1, '01:30 PM', '02:15 PM', 'Lunch Break'),
            (5, 0, '02:15 PM', '03:15 PM', None),
            (6, 1, '03:15 PM', '03:30 PM', 'Short Break'),
            (7, 0, '03:30 PM', '04:30 PM', None),
            (8, 0, '04:30 PM', '05:30 PM', None)
        ]
        cur.executemany('INSERT INTO schedule_config (config_id, is_break, start_time, end_time, break_name) VALUES (?, ?, ?, ?, ?)', config)
    
    teachers = [('Prof. Ghule',), ('Prof. Bhosle',), ('Prof. Pingle',), ('Dr. Deshmukh',), ('Ms. Shaikh',)]
    cur.executemany('INSERT INTO teachers (name) VALUES (?)', teachers)
    teacher_ids = {row['name']: row['teacher_id'] for row in cur.execute('SELECT teacher_id, name FROM teachers').fetchall()}
    subjects = [('Data Structures', 'CS201'), ('Operating Systems', 'CS202'), ('Database Systems', 'CS301'), ('Programming Lab', 'CSL201'), ('Networks Lab', 'CSL301')]
    cur.executemany('INSERT INTO subjects (name, code) VALUES (?, ?)', subjects)
    subject_ids = {row['code']: row['subject_id'] for row in cur.execute('SELECT subject_id, code FROM subjects').fetchall()}
    classes = [('TE-B1',), ('TE-B2',), ('BE-A',)]
    cur.executemany('INSERT INTO classes (name) VALUES (?)', classes)
    class_ids = {row['name']: row['class_id'] for row in cur.execute('SELECT class_id, name FROM classes').fetchall()}
    classrooms = [('CR-1', 0), ('CR-2', 0), ('LAB-1', 1), ('LAB-2', 1)]
    cur.executemany('INSERT INTO classrooms (name, is_lab) VALUES (?, ?)', classrooms)
    classroom_ids = {row['name']: row['classroom_id'] for row in cur.execute('SELECT classroom_id, name FROM classrooms').fetchall()}
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
    cur.execute('SELECT start_time, end_time, is_break, break_name FROM schedule_config ORDER BY config_id')
    return cur.fetchall()

def generate_timetable():
    db = get_db()
    cur = db.cursor()
    cur.execute('DELETE FROM timetable_slots')
    db.commit()
    cur.execute('''SELECT * FROM courses JOIN subjects ON courses.subject_id = subjects.subject_id''')
    courses = cur.fetchall()
    teacher_prefs = {row['teacher_id']: row['preference'] for row in cur.execute('SELECT * FROM teacher_preferences').fetchall()}
    teacher_lab_times = {}

    SLOTS = get_slot_times()
    TEACHABLE_SLOTS = [(i, s) for i, s in enumerate(SLOTS) if not s['is_break']]
    
    def is_slot_available(day, time_start, time_end, teacher_id, classroom_id, class_id):
        cur.execute('SELECT 1 FROM timetable_slots WHERE teacher_id = ? AND day = ? AND NOT (time_end <= ? OR time_start >= ?)', (teacher_id, day, time_start, time_end))
        if cur.fetchone(): return False
        cur.execute('SELECT 1 FROM timetable_slots WHERE classroom_id = ? AND day = ? AND NOT (time_end <= ? OR time_start >= ?)', (classroom_id, day, time_start, time_end))
        if cur.fetchone(): return False
        cur.execute('SELECT 1 FROM timetable_slots WHERE class_id = ? AND day = ? AND NOT (time_end <= ? OR time_start >= ?)', (class_id, day, time_start, time_end))
        if cur.fetchone(): return False
        return True

    def schedule_session(course, day, start_slot_index, duration, classroom):
        if start_slot_index + duration > len(TEACHABLE_SLOTS): return False
        start_time_idx = TEACHABLE_SLOTS[start_slot_index][0]
        end_time_idx = TEACHABLE_SLOTS[start_slot_index + duration - 1][0]
        start_time = SLOTS[start_time_idx]['start_time']
        end_time = SLOTS[end_time_idx]['end_time']
        
        if is_slot_available(day, start_time, end_time, course['teacher_id'], classroom['classroom_id'], course['class_id']):
            cur.execute('''
                INSERT INTO timetable_slots (class_id, day, time_start, time_end, course_id, teacher_id, classroom_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (course['class_id'], day, start_time, end_time, course['course_id'], course['teacher_id'], classroom['classroom_id']))
            return True
        return False

    lectures_to_schedule = []
    labs_to_schedule = []
    for course in courses:
        if course['is_lab']:
            for _ in range(course['weekly_lectures'] // 2):
                labs_to_schedule.append(course)
        else:
            for _ in range(course['weekly_lectures']):
                lectures_to_schedule.append(course)
    
    cur.execute('SELECT * FROM classrooms WHERE is_lab = 1')
    lab_rooms = cur.fetchall()
    for lab in labs_to_schedule:
        placed = False
        for day in random.sample(DAYS, len(DAYS)):
            for i in range(len(TEACHABLE_SLOTS) - 1):
                room = random.choice(lab_rooms)
                if schedule_session(lab, day, i, 2, room):
                    placed = True
                    start_slot_idx_abs = TEACHABLE_SLOTS[i][0]
                    teacher_lab_times[lab['teacher_id']] = {'day': day, 'end_time': SLOTS[start_slot_idx_abs + 1]['end_time']}
                    break
            if placed: break
    
    theory_lecture_days = {day: set() for day in DAYS}
    teacher_last_slot = {}
    
    for lecture in lectures_to_schedule:
        placed = False
        teacher_id = lecture['teacher_id']
        teacher_pref = teacher_prefs.get(teacher_id)
        class_id = lecture['class_id']
        
        days_to_try = random.sample(DAYS, len(DAYS))
        random.shuffle(days_to_try)
        
        for day in days_to_try:
            if class_id in theory_lecture_days[day]:
                continue
                
            slots_to_try = list(range(len(TEACHABLE_SLOTS)))
            random.shuffle(slots_to_try)
            
            if teacher_pref == 'morning':
                slots_to_try.sort(key=lambda i: i > 2)
            elif teacher_pref == 'afternoon':
                slots_to_try.sort(key=lambda i: i <= 2)
                
            for i in slots_to_try:
                start_slot_idx_abs = TEACHABLE_SLOTS[i][0]
                start_time = SLOTS[start_slot_idx_abs]['start_time']
                end_time = SLOTS[start_slot_idx_abs]['end_time']
                
                lab_info = teacher_lab_times.get(teacher_id)
                if lab_info and lab_info['day'] == day:
                    lab_end_time = datetime.strptime(lab_info['end_time'], '%I:%M %p')
                    current_start_time = datetime.strptime(start_time, '%I:%M %p')
                    if (current_start_time - lab_end_time).total_seconds() < 7200:
                        continue
                
                cur.execute('SELECT * FROM classrooms WHERE is_lab=0')
                theory_rooms = cur.fetchall()
                if not theory_rooms: continue
                
                room = random.choice(theory_rooms)
                if schedule_session(lecture, day, i, 1, room):
                    placed = True
                    theory_lecture_days[day].add(class_id)
                    break
            if placed: break
    db.commit()

def validate_change(slot_id, day, time_start, time_end, teacher_id, classroom_id, class_id):
    db = get_db()
    cur = db.cursor()
    
    cur.execute('SELECT is_lab FROM courses WHERE subject_id IN (SELECT subject_id FROM timetable_slots WHERE slot_id = ?)', (slot_id,))
    is_lab_row = cur.fetchone()
    is_lab = is_lab_row['is_lab'] if is_lab_row else 0
    if not is_lab:
        cur.execute('SELECT 1 FROM timetable_slots ts JOIN courses co ON ts.course_id = co.course_id WHERE ts.day = ? AND ts.class_id = ? AND co.is_lab = 0 AND ts.slot_id != ?', (day, class_id, slot_id))
        if cur.fetchone():
            return False, 'Error: Only one theory lecture per day for this class is allowed.'

    query = 'SELECT teacher_id FROM timetable_slots WHERE day = ? AND NOT (time_end <= ? OR time_start >= ?) AND teacher_id = ?'
    params = (day, time_start, time_end, teacher_id)
    if slot_id:
        query += ' AND slot_id != ?'
        params += (slot_id,)
    cur.execute(query, params)
    if cur.fetchone():
        return False, 'Error: The selected teacher is already assigned to another class at this time.'

    query = 'SELECT classroom_id FROM timetable_slots WHERE day = ? AND NOT (time_end <= ? OR time_start >= ?) AND classroom_id = ?'
    params = (day, time_start, time_end, classroom_id)
    if slot_id:
        query += ' AND slot_id != ?'
        params += (slot_id,)
    cur.execute(query, params)
    if cur.fetchone():
        return False, 'Error: The selected classroom is already occupied at this time.'

    query = 'SELECT class_id FROM timetable_slots WHERE day = ? AND NOT (time_end <= ? OR time_start >= ?) AND class_id = ?'
    params = (day, time_start, time_end, class_id)
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
        # Check which form was submitted using a hidden input field
        form_name = request.form.get('form_name')
        if form_name == 'add_teacher_form':
            name = request.form['teacher_name']
            preference = request.form['teacher_pref']
            try:
                db.execute('INSERT INTO teachers (name) VALUES (?)', (name,))
                if preference:
                    db.execute('INSERT OR IGNORE INTO teacher_preferences (teacher_id, preference) VALUES ((SELECT teacher_id FROM teachers WHERE name = ?), ?)', (name, preference))
                db.commit()
            except sqlite3.IntegrityError:
                pass # Teacher already exists
            return redirect(url_for('manage'))
        
        elif form_name == 'add_subject_form':
            name = request.form['subject_name']
            code = request.form['subject_code']
            try:
                db.execute('INSERT INTO subjects (name, code) VALUES (?, ?)', (name, code))
                db.commit()
            except sqlite3.IntegrityError:
                pass # Subject already exists
            return redirect(url_for('manage'))

        elif form_name == 'add_class_form':
            name = request.form['class_name']
            try:
                db.execute('INSERT INTO classes (name) VALUES (?)', (name,))
                db.commit()
            except sqlite3.IntegrityError:
                pass # Class already exists
            return redirect(url_for('manage'))

        elif form_name == 'add_classroom_form':
            name = request.form['classroom_name']
            is_lab = int(request.form['is_lab'])
            try:
                db.execute('INSERT INTO classrooms (name, is_lab) VALUES (?, ?)', (name, is_lab))
                db.commit()
            except sqlite3.IntegrityError:
                pass # Classroom already exists
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
            except sqlite3.IntegrityError:
                pass
            return redirect(url_for('manage'))

        elif form_name == 'schedule_config_form':
            start_times = request.form.getlist('start_time')
            end_times = request.form.getlist('end_time')
            is_breaks = request.form.getlist('is_break')
            break_names = request.form.getlist('break_name')
            
            slots_data = []
            for i in range(len(start_times)):
                is_break_val = int(is_breaks[i])
                break_name_val = break_names[i] if break_names[i] else None
                slots_data.append((i + 1, is_break_val, start_times[i], end_times[i], break_name_val))
            
            cur.execute('DELETE FROM schedule_config')
            cur.executemany('INSERT INTO schedule_config (config_id, is_break, start_time, end_time, break_name) VALUES (?, ?, ?, ?, ?)', slots_data)
            db.commit()
            
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
                    db.execute(f'DELETE FROM {entity}s WHERE {column_id} = ?', (record_id,)) # Note the 's' in the table name
                    db.commit()
                except (sqlite3.IntegrityError, KeyError):
                    pass
            return redirect(url_for('manage'))


    teachers = cur.execute('SELECT * FROM teachers').fetchall()
    subjects = cur.execute('SELECT * FROM subjects').fetchall()
    classes = cur.execute('SELECT * FROM classes').fetchall()
    classrooms = cur.execute('SELECT * FROM classrooms').fetchall()
    courses = cur.execute('''
        SELECT c.*, t.name as teacher_name, sub.name as subject_name, cl.name as class_name 
        FROM courses c 
        JOIN teachers t ON c.teacher_id = t.teacher_id 
        JOIN subjects sub ON c.subject_id = sub.subject_id
        JOIN classes cl ON c.class_id = cl.class_id
    ''').fetchall()
    schedule_config = get_slot_times()
    
    return render_template('manage.html', teachers=teachers, subjects=subjects, classes=classes, classrooms=classrooms, courses=courses, schedule_config=schedule_config)

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
    grid = {day: {slot['start_time']: None for slot in TEACHABLE_SLOTS} for day in DAYS}
    
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
        start_time_obj = datetime.strptime(slot['time_start'], '%I:%M %p')
        end_time_obj = datetime.strptime(slot['time_end'], '%I:%M %p')
        duration_minutes = (end_time_obj - start_time_obj).total_seconds() / 60
        
        try:
            start_index = next(i for i, time in enumerate(SLOTS) if time['start_time'] == slot['time_start'])
        except StopIteration:
            continue
            
        duration_slots = int(duration_minutes / 60)
        
        for i in range(start_index, start_index + duration_slots):
            if i < len(SLOTS) and not SLOTS[i]['is_break']:
                grid[slot['day']][SLOTS[i]['start_time']] = dict(slot)
            
    cur.execute('SELECT teacher_id, name FROM teachers')
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
        'slots': [s['start_time'] for s in SLOTS if not s['is_break']],
        'slots_full': [dict(s) for s in SLOTS],
        'options': {'teachers': teachers, 'subjects': subjects, 'classrooms': classrooms, 'courses': courses, 'classes': classes}
    })

if __name__ == '__main__':
    with app.app_context():
        init_db()
        seed_sample_data()
    app.run(debug=True)