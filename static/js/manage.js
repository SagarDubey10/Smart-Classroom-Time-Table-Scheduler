document.addEventListener('DOMContentLoaded', () => {
  const generateBtn = document.getElementById('generateBtn');
  const classSelect = document.getElementById('classSelect');
  const printBtn = document.getElementById('printBtn');
  const addSlotBtn = document.getElementById('addSlotBtn');
  const slotInputsContainer = document.getElementById('slotInputs');

  function addSlotRow(slot = {}) {
    const newRow = document.createElement('div');
    newRow.classList.add('input-group', 'mb-2');
    newRow.innerHTML = `
            <input type="hidden" name="config_id" value="${slot.config_id || ''}">
            <input type="time" class="form-control" name="start_time" value="${slot.start_time || ''}" required>
            <input type="time" class="form-control" name="end_time" value="${slot.end_time || ''}" required>
            <select class="form-control" name="is_break">
                <option value="0" ${slot.is_break === 0 ? 'selected' : ''}>Lecture</option>
                <option value="1" ${slot.is_break === 1 ? 'selected' : ''}>Break</option>
            </select>
            <input type="text" class="form-control break-name-input" name="break_name" placeholder="Break Name (optional)" value="${slot.break_name || ''}" ${slot.is_break === 0 ? 'disabled' : ''}>
            <button type="button" class="btn btn-danger remove-slot">X</button>
        `;

    slotInputsContainer.appendChild(newRow);

    const removeButton = newRow.querySelector('.remove-slot');
    removeButton.addEventListener('click', (e) => {
      e.target.closest('.input-group').remove();
    });

    const isBreakSelect = newRow.querySelector('[name="is_break"]');
    const breakNameInput = newRow.querySelector('[name="break_name"]');
    isBreakSelect.addEventListener('change', () => {
      if (isBreakSelect.value === '1') {
        breakNameInput.disabled = false;
      } else {
        breakNameInput.disabled = true;
        breakNameInput.value = '';
      }
    });
  }

  // Attach event listeners to initial elements rendered by Flask
  document.querySelectorAll('.remove-slot').forEach(button => {
    button.addEventListener('click', (e) => {
      e.target.closest('.input-group').remove();
    });
  });

  document.querySelectorAll('[name="is_break"]').forEach(select => {
    const breakNameInput = select.closest('.input-group').querySelector('[name="break_name"]');
    select.addEventListener('change', () => {
      if (select.value === '1') {
        breakNameInput.disabled = false;
      } else {
        breakNameInput.disabled = true;
        breakNameInput.value = '';
      }
    });
  });

  addSlotBtn.addEventListener('click', () => {
    addSlotRow();
  });


  // Modal elements
  const editSlotModal = new bootstrap.Modal(document.getElementById('editSlotModal'));
  const modalTitle = document.getElementById('editSlotModalLabel');
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
  const deleteSlotBtn = document.getElementById('deleteSlotBtn');
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

  printBtn.addEventListener('click', async () => {
    const selectedClass = classSelect.value;
    if (!selectedClass) {
      alert("Please select a class to print.");
      return;
    }

    const res = await fetch(`/api/timetables/${selectedClass}`);
    const data = await res.json();

    let printWindow = window.open('', '_blank');
    let printContent = `
            <html>
            <head>
                <title>Timetable for ${selectedClass}</title>
                <style>
                    body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 1cm; }
                    .timetable-table { width: 100%; border-collapse: collapse; }
                    .timetable-table th, .timetable-table td { border: 1px solid #000; padding: 5px; text-align: center; font-size: 8pt; }
                    .timetable-table th { background-color: #e9ecef; }
                    .break-slot { background-color: #d1d1d1; font-weight: bold; }
                    .empty-slot::before { content: ""; }
                    .timetable-table, .timetable-table th, .timetable-table td { background-color: #fff !important; color: #000 !important; }
                    @page { size: A4 landscape; margin: 1cm; }
                </style>
            </head>
            <body>
                <h1 style="text-align: center;">Timetable for ${selectedClass}</h1>
                <table class="timetable-table">
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
        return `<tr>
                                            <td>${timeFormatted}</td>
                                            <td colspan="${data.days.length}" class="break-slot">${slot.break_name}</td>
                                        </tr>`;
      }
      return `<tr>
                                        <td>${timeFormatted}</td>
                                        ${data.days.map(day => {
        const cellData = data.grid[day][slotStart];
        if (cellData) {
          return `<td style="background-color: #fff !important; color: #000 !important;">
                                                            <strong>${cellData.subject_name}</strong><br>
                                                            <small>${cellData.teacher_name}</small><br>
                                                            <small>@${cellData.classroom_name}</small>
                                                        </td>`;
        } else {
          return `<td style="background-color: #fff !important; color: #000 !important;" class="empty-slot"></td>`;
        }
      }).join('')}
                                    </tr>`;
    }).join('')}
                    </tbody>
                </table>
            </body>
            </html>
        `;

    printWindow.document.write(printContent);
    printWindow.document.close();
    printWindow.focus();
    printWindow.print();
    printWindow.close();
  });

  // Save/Add slot changes
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

  // Delete slot
  deleteSlotBtn.addEventListener('click', async () => {
    const slotId = modalSlotId.value;
    if (!slotId) {
      alert("This is an empty slot and cannot be deleted.");
      return;
    }

    if (confirm('Are you sure you want to delete this slot?')) {
      const res = await fetch('/api/timetable/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ slot_id: slotId })
      });
      const data = await res.json();
      if (data.status === 'success') {
        alert(data.message);
        editSlotModal.hide();
        renderTimetable();
      } else {
        alert('Error deleting slot: ' + data.message);
      }
    }
  });

  async function renderTimetable() {
    const selectedClass = classSelect.value;
    if (!selectedClass) {
      document.getElementById('timetableContainer').innerHTML = '<p class="text-center">Please select a class.</p>';
      return;
    }

    const res = await fetch(`/api/timetables/${selectedClass}`);
    const data = await res.json();
    const timetableContainer = document.getElementById('timetableContainer');
    const classId = classSelect.options[classSelect.selectedIndex].dataset.id;

    let html = `
            <h2 class="mb-3">Timetable for ${selectedClass}</h2>
            <div class="table-responsive">
                <table class="table table-bordered text-center timetable-table">
                    <thead>
                        <tr>
                            <th>Time</th>
                            ${data.days.map(day => `<th>${day}</th>`).join('')}
                        </tr>
                    </thead>
                    <tbody>
                        ${data.slots_full.map(slot => {
      let timeFormatted = `${slot.start_time} - ${slot.end_time}`;
      if (slot.is_break) {
        return `<tr>
                                            <td>${timeFormatted}</td>
                                            <td colspan="${data.days.length}" class="break-slot">${slot.break_name}</td>
                                        </tr>`;
      }
      return `<tr>
                                        <td>${timeFormatted}</td>
                                        ${data.days.map(day => {
        const cellData = data.grid[day][slot.start_time];
        if (cellData) {
          return `<td class="${cellData.is_lab ? 'lab-session' : 'theory-session'}"
                                                            data-day="${day}"
                                                            data-time="${slot.start_time}"
                                                            data-class-id="${classId}"
                                                            data-slot-id="${cellData.slot_id}"
                                                            data-subject-id="${cellData.subject_id}"
                                                            data-teacher-id="${cellData.teacher_id}"
                                                            data-classroom-id="${cellData.classroom_id}"
                                                            data-bs-toggle="modal"
                                                            data-bs-target="#editSlotModal">
                                                            <strong>${cellData.subject_name}</strong><br>
                                                            <small>${cellData.teacher_name}</small><br>
                                                            <small class="text-muted">@${cellData.classroom_name}</small>
                                                        </td>`;
        } else {
          return `<td class="empty-slot"
                                                            data-day="${day}"
                                                            data-time="${slot.start_time}"
                                                            data-class-id="${classId}"
                                                            data-bs-toggle="modal"
                                                            data-bs-target="#editSlotModal">
                                                            Click to add
                                                        </td>`;
        }
      }).join('')}
                                    </tr>`;
    }).join('')}
                    </tbody>
                </table>
            </div>
        `;
    timetableContainer.innerHTML = html;

    // Modal pop-up for editing/adding slots
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

        // Set modal title and show/hide delete button
        if (slotId) {
          modalTitle.innerText = 'Edit Slot';
          deleteSlotBtn.style.display = 'inline-block';
        } else {
          modalTitle.innerText = 'Add New Slot';
          deleteSlotBtn.style.display = 'none';
        }

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