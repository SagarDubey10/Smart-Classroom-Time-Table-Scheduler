# admin_routes.py
from flask import Blueprint, request, jsonify, g
import sqlite3
# Assuming you have the helper functions imported or defined here as well
# For simplicity, we'll assume the helper functions are in app.py

admin_bp = Blueprint('admin_bp', __name__, url_prefix='/api/admin')

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = sqlite3.connect('timetable.db')
        db.row_factory = sqlite3.Row
        g._database = db
    return db

@admin_bp.route('/add_teacher', methods=['POST'])
def add_teacher():
    data = request.json
    db = get_db()
    try:
        db.execute('INSERT INTO teachers (name) VALUES (?)', (data['name'],))
        if 'preference' in data and data['preference']:
            db.execute('INSERT OR IGNORE INTO teacher_preferences (teacher_id, preference) VALUES ((SELECT teacher_id FROM teachers WHERE name = ?), ?)', (data['name'], data['preference']))
        db.commit()
        return jsonify({'status': 'success', 'message': 'Teacher added successfully!'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@admin_bp.route('/add_subject', methods=['POST'])
def add_subject():
    data = request.json
    db = get_db()
    try:
        db.execute('INSERT INTO subjects (name, code) VALUES (?, ?)', (data['name'], data['code']))
        db.commit()
        return jsonify({'status': 'success', 'message': 'Subject added successfully!'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@admin_bp.route('/add_class', methods=['POST'])
def add_class():
    data = request.json
    db = get_db()
    try:
        db.execute('INSERT INTO classes (name) VALUES (?)', (data['name'],))
        db.commit()
        return jsonify({'status': 'success', 'message': 'Class added successfully!'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@admin_bp.route('/add_classroom', methods=['POST'])
def add_classroom():
    data = request.json
    db = get_db()
    try:
        db.execute('INSERT INTO classrooms (name, is_lab) VALUES (?, ?)', (data['name'], data['is_lab']))
        db.commit()
        return jsonify({'status': 'success', 'message': 'Classroom added successfully!'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@admin_bp.route('/add_course', methods=['POST'])
def add_course():
    data = request.json
    db = get_db()
    try:
        db.execute('INSERT INTO courses (class_id, subject_id, teacher_id, weekly_lectures, is_lab) VALUES (?, ?, ?, ?, ?)',
                   (data['class_id'], data['subject_id'], data['teacher_id'], data['weekly_lectures'], data['is_lab']))
        db.commit()
        return jsonify({'status': 'success', 'message': 'Course assignment added successfully!'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# The delete route stays the same
@admin_bp.route('/delete/<entity>/<id>', methods=['DELETE'])
def delete_entity(entity, id):
    db = get_db()
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