document.addEventListener('DOMContentLoaded', () => {
  const generateBtn = document.getElementById('generateBtn');
  const classSelect = document.getElementById('classSelect');
  const downloadPdfBtn = document.getElementById('downloadPdfBtn');

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

  downloadPdfBtn.addEventListener('click', () => {
    const selectedClass = classSelect.value;
    if (selectedClass) {
      window.open(`/download/pdf/${selectedClass}`, '_blank');
    } else {
      alert('Please select a class to download.');
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

    let html = `
            <h2 class="text-white mb-3">${selectedClass} Timetable</h2>
            <div class="table-responsive">
                <table class="table table-dark table-striped table-bordered text-center">
                    <thead>
                        <tr>
                            <th>Time</th>
                            ${data.days.map(day => `<th>${day}</th>`).join('')}
                        </tr>
                    </thead>
                    <tbody>
                        ${data.slots.map(slotTime => {
      const timeFormatted = `${slotTime} - ${data.slots[data.slots.indexOf(slotTime) + 1] || ' '}`;
      return `
                                <tr>
                                    <td>${slotTime}</td>
                                    ${data.days.map(day => {
        const cellData = data.grid[day][slotTime];
        if (cellData) {
          return `
                                                <td class="${cellData.is_lab ? 'lab-session' : 'theory-session'}">
                                                    <strong>${cellData.subject_name}</strong><br>
                                                    <small>${cellData.teacher_name}</small><br>
                                                    <small class="text-muted">@${cellData.classroom_name}</small>
                                                </td>
                                            `;
        } else {
          return `<td></td>`;
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
  }
});