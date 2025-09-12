from flask import Flask, g, render_template, request, jsonify
import sqlite3
import os
from datetime import datetime

DB_PATH = 'timetable.db'
app = Flask(__name__)

DAYS = ['MON','TUE','WED','THU','FRI','SAT']
SLOT_TIMES = [
    ('09:00','10:00'), ('10:00','11:00'), ('11:00','12:00'),
    ('12:30','13:30'), ('13:30','14:30'), ('14:30','15:30'), ('15:30','16:30')
]

# --- Database helpers ---
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
    if db:
        db.close()

def init_db():
    db = sqlite3.connect(DB_PATH)
    c = db.cursor()
    # Teachers
    c.execute('''CREATE TABLE IF NOT EXISTS teachers (
        teacher_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        preference TEXT DEFAULT 'NONE'
    )''')
    # Subjects
    c.execute('''CREATE TABLE IF NOT EXISTS subjects (
        subject_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        weekly_lectures INTEGER DEFAULT 3,
        is_lab INTEGER DEFAULT 0,
        duration INTEGER DEFAULT 1
    )''')
    # Classrooms
    c.execute('''CREATE TABLE IF NOT EXISTS classrooms (
        classroom_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        type TEXT DEFAULT 'THEORY'
    )''')
    # Assignments
    c.execute('''CREATE TABLE IF NOT EXISTS assignments (
        assign_id INTEGER PRIMARY KEY AUTOINCREMENT,
        teacher_id INTEGER,
        subject_id INTEGER,
        class_year TEXT,
        classroom_id INTEGER
    )''')
    # Timetable slots
    c.execute('''CREATE TABLE IF NOT EXISTS timetable_slots (
        slot_id INTEGER PRIMARY KEY AUTOINCREMENT,
        day TEXT,
        time_start TEXT,
        time_end TEXT,
        teacher_id INTEGER,
        subject_id INTEGER,
        classroom_id INTEGER,
        class_year TEXT
    )''')
    db.commit()
    db.close()

# --- Sample data seed ---
def seed_sample_data():
    db = sqlite3.connect(DB_PATH)
    c = db.cursor()
    c.executescript('''
        DELETE FROM timetable_slots;
        DELETE FROM assignments;
        DELETE FROM teachers;
        DELETE FROM subjects;
        DELETE FROM classrooms;
    ''')
    # Teachers
    teachers = [('Prof. Bhosle','MORNING'), ('Prof. Ghule','NONE'),
                ('Prof. S.D. Pingle','AFTERNOON'), ('Prof. R.K. Ghule','NONE')]
    c.executemany('INSERT INTO teachers (name,preference) VALUES (?,?)', teachers)
    # Subjects
    subjects = [('Data Structures',3,0,1), ('Operating Systems',3,0,1),
                ('Database Systems',3,0,1), ('Programming Lab',2,1,2),
                ('Networks Lab',2,1,2), ('Software Eng',2,0,1)]
    c.executemany('INSERT INTO subjects (name,weekly_lectures,is_lab,duration) VALUES (?,?,?,?)', subjects)
    # Classrooms
    rooms = [('CR-1','THEORY'),('CR-2','THEORY'),('LAB-1','LAB'),('LAB-2','LAB')]
    c.executemany('INSERT INTO classrooms (name,type) VALUES (?,?)', rooms)
    db.commit()

    # Assignments
    c.execute('SELECT teacher_id FROM teachers'); t_ids = [r[0] for r in c.fetchall()]
    c.execute('SELECT subject_id FROM subjects'); s_ids = [r[0] for r in c.fetchall()]
    c.execute('SELECT classroom_id FROM classrooms'); c_ids = [r[0] for r in c.fetchall()]
    assignments = [
        (t_ids[0], s_ids[0], 'TE-B1', c_ids[0]),
        (t_ids[1], s_ids[1], 'TE-B1', c_ids[1]),
        (t_ids[2], s_ids[3], 'TE-B1', c_ids[2]),
        (t_ids[0], s_ids[2], 'TE-B2', c_ids[0]),
        (t_ids[1], s_ids[4], 'TE-B2', c_ids[3]),
        (t_ids[3], s_ids[5], 'TE-B3', c_ids[1])
    ]
    c.executemany('INSERT INTO assignments (teacher_id,subject_id,class_year,classroom_id) VALUES (?,?,?,?)', assignments)
    db.commit(); db.close()

# --- Scheduler ---
def clear_timetable():
    db = get_db()
    db.execute('DELETE FROM timetable_slots')
    db.commit()

def generate_timetable():
    db = get_db(); cur = db.cursor()
    clear_timetable()
    cur.execute('''SELECT a.assign_id,a.teacher_id,a.subject_id,a.class_year,a.classroom_id,
                   s.weekly_lectures,s.is_lab,s.duration
                   FROM assignments a JOIN subjects s ON a.subject_id=s.subject_id''')
    assigns = cur.fetchall()
    tasks = []
    for a in assigns:
        for _ in range(a['weekly_lectures']):
            tasks.append({'assign_id': a['assign_id'], 'teacher_id': a['teacher_id'], 'subject_id': a['subject_id'],
                          'class_year': a['class_year'], 'classroom_id': a['classroom_id'],
                          'is_lab': a['is_lab'], 'duration': a['duration']})
    labs = [t for t in tasks if t['duration']>1]
    lectures = [t for t in tasks if t['duration']==1]

    def teacher_busy(day,start,end,teacher_id):
        cur.execute('SELECT 1 FROM timetable_slots WHERE teacher_id=? AND day=? AND NOT (time_end<=? OR time_start>=?)',
                    (teacher_id, day, start, end))
        return cur.fetchone() is not None
    def room_busy(day,start,end,room_id):
        cur.execute('SELECT 1 FROM timetable_slots WHERE classroom_id=? AND day=? AND NOT (time_end<=? OR time_start>=?)',
                    (room_id, day, start, end))
        return cur.fetchone() is not None

    def place_task(t):
        for day in DAYS:
            for i,slot in enumerate(SLOT_TIMES):
                start,end = slot
                if t['duration']==2:
                    if i+1>=len(SLOT_TIMES): continue
                    start2,end2 = SLOT_TIMES[i+1]
                    full_start,full_end = start,end2
                else:
                    full_start,full_end = start,end
                if teacher_busy(day,full_start,full_end,t['teacher_id']): continue
                if room_busy(day,full_start,full_end,t['classroom_id']): continue
                cur.execute('INSERT INTO timetable_slots (day,time_start,time_end,teacher_id,subject_id,classroom_id,class_year) VALUES (?,?,?,?,?,?,?)',
                            (day,full_start,full_end,t['teacher_id'],t['subject_id'],t['classroom_id'],t['class_year']))
                db.commit(); return True
        return False

    for l in labs: place_task(l)
    for lec in lectures: place_task(lec)

# --- Validation ---
def validate_change(payload):
    db = get_db(); cur = db.cursor()
    slot_id = payload.get('slot_id'); day = payload['day']
    start,end = payload['time_start'],payload['time_end']
    teacher_id,classroom_id,subject_id,class_year = payload['teacher_id'],payload['classroom_id'],payload['subject_id'],payload['class_year']
    q = 'SELECT 1 FROM timetable_slots WHERE teacher_id=? AND day=? AND NOT (time_end<=? OR time_start>=?)'
    params = (teacher_id, day, start, end)
    if slot_id: q+=' AND slot_id!=?'; params+=(slot_id,)
    cur.execute(q,params); 
    if cur.fetchone(): return False,'Teacher already assigned at this time.'
    q2='SELECT 1 FROM timetable_slots WHERE classroom_id=? AND day=? AND NOT (time_end<=? OR time_start>=?)'
    params2=(classroom_id, day, start, end)
    if slot_id:q2+=' AND slot_id!=?'; params2+=(slot_id,)
    cur.execute(q2,params2)
    if cur.fetchone(): return False,'Classroom already occupied at this time.'
    cur.execute('SELECT weekly_lectures,is_lab,duration FROM subjects WHERE subject_id=?',(subject_id,))
    subj=cur.fetchone()
    if subj:
        cur.execute('SELECT COUNT(*) as cnt FROM timetable_slots WHERE subject_id=? AND class_year=?',(subject_id,class_year))
        cnt=cur.fetchone()['cnt']
        if cnt>=subj['weekly_lectures']: return False,'This subject already has its weekly lecture count.'
        if subj['is_lab'] and subj['duration']>1:
            fmt='%H:%M'
            tstart=datetime.strptime(start,fmt); tend=datetime.strptime(end,fmt)
            diff=(tend-tstart).seconds/3600
            if diff<subj['duration']: return False,'Lab must be scheduled for continuous {} hours.'.format(subj['duration'])
    return True,'OK'

# --- Routes ---
@app.route('/')
def index(): return render_template('index.html')
@app.route('/manage') 
def manage(): return render_template('manage.html')

@app.route('/api/options')
def api_options():
    db=get_db(); cur=db.cursor()
    cur.execute('SELECT teacher_id,name,preference FROM teachers'); teachers=[dict(r) for r in cur.fetchall()]
    cur.execute('SELECT subject_id,name,weekly_lectures,is_lab,duration FROM subjects'); subjects=[dict(r) for r in cur.fetchall()]
    cur.execute('SELECT classroom_id,name,type FROM classrooms'); rooms=[dict(r) for r in cur.fetchall()]
    cur.execute('SELECT assign_id,a.teacher_id,a.subject_id,a.class_year,a.classroom_id,t.name as teacher_name,s.name as subject_name,c.name as classroom_name FROM assignments a JOIN teachers t ON a.teacher_id=t.teacher_id JOIN subjects s ON a.subject_id=s.subject_id JOIN classrooms c ON a.classroom_id=c.classroom_id')
    assigns=[dict(r) for r in cur.fetchall()]
    cur.execute('SELECT DISTINCT class_year FROM assignments')
    class_years=[r['class_year'] for r in cur.fetchall()] or ['TE-B1','TE-B2','TE-B3']
    return jsonify({'teachers':teachers,'subjects':subjects,'classrooms':rooms,'assignments':assigns,'class_years':class_years})

@app.route('/api/timetables')
def api_timetables():
    db=get_db(); cur=db.cursor()
    cur.execute('SELECT DISTINCT class_year FROM assignments'); years=[r['class_year'] for r in cur.fetchall()]
    if not years: years=['TE-B1','TE-B2','TE-B3']
    blocks=[]
    for y in years:
        grid={d:{} for d in DAYS}
        times=['{} - {}'.format(t[0],t[1]) for t in SLOT_TIMES]
        cur.execute('''SELECT s.slot_id,s.day,s.time_start,s.time_end,s.teacher_id,s.subject_id,s.classroom_id,s.class_year,
                       t.name as teacher_name, sub.name as subject_name, c.name as classroom_name
                       FROM timetable_slots s LEFT JOIN teachers t ON s.teacher_id=t.teacher_id
                       LEFT JOIN subjects sub ON s.subject_id=sub.subject_id
                       LEFT JOIN classrooms c ON s.classroom_id=c.classroom_id
                       WHERE s.class_year=?''',(y,))
        rows=cur.fetchall()
        for r in rows: grid[r['day']]['{} - {}'.format(r['time_start'],r['time_end'])]=dict(r)
        cur.execute('SELECT c.name as classroom_name FROM assignments a JOIN classrooms c ON a.classroom_id=c.classroom_id WHERE a.class_year=? LIMIT 1',(y,))
        cref=cur.fetchone(); classroom_name=cref['classroom_name'] if cref else ''
        blocks.append({'year':y,'grid':grid,'times':times,'classroom_name':classroom_name})
    return jsonify({'years':blocks})

@app.route('/api/seed',methods=['POST'])
def api_seed(): seed_sample_data(); return jsonify({'status':'ok'})
@app.route('/api/generate',methods=['POST'])
def api_generate(): generate_timetable(); return jsonify({'status':'ok'})
@app.route('/api/edit_slot',methods=['POST'])
def api_edit_slot():
    data = request.form.to_dict() if request.form else request.get_json()
    slot_id = data.get('slot_id') or None
    payload={'slot_id':slot_id,'day':data['day'],'time_start':data['time_start'],
             'time_end':data['time_end'],'teacher_id':int(data['teacher_id']) if data.get('teacher_id') else None,
             'subject_id':int(data['subject_id']) if data.get('subject_id') else None,
             'classroom_id':int(data['classroom_id']) if data.get('classroom_id') else None,
             'class_year':data['class_year']}
    valid,msg = validate_change(payload)
    if not valid: return jsonify({'status':'error','message':msg})
    db=get_db(); cur=db.cursor()
    if slot_id:
        cur.execute('UPDATE timetable_slots SET teacher_id=?,subject_id=?,classroom_id=? WHERE slot_id=?',
                    (payload['teacher_id'],payload['subject_id'],payload['classroom_id'],slot_id))
    else:
        cur.execute('INSERT INTO timetable_slots (day,time_start,time_end,teacher_id,subject_id,classroom_id,class_year) VALUES (?,?,?,?,?,?,?)',
                    (payload['day'],payload['time_start'],payload['time_end'],payload['teacher_id'],payload['subject_id'],payload['classroom_id'],payload['class_year']))
    db.commit(); return jsonify({'status':'ok'})

# --- Run ---
if __name__=='__main__':
    if not os.path.exists(DB_PATH): init_db(); seed_sample_data()
    app.run(debug=True)
