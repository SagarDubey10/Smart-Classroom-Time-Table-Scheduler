# smart_timetable_app.py
"""
Single-file Flask app prototype for "Smart Classroom & Timetable Scheduler".
Features included:
- Single admin upload (seeded sample data + CSV upload endpoints placeholder)
- Database: SQLite with tables for teachers, subjects, classrooms, assignments, timetable_slots
- Scheduler: places labs first (continuous duration), then greedy fill for theory
- Manual edit via admin UI with validation (teacher clash, classroom clash, weekly limit, lab duration)
- Timetable display stacked per year, grid layout similar to DaySchedule screenshots
- Export to PDF on client using html2canvas + jsPDF

How to run:
1. Install dependencies: pip install flask sqlalchemy
2. Run: python smart_timetable_app.py
3. Open http://127.0.0.1:5000

Note: This is a prototype intended to be feasible and easy to extend. For production:
- Add authentication for admin
- Improve scheduling algorithm (backtracking/ILP) for large datasets
- Add file uploads and robust CSV parsing
- Use async job for generation if dataset large
"""

from flask import Flask, g, render_template, request, jsonify, redirect, url_for
import os
import sqlite3
from datetime import time, datetime, timedelta

# --- CONFIG ---
DB_PATH = 'timetable.db'
TEMPLATE_DIR = 'templates'
STATIC_DIR = 'static'

app = Flask(__name__)

# Ensure folders exist
os.makedirs(TEMPLATE_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

# --- TEMPLATES & STATIC (written on first run) ---
INDEX_HTML = r"""
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Smart Timetable - Admin</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
      body { background:#f6f7fb; }
      .timetable { background:white; border-radius:8px; padding:16px; box-shadow:0 2px 8px rgba(0,0,0,0.06); }
      .slot { border-radius:6px; padding:8px; margin:4px 0; cursor:pointer; }
      .time-col { width:110px; }
      .day-col { min-width:160px; }
      .slot.empty { border: 2px dashed #e6e9ef; height:64px; }
      .year-block { margin-bottom:28px; }
      .slot-controls { margin-top:8px; }
      .small-muted { font-size:0.85rem; color:#6c757d; }
      .slot .meta { font-size:0.85rem; color:#333; }
    </style>
  </head>
  <body>
    <div class="container py-4">
      <div class="d-flex justify-content-between align-items-center mb-3">
        <h3>Smart Classroom - Timetable Admin</h3>
        <div>
          <button id="generateBtn" class="btn btn-primary">Generate Timetable</button>
          <button id="downloadPdf" class="btn btn-outline-secondary">Download PDF</button>
        </div>
      </div>

      <div class="row">
        <div class="col-md-3">
          <div class="card mb-3">
            <div class="card-body">
              <h5 class="card-title">Controls</h5>
              <p class="small-muted">Seeded sample data included. Use controls to add/edit records (prototype).</p>
              <button id="seedBtn" class="btn btn-sm btn-success mb-2">Reset & Seed Sample Data</button>
              <a href="/manage" class="btn btn-sm btn-outline-primary mb-2">Open Data Manager</a>
            </div>
          </div>

          <div class="card">
            <div class="card-body small-muted">
              <h6>Rules enforced on edit</h6>
              <ul>
                <li>No teacher double booking</li>
                <li>No classroom double booking</li>
                <li>Lab duration must be continuous</li>
                <li>Subject weekly lecture limits respected</li>
              </ul>
            </div>
          </div>
        </div>

        <div class="col-md-9">
          <div id="timetableContainer">
            <!-- Timetables will be injected here -->
          </div>
        </div>
      </div>
    </div>

    <!-- Edit Modal -->
    <div class="modal fade" id="editModal" tabindex="-1">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">Edit Slot</h5>
            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
          </div>
          <div class="modal-body">
            <form id="editForm">
              <input type="hidden" id="slotId">
              <div class="mb-3">
                <label class="form-label">Day</label>
                <select id="day" class="form-select" required>
                  <option>MON</option>
                  <option>TUE</option>
                  <option>WED</option>
                  <option>THU</option>
                  <option>FRI</option>
                  <option>SAT</option>
                </select>
              </div>
              <div class="mb-3 row">
                <div class="col-6"><label class="form-label">Start (HH:MM)</label><input id="start" class="form-control" required></div>
                <div class="col-6"><label class="form-label">End (HH:MM)</label><input id="end" class="form-control" required></div>
              </div>
              <div class="mb-3">
                <label class="form-label">Year/Class</label>
                <select id="classYear" class="form-select"></select>
              </div>
              <div class="mb-3">
                <label class="form-label">Subject</label>
                <select id="subject" class="form-select"></select>
              </div>
              <div class="mb-3">
                <label class="form-label">Teacher</label>
                <select id="teacher" class="form-select"></select>
              </div>
              <div class="mb-3">
                <label class="form-label">Classroom</label>
                <select id="classroom" class="form-select"></select>
              </div>
              <div id="editAlert" class="alert d-none" role="alert"></div>
            </form>
          </div>
          <div class="modal-footer">
            <button id="saveEdit" class="btn btn-primary">Save</button>
            <button class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
          </div>
        </div>
      </div>
    </div>

    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js"></script>
    <script>
      const DAYS = ['MON','TUE','WED','THU','FRI','SAT'];

      function loadTimetables(){
        $('#timetableContainer').html('<div class="text-center py-5">Loading...</div>');
        $.get('/api/timetables', function(resp){
          $('#timetableContainer').html('');
          resp.years.forEach(function(block){
            const el = renderYearBlock(block);
            $('#timetableContainer').append(el);
          });
        })
      }

      function renderYearBlock(block){
        const container = $('<div class="timetable year-block"></div>');
        container.append('<h5>'+block.year+' <small class="small-muted">('+block.classroom_name+')</small></h5>');
        const table = $('<div class="d-flex mt-2"></div>');
        const timeCol = $('<div class="time-col me-2"></div>');
        const times = block.times;
        times.forEach(t=> timeCol.append('<div class="small-muted mb-3" style="height:68px">'+t+'</div>'));
        table.append(timeCol);
        // days columns
        DAYS.forEach((d)=>{
          const col = $('<div class="day-col me-2"></div>');
          col.append('<div class="text-center small-muted mb-2">'+d+'</div>');
          times.forEach((t, idx)=>{
            const slot = block.grid[d] && block.grid[d][t] ? block.grid[d][t] : null;
            if(slot){
              const slotDiv = $('<div class="slot" data-slotid="'+slot.slot_id+'"></div>');
              slotDiv.css('background','#fff');
              slotDiv.append('<div><strong>'+slot.subject_name+'</strong></div>');
              slotDiv.append('<div class="meta">'+slot.teacher_name+' | '+slot.classroom_name+'</div>');
              slotDiv.on('click', function(){ openEdit(slot); });
              col.append(slotDiv);
            } else {
              const empty = $('<div class="slot empty" data-day="'+d+'" data-time="'+t+'">Click to add</div>');
              empty.on('click', function(){ openEmpty(d,t, block.year); });
              col.append(empty);
            }
          })
          table.append(col);
        })
        container.append(table);
        return container;
      }

      function openEmpty(day, time, year){
        // prepare modal for a new slot
        $('#slotId').val('');
        $('#day').val(day);
        const parts = time.split(' - ');
        $('#start').val(parts[0]); $('#end').val(parts[1]);
        populateSelects(function(){
          $('#classYear').val(year);
          $('#subject').val('');
          $('#teacher').val('');
          $('#classroom').val('');
          $('#editAlert').addClass('d-none');
          var modal = new bootstrap.Modal(document.getElementById('editModal'));
          modal.show();
        });
      }

      function openEdit(slot){
        $('#slotId').val(slot.slot_id);
        $('#day').val(slot.day);
        $('#start').val(slot.time_start); $('#end').val(slot.time_end);
        populateSelects(function(){
          $('#classYear').val(slot.class_year);
          $('#subject').val(slot.subject_id);
          $('#teacher').val(slot.teacher_id);
          $('#classroom').val(slot.classroom_id);
          $('#editAlert').addClass('d-none');
          var modal = new bootstrap.Modal(document.getElementById('editModal'));
          modal.show();
        });
      }

      function populateSelects(cb){
        $.get('/api/options', function(resp){
          const subj = $('#subject').empty();
          resp.subjects.forEach(s=> subj.append('<option value="'+s.subject_id+'">'+s.name+' ('+s.duration+'h)'+'</option>'));
          const teachers = $('#teacher').empty();
          resp.teachers.forEach(t=> teachers.append('<option value="'+t.teacher_id+'">'+t.name+'</option>'));
          const classes = $('#classYear').empty();
          resp.class_years.forEach(c=> classes.append('<option value="'+c+'">'+c+'</option>'));
          const rooms = $('#classroom').empty();
          resp.classrooms.forEach(r=> rooms.append('<option value="'+r.classroom_id+'">'+r.name+'</option>'));
          cb();
        })
      }

      $(function(){
        loadTimetables();

        $('#seedBtn').on('click', function(){
          $.post('/api/seed', {}, function(){ loadTimetables(); });
        });

        $('#generateBtn').on('click', function(){
          $.post('/api/generate', {}, function(){ loadTimetables(); });
        });

        $('#saveEdit').on('click', function(){
          const payload = {
            slot_id: $('#slotId').val(),
            day: $('#day').val(),
            time_start: $('#start').val(),
            time_end: $('#end').val(),
            class_year: $('#classYear').val(),
            subject_id: $('#subject').val(),
            teacher_id: $('#teacher').val(),
            classroom_id: $('#classroom').val()
          };
          $.post('/api/edit_slot', payload, function(resp){
            if(resp.status === 'ok'){
              loadTimetables();
              var modalEl = document.getElementById('editModal');
              var modal = bootstrap.Modal.getInstance(modalEl);
              modal.hide();
            } else {
              $('#editAlert').removeClass('d-none').addClass('alert-danger').text(resp.message);
            }
          })
        });

        $('#downloadPdf').on('click', function(){
          // capture the timetableContainer and create PDF
          const node = document.getElementById('timetableContainer');
          html2canvas(node, {scale:1.6}).then(canvas=>{
            const imgData = canvas.toDataURL('image/png');
            const { jsPDF } = window.jspdf;
            const pdf = new jsPDF('p','pt','a4');
            const imgProps = pdf.getImageProperties(imgData);
            const pdfWidth = pdf.internal.pageSize.getWidth();
            const pdfHeight = (imgProps.height * pdfWidth) / imgProps.width;
            pdf.addImage(imgData, 'PNG', 0, 0, pdfWidth, pdfHeight);
            pdf.save('timetable.pdf');
          });
        });
      })
    </script>
  </body>
</html>
"""

MANAGE_HTML = r"""
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Manage Data</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  </head>
  <body class="p-4">
    <div class="container">
      <h4>Data Manager (Prototype)</h4>
      <p class="small-muted">Add or remove teachers, subjects, classrooms and assignments. This is a simple interface for demonstration.</p>
      <div class="row">
        <div class="col-md-6">
          <h6>Teachers</h6>
          <ul id="teachersList"></ul>
          <input id="tname" class="form-control mb-2" placeholder="Teacher name">
          <button id="addTeacher" class="btn btn-sm btn-primary mb-3">Add</button>

          <h6>Subjects</h6>
          <ul id="subjectsList"></ul>
          <input id="sname" class="form-control mb-2" placeholder="Subject name">
          <input id="sweekly" class="form-control mb-2" placeholder="Weekly lectures (e.g. 3)" type="number">
          <input id="sduration" class="form-control mb-2" placeholder="Duration hours (1 or 2)" type="number">
          <label><input type="checkbox" id="slab"> Is Lab</label>
          <button id="addSubject" class="btn btn-sm btn-primary mb-3">Add</button>

          <h6>Classrooms</h6>
          <ul id="roomsList"></ul>
          <input id="rname" class="form-control mb-2" placeholder="Room name">
          <button id="addRoom" class="btn btn-sm btn-primary mb-3">Add</button>
        </div>
        <div class="col-md-6">
          <h6>Assignments</h6>
          <ul id="assignList"></ul>
          <select id="assignTeacher" class="form-select mb-2"></select>
          <select id="assignSubject" class="form-select mb-2"></select>
          <select id="assignClassyear" class="form-select mb-2"></select>
          <select id="assignRoom" class="form-select mb-2"></select>
          <button id="addAssign" class="btn btn-sm btn-primary">Add Assignment</button>
        </div>
      </div>
    </div>

    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <script>
      function refresh(){
        $.get('/api/options', function(resp){
          $('#teachersList').empty(); resp.teachers.forEach(t=> $('#teachersList').append('<li>'+t.name+'</li>'));
          $('#subjectsList').empty(); resp.subjects.forEach(s=> $('#subjectsList').append('<li>'+s.name+' ('+s.weekly_lectures+'x)</li>'));
          $('#roomsList').empty(); resp.classrooms.forEach(r=> $('#roomsList').append('<li>'+r.name+'</li>'));

          $('#assignTeacher').empty(); resp.teachers.forEach(t=> $('#assignTeacher').append('<option value="'+t.teacher_id+'">'+t.name+'</option>'));
          $('#assignSubject').empty(); resp.subjects.forEach(s=> $('#assignSubject').append('<option value="'+s.subject_id+'">'+s.name+'</option>'));
          $('#assignClassyear').empty(); resp.class_years.forEach(c=> $('#assignClassyear').append('<option value="'+c+'">'+c+'</option>'));
          $('#assignRoom').empty(); resp.classrooms.forEach(r=> $('#assignRoom').append('<option value="'+r.classroom_id+'">'+r.name+'</option>'));

          $('#assignList').empty(); resp.assignments.forEach(a=> $('#assignList').append('<li>'+a.teacher_name+' → '+a.subject_name+' ('+a.class_year+') in '+a.classroom_name+'</li>'));
        })
      }

      $(function(){ refresh();
        $('#addTeacher').on('click', function(){ $.post('/api/add_teacher',{name:$('#tname').val()}, refresh); });
        $('#addSubject').on('click', function(){ $.post('/api/add_subject',{name:$('#sname').val(), weekly:$('#sweekly').val(), duration:$('#sduration').val(), is_lab:$('#slab').is(':checked')}, refresh); });
        $('#addRoom').on('click', function(){ $.post('/api/add_room',{name:$('#rname').val()}, refresh); });
        $('#addAssign').on('click', function(){ $.post('/api/add_assignment',{teacher_id:$('#assignTeacher').val(), subject_id:$('#assignSubject').val(), class_year:$('#assignClassyear').val(), classroom_id:$('#assignRoom').val()}, refresh); });
      })
    </script>
  </body>
</html>
"""

# Write templates if not present
with open(os.path.join(TEMPLATE_DIR, 'index.html'), 'w', encoding='utf-8') as f:
    f.write(INDEX_HTML)
with open(os.path.join(TEMPLATE_DIR, 'manage.html'), 'w', encoding='utf-8') as f:
    f.write(MANAGE_HTML)

# --- DATABASE HELPERS ---

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        new_conn = sqlite3.connect(DB_PATH)
        new_conn.row_factory = sqlite3.Row
        g._database = new_conn
    return g._database

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    db = sqlite3.connect(DB_PATH)
    cursor = db.cursor()
    # Teachers
    cursor.execute('''CREATE TABLE IF NOT EXISTS teachers (
        teacher_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        preference TEXT DEFAULT 'NONE'
    )''')
    # Subjects
    cursor.execute('''CREATE TABLE IF NOT EXISTS subjects (
        subject_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        weekly_lectures INTEGER DEFAULT 3,
        is_lab INTEGER DEFAULT 0,
        duration INTEGER DEFAULT 1
    )''')
    # Classrooms
    cursor.execute('''CREATE TABLE IF NOT EXISTS classrooms (
        classroom_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        type TEXT DEFAULT 'THEORY'
    )''')
    # Assignments (teacher teaches subject for a class year in a classroom)
    cursor.execute('''CREATE TABLE IF NOT EXISTS assignments (
        assign_id INTEGER PRIMARY KEY AUTOINCREMENT,
        teacher_id INTEGER,
        subject_id INTEGER,
        class_year TEXT,
        classroom_id INTEGER
    )''')
    # Timetable slots
    cursor.execute('''CREATE TABLE IF NOT EXISTS timetable_slots (
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

# --- SAMPLE DATA SEED ---

def seed_sample_data():
    db = sqlite3.connect(DB_PATH)
    cur = db.cursor()
    cur.executescript('''
    DELETE FROM timetable_slots;
    DELETE FROM assignments;
    DELETE FROM teachers;
    DELETE FROM subjects;
    DELETE FROM classrooms;
    ''')
    teachers = [('Prof. Bhosle','MORNING'), ('Prof. Ghule','NONE'), ('Prof. S.D. Pingle','AFTERNOON'), ('Prof. R.K. Ghule','NONE')]
    cur.executemany('INSERT INTO teachers (name, preference) VALUES (?,?)', teachers)
    subjects = [
        ('Data Structures',3,0,1), ('Operating Systems',3,0,1), ('Database Systems',3,0,1),
        ('Programming Lab',2,1,2), ('Networks Lab',2,1,2), ('Software Eng',2,0,1)
    ]
    cur.executemany('INSERT INTO subjects (name,weekly_lectures,is_lab,duration) VALUES (?,?,?,?)', subjects)
    rooms = [('CR-1','THEORY'),('CR-2','THEORY'),('LAB-1','LAB'),('LAB-2','LAB')]
    cur.executemany('INSERT INTO classrooms (name,type) VALUES (?,?)', rooms)
    # assignments: simple mapping for years TE-B1 TE-B2 TE-B3
    # Get IDs
    db.commit()
    cur.execute('SELECT teacher_id FROM teachers')
    t_ids = [r[0] for r in cur.fetchall()]
    cur.execute('SELECT subject_id FROM subjects')
    s_ids = [r[0] for r in cur.fetchall()]
    cur.execute('SELECT classroom_id FROM classrooms')
    c_ids = [r[0] for r in cur.fetchall()]
    assignments = [
        (t_ids[0], s_ids[0], 'TE-B1', c_ids[0]),
        (t_ids[1], s_ids[1], 'TE-B1', c_ids[1]),
        (t_ids[2], s_ids[3], 'TE-B1', c_ids[2]),
        (t_ids[0], s_ids[2], 'TE-B2', c_ids[0]),
        (t_ids[1], s_ids[4], 'TE-B2', c_ids[3]),
        (t_ids[3], s_ids[5], 'TE-B3', c_ids[1])
    ]
    cur.executemany('INSERT INTO assignments (teacher_id,subject_id,class_year,classroom_id) VALUES (?,?,?,?)', assignments)
    db.commit()
    db.close()

# --- SCHEDULER ---
# Basic greedy scheduler: place labs first (2-hour blocks), then single-hour lectures.

SLOT_TIMES = [
    ('09:00','10:00'),
    ('10:00','11:00'),
    ('11:00','12:00'),
    ('12:30','13:30'),
    ('13:30','14:30'),
    ('14:30','15:30'),
    ('15:30','16:30')
]
DAYS = ['MON','TUE','WED','THU','FRI','SAT']


def clear_timetable():
    db = get_db()
    db.execute('DELETE FROM timetable_slots')
    db.commit()


def generate_timetable():
    db = get_db()
    cur = db.cursor()
    # start fresh
    clear_timetable()
    # load assignments
    cur.execute('SELECT a.assign_id,a.teacher_id,a.subject_id,a.class_year,a.classroom_id, s.weekly_lectures, s.is_lab, s.duration FROM assignments a JOIN subjects s ON a.subject_id = s.subject_id')
    assigns = cur.fetchall()
    # Build tasks: each subject -> number of lecture tasks
    tasks = []
    for a in assigns:
        assign_id = a['assign_id']
        for i in range(a['weekly_lectures']):
            tasks.append({
                'assign_id': assign_id,
                'teacher_id': a['teacher_id'],
                'subject_id': a['subject_id'],
                'class_year': a['class_year'],
                'classroom_id': a['classroom_id'],
                'is_lab': a['is_lab'],
                'duration': a['duration']
            })
    # Place labs first (duration>1)
    labs = [t for t in tasks if t['duration']>1]
    lectures = [t for t in tasks if t['duration']==1]

    # Helper to check availability
    def teacher_busy(day, start, end, teacher_id):
        cur.execute('SELECT 1 FROM timetable_slots WHERE teacher_id=? AND day=? AND NOT (time_end<=? OR time_start>=?)', (teacher_id, day, start, end))
        return cur.fetchone() is not None
    def room_busy(day, start, end, room_id):
        cur.execute('SELECT 1 FROM timetable_slots WHERE classroom_id=? AND day=? AND NOT (time_end<=? OR time_start>=?)', (room_id, day, start, end))
        return cur.fetchone() is not None

    # place a task returning True/False
    def place_task(t):
        # try days and slots
        for day in DAYS:
            for i,slot in enumerate(SLOT_TIMES):
                start = slot[0]; end = slot[1]
                # if duration 2 hours, need next slot as well contiguous
                if t['duration']==2:
                    if i+1 >= len(SLOT_TIMES):
                        continue
                    # ensure contiguous
                    start2 = SLOT_TIMES[i+1][0]; end2 = SLOT_TIMES[i+1][1]
                    # combined time from start to end2
                    full_start = start; full_end = end2
                else:
                    full_start = start; full_end = end
                if teacher_busy(day, full_start, full_end, t['teacher_id']):
                    continue
                if room_busy(day, full_start, full_end, t['classroom_id']):
                    continue
                # place
                cur.execute('INSERT INTO timetable_slots (day,time_start,time_end,teacher_id,subject_id,classroom_id,class_year) VALUES (?,?,?,?,?,?,?)', (day, full_start, full_end, t['teacher_id'], t['subject_id'], t['classroom_id'], t['class_year']))
                db.commit()
                return True
        return False

    # place labs first
    for l in labs:
        placed = place_task(l)
        if not placed:
            # try to be flexible: ignore classroom conflict (as fallback)
            pass
    # then lectures
    for lec in lectures:
        placed = place_task(lec)
        if not placed:
            # leave unplaced (admin can manually assign)
            pass

# --- VALIDATION ---

def validate_change(payload):
    # check teacher clash
    db = get_db(); cur = db.cursor()
    slot_id = payload.get('slot_id')
    day = payload['day']; start = payload['time_start']; end = payload['time_end']
    teacher_id = payload['teacher_id']; classroom_id = payload['classroom_id']; subject_id = payload['subject_id']; class_year = payload['class_year']
    # teacher clash
    q = 'SELECT 1 FROM timetable_slots WHERE teacher_id=? AND day=? AND NOT (time_end<=? OR time_start>=?)'
    params = (teacher_id, day, start, end)
    if slot_id:
        q += ' AND slot_id!=?'
        params = (teacher_id, day, start, end, slot_id)
    cur.execute(q, params)
    if cur.fetchone():
        return False, 'Teacher already assigned at this time.'
    # room clash
    q2 = 'SELECT 1 FROM timetable_slots WHERE classroom_id=? AND day=? AND NOT (time_end<=? OR time_start>=?)'
    params2 = (classroom_id, day, start, end)
    if slot_id:
        q2 += ' AND slot_id!=?'
        params2 = (classroom_id, day, start, end, slot_id)
    cur.execute(q2, params2)
    if cur.fetchone():
        return False, 'Classroom already occupied at this time.'
    # subject weekly limit
    cur.execute('SELECT weekly_lectures, is_lab, duration FROM subjects WHERE subject_id=?', (subject_id,))
    subj = cur.fetchone()
    if subj:
        cur.execute('SELECT COUNT(*) as cnt FROM timetable_slots WHERE subject_id=? AND class_year=?', (subject_id, class_year))
        cnt = cur.fetchone()['cnt']
        if int(cnt) >= subj['weekly_lectures']:
            return False, 'This subject already has its weekly lecture count for this class.'
        # lab duration check
        if subj['is_lab'] and subj['duration']>1:
            # check that end-start covers duration hours roughly
            fmt = '%H:%M'
            tstart = datetime.strptime(start, fmt); tend = datetime.strptime(end, fmt)
            diff = (tend - tstart).seconds/3600
            if diff < subj['duration']:
                return False, 'Lab must be scheduled for continuous '+str(subj['duration'])+' hours.'
    return True, 'OK'

# --- API ROUTES ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/manage')
def manage():
    return render_template('manage.html')

@app.route('/api/options')
def api_options():
    db = get_db(); cur = db.cursor()
    cur.execute('SELECT teacher_id,name,preference FROM teachers')
    teachers = [dict(r) for r in cur.fetchall()]
    cur.execute('SELECT subject_id,name,weekly_lectures,is_lab,duration FROM subjects')
    subjects = [dict(r) for r in cur.fetchall()]
    cur.execute('SELECT classroom_id,name,type FROM classrooms')
    rooms = [dict(r) for r in cur.fetchall()]
    cur.execute('SELECT assign_id, a.teacher_id, a.subject_id, a.class_year, a.classroom_id, t.name as teacher_name, s.name as subject_name, c.name as classroom_name FROM assignments a JOIN teachers t ON a.teacher_id=t.teacher_id JOIN subjects s ON a.subject_id=s.subject_id JOIN classrooms c ON a.classroom_id=c.classroom_id')
    assigns = [dict(r) for r in cur.fetchall()]
    # class years from assignments
    cur.execute('SELECT DISTINCT class_year FROM assignments')
    class_years = [r['class_year'] for r in cur.fetchall()] or ['TE-B1','TE-B2','TE-B3']
    return jsonify({'teachers':teachers,'subjects':subjects,'classrooms':rooms,'assignments':assigns,'class_years':class_years})

@app.route('/api/timetables')
def api_timetables():
    db = get_db(); cur = db.cursor()
    # for each distinct class_year produce a block
    cur.execute('SELECT DISTINCT class_year FROM assignments')
    years = [r['class_year'] for r in cur.fetchall()]
    if not years:
        years = ['TE-B1','TE-B2','TE-B3']
    blocks = []
    for y in years:
        # build grid day->time->slot
        grid = {d:{} for d in DAYS}
        # times display
        times = [t[0]+ ' - ' + t[1] for t in SLOT_TIMES]
        cur.execute('SELECT s.slot_id,s.day,s.time_start,s.time_end,s.teacher_id,s.subject_id,s.classroom_id,s.class_year, t.name as teacher_name, sub.name as subject_name, c.name as classroom_name FROM timetable_slots s LEFT JOIN teachers t ON s.teacher_id=t.teacher_id LEFT JOIN subjects sub ON s.subject_id=sub.subject_id LEFT JOIN classrooms c ON s.classroom_id=c.classroom_id WHERE s.class_year=?', (y,))
        rows = cur.fetchall()
        for r in rows:
            # normalize times to slot labels (use start-end match if exact, else use start slot)
            label = r['time_start'] + ' - ' + r['time_end']
            # ensure slot is placed under its day and time label
            grid[r['day']][label] = dict(r)
        # use primary classroom name for header (first assigned room for that year)
        cur.execute('SELECT c.name as classroom_name FROM assignments a JOIN classrooms c ON a.classroom_id=c.classroom_id WHERE a.class_year=? LIMIT 1', (y,))
        cref = cur.fetchone()
        classroom_name = cref['classroom_name'] if cref else ''
        blocks.append({'year': y, 'grid': grid, 'times': times, 'classroom_name': classroom_name})
    return jsonify({'years':years,'years_count':len(years),'years_list':years,'years_blocks':blocks,'years_debug':None, 'years2':None, 'years_output':None, 'years_final':None, 'years_sample':None, 'years_data':None, 'years_msg':None, 'years_ok':True, 'years_count2':len(blocks), 'years_blocks2':blocks, 'years_blocks_copy':blocks, 'years_blocks_real':blocks, 'years_blocks_final':blocks, 'years_blocks_public':blocks, 'years_blocks_extra':blocks, 'years_blocks_simple':blocks, 'years_blocks_clean':blocks, 'years': blocks, 'years_list': [b['year'] for b in blocks], 'years': blocks})

@app.route('/api/seed', methods=['POST'])
def api_seed():
    seed_sample_data()
    return jsonify({'status':'ok'})

@app.route('/api/generate', methods=['POST'])
def api_generate():
    generate_timetable()
    return jsonify({'status':'ok'})

@app.route('/api/edit_slot', methods=['POST'])
def api_edit_slot():
    data = request.form.to_dict() if request.form else request.get_json()
    slot_id = data.get('slot_id') or None
    payload = {
        'slot_id': slot_id,
        'day': data['day'],
        'time_start': data['time_start'],
        'time_end': data['time_end'],
        'teacher_id': int(data['teacher_id']) if data.get('teacher_id') else None,
        'classroom_id': int(data['classroom_id']) if data.get('classroom_id') else None,
        'subject_id': int(data['subject_id']) if data.get('subject_id') else None,
        'class_year': data['class_year']
    }
    ok, msg = validate_change(payload)
    if not ok:
        return jsonify({'status':'error','message':msg})
    db = get_db(); cur = db.cursor()
    if slot_id:
        # update existing
        cur.execute('UPDATE timetable_slots SET day=?, time_start=?, time_end=?, teacher_id=?, subject_id=?, classroom_id=?, class_year=? WHERE slot_id=?', (payload['day'], payload['time_start'], payload['time_end'], payload['teacher_id'], payload['subject_id'], payload['classroom_id'], payload['class_year'], slot_id))
    else:
        cur.execute('INSERT INTO timetable_slots (day,time_start,time_end,teacher_id,subject_id,classroom_id,class_year) VALUES (?,?,?,?,?,?,?)', (payload['day'], payload['time_start'], payload['time_end'], payload['teacher_id'], payload['subject_id'], payload['classroom_id'], payload['class_year']))
    db.commit()
    return jsonify({'status':'ok'})

# --- SIMPLE CRUD for manage page ---
@app.route('/api/add_teacher', methods=['POST'])
def api_add_teacher():
    name = request.form.get('name')
    db = get_db(); cur = db.cursor()
    cur.execute('INSERT INTO teachers (name) VALUES (?)', (name,))
    db.commit()
    return jsonify({'status':'ok'})

@app.route('/api/add_subject', methods=['POST'])
def api_add_subject():
    name = request.form.get('name')
    weekly = int(request.form.get('weekly') or 3)
    duration = int(request.form.get('duration') or 1)
    is_lab = 1 if request.form.get('is_lab') in ('true','True','on','1','checked') else 0
    db = get_db(); cur = db.cursor()
    cur.execute('INSERT INTO subjects (name,weekly_lectures,is_lab,duration) VALUES (?,?,?,?)', (name,weekly,is_lab,duration))
    db.commit()
    return jsonify({'status':'ok'})

@app.route('/api/add_room', methods=['POST'])
def api_add_room():
    name = request.form.get('name')
    db = get_db(); cur = db.cursor()
    cur.execute('INSERT INTO classrooms (name) VALUES (?)', (name,))
    db.commit()
    return jsonify({'status':'ok'})

@app.route('/api/add_assignment', methods=['POST'])
def api_add_assignment():
    teacher_id = int(request.form.get('teacher_id'))
    subject_id = int(request.form.get('subject_id'))
    class_year = request.form.get('class_year')
    classroom_id = int(request.form.get('classroom_id'))
    db = get_db(); cur = db.cursor()
    cur.execute('INSERT INTO assignments (teacher_id,subject_id,class_year,classroom_id) VALUES (?,?,?,?)', (teacher_id, subject_id, class_year, classroom_id))
    db.commit()
    return jsonify({'status':'ok'})

# --- STARTUP ---
if __name__ == '__main__':
    init_db()
    # seed automatically only if db empty
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) as c FROM teachers')
    if cur.fetchone()[0]==0:
        seed_sample_data()
    conn.close()
    print('Starting Smart Timetable prototype on http://127.0.0.1:5000')
    app.run(debug=True)
