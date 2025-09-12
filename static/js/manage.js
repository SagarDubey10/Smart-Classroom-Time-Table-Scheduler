document.addEventListener('DOMContentLoaded', () => {
    // Event listeners for forms
    document.getElementById('addTeacherForm').addEventListener('submit', handleAddTeacher);
    document.getElementById('addSubjectForm').addEventListener('submit', handleAddSubject);
    document.getElementById('addClassForm').addEventListener('submit', handleAddClass);
    document.getElementById('addClassroomForm').addEventListener('submit', handleAddClassroom);
    document.getElementById('addCourseForm').addEventListener('submit', handleAddCourse);
});

async function handleAddTeacher(event) {
    event.preventDefault();
    const name = document.getElementById('teacherName').value;
    const preference = document.getElementById('teacherPref').value;
    await postData('/api/admin/add_teacher', { name, preference });
    window.location.reload();
}

async function handleAddSubject(event) {
    event.preventDefault();
    const name = document.getElementById('subjectName').value;
    const code = document.getElementById('subjectCode').value;
    await postData('/api/admin/add_subject', { name, code });
    window.location.reload();
}

async function handleAddClass(event) {
    event.preventDefault();
    const name = document.getElementById('className').value;
    await postData('/api/admin/add_class', { name });
    window.location.reload();
}

async function handleAddClassroom(event) {
    event.preventDefault();
    const name = document.getElementById('classroomName').value;
    const isLab = document.getElementById('isLab').value;
    await postData('/api/admin/add_classroom', { name, is_lab: isLab });
    window.location.reload();
}

async function handleAddCourse(event) {
    event.preventDefault();
    const class_id = document.getElementById('courseClass').value;
    const subject_id = document.getElementById('courseSubject').value;
    const teacher_id = document.getElementById('courseTeacher').value;
    const weekly_lectures = document.getElementById('weeklyLectures').value;
    const is_lab = document.getElementById('isLabCheckbox').checked ? 1 : 0;

    const res = await postData('/api/admin/add_course', {
        class_id,
        subject_id,
        teacher_id,
        weekly_lectures,
        is_lab
    });

    if (res.status === 'success') {
        alert('Course assignment added successfully!');
        window.location.reload();
    } else {
        alert('Error: ' + res.message);
    }
}

async function deleteEntity(entity, id) {
    if (confirm(`Are you sure you want to delete this ${entity} and all its related data?`)) {
        const res = await fetch(`/api/admin/delete/${entity}/${id}`, { method: 'DELETE' });
        const data = await res.json();
        alert(data.message);
        window.location.reload();
    }
}

async function postData(url, data) {
    const response = await fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(data),
    });
    return response.json();
}