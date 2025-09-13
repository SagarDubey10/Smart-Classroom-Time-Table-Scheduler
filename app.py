# app.py
from flask import Flask, render_template, request, jsonify, g, redirect, url_for, send_file
import sqlite3
from datetime import datetime, timedelta
import random
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
import io

# Import the blueprint from the new file
from admin_routes import admin_bp

app = Flask(__name__)
DB_PATH = 'timetable.db'
DAYS = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT']
SLOT_TIMES = [
    ('09:00', '10:00'), ('10:00', '11:00'), ('11:00', '12:00'),
    ('12:30', '13:30'), ('13:30', '14:30'), ('14:30', '15:30'), ('15:30', '16:30')
]

# Register the blueprint
app.register_blueprint(admin_bp)

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
        (class_ids['TE-B1'], subject_ids['CSL201'], teacher_ids['Prof. Pingle'], 2, 1), # Lab (2-hr session, 2 times a week = 4 hours)
        (class_ids['TE-B2'], subject_ids['CS301'], teacher_ids['Dr. Deshmukh'], 3, 0),
        (class_ids['TE-B2'], subject_ids['CSL301'], teacher_ids['Ms. Shaikh'], 2, 1),  # Lab (2-hr session, 2 times a week = 4 hours)
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
        cur.execute('SELECT 1 FROM timetable_slots WHERE teacher_id = ? AND day = ? AND NOT (time_end <= ? OR time_start >= ?)', (teacher_id, day, time_start, time_end))
        if cur.fetchone(): return False
        cur.execute('SELECT 1 FROM timetable_slots WHERE classroom_id = ? AND day = ? AND NOT (time_end <= ? OR time_start >= ?)', (classroom_id, day, time_start, time_end))
        if cur.fetchone(): return False
        cur.execute('SELECT 1 FROM timetable_slots WHERE class_id = ? AND day = ? AND NOT (time_end <= ? OR time_start >= ?)', (class_id, day, time_start, time_end))
        if cur.fetchone(): return False
        return True

    def schedule_session(course, day, start_slot_index, duration, classroom):
        if start_slot_index + duration > len(SLOT_TIMES): return False
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
        if course['is_lab']:
            # Schedule a 2-hour lab session for a total of 'weekly_lectures' hours
            for _ in range(course['weekly_lectures'] // 2):
                labs_to_schedule.append(course)
        else:
            for _ in range(course['weekly_lectures']):
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
                slots_to_try.sort(key=lambda i: i > 2)
            elif teacher_pref == 'afternoon':
                slots_to_try.sort(key=lambda i: i <= 2)
                
            for i in slots_to_try:
                start_time = SLOT_TIMES[i][0]
                end_time = SLOT_TIMES[i][1]
                
                # Check for 2-hour gap after lab
                lab_info = teacher_lab_times.get(teacher_id)
                if lab_info and lab_info['day'] == day:
                    lab_end_time = datetime.strptime(lab_info['end_time'], '%H:%M')
                    current_start_time = datetime.strptime(start_time, '%H:%M')
                    if (current_start_time - lab_end_time).total_seconds() < 7200:
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

def validate_change(slot_id, day, time_start, time_end, teacher_id, classroom_id, class_id):
    db = get_db()
    cur = db.cursor()
    
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
    class_id_row = cur.fetchone()
    if class_id_row is None:
        return jsonify({'error': 'Class not found'}), 404
    class_id = class_id_row['class_id']
    
    grid = {day: {slot[0]: None for slot in SLOT_TIMES} for day in DAYS}
    
    slots_query = '''
        SELECT ts.*, t.name as teacher_name, s.name as subject_name, c.name as classroom_name, co.is_lab
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
        start_time_obj = datetime.strptime(slot['time_start'], '%H:%M')
        end_time_obj = datetime.strptime(slot['time_end'], '%H:%M')
        duration_minutes = (end_time_obj - start_time_obj).total_seconds() / 60
        
        start_index = next(i for i, time in enumerate(SLOT_TIMES) if time[0] == slot['time_start'])
        
        # Determine how many slots to fill
        # This assumes each slot is 60 minutes.
        duration_slots = int(duration_minutes / 60)
        
        for i in range(start_index, start_index + duration_slots):
            if i < len(SLOT_TIMES):
                grid[slot['day']][SLOT_TIMES[i][0]] = dict(slot)
            
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
        'slots': [s[0] for s in SLOT_TIMES],
        'options': {'teachers': teachers, 'subjects': subjects, 'classrooms': classrooms, 'courses': courses, 'classes': classes}
    })

@app.route('/api/timetable/update', methods=['POST'])
def api_update():
    data = request.json
    slot_id = data.get('slot_id')
    
    if not data['teacher_id'] and not data['subject_id'] and not data['classroom_id']:
        if slot_id:
            db = get_db()
            db.execute('DELETE FROM timetable_slots WHERE slot_id = ?', (slot_id,))
            db.commit()
            return jsonify({'status': 'success', 'message': 'Slot cleared successfully.'})
        return jsonify({'status': 'error', 'message': 'Invalid update request.'}), 400

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


# --- Admin Panel Delete Route ---
@app.route('/api/admin/delete/<entity>/<id>', methods=['DELETE'])
def delete_entity(entity, id):
    db = get_db()
    # Use a dictionary to map plural entity names to singular column IDs
    id_map = {
        'teachers': 'teacher_id',
        'subjects': 'subject_id',
        'classes': 'class_id',
        'classrooms': 'classroom_id',
        'courses': 'course_id'
    }

    if entity not in id_map:
        return jsonify({'status': 'error', 'message': 'Invalid entity'}), 400
    
    column_id = id_map[entity]

    try:
        db.execute(f'DELETE FROM {entity} WHERE {column_id} = ?', (id,))
        db.commit()
        return jsonify({'status': 'success', 'message': f'{entity.capitalize()} deleted successfully.'})
    except sqlite3.IntegrityError:
        return jsonify({'status': 'error', 'message': 'Cannot delete, it is in use by another table.'}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/download/pdf/<class_name>')
def download_pdf(class_name):
    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT class_id FROM classes WHERE name = ?', (class_name,))
    class_id = cur.fetchone()['class_id']
    timetable_data = [['Time'] + DAYS]
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