document.addEventListener('DOMContentLoaded', () => {
    // Event listeners for forms
    document.getElementById('addTeacherForm').addEventListener('submit', handleAddTeacher);
    document.getElementById('addSubjectForm').addEventListener('submit', handleAddSubject);
    document.getElementById('addClassForm').addEventListener('submit', handleAddClass);
    document.getElementById('addClassroomForm').addEventListener('submit', handleAddClassroom);
    document.getElementById('addCourseForm').addEventListener('submit', handleAddCourse);

    // Schedule Config form event listeners
    const scheduleConfigForm = document.getElementById('scheduleConfigForm');
    const slotInputsContainer = document.getElementById('slotInputs');
    const addSlotBtn = document.getElementById('addSlotBtn');

    addSlotBtn.addEventListener('click', () => addSlotInput());
    scheduleConfigForm.addEventListener('submit', handleScheduleConfig);

    fetchScheduleConfig();
});

async function fetchScheduleConfig() {
    const res = await fetch('/api/admin/schedule_config');
    const data = await res.json();
    if (data.status === 'success' && data.config.length > 0) {
        renderScheduleConfigForm(data.config);
    } else {
        addSlotInput();
    }
}

function renderScheduleConfigForm(config) {
    const slotInputsContainer = document.getElementById('slotInputs');
    slotInputsContainer.innerHTML = '';

    config.forEach(slot => {
        addSlotInput(slot);
    });
}

function addSlotInput(slot = { start_time: '', end_time: '', is_break: 0, break_name: '' }) {
    const slotInputsContainer = document.getElementById('slotInputs');
    const div = document.createElement('div');
    div.className = 'input-group mb-2';
    // Use type="time" for native browser time picker
    div.innerHTML = `
        <input type="time" class="form-control" placeholder="Start Time" value="${slot.start_time || ''}" required>
        <input type="time" class="form-control" placeholder="End Time" value="${slot.end_time || ''}" required>
        <select class="form-control is-break-select">
            <option value="0" ${!slot.is_break ? 'selected' : ''}>Lecture</option>
            <option value="1" ${slot.is_break ? 'selected' : ''}>Break</option>
        </select>
        <input type="text" class="form-control break-name-input" placeholder="Break Name (optional)" value="${slot.break_name || ''}" ${!slot.is_break ? 'disabled' : ''}>
        <button type="button" class="btn btn-danger remove-slot">X</button>
    `;
    div.querySelector('.remove-slot').onclick = () => div.remove();
    div.querySelector('.is-break-select').onchange = (e) => {
        const breakNameInput = div.querySelector('.break-name-input');
        breakNameInput.disabled = e.target.value === '0';
        if (e.target.value === '0') breakNameInput.value = '';
    };
    slotInputsContainer.appendChild(div);
}

// Function to convert HH:MM to HH:MM AM/PM
function formatTimeFromInput(time24) {
    if (!time24) return '';
    const [hours, minutes] = time24.split(':');
    let h = parseInt(hours);
    let ampm = h >= 12 ? 'PM' : 'AM';
    h = h % 12;
    h = h ? h : 12; // the hour '0' should be '12'
    let m = minutes < 10 ? '0' + minutes : minutes;
    return `${h}:${m} ${ampm}`;
}


async function handleScheduleConfig(event) {
    event.preventDefault();
    const slotInputs = document.querySelectorAll('#slotInputs .input-group');
    const slots = [];
    slotInputs.forEach(group => {
        const inputs = group.querySelectorAll('input, select');
        const isBreak = inputs[2].value === '1';
        slots.push({
            start: formatTimeFromInput(inputs[0].value),
            end: formatTimeFromInput(inputs[1].value),
            is_break: isBreak,
            name: isBreak ? inputs[3].value : null
        });
    });

    const payload = {
        slots: slots
    };

    const res = await postData('/api/admin/schedule_config', payload);
    if (res.status === 'success') {
        alert(res.message);
        window.location.reload();
    } else {
        alert('Error: ' + res.message);
    }
}

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