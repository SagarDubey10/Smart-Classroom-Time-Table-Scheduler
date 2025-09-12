from flask import Flask, render_template, request, jsonify, g, redirect, url_for, send_file
import sqlite3
from datetime import datetime, timedelta
import random
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
import io

app = Flask(__name__)
DB_PATH = 'timetable.db'
DAYS = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT']
SLOT_TIMES = [
    ('09:00', '10:00'), ('10:00', '11:00'), ('11:00', '12:00'),
    ('12:30', '13:30'), ('13:30', '14:30'), ('14:30', '15:30'), ('15:30', '16:30')
]

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
        (class_ids['TE-B1'], subject_ids['CSL201'], teacher_ids['Prof. Pingle'], 2, 1), # Lab
        (class_ids['TE-B2'], subject_ids['CS301'], teacher_ids['Dr. Deshmukh'], 3, 0),
        (class_ids['TE-B2'], subject_ids['CSL301'], teacher_ids['Ms. Shaikh'], 2, 1),  # Lab
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

def generate_timetable():
    db = get_db()
    cur = db.cursor()
    cur.execute('DELETE FROM timetable_slots')
    db.commit()

    cur.execute('''SELECT * FROM courses JOIN subjects ON courses.subject_id = subjects.subject_id''')
    courses = cur.fetchall()

    teacher_prefs = {row['teacher_id']: row['preference'] for row in cur.execute('SELECT * FROM teacher_preferences').fetchall()}
    teacher_lab_times = {}

    def is_slot_available(day, time_start, time_end, teacher_id, classroom_id, class_id):
        # Teacher collision check
        cur.execute('SELECT 1 FROM timetable_slots WHERE teacher_id = ? AND day = ? AND NOT (time_end <= ? OR time_start >= ?)', (teacher_id, day, time_start, time_end))
        if cur.fetchone(): return False

        # Classroom collision check
        cur.execute('SELECT 1 FROM timetable_slots WHERE classroom_id = ? AND day = ? AND NOT (time_end <= ? OR time_start >= ?)', (classroom_id, day, time_start, time_end))
        if cur.fetchone(): return False

        # Class collision check
        cur.execute('SELECT 1 FROM timetable_slots WHERE class_id = ? AND day = ? AND NOT (time_end <= ? OR time_start >= ?)', (class_id, day, time_start, time_end))
        if cur.fetchone(): return False

        return True

    def schedule_session(course, day, start_slot_index, duration, classroom):
        if start_slot_index + duration > len(SLOT_TIMES):
            return False
        
        start_time = SLOT_TIMES[start_slot_index][0]
        end_time = SLOT_TIMES[start_slot_index + duration - 1][1]

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
        for _ in range(course['weekly_lectures']):
            if course['is_lab']:
                labs_to_schedule.append(course)
            else:
                lectures_to_schedule.append(course)
    
    # 1. Schedule Labs First (2-hour blocks)
    cur.execute('SELECT * FROM classrooms WHERE is_lab = 1')
    lab_rooms = cur.fetchall()
    
    for lab in labs_to_schedule:
        placed = False
        for day in random.sample(DAYS, len(DAYS)):
            for i in range(len(SLOT_TIMES) - 1):
                room = random.choice(lab_rooms)
                if schedule_session(lab, day, i, 2, room):
                    placed = True
                    teacher_lab_times[lab['teacher_id']] = {'day': day, 'end_time': SLOT_TIMES[i + 1][1]}
                    break
            if placed: break

    # 2. Schedule Lectures with constraints
    for lecture in lectures_to_schedule:
        placed = False
        teacher_id = lecture['teacher_id']
        teacher_pref = teacher_prefs.get(teacher_id)
        
        days_to_try = random.sample(DAYS, len(DAYS))
        random.shuffle(days_to_try)

        for day in days_to_try:
            slots_to_try = list(range(len(SLOT_TIMES)))
            random.shuffle(slots_to_try)

            # Prioritize based on preference
            if teacher_pref == 'morning':
                slots_to_try.sort(key=lambda i: i > 2) # morning slots (0-2) first
            elif teacher_pref == 'afternoon':
                slots_to_try.sort(key=lambda i: i <= 2) # afternoon slots (3+) first

            for i in slots_to_try:
                start_time = SLOT_TIMES[i][0]
                end_time = SLOT_TIMES[i][1]
                
                # Check for 2-hour gap after lab
                lab_info = teacher_lab_times.get(teacher_id)
                if lab_info and lab_info['day'] == day:
                    lab_end_time = datetime.strptime(lab_info['end_time'], '%H:%M')
                    current_start_time = datetime.strptime(start_time, '%H:%M')
                    if (current_start_time - lab_end_time).total_seconds() < 7200: # 2 hours
                        continue
                
                cur.execute('SELECT * FROM classrooms WHERE is_lab=0')
                theory_rooms = cur.fetchall()
                if not theory_rooms: continue

                room = random.choice(theory_rooms)
                if schedule_session(lecture, day, i, 1, room):
                    placed = True
                    break
            if placed: break
    
    db.commit()

# --- ROUTES ---
@app.route('/')
def index():
    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT name FROM classes')
    classes = [row['name'] for row in cur.fetchall()]
    return render_template('index.html', classes=classes)

@app.route('/manage')
def manage():
    db = get_db()
    cur = db.cursor()
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
    return render_template('manage.html', teachers=teachers, subjects=subjects, classes=classes, classrooms=classrooms, courses=courses)

@app.route('/api/timetable/generate', methods=['POST'])
def api_generate():
    generate_timetable()
    return jsonify({'status': 'success', 'message': 'Timetable generated successfully!'})

@app.route('/api/timetables/<class_name>')
def api_get_timetable(class_name):
    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT class_id FROM classes WHERE name = ?', (class_name,))
    class_id = cur.fetchone()['class_id']
    
    grid = {day: {slot[0]: None for slot in SLOT_TIMES} for day in DAYS}
    
    slots_query = '''
        SELECT ts.*, t.name as teacher_name, s.name as subject_name, c.name as classroom_name
        FROM timetable_slots ts
        JOIN courses co ON ts.course_id = co.course_id
        JOIN teachers t ON ts.teacher_id = t.teacher_id
        JOIN subjects s ON co.subject_id = s.subject_id
        JOIN classrooms c ON ts.classroom_id = c.classroom_id
        WHERE ts.class_id = ?
    '''
    cur.execute(slots_query, (class_id,))
    slots = cur.fetchall()

    for slot in slots:
        start_time = slot['time_start']
        end_time = slot['time_end']
        
        # Handle multi-slot sessions
        start_index = next(i for i, time in enumerate(SLOT_TIMES) if time[0] == start_time)
        end_index = next(i for i, time in enumerate(SLOT_TIMES) if time[1] == end_time)
        
        for i in range(start_index, end_index + 1):
            grid[slot['day']][SLOT_TIMES[i][0]] = slot

    return jsonify({'grid': grid, 'days': DAYS, 'slots': [s[0] for s in SLOT_TIMES]})

@app.route('/api/admin/add_teacher', methods=['POST'])
def add_teacher():
    data = request.json
    db = get_db()
    db.execute('INSERT INTO teachers (name) VALUES (?)', (data['name'],))
    if 'preference' in data and data['preference']:
        db.execute('INSERT INTO teacher_preferences (teacher_id, preference) VALUES ((SELECT teacher_id FROM teachers WHERE name = ?), ?)', (data['name'], data['preference']))
    db.commit()
    return jsonify({'status': 'success'})

@app.route('/api/admin/add_subject', methods=['POST'])
def add_subject():
    data = request.json
    db = get_db()
    db.execute('INSERT INTO subjects (name, code) VALUES (?, ?)', (data['name'], data['code']))
    db.commit()
    return jsonify({'status': 'success'})

@app.route('/api/admin/add_class', methods=['POST'])
def add_class():
    data = request.json
    db = get_db()
    db.execute('INSERT INTO classes (name) VALUES (?)', (data['name'],))
    db.commit()
    return jsonify({'status': 'success'})

@app.route('/api/admin/add_classroom', methods=['POST'])
def add_classroom():
    data = request.json
    db = get_db()
    db.execute('INSERT INTO classrooms (name, is_lab) VALUES (?, ?)', (data['name'], data['is_lab']))
    db.commit()
    return jsonify({'status': 'success'})

@app.route('/api/admin/add_course', methods=['POST'])
def add_course():
    data = request.json
    db = get_db()
    try:
        db.execute('INSERT INTO courses (class_id, subject_id, teacher_id, weekly_lectures, is_lab) VALUES (?, ?, ?, ?, ?)',
                   (data['class_id'], data['subject_id'], data['teacher_id'], data['weekly_lectures'], data['is_lab']))
        db.commit()
        return jsonify({'status': 'success'})
    except sqlite3.IntegrityError:
        return jsonify({'status': 'error', 'message': 'Assignment already exists or invalid data.'}), 400

@app.route('/api/admin/delete/<entity>/<id>', methods=['DELETE'])
def delete_entity(entity, id):
    db = get_db()
    try:
        if entity in ['teachers', 'subjects', 'classes', 'classrooms', 'courses']:
            db.execute(f'DELETE FROM {entity} WHERE {entity}_id = ?', (id,))
            db.commit()
            return jsonify({'status': 'success'})
        return jsonify({'status': 'error', 'message': 'Invalid entity'}), 400
    except sqlite3.IntegrityError:
        return jsonify({'status': 'error', 'message': 'Cannot delete, it is in use.'}), 400

@app.route('/download/pdf/<class_name>')
def download_pdf(class_name):
    db = get_db()
    cur = db.cursor()

    cur.execute('SELECT class_id FROM classes WHERE name = ?', (class_name,))
    class_id = cur.fetchone()['class_id']
    
    timetable_data = [
        ['Time'] + DAYS
    ]
    
    for slot_time in SLOT_TIMES:
        row = [f"{slot_time[0]} - {slot_time[1]}"]
        for day in DAYS:
            cur.execute('''
                SELECT s.name as subject_name, t.name as teacher_name, c.name as classroom_name
                FROM timetable_slots ts
                JOIN courses co ON ts.course_id = co.course_id
                JOIN subjects s ON co.subject_id = s.subject_id
                JOIN teachers t ON ts.teacher_id = t.teacher_id
                JOIN classrooms c ON ts.classroom_id = c.classroom_id
                WHERE ts.class_id = ? AND ts.day = ? AND ts.time_start = ?
            ''', (class_id, day, slot_time[0]))
            result = cur.fetchone()
            if result:
                row.append(f"{result['subject_name']}\n({result['teacher_name']})\n@{result['classroom_name']}")
            else:
                row.append('')
        timetable_data.append(row)
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    
    story = []
    
    title_style = styles['Title']
    story.append(Paragraph(f"Timetable for {class_name}", title_style))
    story.append(Spacer(1, 0.2 * 10))
    
    table_style = TableStyle([
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2a2a3d')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
    ])

    timetable_table = Table(timetable_data, colWidths=[1.5*72, 1.5*72, 1.5*72, 1.5*72, 1.5*72, 1.5*72, 1.5*72])
    timetable_table.setStyle(table_style)
    
    story.append(timetable_table)
    doc.build(story)
    
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f'timetable_{class_name}.pdf', mimetype='application/pdf')

if __name__ == '__main__':
    with app.app_context():
        init_db()
        seed_sample_data()
    app.run(debug=True)