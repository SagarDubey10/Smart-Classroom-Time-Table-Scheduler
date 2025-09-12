let optionsData = {};

async function fetchOptions() {
  let res = await fetch('/api/options');
  optionsData = await res.json();
}

async function seedData() {
  await fetch('/api/seed', { method: 'POST' });
  alert('Sample data seeded!');
  await fetchOptions();
  loadTimetable();
}

async function generateTT() {
  await fetch('/api/generate', { method: 'POST' });
  alert('Timetable generated!');
  loadTimetable();
}

async function loadTimetable() {
  let res = await fetch('/api/timetables');
  let data = await res.json();
  let container = document.getElementById('timetable-container');
  container.innerHTML = '';
  data.years.forEach(y => {
    let html = '<h2>' + y.year + '</h2><table><tr><th>Time</th>';
    Object.keys(y.grid).forEach(day => html += '<th>' + day + '</th>'); html += '</tr>';
    y.times.forEach(time => {
      html += '<tr><td>' + time + '</td>';
      Object.keys(y.grid).forEach(day => {
        let cell = y.grid[day][time];
        if (cell) html += '<td onclick="editSlot(' + cell.slot_id + ',\'' + day + '\',\'' + time + '\',\'' + y.year + '\')">' + cell.subject_name + '<br>' + cell.teacher_name + '</td>';
        else html += '<td onclick="addSlot(\'' + day + '\',\'' + time + '\',\'' + y.year + '\')"></td>';
      });
      html += '</tr>';
    });
    html += '</table>'; container.innerHTML += html;
  });
}

// --- Modal ---
function openModal() {
  document.getElementById('editModal').style.display = 'block';
}
function closeModal() {
  document.getElementById('editModal').style.display = 'none';
}

function populateSelect(id, data, selected) {
  let sel = document.getElementById(id); sel.innerHTML = '';
  data.forEach(d => {
    let opt = document.createElement('option');
    opt.value = d[id.replace('_id', '_id')];
    opt.text = d.name;
    if (selected && selected == d[id.replace('_id', '_id')]) opt.selected = true;
    sel.appendChild(opt);
  });
}

function editSlot(slot_id, day, time, class_year) {
  openModal();
  document.getElementById('slot_id').value = slot_id;
  populateSelect('teacher_id', optionsData.teachers);
  populateSelect('subject_id', optionsData.subjects);
  populateSelect('classroom_id', optionsData.classrooms);
}

function addSlot(day, time, class_year) {
  openModal();
  document.getElementById('slot_id').value = '';
  populateSelect('teacher_id', optionsData.teachers);
  populateSelect('subject_id', optionsData.subjects);
  populateSelect('classroom_id', optionsData.classrooms);
}

// --- Save form ---
document.getElementById('editForm').onsubmit = async function (e) {
  e.preventDefault();
  let data = {
    slot_id: document.getElementById('slot_id').value || null,
    teacher_id: document.getElementById('teacher_id').value,
    subject_id: document.getElementById('subject_id').value,
    classroom_id: document.getElementById('classroom_id').value,
    day: 'MON', // placeholder, can enhance later
    time_start: '09:00', time_end: '10:00', class_year: 'TE-B1'
  };
  let res = await fetch('/api/edit_slot', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  });
  let resp = await res.json();
  alert(resp.status == 'ok' ? 'Saved!' : resp.message);
  closeModal(); loadTimetable();
}

// --- PDF export ---
function exportPDF() {
  const { jsPDF } = window.jspdf;
  let doc = new jsPDF();
  let tables = document.querySelectorAll('table');
  let y = 10;
  tables.forEach(t => {
    doc.text(t.previousElementSibling.innerText, 10, y); y += 6;
    let rows = t.querySelectorAll('tr');
    rows.forEach(r => {
      let rowData = [];
      r.querySelectorAll('th,td').forEach(c => rowData.push(c.innerText));
      doc.text(rowData.join(' | '), 10, y); y += 6;
    });
    y += 10;
  });
  doc.save('timetable.pdf');
}

window.onload = async function () {
  await fetchOptions();
  loadTimetable();
};
