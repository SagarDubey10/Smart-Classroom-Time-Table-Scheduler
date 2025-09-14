document.addEventListener('DOMContentLoaded', () => {
  const generateBtn = document.getElementById('generateBtn');
  const classSelect = document.getElementById('classSelect');
  const printBtn = document.getElementById('printBtn');

  // Modal elements
  const editSlotModal = new bootstrap.Modal(document.getElementById('editSlotModal'));
  const modalDay = document.getElementById('modalDay');
  const modalTime = document.getElementById('modalTime');
  const modalSlotId = document.getElementById('modalSlotId');
  const modalClassId = document.getElementById('modalClassId');
  const modalStartTime = document.getElementById('modalStartTime');
  const modalEndTime = document.getElementById('modalEndTime');
  const modalSubject = document.getElementById('modalSubject');
  const modalTeacher = document.getElementById('modalTeacher');
  const modalClassroom = document.getElementById('modalClassroom');
  const saveSlotBtn = document.getElementById('saveSlotBtn');
  const clearSlotBtn = document.getElementById('clearSlotBtn');
  const validationAlert = document.getElementById('validation-alert');

  // Initial render
  renderTimetable();

  // Event Listeners
  generateBtn.addEventListener('click', async () => {
    generateBtn.disabled = true;
    generateBtn.innerText = 'Generating...';
    const res = await fetch('/api/timetable/generate', { method: 'POST' });
    const data = await res.json();
    alert(data.message);
    generateBtn.disabled = false;
    generateBtn.innerText = 'Generate Timetable';
    renderTimetable();
  });

  classSelect.addEventListener('change', () => {
    renderTimetable();
  });

  printBtn.addEventListener('click', () => {
    window.print();
  });

  saveSlotBtn.addEventListener('click', async () => {
    const payload = {
      slot_id: modalSlotId.value || null,
      day: modalDay.value,
      time_start: modalStartTime.value,
      time_end: modalEndTime.value,
      class_id: modalClassId.value,
      teacher_id: modalTeacher.value,
      subject_id: modalSubject.value,
      classroom_id: modalClassroom.value
    };

    const res = await fetch('/api/timetable/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (data.status === 'success') {
      alert(data.message);
      editSlotModal.hide();
      renderTimetable();
    } else {
      validationAlert.innerText = data.message;
      validationAlert.classList.remove('d-none');
    }
  });

  clearSlotBtn.addEventListener('click', async () => {
    if (!modalSlotId.value) {
      alert('This slot is already empty.');
      return;
    }

    if (confirm('Are you sure you want to clear this slot?')) {
      const payload = {
        slot_id: modalSlotId.value,
        day: modalDay.value,
        time_start: modalStartTime.value,
        time_end: modalEndTime.value,
        class_id: modalClassId.value,
        teacher_id: null,
        subject_id: null,
        classroom_id: null
      };

      const res = await fetch('/api/timetable/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      const data = await res.json();
      if (data.status === 'success') {
        alert(data.message);
        editSlotModal.hide();
        renderTimetable();
      } else {
        alert('Error clearing slot: ' + data.message);
      }
    }
  });

  async function renderTimetable() {
    const selectedClass = classSelect.value;
    if (!selectedClass) {
      document.getElementById('timetableContainer').innerHTML = '<p class="text-white text-center">Please select a class.</p>';
      return;
    }

    const res = await fetch(`/api/timetables/${selectedClass}`);
    const data = await res.json();
    const timetableContainer = document.getElementById('timetableContainer');
    const classId = classSelect.options[classSelect.selectedIndex].dataset.id;

    let html = `
            <h2 class="text-white mb-3">Timetable for ${selectedClass}</h2>
            <div class="table-responsive">
                <table class="table table-dark table-striped table-bordered text-center timetable-table">
                    <thead>
                        <tr>
                            <th>Time</th>
                            ${data.days.map(day => `<th>${day}</th>`).join('')}
                        </tr>
                    </thead>
                    <tbody>
                        ${data.slots_full.map(slot => {
      let slotStart = slot.start_time;
      let slotEnd = slot.end_time;
      let timeFormatted = `${slotStart} - ${slotEnd}`;

      if (slot.is_break) {
        return `
                                    <tr>
                                        <td>${timeFormatted}</td>
                                        <td colspan="${data.days.length}" class="break-slot text-center">${slot.break_name}</td>
                                    </tr>
                                `;
      }

      return `
                                <tr>
                                    <td>${timeFormatted}</td>
                                    ${data.days.map(day => {
        const cellData = data.grid[day][slotStart];
        if (cellData) {
          return `
                                                <td class="${cellData.is_lab ? 'lab-session' : 'theory-session'}" 
                                                    data-day="${day}" 
                                                    data-time="${slotStart}" 
                                                    data-class-id="${classId}"
                                                    data-slot-id="${cellData.slot_id}"
                                                    data-course-id="${cellData.course_id}"
                                                    data-subject-id="${cellData.subject_id}"
                                                    data-teacher-id="${cellData.teacher_id}"
                                                    data-classroom-id="${cellData.classroom_id}"
                                                    data-bs-toggle="modal" 
                                                    data-bs-target="#editSlotModal">
                                                    <strong>${cellData.subject_name}</strong><br>
                                                    <small>${cellData.teacher_name}</small><br>
                                                    <small class="text-muted">@${cellData.classroom_name}</small>
                                                </td>
                                            `;
        } else {
          return `
                                                <td class="empty-slot" 
                                                    data-day="${day}" 
                                                    data-time="${slotStart}" 
                                                    data-class-id="${classId}"
                                                    data-bs-toggle="modal" 
                                                    data-bs-target="#editSlotModal">
                                                    Click to add
                                                </td>
                                            `;
        }
      }).join('')}
                                </tr>
                            `;
    }).join('')}
                    </tbody>
                </table>
            </div>
        `;
    timetableContainer.innerHTML = html;

    document.querySelectorAll('.timetable-table td').forEach(cell => {
      cell.addEventListener('click', (e) => {
        const day = e.target.dataset.day;
        const time = e.target.dataset.time;
        if (!day || !time) return;

        const slotId = e.target.dataset.slotId || '';
        const subjectId = e.target.dataset.subjectId || '';
        const teacherId = e.target.dataset.teacherId || '';
        const classroomId = e.target.dataset.classroomId || '';
        const classId = e.target.dataset.classId;

        modalDay.value = day;
        modalTime.value = time;
        modalSlotId.value = slotId;
        modalClassId.value = classId;
        modalStartTime.value = time;

        const fullSlot = data.slots_full.find(s => s.start_time === time);
        modalEndTime.value = fullSlot ? fullSlot.end_time : '';

        populateSelect(modalSubject, data.options.subjects, 'subject_id', 'name', subjectId);
        populateSelect(modalTeacher, data.options.teachers, 'teacher_id', 'name', teacherId);
        populateSelect(modalClassroom, data.options.classrooms, 'classroom_id', 'name', classroomId);

        validationAlert.classList.add('d-none');
        editSlotModal.show();
      });
    });
  }

  function populateSelect(selectElement, items, valueKey, textKey, selectedValue) {
    selectElement.innerHTML = '<option value="">-- Select --</option>';
    items.forEach(item => {
      const option = document.createElement('option');
      option.value = item[valueKey];
      option.textContent = item[textKey];
      if (String(item[valueKey]) === String(selectedValue)) {
        option.selected = true;
      }
      selectElement.appendChild(option);
    });
  }
});