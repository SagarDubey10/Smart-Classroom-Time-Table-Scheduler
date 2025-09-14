document.addEventListener('DOMContentLoaded', () => {
    // Event listeners for form submissions on the schedule configuration form
    const scheduleConfigForm = document.getElementById('scheduleConfigForm');
    const addSlotBtn = document.getElementById('addSlotBtn');

    // Add slot button listener
    if (addSlotBtn) {
        addSlotBtn.addEventListener('click', addSlotInput);
    }

    // Set up the listeners for initial slots
    linkNewSlotToPrevious();

    // Helper function to handle time auto-population
    function handleTimeChange(event) {
        const currentInputGroup = event.target.closest('.input-group');
        const nextInputGroup = currentInputGroup.nextElementSibling;
        if (nextInputGroup) {
            const nextStartTimeInput = nextInputGroup.querySelector('.start-time-input');
            if (nextStartTimeInput) {
                nextStartTimeInput.value = event.target.value;
            }
        }
    }

    // Function to add a new time slot row
    function addSlotInput(slot = { start_time: '', end_time: '', is_break: 0, break_name: '' }) {
        const slotInputsContainer = document.getElementById('slotInputs');
        const div = document.createElement('div');
        div.className = 'input-group mb-2';

        const start24h = convert12to24(slot.start_time);
        const end24h = convert12to24(slot.end_time);

        div.innerHTML = `
            <input type="time" class="form-control start-time-input" value="${start24h || ''}" name="start_time" required>
            <input type="time" class="form-control end-time-input" value="${end24h || ''}" name="end_time" required>
            <select class="form-control" name="is_break">
                <option value="0" ${!slot.is_break ? 'selected' : ''}>Lecture</option>
                <option value="1" ${slot.is_break ? 'selected' : ''}>Break</option>
            </select>
            <input type="text" class="form-control break-name-input" placeholder="Break Name (optional)" value="${slot.break_name || ''}" ${!slot.is_break ? 'disabled' : ''} name="break_name">
            <button type="button" class="btn btn-danger remove-slot">X</button>
        `;

        div.querySelector('.remove-slot').onclick = () => {
            div.remove();
            linkNewSlotToPrevious();
        };

        div.querySelector('select[name="is_break"]').onchange = (e) => {
            const breakNameInput = div.querySelector('input[name="break_name"]');
            breakNameInput.disabled = e.target.value === '0';
            if (e.target.value === '0') breakNameInput.value = '';
        };

        slotInputsContainer.appendChild(div);
        linkNewSlotToPrevious();
    }

    // The link functionality is now a separate function for better organization
    function linkNewSlotToPrevious() {
        const slotInputs = document.querySelectorAll('#slotInputs .input-group');
        if (slotInputs.length > 1) {
            const lastSlot = slotInputs[slotInputs.length - 2];
            const newSlot = slotInputs[slotInputs.length - 1];

            const lastEndTimeInput = lastSlot.querySelector('.end-time-input');
            const newStartTimeInput = newSlot.querySelector('.start-time-input');

            if (lastEndTimeInput && newStartTimeInput) {
                lastEndTimeInput.removeEventListener('change', handleTimeChange);
                lastEndTimeInput.addEventListener('change', (e) => {
                    newStartTimeInput.value = e.target.value;
                });
            }
        }
    }

    // Helper functions for time conversion
    function convert12to24(time12) {
        if (!time12) return '';
        const [time, ampm] = time12.split(' ');
        if (!ampm) return time;
        let [hours, minutes] = time.split(':');
        if (ampm.toUpperCase() === 'PM' && hours !== '12') {
            hours = parseInt(hours) + 12;
        }
        if (ampm.toUpperCase() === 'AM' && hours === '12') {
            hours = '00';
        }
        return `${hours}:${minutes}`;
    }

    function formatTimeFromInput(time24) {
        if (!time24) return '';
        const [hours, minutes] = time24.split(':');
        let h = parseInt(hours);
        let ampm = h >= 12 ? 'PM' : 'AM';
        h = h % 12;
        h = h ? h : 12;
        let m = minutes.padStart(2, '0');
        return `${h}:${m} ${ampm}`;
    }

});