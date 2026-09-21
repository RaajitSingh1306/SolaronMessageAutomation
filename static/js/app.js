/**
 * app.js — Solaron Multi-Platform Solar Reporting & Messaging Frontend Logic
 *
 * Supports:
 *   - Multi-source data fetching (Growatt, iSolarCloud, SuryaLog)
 *   - Live Real-Time Polling & Adaptive Granularity (Daily / Weekly / Monthly / Yearly)
 *   - Dated History Presets & Plant Analytics Graph Modal
 *   - Summary stats & fleet breakdown
 *   - Platform badges & filtering
 *   - CSV report export
 *   - WhatsApp automated messaging
 */

'use strict';

// ── Calendar Month Constants ───────────────────────────────────────────────
const CAL_MONTH_NAMES = [
    { num: '01', short: 'Jan', full: 'January' },
    { num: '02', short: 'Feb', full: 'February' },
    { num: '03', short: 'Mar', full: 'March' },
    { num: '04', short: 'Apr', full: 'April' },
    { num: '05', short: 'May', full: 'May' },
    { num: '06', short: 'Jun', full: 'June' },
    { num: '07', short: 'Jul', full: 'July' },
    { num: '08', short: 'Aug', full: 'August' },
    { num: '09', short: 'Sep', full: 'September' },
    { num: '10', short: 'Oct', full: 'October' },
    { num: '11', short: 'Nov', full: 'November' },
    { num: '12', short: 'Dec', full: 'December' },
];

function _hideSpinner() {
    renderTable();
}

// ── Theme Management ───────────────────────────────────────────────────────
function initTheme() {
    const savedTheme = localStorage.getItem('theme') || 'dark';
    document.documentElement.setAttribute('data-theme', savedTheme);
    const icon = document.getElementById('themeIcon');
    if (icon) {
        icon.textContent = savedTheme === 'light' ? '☀️' : '🌒';
    }
}

function toggleTheme() {
    const html = document.documentElement;
    const current = html.getAttribute('data-theme');
    const target = current === 'light' ? 'dark' : 'light';
    html.setAttribute('data-theme', target);
    localStorage.setItem('theme', target);
    
    const icon = document.getElementById('themeIcon');
    if (icon) {
        icon.textContent = target === 'light' ? '☀️' : '🌒';
    }
}

// Initialize theme immediately
initTheme();

// ── State ──────────────────────────────────────────────────────────────────

let currentData = {
    plants: {},   // { "Active": [...], "Offline": [...], "Not Commissioned": [...] }
    counts: {},   // { "Active": 256, ... }
};

let currentSummary = null;
let currentView = 'monthly'; // 'daily' | 'weekly' | 'monthly' | 'yearly'
let currentSortKey = 'energy'; // 'name' | 'capacity' | 'energy' | 'savings' | 'power'
let currentSortOrder = 'desc'; // 'asc' | 'desc'
let selectedDateStr = '';
let selectedYearStr = '2026';
let lastUpdatedTimestamp = Date.now();

// Expose state on window for runtime inspection and testing
window.currentData = currentData;
Object.defineProperty(window, 'currentView', {
    get: () => currentView,
    set: (v) => { currentView = v; },
    configurable: true
});
Object.defineProperty(window, 'currentSortKey', {
    get: () => currentSortKey,
    set: (v) => { currentSortKey = v; },
    configurable: true
});
Object.defineProperty(window, 'currentSortOrder', {
    get: () => currentSortOrder,
    set: (v) => { currentSortOrder = v; },
    configurable: true
});

// Live Auto-Sync Configuration
let isLiveSyncActive = true;
let liveSyncTimer = null;
let liveSyncSecondsRemaining = 60;

let config = {
    price_per_unit: 14.0,
    month_name: '',
    year: '',
    test_phone_number: '',
    support_phone: '',
};

// Track which plants were sent in this session
const sentInSession = new Set();


// ── Adaptive Date & History Picker ────────────────────────────────────────

function initCalendarPicker() {
    const reportMonthInput = document.getElementById('reportMonth');
    const reportDateInput = document.getElementById('reportDate');
    const reportYearSelect = document.getElementById('reportYearSelect');
    
    const now = new Date();
    const curYear = now.getFullYear();
    const curMonthNum = String(now.getMonth() + 1).padStart(2, '0');
    const curDayNum = String(now.getDate()).padStart(2, '0');
    
    selectedDateStr = `${curYear}-${curMonthNum}-${curDayNum}`;
    selectedYearStr = String(curYear);
    
    if (reportMonthInput && !reportMonthInput.value) {
        reportMonthInput.value = `${curYear}-${curMonthNum}`;
        config.year = String(curYear);
        const mObj = CAL_MONTH_NAMES.find(m => m.num === curMonthNum);
        if (mObj) config.month_name = mObj.full;
    }
    
    if (reportDateInput && !reportDateInput.value) {
        reportDateInput.value = selectedDateStr;
    }
    
    if (reportYearSelect) {
        reportYearSelect.value = selectedYearStr;
    }
}

function onMonthPicked(val) {
    if (!val) return;
    const parts = val.split('-');
    if (parts.length === 2) {
        const y = parts[0];
        const m = parts[1];
        config.year = y;
        selectedYearStr = y;
        const mObj = CAL_MONTH_NAMES.find(x => x.num === m);
        if (mObj) config.month_name = mObj.full;
        
        updateStats();
        renderTable();
        highlightActivePreset();
    }
}

function onDatePicked(val) {
    if (!val) return;
    selectedDateStr = val;
    const parts = val.split('-');
    if (parts.length === 3) {
        config.year = parts[0];
        const mObj = CAL_MONTH_NAMES.find(x => x.num === parts[1]);
        if (mObj) config.month_name = mObj.full;
    }
    updateStats();
    renderTable();
    highlightActivePreset();
}

function onYearPicked(val) {
    if (!val) return;
    selectedYearStr = String(val);
    config.year = String(val);
    updateStats();
    renderTable();
    highlightActivePreset();
}

function setPreset(presetKey) {
    const now = new Date();
    const curYear = now.getFullYear();
    const curMonthNum = String(now.getMonth() + 1).padStart(2, '0');
    const curDayNum = String(now.getDate()).padStart(2, '0');
    
    const reportMonthInput = document.getElementById('reportMonth');
    const reportDateInput = document.getElementById('reportDate');
    const reportYearSelect = document.getElementById('reportYearSelect');

    // Remove active state from all preset buttons
    document.querySelectorAll('.btn-preset').forEach(b => b.classList.remove('active'));

    if (presetKey === 'today') {
        selectedDateStr = `${curYear}-${curMonthNum}-${curDayNum}`;
        if (reportDateInput) reportDateInput.value = selectedDateStr;
        switchView('daily');
    } else if (presetKey === 'yesterday') {
        const yday = new Date(now);
        yday.setDate(now.getDate() - 1);
        const yYear = yday.getFullYear();
        const yMonth = String(yday.getMonth() + 1).padStart(2, '0');
        const yDay = String(yday.getDate()).padStart(2, '0');
        selectedDateStr = `${yYear}-${yMonth}-${yDay}`;
        if (reportDateInput) reportDateInput.value = selectedDateStr;
        switchView('daily');
    } else if (presetKey === 'this_week') {
        switchView('weekly');
    } else if (presetKey === 'this_month') {
        if (reportMonthInput) {
            reportMonthInput.value = `${curYear}-${curMonthNum}`;
            onMonthPicked(reportMonthInput.value);
        }
        switchView('monthly');
    } else if (presetKey === 'prev_month') {
        const prev = new Date(now.getFullYear(), now.getMonth() - 1, 1);
        const pYear = prev.getFullYear();
        const pMonth = String(prev.getMonth() + 1).padStart(2, '0');
        if (reportMonthInput) {
            reportMonthInput.value = `${pYear}-${pMonth}`;
            onMonthPicked(reportMonthInput.value);
        }
        switchView('monthly');
    } else if (presetKey === 'year_2026') {
        if (reportYearSelect) reportYearSelect.value = '2026';
        onYearPicked('2026');
        switchView('yearly');
    } else if (presetKey === 'year_2025') {
        if (reportYearSelect) reportYearSelect.value = '2025';
        onYearPicked('2025');
        switchView('yearly');
    }
    
    highlightActivePreset();
}

function highlightActivePreset() {
    const now = new Date();
    const curYear = String(now.getFullYear());
    const curMonthNum = String(now.getMonth() + 1).padStart(2, '0');
    const curMonthVal = `${curYear}-${curMonthNum}`;
    const curDayNum = String(now.getDate()).padStart(2, '0');
    const todayVal = `${curYear}-${curMonthNum}-${curDayNum}`;

    const reportMonthInput = document.getElementById('reportMonth');
    const reportDateInput = document.getElementById('reportDate');

    document.querySelectorAll('.btn-preset').forEach(b => b.classList.remove('active'));

    let activeKey = null;
    if (currentView === 'daily') {
        if (reportDateInput && reportDateInput.value === todayVal) {
            activeKey = 'today';
        }
    } else if (currentView === 'weekly') {
        activeKey = 'this_week';
    } else if (currentView === 'monthly') {
        if (reportMonthInput && reportMonthInput.value === curMonthVal) {
            activeKey = 'this_month';
        }
    } else if (currentView === 'yearly') {
        if (selectedYearStr === '2026') activeKey = 'year_2026';
        else if (selectedYearStr === '2025') activeKey = 'year_2025';
    }

    if (activeKey) {
        const btn = document.querySelector(`.btn-preset[onclick*="'${activeKey}'"]`);
        if (btn) btn.classList.add('active');
    }
}

function syncCalendarPickerState(yearStr, monthNameStr) {
    const reportMonthInput = document.getElementById('reportMonth');
    if (!reportMonthInput) return;
    
    let mNum = "01";
    if (monthNameStr) {
        const found = CAL_MONTH_NAMES.find(m =>
            m.full.toLowerCase() === monthNameStr.toLowerCase() ||
            m.short.toLowerCase() === monthNameStr.toLowerCase()
        );
        if (found) mNum = found.num;
    }
    
    const y = parseInt(yearStr, 10);
    if (!isNaN(y)) {
        reportMonthInput.value = `${y}-${mNum}`;
    }
}


// ── Real-Time Live Auto-Sync Engine ───────────────────────────────────────

function startLiveSyncTimer() {
    if (liveSyncTimer) clearInterval(liveSyncTimer);
    liveSyncSecondsRemaining = 60;
    
    liveSyncTimer = setInterval(() => {
        if (!isLiveSyncActive) return;
        
        liveSyncSecondsRemaining--;
        const txt = document.getElementById('liveSyncText');
        if (txt) {
            txt.textContent = `Live (${liveSyncSecondsRemaining}s)`;
        }
        
        if (liveSyncSecondsRemaining <= 0) {
            liveSyncSecondsRemaining = 60;
            refreshLiveData(true); // Silent background refresh
        }
        
        updateLastUpdatedLabel();
    }, 1000);
}

function toggleLiveSync() {
    isLiveSyncActive = !isLiveSyncActive;
    const btn = document.getElementById('liveSyncBtn');
    const txt = document.getElementById('liveSyncText');
    const pulse = document.getElementById('livePulseTag');
    
    if (isLiveSyncActive) {
        if (btn) btn.classList.add('active');
        if (txt) txt.textContent = `Live (${liveSyncSecondsRemaining}s)`;
        if (pulse) pulse.style.display = 'inline-flex';
        startLiveSyncTimer();
    } else {
        if (btn) btn.classList.remove('active');
        if (txt) txt.textContent = `Paused`;
        if (pulse) pulse.style.display = 'none';
        if (liveSyncTimer) clearInterval(liveSyncTimer);
    }
}

async function refreshLiveData(silent = false) {
    const btn = document.getElementById('quickRefreshBtn');
    if (btn && !silent) {
        btn.disabled = true;
        btn.textContent = '⏳ Refreshing...';
    }
    
    try {
        const res = await fetch('/api/plants', { headers: _getHeaders() });
        const result = await res.json();
        if (result.data && Object.keys(result.data).length > 0) {
            _applyResult(result);
            lastUpdatedTimestamp = Date.now();
            updateLastUpdatedLabel();
        }
        _fetchSummary();
        _fetchDiagnostics();
    } catch (e) {
        console.warn('Live refresh note:', e);
    } finally {
        if (btn && !silent) {
            btn.disabled = false;
            btn.textContent = '🔄 Live Refresh';
        }
    }
}

function updateLastUpdatedLabel() {
    const lbl = document.getElementById('lastUpdatedBadge');
    if (!lbl) return;
    const elapsedSecs = Math.floor((Date.now() - lastUpdatedTimestamp) / 1000);
    if (elapsedSecs < 10) {
        lbl.textContent = 'Updated: Just now';
    } else if (elapsedSecs < 60) {
        lbl.textContent = `Updated: ${elapsedSecs}s ago`;
    } else {
        const mins = Math.floor(elapsedSecs / 60);
        lbl.textContent = `Updated: ${mins}m ago`;
    }
}


// ── Bootstrap ──────────────────────────────────────────────────────────────

window.addEventListener('load', async () => {
    initCalendarPicker();
    startLiveSyncTimer();

    // Try restoring or auto-hydrating state from server
    try {
        const res = await fetch('/api/plants', { headers: _getHeaders() });
        const result = await res.json();
        if (result.data && Object.keys(result.data).length > 0) {
            _applyResult(result);
        }
    } catch (e) {
        console.warn('Could not restore previous session data:', e);
    }

    // Also fetch summary and live diagnostics
    _fetchSummary();
    _fetchDiagnostics();
});


// ── Multi-Source Fetch ─────────────────────────────────────────────────────

function getSelectedSources() {
    const sources = [];
    if (document.getElementById('srcGrowatt')?.checked) sources.push('growatt');
    if (document.getElementById('srcIsolarcloud')?.checked) sources.push('isolarcloud');
    if (document.getElementById('srcSuryalog')?.checked) sources.push('suryalog');
    return sources;
}

function onSourceCheckboxChange() {
    const selected = getSelectedSources();
    if (selected.length === 0) {
        alert("Please leave at least one source selected.");
        const gw = document.getElementById('srcGrowatt');
        if (gw) gw.checked = true;
    }
    updateStats();
    renderTable();
}

async function cancelActiveFetch() {
    try {
        await fetch('/api/fetch/cancel', { method: 'POST', headers: _getHeaders() });
        _hideSpinner();
        const fetchBtn = document.getElementById('fetchBtn');
        if (fetchBtn) fetchBtn.disabled = false;
        renderTable();
    } catch (e) {
        console.error('Error cancelling fetch:', e);
    }
}

async function fetchData() {
    const monthInput = document.getElementById('reportMonth');
    const targetMonth = monthInput ? monthInput.value : '';
    const fetchBtn = document.getElementById('fetchBtn');

    if (!targetMonth) {
        alert("Please select a month to fetch.");
        return;
    }

    if (!/^\d{4}-\d{2}$/.test(targetMonth)) {
        alert("Invalid month format. Please use YYYY-MM.");
        return;
    }

    // Gather selected sources
    const sources = getSelectedSources();
    if (sources.length === 0) {
        alert("Please select at least one data source checkbox (Growatt, iSolarCloud, or SuryaLog).");
        return;
    }

    const forceRefreshCheckbox = document.getElementById('forceRefresh');
    const forceRefresh = forceRefreshCheckbox ? forceRefreshCheckbox.checked : false;

    if (fetchBtn) fetchBtn.disabled = true;
    _showSpinner(`Connecting to selected portals [${sources.join(', ')}]...`);
    sentInSession.clear();

    try {
        const res = await fetch('/api/fetch', {
            method: 'POST',
            headers: _getHeaders({ 'Content-Type': 'application/json' }),
            body: JSON.stringify({
                month: targetMonth,
                sources: sources,
                save_excel: true,
                force_refresh: forceRefresh
            })
        });
        const result = await res.json();

        if (result.success) {
            if (result.job_id) {
                _pollFetchStatus(result.job_id);
            } else if (result.from_cache) {
                if (fetchBtn) fetchBtn.disabled = false;
                _applyResult(result);
                _fetchSummary();
                alert(`Loaded ${result.fetch_stats?.total_plants_fetched || 'all'} plants from cache.`);
            }
        } else {
            if (fetchBtn) fetchBtn.disabled = false;
            _showError(result.error || result.message || 'Fetch failed to start.');
        }
    } catch (e) {
        if (fetchBtn) fetchBtn.disabled = false;
        _showError('Network error starting fetch. Check server console.');
        console.error(e);
    }
}

async function _pollFetchStatus(jobId) {
    const fetchBtn = document.getElementById('fetchBtn');
    try {
        const res = await fetch(`/api/fetch-status/${jobId}`, { headers: _getHeaders() });
        const result = await res.json();

        if (!result.success) {
            if (fetchBtn) fetchBtn.disabled = false;
            _showError('Failed to check fetch status.');
            return;
        }

        if (result.status === 'running' || result.status === 'queued') {
            const currentPlant = result.current_plant || 'Initializing...';
            const progressHtml = `
                <b>Fetching Solar Portals...</b><br>
                <span class="progress-msg">${_esc(currentPlant)}</span><br>
                <small style="color: #94a3b8;">Portals: ${(result.sources || []).join(', ')}</small><br>
                <button class="btn btn-outline btn-sm" onclick="cancelActiveFetch()" style="margin-top: 10px; border-color: #ef4444; color: #f87171; font-size: 0.75rem; padding: 3px 10px; border-radius: 6px; cursor: pointer;">
                    ✕ Cancel Fetch
                </button>
            `;
            _showSpinner(progressHtml);
            setTimeout(() => _pollFetchStatus(jobId), 1500);
        } else if (result.status === 'done') {
            if (fetchBtn) fetchBtn.disabled = false;
            const fetchYearlyBtn = document.getElementById('fetchYearlyBtn');
            if (fetchYearlyBtn) fetchYearlyBtn.disabled = false;
            _applyResult(result);
            _fetchSummary();
            const stats = result.fetch_stats;
            const timeTaken = stats ? ` in ${stats.fetch_time_seconds}s` : '';
            const totalFetched = stats ? (stats.total_histories_fetched || stats.total_plants_fetched || 'All') : 'All';
            alert(`Fetch complete${timeTaken}! Updated ${totalFetched} plant records.`);
        } else if (result.status === 'cancelled') {
            if (fetchBtn) fetchBtn.disabled = false;
            _hideSpinner();
            renderTable();
        } else if (result.status === 'error') {
            if (fetchBtn) fetchBtn.disabled = false;
            const fetchYearlyBtn = document.getElementById('fetchYearlyBtn');
            if (fetchYearlyBtn) fetchYearlyBtn.disabled = false;
            _showError(result.error || 'Fetch job encountered an error.');
        }
    } catch (e) {
        if (fetchBtn) fetchBtn.disabled = false;
        const fetchYearlyBtn = document.getElementById('fetchYearlyBtn');
        if (fetchYearlyBtn) fetchYearlyBtn.disabled = false;
        _showError('Network error checking fetch progress.');
        console.error(e);
    }
}


// ── File Upload (SolarOn Excel fallback) ───────────────────────────────────

async function uploadFile() {
    const input = document.getElementById('fileUpload');
    if (!input.files.length) return;

    _showSpinner('Parsing uploaded Excel report, please wait…');
    sentInSession.clear();

    const form = new FormData();
    form.append('file', input.files[0]);

    try {
        const res = await fetch('/upload', {
            method: 'POST',
            body: form,
            headers: _getHeaders()
        });
        const result = await res.json();

        if (result.success) {
            _applyResult(result);
            _fetchSummary();
        } else {
            _showError(result.error || 'Upload failed.');
        }
    } catch (e) {
        _showError('Network error during upload. Check server.');
        console.error(e);
    }

    input.value = '';
}


// ── View Switching (Daily / Weekly / Monthly / Yearly) ─────────────────────

function switchView(view) {
    currentView = view;
    
    // Update button active state
    document.querySelectorAll('.tab-btn').forEach(btn => {
        if (btn.getAttribute('data-view') === view) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });

    // Adaptive date controls visibility
    const monthInput = document.getElementById('reportMonth');
    const dateInput = document.getElementById('reportDate');
    const yearSelect = document.getElementById('reportYearSelect');
    const pickerIcon = document.getElementById('pickerIcon');

    if (monthInput) monthInput.style.display = 'none';
    if (dateInput) dateInput.style.display = 'none';
    if (yearSelect) yearSelect.style.display = 'none';

    if (view === 'daily') {
        if (dateInput) dateInput.style.display = 'inline-block';
        if (pickerIcon) pickerIcon.textContent = '📅';
    } else if (view === 'weekly') {
        if (dateInput) dateInput.style.display = 'inline-block';
        if (pickerIcon) pickerIcon.textContent = '📊';
    } else if (view === 'yearly') {
        if (yearSelect) yearSelect.style.display = 'inline-block';
        if (pickerIcon) pickerIcon.textContent = '📆';
    } else {
        if (monthInput) monthInput.style.display = 'inline-block';
        if (pickerIcon) pickerIcon.textContent = '🗓';
    }

    // Update table header & stat period label
    const headerEl = document.getElementById('energyHeader');
    const periodLabelEl = document.getElementById('stat-period-label');
    if (view === 'daily') {
        const now = new Date();
        const yday = new Date(now);
        yday.setDate(now.getDate() - 1);
        const yStr = `${yday.getFullYear()}-${String(yday.getMonth() + 1).padStart(2, '0')}-${String(yday.getDate()).padStart(2, '0')}`;
        
        let dStr = ' (Today)';
        if (selectedDateStr === yStr) {
            dStr = ` (Yesterday, ${yStr})`;
        } else if (selectedDateStr) {
            dStr = ` (${selectedDateStr})`;
        }
        if (headerEl) headerEl.innerHTML = `Daily Energy${dStr} (kWh) <span id="sortIcon-energy" class="sort-icon">▼</span>`;
        if (periodLabelEl) periodLabelEl.textContent = (selectedDateStr === yStr) ? 'Yesterday' : (selectedDateStr || 'Today');
    } else if (view === 'weekly') {
        if (headerEl) headerEl.innerHTML = `Weekly Energy (Past 7 Days) <span id="sortIcon-energy" class="sort-icon">▼</span>`;
        if (periodLabelEl) periodLabelEl.textContent = 'Past 7 Days';
    } else if (view === 'yearly') {
        const yr = selectedYearStr || config.year || new Date().getFullYear();
        if (headerEl) headerEl.innerHTML = `Energy Year ${yr} (kWh) <span id="sortIcon-energy" class="sort-icon">▼</span>`;
        if (periodLabelEl) periodLabelEl.textContent = `Year ${yr}`;
    } else {
        const mLabel = config.month_name ? ` (${config.month_name})` : '';
        if (headerEl) headerEl.innerHTML = `Energy Month${mLabel} (kWh) <span id="sortIcon-energy" class="sort-icon">▼</span>`;
        if (periodLabelEl) periodLabelEl.textContent = config.month_name ? config.month_name : 'Month';
    }

    updateStats();
    renderTable();
}


// ── On-Demand Yearly Fetch Modal & Operations ──────────────────────────────

function openYearlyFetchModal() {
    const modal = document.getElementById('yearlyFetchModal');
    if (modal) {
        const yr = selectedYearStr || config.year || new Date().getFullYear();
        const lbl = document.getElementById('yearlyTargetYearLabel');
        if (lbl) lbl.textContent = `${yr} & ${parseInt(yr, 10) - 1}`;
        const sel = document.getElementById('yearlyFetchSelect');
        if (sel) sel.value = String(yr);
        modal.style.display = 'flex';
    }
}

function closeYearlyFetchModal() {
    const modal = document.getElementById('yearlyFetchModal');
    if (modal) modal.style.display = 'none';
}

function closeYearlyModalOnBackdrop(event) {
    if (event.target === document.getElementById('yearlyFetchModal')) {
        closeYearlyFetchModal();
    }
}

async function confirmYearlyFetch() {
    closeYearlyFetchModal();
    const sel = document.getElementById('yearlyFetchSelect');
    const targetYear = sel ? parseInt(sel.value, 10) : new Date().getFullYear();

    // Gather selected sources
    const sources = [];
    if (document.getElementById('srcGrowatt')?.checked) sources.push('growatt');
    if (document.getElementById('srcIsolarcloud')?.checked) sources.push('isolarcloud');
    if (document.getElementById('srcSuryalog')?.checked) sources.push('suryalog');

    if (sources.length === 0) {
        alert("Please select at least one data source checkbox.");
        return;
    }

    const fetchYearlyBtn = document.getElementById('fetchYearlyBtn');
    if (fetchYearlyBtn) fetchYearlyBtn.disabled = true;

    _showSpinner(`
        <b>Fetching Yearly Generation History (${targetYear})...</b><br>
        <span class="progress-msg">Connecting to solar monitoring portals in background...</span><br>
        <small style="color: #c4b5fd;">This comprehensive query takes ~8-20 min. You may continue using the dashboard.</small>
    `);

    try {
        const res = await fetch('/api/fetch-yearly', {
            method: 'POST',
            headers: _getHeaders({ 'Content-Type': 'application/json' }),
            body: JSON.stringify({ year: targetYear, sources: sources })
        });
        const result = await res.json();
        if (result.success && result.job_id) {
            _pollFetchStatus(result.job_id);
        } else {
            if (fetchYearlyBtn) fetchYearlyBtn.disabled = false;
            _showError(result.error || result.message || 'Failed to start yearly fetch.');
        }
    } catch (err) {
        if (fetchYearlyBtn) fetchYearlyBtn.disabled = false;
        _showError('Network error starting yearly history fetch.');
        console.error(err);
    }
}


// ── CSV Export ─────────────────────────────────────────────────────────────

function exportCsv() {
    const sourceFilter = document.getElementById('sourceFilter')?.value || 'All';
    let url = `/api/report/csv?view=${encodeURIComponent(currentView)}&sort_by=${encodeURIComponent(currentSortKey)}&sort_order=${encodeURIComponent(currentSortOrder)}`;
    if (sourceFilter !== 'All') {
        url += `&source=${encodeURIComponent(sourceFilter)}`;
    }
    if (selectedYearStr) {
        url += `&year=${encodeURIComponent(selectedYearStr)}`;
    }
    window.location.href = url;
}


// ── Summary & Stats ────────────────────────────────────────────────────────

async function _fetchSummary() {
    try {
        const res = await fetch('/api/report/summary', { headers: _getHeaders() });
        const result = await res.json();
        if (result.success && result.summary) {
            currentSummary = result.summary;
            updateStats();
        }
    } catch (e) {
        console.debug('Could not fetch report summary:', e);
    }
}

function updateStats() {
    const activeSources = getSelectedSources();

    // Gather plants filtered by enabled source toggles
    const allPlants = [];
    const statusCounts = { 'Active': 0, 'Not Working': 0, 'Offline': 0, 'Not Commissioned': 0 };

    for (const [status, list] of Object.entries(currentData.plants)) {
        for (const p of list) {
            const src = (p.source || 'growatt').toLowerCase();
            if (activeSources.includes(src)) {
                allPlants.push(p);
                const stKey = p.status || status;
                if (statusCounts.hasOwnProperty(stKey)) {
                    statusCounts[stKey]++;
                } else if (statusCounts.hasOwnProperty(status)) {
                    statusCounts[status]++;
                }
            }
        }
    }

    // 1. Status card counts
    _setText('stat-active',      statusCounts['Active'] ?? 0);
    _setText('stat-not-working', statusCounts['Not Working'] ?? 0);
    _setText('stat-offline',     statusCounts['Offline'] ?? 0);
    _setText('stat-nc',          statusCounts['Not Commissioned'] ?? 0);

    // 2. Generation, live power & savings by view
    let totalEnergy = 0;
    let totalCapacity = 0;
    let totalLivePower = 0;
    let operatingCapacity = 0;
    let operatingEnergy = 0;

    for (const p of allPlants) {
        totalCapacity += (p.capacity_kwp || 0);
        totalLivePower += (p.current_power_kw || 0);
        
        const dispE = _calcDisplayEnergy(p);
        totalEnergy += (dispE || 0);

        if ((p.capacity_kwp || 0) > 0 && dispE > 0) {
            operatingCapacity += (p.capacity_kwp || 0);
            operatingEnergy += dispE;
        }
    }

    const price = config.price_per_unit || 14.0;
    const totalSavings = Math.round(totalEnergy * price);

    _setText('stat-total-energy', `${Math.round(totalEnergy).toLocaleString('en-IN')} kWh`);
    _setText('stat-total-savings', `Est. Savings: ₹${totalSavings.toLocaleString('en-IN')}`);
    _setText('stat-total-cap', `Total Cap: ${Math.round(totalCapacity).toLocaleString('en-IN')} kWp`);
    _setText('stat-live-power', `Live: ${totalLivePower.toFixed(1)} kW`);

    const meanSy = operatingCapacity > 0 ? (operatingEnergy / operatingCapacity).toFixed(2) : '—';
    _setText('stat-fleet-yield', `Mean Yield: ${meanSy} kWh/kWp`);

    // 3. Platform breakdown chips
    const sourceCounts = { growatt: 0, isolarcloud: 0, suryalog: 0 };
    for (const p of allPlants) {
        const src = (p.source || 'growatt').toLowerCase();
        if (sourceCounts.hasOwnProperty(src)) {
            sourceCounts[src]++;
        }
    }

    _setText('chip-growatt', `Growatt: ${sourceCounts.growatt}`);
    _setText('chip-isolar',  `iSolar: ${sourceCounts.isolarcloud}`);
    _setText('chip-surya',   `SuryaLog: ${sourceCounts.suryalog}`);
}


// ── Table Rendering & Sorting ──────────────────────────────────────────────

function _calcDisplayEnergy(plant) {
    if (!plant) return 0;
    
    if (currentView === 'daily') {
        const now = new Date();
        const yday = new Date(now);
        yday.setDate(now.getDate() - 1);
        const yStr = `${yday.getFullYear()}-${String(yday.getMonth() + 1).padStart(2, '0')}-${String(yday.getDate()).padStart(2, '0')}`;

        if (selectedDateStr) {
            if (plant.daily_history && plant.daily_history[selectedDateStr] !== undefined) {
                return plant.daily_history[selectedDateStr] || 0;
            }
            if (selectedDateStr === yStr) {
                return plant.energy_yesterday !== undefined ? plant.energy_yesterday : (plant.energy_today || 0);
            }
        }
        return plant.energy_today || 0;
    } else if (currentView === 'weekly') {
        if (plant.energy_weekly !== undefined && plant.energy_weekly > 0) {
            return plant.energy_weekly;
        }
        return plant.energy_this_month ? Math.round(plant.energy_this_month / 4.33) : 0;
    } else if (currentView === 'yearly') {
        const yr = selectedYearStr || config.year || '2026';
        if (plant.yearly_history && plant.yearly_history[yr] !== undefined) {
            return plant.yearly_history[yr] || 0;
        }
        if (plant.yearly_breakdown && Object.keys(plant.yearly_breakdown).length > 0) {
            const sumVal = Object.values(plant.yearly_breakdown).reduce((a, b) => a + (parseFloat(b) || 0), 0);
            if (sumVal > 0) return Math.round(sumVal);
        }
        return plant.energy_this_year || 0;
    } else {
        return plant.energy_this_month || 0;
    }
}

function setSort(key, order) {
    currentSortKey = key;
    currentSortOrder = order || 'desc';
    _syncSortUI();
    renderTable();
}

function toggleSort(key) {
    if (currentSortKey === key) {
        currentSortOrder = (currentSortOrder === 'asc') ? 'desc' : 'asc';
    } else {
        currentSortKey = key;
        // Default descending for numeric metrics, ascending for plant name
        currentSortOrder = (key === 'name') ? 'asc' : 'desc';
    }
    _syncSortUI();
    renderTable();
}

function onSortFilterChange() {
    const val = document.getElementById('sortFilter')?.value || 'energy_desc';
    const parts = val.split('_');
    currentSortKey = parts[0] || 'energy';
    currentSortOrder = parts[1] || 'desc';
    _updateHeaderIcons();
    renderTable();
}

function _syncSortUI() {
    const select = document.getElementById('sortFilter');
    if (select) {
        const targetVal = `${currentSortKey}_${currentSortOrder}`;
        for (const opt of select.options) {
            if (opt.value === targetVal) {
                select.value = targetVal;
                break;
            }
        }
    }
    _updateHeaderIcons();
}

function _updateHeaderIcons() {
    const keys = ['name', 'capacity', 'power', 'energy', 'savings', 'platform', 'phone', 'status'];
    for (const k of keys) {
        const icon = document.getElementById(`sortIcon-${k}`);
        const th = document.getElementById(`th-${k}`) || (k === 'energy' ? document.getElementById('energyHeader') : null);
        if (!icon) continue;
        if (currentSortKey === k) {
            icon.textContent = (currentSortOrder === 'asc') ? '▲' : '▼';
            if (th) th.classList.add('active-sort');
        } else {
            icon.textContent = '↕';
            if (th) th.classList.remove('active-sort');
        }
    }
}

function renderTable() {
    const statusFilter    = document.getElementById('statusFilter')?.value || 'All';
    const deviationFilter = document.getElementById('deviationFilter')?.value || 'all';
    const sourceFilter    = document.getElementById('sourceFilter')?.value || 'All';
    const searchTerm      = (document.getElementById('searchInput')?.value || '').toLowerCase().trim();
    const tbody           = document.getElementById('plantsBody');

    if (!tbody) return;

    const activeSources = getSelectedSources();

    // Gather plants
    let plants = [];
    if (statusFilter === 'All') {
        for (const list of Object.values(currentData.plants)) {
            plants.push(...list);
        }
    } else if (statusFilter === 'unsent') {
        for (const list of Object.values(currentData.plants)) {
            plants.push(...list.filter(p => (p.message_status || '').toLowerCase() !== 'done' && !sentInSession.has(p.plant_name)));
        }
    } else if (statusFilter === 'sent') {
        for (const list of Object.values(currentData.plants)) {
            plants.push(...list.filter(p => (p.message_status || '').toLowerCase() === 'done' || sentInSession.has(p.plant_name)));
        }
    } else if (statusFilter === 'missing_phone') {
        for (const list of Object.values(currentData.plants)) {
            plants.push(...list.filter(p => !p.phone || p.phone.trim() === ''));
        }
    } else if (statusFilter === 'deviated') {
        for (const list of Object.values(currentData.plants)) {
            plants.push(...list.filter(p => (p.deviation_pct !== undefined ? p.deviation_pct : 0) <= -15.0));
        }
    } else {
        if (currentData.plants[statusFilter]) {
            plants = currentData.plants[statusFilter];
        } else {
            for (const list of Object.values(currentData.plants)) {
                plants.push(...list.filter(p => (p.status || '').toLowerCase() === statusFilter.toLowerCase()));
            }
        }
    }

    // Filter by header source checkboxes
    plants = plants.filter(p => activeSources.includes((p.source || 'growatt').toLowerCase()));

    // Filter by source platform dropdown if specifically chosen
    if (sourceFilter !== 'All') {
        const srcClean = sourceFilter.toLowerCase();
        plants = plants.filter(p => (p.source || '').toLowerCase() === srcClean);
    }

    // Apply search filter
    if (searchTerm) {
        plants = plants.filter(p =>
            (p.plant_name || '').toLowerCase().includes(searchTerm) ||
            (p.city || '').toLowerCase().includes(searchTerm) ||
            (p.phone || '').toLowerCase().includes(searchTerm)
        );
    }

    // Calculate fleet benchmark for specific yield across currently filtered plants
    let opCap = 0;
    let opEnergy = 0;
    for (const p of plants) {
        const e = _calcDisplayEnergy(p);
        const cap = p.capacity_kwp || 0;
        if (cap > 0 && e > 0) {
            opCap += cap;
            opEnergy += e;
        }
    }
    const fleetMeanYield = opCap > 0 ? (opEnergy / opCap) : 0;

    // Annotate specific yield and deviation % for all plants
    for (const p of plants) {
        const e = _calcDisplayEnergy(p);
        const cap = p.capacity_kwp || 0;
        const sy = (cap > 0 && e > 0) ? (e / cap) : 0;
        p.specific_yield = sy;
        if (fleetMeanYield > 0.05 && cap > 0) {
            p.deviation_pct = Math.round(((sy - fleetMeanYield) / fleetMeanYield) * 1000) / 10;
        } else if (p.deviation_pct === undefined) {
            p.deviation_pct = 0;
        }
    }

    // Apply performance deviation dropdown filter
    if (deviationFilter === 'deviated_moderate') {
        plants = plants.filter(p => (p.deviation_pct || 0) <= -15.0);
    } else if (deviationFilter === 'deviated_severe') {
        plants = plants.filter(p => (p.deviation_pct || 0) <= -25.0);
    } else if (deviationFilter === 'top_performers') {
        plants = plants.filter(p => (p.deviation_pct || 0) >= 10.0);
    }

    tbody.innerHTML = '';

    if (plants.length === 0) {
        tbody.innerHTML = `
            <tr><td colspan="12">
                <div class="empty-state">
                    <strong>${Object.keys(currentData.plants).length === 0 ? 'No data loaded' : 'No matching plants'}</strong>
                    <p>${Object.keys(currentData.plants).length === 0 ? 'Click "Fetch Data" or upload an Excel report to begin.' : 'Try adjusting your search, status, or deviation filters.'}</p>
                </div>
            </td></tr>`;
        return;
    }

    const price = config.price_per_unit || 14.0;

    // ── Apply Sorting ──
    plants.sort((a, b) => {
        let diff = 0;
        if (currentSortKey === 'capacity') {
            diff = (a.capacity_kwp || 0) - (b.capacity_kwp || 0);
        } else if (currentSortKey === 'power') {
            diff = (a.current_power_kw || 0) - (b.current_power_kw || 0);
        } else if (currentSortKey === 'energy') {
            diff = _calcDisplayEnergy(a) - _calcDisplayEnergy(b);
        } else if (currentSortKey === 'yield' || currentSortKey === 'specific_yield') {
            diff = (a.specific_yield || 0) - (b.specific_yield || 0);
        } else if (currentSortKey === 'deviation' || currentSortKey === 'deviation_pct') {
            diff = (a.deviation_pct || 0) - (b.deviation_pct || 0);
        } else if (currentSortKey === 'savings' || currentSortKey === 'saving') {
            diff = (_calcDisplayEnergy(a) * price) - (_calcDisplayEnergy(b) * price);
        } else if (currentSortKey === 'platform') {
            const aSrc = (a.source || '').toLowerCase();
            const bSrc = (b.source || '').toLowerCase();
            diff = aSrc.localeCompare(bSrc);
        } else if (currentSortKey === 'phone') {
            const aPhone = (a.phone || '').toLowerCase();
            const bPhone = (b.phone || '').toLowerCase();
            diff = aPhone.localeCompare(bPhone);
        } else if (currentSortKey === 'status') {
            const aStatus = (a.status || '').toLowerCase();
            const bStatus = (b.status || '').toLowerCase();
            diff = aStatus.localeCompare(bStatus);
        } else {
            // Sort by plant name
            const aName = (a.plant_name || '').toLowerCase();
            const bName = (b.plant_name || '').toLowerCase();
            diff = aName.localeCompare(bName, undefined, { numeric: true, sensitivity: 'base' });
        }
        return (currentSortOrder === 'desc') ? -diff : diff;
    });

    _updateHeaderIcons();

    const fragment = document.createDocumentFragment();

    for (const plant of plants) {
        const badgeClass = _badgeClass(plant.status);
        const srcBadgeHtml = _sourceBadgeHtml(plant.source);
        const displayEnergy = _calcDisplayEnergy(plant);
        const savings = Math.round(displayEnergy * price);
        const wasSent = sentInSession.has(plant.plant_name);
        const cap = plant.capacity_kwp ? `${plant.capacity_kwp} kWp` : '—';
        const curPower = plant.current_power_kw || 0;
        const escapedPlantName = encodeURIComponent(plant.plant_name || '');
        const escapedPhone = encodeURIComponent(plant.phone || '');

        const powerHtml = curPower > 0
            ? `<span class="power-live-badge"><span class="live-indicator-dot mini"></span> ${curPower.toFixed(2)} kW</span>`
            : `<span class="power-live-badge idle">0.00 kW</span>`;

        const phoneHtml = plant.phone
            ? `<div style="display: inline-flex; align-items: center; gap: 4px;">
                 <span style="font-family: monospace; font-size: 0.8rem; color: #38bdf8;">${_esc(plant.phone)}</span>
                 <button class="btn-icon" onclick="openEditContactModal('${escapedPlantName}','${escapedPhone}')" title="Edit phone number" style="background: none; border: none; cursor: pointer; font-size: 0.75rem; opacity: 0.7; padding: 2px 4px; border-radius: 4px;" onmouseover="this.style.opacity=1" onmouseout="this.style.opacity=0.7">✏️</button>
               </div>`
            : `<div style="display: inline-flex; align-items: center; gap: 6px;">
                 <span style="font-size: 0.72rem; color: #ef4444; background: rgba(239,68,68,0.15); padding: 2px 6px; border-radius: 4px; border: 1px solid rgba(239,68,68,0.3);">⚠️ No Phone</span>
                 <button class="btn btn-outline btn-xs" onclick="openEditContactModal('${escapedPlantName}','')" style="font-size: 0.7rem; padding: 2px 6px; border-color: #38bdf8; color: #38bdf8;" title="Add phone number">➕ Add</button>
               </div>`;

        // Format specific yield and deviation pill
        const syVal = plant.specific_yield || 0;
        const devVal = plant.deviation_pct !== undefined ? plant.deviation_pct : 0;
        let devPillHtml = '<span class="deviation-pill dev-neutral">—</span>';
        if (plant.capacity_kwp && displayEnergy > 0) {
            const devSign = devVal >= 0 ? '+' : '';
            let pillClass = 'dev-neutral';
            if (devVal >= 10) pillClass = 'dev-positive';
            else if (devVal <= -25) pillClass = 'dev-critical';
            else if (devVal <= -15) pillClass = 'dev-warning';

            devPillHtml = `<span class="deviation-pill ${pillClass}" title="Specific Yield: ${syVal.toFixed(2)} kWh/kWp (Fleet Benchmark: ${fleetMeanYield.toFixed(2)} kWh/kWp, Deviation: ${devSign}${devVal.toFixed(1)}%)">
                ${syVal.toFixed(2)} (${devSign}${devVal.toFixed(1)}%)
            </span>`;
        } else if (plant.status === 'Not Working') {
            devPillHtml = `<span class="deviation-pill dev-critical" title="Inverter zero output / fault">0.00 (-100%)</span>`;
        }

        let energyTooltip = '';
        if (currentView === 'yearly' && plant.yearly_breakdown && Object.keys(plant.yearly_breakdown).length > 0) {
            energyTooltip = Object.entries(plant.yearly_breakdown)
                .map(([m, v]) => {
                    const mIdx = parseInt(m, 10) - 1;
                    const name = (mIdx >= 0 && mIdx < 12) ? CAL_MONTH_NAMES[mIdx].short : `M${m}`;
                    return `${name}: ${Math.round(v)} kWh`;
                })
                .join(' | ');
        }

        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><input type="checkbox" class="row-checkbox"
                value="${_esc(plant.plant_name)}"
                data-status="${_esc(plant.status)}"
                data-deviated="${Boolean(devVal <= -15.0)}"
                onchange="updateSelectedCount()"></td>
            <td>${srcBadgeHtml}</td>
            <td>
                <strong class="plant-clickable-name" onclick="openPlantAnalyticsModal('${escapedPlantName}')" title="Click to view detailed generation analytics & history">
                    ${_esc(plant.plant_name)}
                </strong>
                ${plant.city ? `<br><small style="color: #64748b;">${_esc(plant.city)}</small>` : ''}
            </td>
            <td>${phoneHtml}</td>
            <td><span class="status-badge ${badgeClass}">${_esc(plant.status)}</span></td>
            <td>${_esc(cap)}</td>
            <td>${powerHtml}</td>
            <td title="${_esc(energyTooltip)}" style="${energyTooltip ? 'cursor: help; text-decoration: underline dotted #a78bfa;' : ''}">
                ${Math.round(displayEnergy).toLocaleString('en-IN')}
                ${currentView === 'yearly' && !displayEnergy ? '<br><small style="color: #a78bfa; font-size: 0.68rem;">(Not fetched)</small>' : ''}
            </td>
            <td>${devPillHtml}</td>
            <td>₹${savings.toLocaleString('en-IN')}</td>
            <td>
                <div style="display: inline-flex; gap: 6px; align-items: center;">
                    <button class="btn btn-outline btn-sm"
                           onclick="openPlantAnalyticsModal('${escapedPlantName}')"
                           title="View Plant History Chart & KPIs"
                           style="border-color: #a78bfa; color: #c4b5fd; padding: 3px 7px; font-size: 0.72rem;">
                           📊 Chart
                    </button>
                    ${plant.message
                        ? `<button class="btn btn-outline btn-sm"
                               onclick="previewMessage('${escapedPlantName}','${encodeURIComponent(plant.message)}','${escapedPhone}','${encodeURIComponent(plant.whatsapp_url || '')}')">
                               👁 Preview</button>`
                        : '<span class="sent-no">—</span>'}
                    ${(plant.phone && plant.message)
                        ? `<button class="btn btn-sm btn-send-row"
                               id="sendBtn-${_cleanDomId(plant.plant_name)}"
                               onclick="sendSinglePlantDirect('${escapedPlantName}')"
                               style="background: #25D366; color: #fff; border: none; padding: 4px 9px; font-size: 0.75rem; border-radius: 6px; font-weight: 600; cursor: pointer; display: inline-flex; align-items: center; gap: 4px;"
                               title="Send WhatsApp message directly to ${_esc(plant.plant_name)}">
                               💬 Send
                           </button>`
                        : ''}
                </div>
            </td>
            <td>${(plant.message_status && plant.message_status.toLowerCase() === 'done') || wasSent
                ? `<span class="sent-done" style="background: rgba(34, 197, 94, 0.18); color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.35); padding: 3px 8px; border-radius: 6px; font-weight: 700; font-size: 0.74rem; display: inline-flex; align-items: center; gap: 4px;" title="Recorded as Sent in Database & Excel">
                     ✅ Done ${plant.sent_at ? `<small style="color: #86efac; font-size: 0.68rem; margin-left: 2px;">(${_esc(plant.sent_at)})</small>` : ''}
                   </span>`
                : '<span class="sent-no" style="color: #64748b; font-size: 0.78rem;">⏳ Unsent</span>'}</td>
        `;
        fragment.appendChild(tr);
    }

    tbody.appendChild(fragment);
    updateSelectedCount();
}

function _badgeClass(status) {
    if (status === 'Active')           return 'badge-active';
    if (status === 'Not Working')      return 'badge-not-working';
    if (status === 'Offline')          return 'badge-offline';
    if (status === 'Not Commissioned') return 'badge-nc';
    return '';
}

function _sourceBadgeHtml(source) {
    const src = (source || 'growatt').toLowerCase();
    if (src === 'isolarcloud') {
        return '<span class="source-badge badge-isolarcloud">🔵 iSolar</span>';
    } else if (src === 'suryalog') {
        return '<span class="source-badge badge-suryalog">🟠 SuryaLog</span>';
    } else if (src === 'excel') {
        return '<span class="source-badge" style="background: rgba(148,163,184,0.15); color: #cbd5e1; border: 1px solid rgba(148,163,184,0.3);">📄 Excel</span>';
    } else {
        return '<span class="source-badge badge-growatt">🟢 Growatt</span>';
    }
}


// ── Checkboxes & Selection ──────────────────────────────────────────────────

function _cleanDomId(str) {
    return (str || '').replace(/[^a-zA-Z0-9_-]/g, '_');
}

function updateSelectedCount() {
    const checked = document.querySelectorAll('.row-checkbox:checked');
    const badge = document.getElementById('selectedCountBadge');
    const btn = document.getElementById('sendSelectedBtn');
    const floatingBar = document.getElementById('floatingSelectionBar');
    const floatCount = document.getElementById('floatingSelectedCount');
    const dockBadge = document.getElementById('dockSendBadge');
    const count = checked.length;

    if (badge) badge.textContent = count;
    if (floatCount) floatCount.textContent = count;
    if (dockBadge) dockBadge.textContent = count;

    if (btn) {
        if (count > 0) {
            btn.style.background = 'linear-gradient(135deg, #16a34a, #15803d)';
            btn.style.boxShadow = '0 2px 10px rgba(22, 163, 74, 0.4)';
        } else {
            btn.style.background = 'linear-gradient(135deg, #0284c7, #2563eb)';
            btn.style.boxShadow = '0 2px 8px rgba(2, 132, 199, 0.4)';
        }
    }

    if (floatingBar) {
        if (count > 0) {
            floatingBar.style.display = 'flex';
            requestAnimationFrame(() => {
                floatingBar.classList.add('visible');
            });
        } else {
            floatingBar.classList.remove('visible');
            setTimeout(() => {
                if (document.querySelectorAll('.row-checkbox:checked').length === 0) {
                    floatingBar.style.display = 'none';
                }
            }, 250);
        }
    }
}

function clearSelectedCheckboxes() {
    document.querySelectorAll('.row-checkbox').forEach(cb => cb.checked = false);
    const selectAll = document.getElementById('selectAll');
    if (selectAll) selectAll.checked = false;
    updateSelectedCount();
}

function copySelectedMessages() {
    const checked = document.querySelectorAll('.row-checkbox:checked');
    if (checked.length === 0) return;

    let textBlocks = [];
    checked.forEach(cb => {
        const name = cb.value;
        for (const list of Object.values(currentData.plants)) {
            const p = list.find(x => x.plant_name === name);
            if (p && p.message) {
                textBlocks.push(`=== Plant: ${p.plant_name} (${p.phone || 'No phone'}) ===\n${p.message}\n`);
                break;
            }
        }
    });

    if (textBlocks.length === 0) {
        alert('No messages found for selected plants.');
        return;
    }

    navigator.clipboard.writeText(textBlocks.join('\n----------------------------------------\n\n'))
        .then(() => {
            alert(`📋 Copied formatted messages for ${textBlocks.length} plant(s) to clipboard!`);
        })
        .catch(err => {
            console.error('Failed to copy text: ', err);
            alert('Failed to copy to clipboard.');
        });
}

function toggleAllCheckboxes() {
    const checked = document.getElementById('selectAll')?.checked || false;
    document.querySelectorAll('.row-checkbox').forEach(cb => cb.checked = checked);
    updateSelectedCount();
}


// ── Message Preview Modal ──────────────────────────────────────────────────

let _currentPreviewPlantName = '';
let _currentPreviewUrl = '';

function previewMessage(encodedName, encodedMsg, encodedPhone, encodedUrl) {
    const plantName = decodeURIComponent(encodedName);
    const msg = decodeURIComponent(encodedMsg);
    const phone = encodedPhone ? decodeURIComponent(encodedPhone) : '';
    const waUrl = encodedUrl ? decodeURIComponent(encodedUrl) : '';

    _currentPreviewPlantName = plantName;
    _currentPreviewUrl = waUrl;

    document.getElementById('modalPlantName').textContent = plantName;
    document.getElementById('messageText').value = msg;

    const phoneBadge = document.getElementById('modalPhoneBadge');
    if (phoneBadge) {
        if (phone) {
            phoneBadge.textContent = `📞 ${phone}`;
            phoneBadge.style.display = 'inline-block';
            phoneBadge.style.color = '#4ade80';
            phoneBadge.style.borderColor = 'rgba(34, 197, 94, 0.3)';
        } else {
            phoneBadge.textContent = `⚠️ No Phone Number Found`;
            phoneBadge.style.display = 'inline-block';
            phoneBadge.style.color = '#ef4444';
            phoneBadge.style.borderColor = 'rgba(239, 68, 68, 0.3)';
        }
    }

    const waBtn = document.getElementById('modalWhatsAppBtn');
    const sendDirectBtn = document.getElementById('modalSendDirectBtn');

    if (waUrl) {
        if (waBtn) waBtn.style.display = 'inline-flex';
        if (sendDirectBtn) sendDirectBtn.style.display = 'inline-flex';
    } else {
        if (waBtn) waBtn.style.display = 'none';
        if (sendDirectBtn) sendDirectBtn.style.display = 'none';
    }

    document.getElementById('messageModal').style.display = 'flex';
}

function openWhatsAppManual(event) {
    if (event) event.preventDefault();
    if (_currentPreviewUrl) {
        // Reuses named window 'SolaronWhatsApp' to prevent multiple window conflict
        window.open(_currentPreviewUrl, 'SolaronWhatsApp');
    }
}

function sendDirectFromPreviewModal() {
    if (_currentPreviewPlantName) {
        const name = _currentPreviewPlantName;
        closeModal();
        sendSinglePlantDirect(name);
    }
}

function closeModal() {
    document.getElementById('messageModal').style.display = 'none';
}

function closeModalOnBackdrop(event) {
    if (event.target === document.getElementById('messageModal')) closeModal();
}

// ── Plant Analytics & Dated History Modal ──────────────────────────────────

function openPlantAnalyticsModal(encodedPlantName) {
    const plantName = decodeURIComponent(encodedPlantName || '');
    let plant = null;
    
    for (const list of Object.values(currentData.plants)) {
        const found = list.find(x => x.plant_name === plantName);
        if (found) {
            plant = found;
            break;
        }
    }
    
    if (!plant) {
        alert('Plant details not found in current session.');
        return;
    }
    
    const price = config.price_per_unit || 14.0;
    const curPower = plant.current_power_kw || 0;
    const eToday = plant.energy_today || 0;
    const eYesterday = (plant.energy_yesterday !== undefined && plant.energy_yesterday !== null) ? plant.energy_yesterday : 0;
    const eWeekly = (plant.energy_weekly !== undefined && plant.energy_weekly !== null) ? plant.energy_weekly : 0;
    const cap = plant.capacity_kwp || 0;
    const specYield = (plant.specific_yield !== undefined && plant.specific_yield !== null) 
        ? plant.specific_yield 
        : (cap > 0 ? (eToday / cap) : 0);
    const devPct = (plant.deviation_pct !== undefined && plant.deviation_pct !== null) ? plant.deviation_pct : null;
    const eMonth = plant.energy_this_month || 0;
    const eYear = plant.energy_this_year || 0;
    const savingsMonth = Math.round(eMonth * price);
    
    _setText('paPlantName', plant.plant_name);
    _setText('paCapacity', plant.capacity_kwp ? `${plant.capacity_kwp} kWp` : '— kWp');
    _setText('paLivePower', curPower > 0 ? `${curPower.toFixed(2)} kW` : '0.00 kW');
    _setText('paEnergyToday', `${Math.round(eToday).toLocaleString('en-IN')} kWh`);
    _setText('paEnergyYesterday', `${Math.round(eYesterday).toLocaleString('en-IN')} kWh`);
    _setText('paEnergyWeekly', `${Math.round(eWeekly).toLocaleString('en-IN')} kWh`);
    _setText('paSpecificYield', specYield > 0 ? `${specYield.toFixed(2)} kWh/kWp` : '--');
    
    const devElem = document.getElementById('paDeviationPct');
    if (devElem) {
        if (devPct !== null && isFinite(devPct)) {
            const sign = devPct > 0 ? '+' : '';
            devElem.textContent = `${sign}${devPct.toFixed(1)}%`;
            if (devPct >= 5) devElem.style.color = '#34d399';
            else if (devPct >= -15) devElem.style.color = '#94a3b8';
            else if (devPct >= -25) devElem.style.color = '#f59e0b';
            else devElem.style.color = '#ef4444';
        } else {
            devElem.textContent = '--';
            devElem.style.color = 'var(--text-secondary)';
        }
    }

    _setText('paMonthCardTitle', config.month_name ? `${config.month_name}` : 'This Month');
    _setText('paEnergyMonth', `${Math.round(eMonth).toLocaleString('en-IN')} kWh`);
    _setText('paEnergyYear', `${Math.round(eYear).toLocaleString('en-IN')} kWh`);
    _setText('paSavings', `₹${savingsMonth.toLocaleString('en-IN')}`);
    _setText('paCityLabel', plant.city ? `📍 ${plant.city}` : '');
    
    const srcBadge = document.getElementById('paSourceBadge');
    if (srcBadge) srcBadge.innerHTML = _sourceBadgeHtml(plant.source);
    
    const stBadge = document.getElementById('paStatusBadge');
    if (stBadge) {
        stBadge.className = `status-badge ${_badgeClass(plant.status)}`;
        stBadge.textContent = plant.status;
    }
    
    // Render Daily Generation Bars (Past 14 Days)
    renderPlantDailyChart(plant);

    // Render Monthly Generation Bars
    renderPlantAnalyticsChart(plant);
    
    // Render Multi-year history chips
    renderPlantYearlyHistory(plant);
    
    // Phone & Actions
    const phoneBox = document.getElementById('paPhoneAction');
    if (phoneBox) {
        const escapedName = encodeURIComponent(plant.plant_name);
        const escapedPhone = encodeURIComponent(plant.phone || '');
        if (plant.phone) {
            phoneBox.innerHTML = `
                <span style="color: #4ade80; font-size: 0.82rem; font-family: monospace;">📞 +91 ${plant.phone}</span>
                ${plant.message ? `
                    <button class="btn btn-sm" style="background: #25D366; color: #fff; font-size: 0.75rem; font-weight: 600; padding: 4px 8px;" onclick="closePlantAnalyticsModal(); sendSinglePlantDirect('${escapedName}')">
                        💬 WhatsApp
                    </button>
                ` : ''}
            `;
        } else {
            phoneBox.innerHTML = `
                <span style="color: #ef4444; font-size: 0.78rem;">⚠️ No Phone</span>
                <button class="btn btn-outline btn-xs" onclick="closePlantAnalyticsModal(); openEditContactModal('${escapedName}', '')" style="font-size: 0.72rem; padding: 2px 6px;">
                    ➕ Add Phone
                </button>
            `;
        }
    }
    
    const modal = document.getElementById('plantAnalyticsModal');
    if (modal) modal.style.display = 'flex';
}

function closePlantAnalyticsModal() {
    const modal = document.getElementById('plantAnalyticsModal');
    if (modal) modal.style.display = 'none';
}

function closePlantAnalyticsOnBackdrop(event) {
    if (event.target === document.getElementById('plantAnalyticsModal')) {
        closePlantAnalyticsModal();
    }
}

function renderPlantDailyChart(plant) {
    const container = document.getElementById('paDailyChartBars');
    if (!container) return;

    let history = plant.daily_history || {};
    let dates = Object.keys(history).sort(); // YYYY-MM-DD
    
    // If daily_history has items, pick the most recent up to 14 days
    if (dates.length > 14) {
        dates = dates.slice(dates.length - 14);
    }
    
    // If no history exists, synthesize today & yesterday if available
    if (dates.length === 0) {
        if (plant.energy_yesterday !== undefined || plant.energy_today !== undefined) {
            history = {
                'Yesterday': plant.energy_yesterday || 0,
                'Today': plant.energy_today || 0
            };
            dates = Object.keys(history);
        }
    }

    if (dates.length === 0) {
        container.innerHTML = '<div style="color: var(--text-secondary); font-size: 0.85rem; padding: 20px; width: 100%; text-align: center;">No daily generation history recorded yet.</div>';
        return;
    }

    let maxVal = 1;
    for (const d of dates) {
        const v = parseFloat(history[d] || 0);
        if (v > maxVal) maxVal = v;
    }

    let html = '';
    for (const d of dates) {
        const val = parseFloat(history[d] || 0);
        const heightPct = Math.max(6, Math.round((val / maxVal) * 100));
        
        let label = d;
        if (d.includes('-')) {
            const parts = d.split('-');
            if (parts.length === 3) {
                label = `${parts[1]}/${parts[2]}`; // MM/DD
            }
        }

        const isZero = val <= 0;
        const barColor = isZero ? '#ef4444' : '#38bdf8';
        const valDisplay = val > 0 ? Math.round(val) : '0';

        html += `
            <div class="chart-bar-col" style="flex: 1; min-width: 32px;" title="${d}: ${val.toFixed(1)} kWh">
                <span class="chart-bar-val" style="font-size: 0.68rem; color: ${isZero ? '#ef4444' : 'var(--text-secondary)'};">${valDisplay}</span>
                <div class="chart-bar-track" style="height: 70px; background: rgba(255,255,255,0.05); border-radius: 3px; position: relative;">
                    <div style="position: absolute; bottom: 0; left: 0; right: 0; height: ${heightPct}%; background: ${barColor}; border-radius: 3px; transition: height 0.3s ease;"></div>
                </div>
                <span class="chart-bar-lbl" style="font-size: 0.68rem; margin-top: 4px; color: var(--text-muted);">${label}</span>
            </div>
        `;
    }
    container.innerHTML = html;
}

function renderPlantAnalyticsChart(plant) {
    const container = document.getElementById('paMonthlyChartBars');
    const label = document.getElementById('paBreakdownYearLabel');
    if (!container) return;
    
    const yr = selectedYearStr || config.year || '2026';
    if (label) label.textContent = `Year ${yr}`;
    
    const breakdown = (plant.yearly_breakdown && Object.keys(plant.yearly_breakdown).length > 0)
        ? { ...plant.yearly_breakdown }
        : {};

    // Determine the active/selected month (0-indexed: 0=Jan ... 7=Aug, 8=Sep)
    let activeMonthIdx = -1;
    if (config.month_name) {
        const found = CAL_MONTH_NAMES.findIndex(m =>
            m.full.toLowerCase() === config.month_name.toLowerCase() ||
            m.short.toLowerCase() === config.month_name.toLowerCase()
        );
        if (found !== -1) activeMonthIdx = found;
    }
    if (activeMonthIdx === -1) {
        const reportMonthInput = document.getElementById('reportMonth');
        if (reportMonthInput && reportMonthInput.value) {
            const parts = reportMonthInput.value.split('-');
            if (parts.length === 2) {
                activeMonthIdx = parseInt(parts[1], 10) - 1;
            }
        }
    }
    if (activeMonthIdx === -1) {
        activeMonthIdx = new Date().getMonth();
    }

    // Populate the selected month's bar with plant.energy_this_month if breakdown entry is missing/0
    const activeKey = String(activeMonthIdx + 1).padStart(2, '0');
    if ((!breakdown[activeKey] || parseFloat(breakdown[activeKey]) === 0) && plant.energy_this_month > 0) {
        breakdown[activeKey] = plant.energy_this_month;
    }
        
    // Calculate maxVal including all months accurately
    let maxVal = 1;
    for (let i = 1; i <= 12; i++) {
        const key = String(i).padStart(2, '0');
        const v = parseFloat(breakdown[key] || 0);
        if (v > maxVal) maxVal = v;
    }
    
    let html = '';
    for (let i = 1; i <= 12; i++) {
        const key = String(i).padStart(2, '0');
        const monthObj = CAL_MONTH_NAMES[i - 1];
        let val = parseFloat(breakdown[key] || 0);
        
        const heightPct = Math.max(4, Math.round((val / maxVal) * 100));
        const isSelectedMonth = (i - 1) === activeMonthIdx;
        const barClass = isSelectedMonth ? 'chart-bar-fill highlight' : 'chart-bar-fill';
        const valDisplay = val > 0 ? Math.round(val) : '-';
        
        html += `
            <div class="chart-bar-col" title="${monthObj.full}: ${val > 0 ? val + ' kWh' : 'No data'}">
                <span class="chart-bar-val">${valDisplay}</span>
                <div class="chart-bar-track">
                    <div class="${barClass}" style="height: ${heightPct}%;"></div>
                </div>
                <span class="chart-bar-lbl" style="${isSelectedMonth ? 'color: #38bdf8; font-weight: 700;' : ''}">${monthObj.short}</span>
            </div>
        `;
    }
    
    container.innerHTML = html;
}

function renderPlantYearlyHistory(plant) {
    const container = document.getElementById('paYearlyHistoryChips');
    if (!container) return;
    
    const history = plant.yearly_history || {};
    const years = Object.keys(history).sort((a, b) => b - a);
    
    if (years.length === 0) {
        container.innerHTML = `<span style="font-size: 0.78rem; color: #94a3b8;">No multi-year history loaded. Click '📈 Fetch Yearly Data' in the action bar to fetch full historical records.</span>`;
        return;
    }
    
    let html = '';
    for (const y of years) {
        const tot = history[y] || 0;
        html += `
            <div style="background: rgba(30, 41, 59, 0.8); border: 1px solid var(--glass-border); padding: 6px 12px; border-radius: 6px; font-size: 0.8rem;">
                <span style="color: #a78bfa; font-weight: 600;">Year ${y}:</span>
                <b style="color: #e2e8f0; margin-left: 4px;">${Math.round(tot).toLocaleString('en-IN')} kWh</b>
            </div>
        `;
    }
    
    container.innerHTML = html;
}

document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
        closeModal();
        closePlantAnalyticsModal();
    }
});


// ── Direct Sending WhatsApp Messages ───────────────────────────────────────

async function sendSinglePlantDirect(encodedOrRawPlantName) {
    const plantName = decodeURIComponent(encodedOrRawPlantName || '');
    const cleanId = _cleanDomId(plantName);
    const btn = document.getElementById(`sendBtn-${cleanId}`);
    const origHtml = btn ? btn.innerHTML : '💬 Send';

    // Verify plant has phone number
    let hasPhone = false;
    for (const list of Object.values(currentData.plants)) {
        const p = list.find(x => x.plant_name === plantName);
        if (p && p.phone) {
            hasPhone = true;
            break;
        }
    }

    if (!hasPhone) {
        alert(`Cannot send: ${plantName} has no verified phone number. Click '➕ Add' in the phone column first.`);
        return;
    }

    // Double-Send Protection: Check if already marked as sent
    let plantObj = null;
    for (const list of Object.values(currentData.plants)) {
        plantObj = list.find(x => x.plant_name === plantName);
        if (plantObj) break;
    }
    const isAlreadySent = (plantObj && plantObj.message_status && plantObj.message_status.toLowerCase() === 'done') || sentInSession.has(plantName);
    if (isAlreadySent) {
        const timeInfo = plantObj && plantObj.sent_at ? ` on ${plantObj.sent_at}` : '';
        const confirmed = confirm(
            `⚠️ Double-Send Warning:\n\n` +
            `A WhatsApp message was already recorded as SENT to "${plantName}"${timeInfo}.\n\n` +
            `Do you really want to send it again?`
        );
        if (!confirmed) return;
    }

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '⏳ Sending…';
        btn.style.opacity = '0.8';
    }

    const gapSelect = document.getElementById('sendSpeedSelect');
    const modeVal = gapSelect ? gapSelect.value : 'manual';
    const isManual = (modeVal === 'manual');

    _showSpinner(`Opening WhatsApp for <b>${_esc(plantName)}</b> [${isManual ? 'Manual: You press Enter' : 'Auto'}]…`);

    try {
        const res = await fetch('/api/send', {
            method:  'POST',
            headers: _getHeaders({ 'Content-Type': 'application/json' }),
            body:    JSON.stringify({ plants: [plantName], view: currentView, manual_mode: isManual }),
        });
        const result = await res.json();

        if (result.success && result.job_id) {
            _pollSendStatus(result.job_id, () => {
                sentInSession.add(plantName);
                if (btn) {
                    btn.innerHTML = '✅ Sent';
                    btn.style.background = 'rgba(34, 197, 94, 0.2)';
                    btn.style.color = '#4ade80';
                    btn.style.border = '1px solid rgba(34, 197, 94, 0.4)';
                }
                renderTable();
            });
        } else {
            _hideSpinner();
            alert(result.message || 'Failed to initiate send.');
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = origHtml;
                btn.style.opacity = '1';
            }
        }
    } catch (e) {
        _hideSpinner();
        alert('Network error while sending message.');
        console.error(e);
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = origHtml;
            btn.style.opacity = '1';
        }
    }
}

function selectFirstN(n) {
    const checkboxes = document.querySelectorAll('.row-checkbox');
    // First uncheck all
    checkboxes.forEach(cb => cb.checked = false);
    
    let selected = 0;
    for (const cb of checkboxes) {
        if (selected >= n) break;
        const name = cb.value;
        let p = null;
        for (const list of Object.values(currentData.plants)) {
            p = list.find(x => x.plant_name === name);
            if (p) break;
        }
        // ONLY select plants that have a phone AND have NOT been sent!
        const isDone = (p && p.message_status && p.message_status.toLowerCase() === 'done') || sentInSession.has(name);
        if (p && p.phone && !isDone) {
            cb.checked = true;
            selected++;
        }
    }
    updateSelectedCount();
    if (selected === 0) {
        alert('All visible plants with verified phone numbers have already been sent! (Preventing double-sending)');
    }
}

function _showToast(message, duration = 3000) {
    let toast = document.getElementById('solaronToast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'solaronToast';
        toast.style.position = 'fixed';
        toast.style.bottom = '24px';
        toast.style.right = '24px';
        toast.style.background = '#0f172a';
        toast.style.color = '#f8fafc';
        toast.style.padding = '10px 18px';
        toast.style.borderRadius = '8px';
        toast.style.boxShadow = '0 10px 25px -5px rgba(0, 0, 0, 0.5), 0 0 0 1px rgba(56, 189, 248, 0.3)';
        toast.style.fontSize = '0.85rem';
        toast.style.fontWeight = '600';
        toast.style.zIndex = '99999';
        toast.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(10px)';
        toast.style.display = 'flex';
        toast.style.alignItems = 'center';
        toast.style.gap = '8px';
        document.body.appendChild(toast);
    }
    toast.innerHTML = message;
    toast.style.opacity = '1';
    toast.style.transform = 'translateY(0)';
    if (window._toastTimer) clearTimeout(window._toastTimer);
    window._toastTimer = setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(10px)';
    }, duration);
}

function selectByCriteria(criteria) {
    const checkboxes = document.querySelectorAll('.row-checkbox');
    checkboxes.forEach(cb => cb.checked = false);

    let count = 0;
    for (const cb of checkboxes) {
        const name = cb.value;
        let p = null;
        for (const list of Object.values(currentData.plants)) {
            p = list.find(x => x.plant_name === name);
            if (p) break;
        }
        if (!p) continue;

        let match = false;
        const status = (p.status || '').trim().toLowerCase();
        const hasPhone = Boolean(p.phone && p.phone.trim().length >= 10);

        if (criteria === 'Active') {
            match = (status === 'active');
        } else if (criteria === 'Offline') {
            match = (status === 'offline');
        } else if (criteria === 'Not Working') {
            match = (status === 'not working');
        } else if (criteria === 'Not Commissioned') {
            match = (status === 'not commissioned');
        } else if (criteria === 'ActiveWithPhone') {
            match = (status === 'active') && hasPhone;
        } else if (criteria === 'OfflineWithPhone') {
            match = (status === 'offline') && hasPhone;
        } else if (criteria === 'NotWorkingWithPhone') {
            match = (status === 'not working') && hasPhone;
        } else if (criteria === 'DeviatedWithPhone') {
            const isDeviated = (p.deviation_pct !== undefined && p.deviation_pct !== null && p.deviation_pct <= -15);
            match = isDeviated && hasPhone;
        } else if (criteria === 'ActiveOfflineWithPhone') {
            const isSendableStatus = (status === 'active' || status === 'offline' || status === 'not working');
            match = isSendableStatus && hasPhone;
        } else if (criteria === 'AllWithPhone') {
            match = hasPhone;
        } else if (criteria === 'Clear') {
            match = false;
        }

        if (match) {
            cb.checked = true;
            count++;
        }
    }
    updateSelectedCount();
    return count;
}

function selectActiveWithPhone() {
    const n = selectByCriteria('ActiveWithPhone');
    _showToast(`📱 Selected <b>${n}</b> Active plants with phone numbers`);
}

function selectOfflineWithPhone() {
    const n = selectByCriteria('OfflineWithPhone');
    _showToast(`📱 Selected <b>${n}</b> Offline plants with phone numbers`);
}

function selectNotWorkingWithPhone() {
    const n = selectByCriteria('NotWorkingWithPhone');
    _showToast(`⚠️ Selected <b>${n}</b> Not Working plants with phone numbers`);
}

function selectDeviatedWithPhone() {
    const n = selectByCriteria('DeviatedWithPhone');
    _showToast(`📉 Selected <b>${n}</b> Deviated plants (<-15%) with phone numbers`);
}

function selectActiveAndOfflineWithPhone() {
    const n = selectByCriteria('ActiveOfflineWithPhone');
    _showToast(`📱 Selected <b>${n}</b> plants with verified phone numbers (Active, Not Working & Offline)`);
}

function selectAllActive() {
    const n = selectByCriteria('Active');
    _showToast(`🟢 Selected all <b>${n}</b> Active plants`);
}

function selectAllOffline() {
    const n = selectByCriteria('Offline');
    _showToast(`🔴 Selected all <b>${n}</b> Offline plants`);
}

function selectAllNotWorking() {
    const n = selectByCriteria('Not Working');
    _showToast(`⚠️ Selected all <b>${n}</b> Not Working plants`);
}

function selectAllNotCommissioned() {
    const n = selectByCriteria('Not Commissioned');
    _showToast(`⚪ Selected all <b>${n}</b> Not Commissioned plants`);
}

function clearAllSelections() {
    selectByCriteria('Clear');
    _showToast(`✕ Cleared all selections`);
}

function onQuickSelectChange(elem) {
    const val = elem.value;
    if (!val) return;
    if (val === 'ActiveWithPhone') {
        selectActiveWithPhone();
    } else if (val === 'OfflineWithPhone') {
        selectOfflineWithPhone();
    } else if (val === 'NotWorkingWithPhone') {
        selectNotWorkingWithPhone();
    } else if (val === 'DeviatedWithPhone') {
        selectDeviatedWithPhone();
    } else if (val === 'ActiveOfflineWithPhone') {
        selectActiveAndOfflineWithPhone();
    } else if (val === 'Active') {
        selectAllActive();
    } else if (val === 'Offline') {
        selectAllOffline();
    } else if (val === 'NotWorking') {
        selectAllNotWorking();
    } else if (val === 'Not Commissioned') {
        selectAllNotCommissioned();
    } else if (val === 'First100') {
        selectFirstN(100);
        _showToast(`⚡ Selected up to 100 unsent plants`);
    } else if (val === 'First50') {
        selectFirstN(50);
        _showToast(`⚡ Selected up to 50 unsent plants`);
    } else if (val === 'AllWithPhone') {
        const n = selectByCriteria('AllWithPhone');
        _showToast(`📞 Selected all <b>${n}</b> plants with phone numbers`);
    } else if (val === 'Clear') {
        clearAllSelections();
    }
    elem.selectedIndex = 0;
}

async function cancelActiveSend() {
    try {
        const res = await fetch('/api/send/cancel', {
            method: 'POST',
            headers: _getHeaders({ 'Content-Type': 'application/json' }),
        });
        const d = await res.json();
        _showToast('✕ Stopping send queue...');
    } catch (e) {
        console.error('Failed to cancel send:', e);
    }
}

async function pauseActiveSend() {
    try {
        const res = await fetch('/api/send/pause', {
            method: 'POST',
            headers: _getHeaders({ 'Content-Type': 'application/json' }),
        });
        const d = await res.json();
        _showToast('⏸ Execution paused. Click Resume when ready.');
    } catch (e) {
        console.error('Failed to pause send:', e);
    }
}

async function resumeActiveSend() {
    try {
        const res = await fetch('/api/send/resume', {
            method: 'POST',
            headers: _getHeaders({ 'Content-Type': 'application/json' }),
        });
        const d = await res.json();
        _showToast('▶ Send execution resumed!');
    } catch (e) {
        console.error('Failed to resume send:', e);
    }
}

async function skipActiveSend() {
    try {
        const res = await fetch('/api/send/skip', {
            method: 'POST',
            headers: _getHeaders({ 'Content-Type': 'application/json' }),
        });
        const d = await res.json();
        _showToast('⏭ Skipping current contact...');
    } catch (e) {
        console.error('Failed to skip send:', e);
    }
}

async function advanceActiveSend() {
    try {
        const res = await fetch('/api/send/next', {
            method: 'POST',
            headers: _getHeaders({ 'Content-Type': 'application/json' }),
        });
        const d = await res.json();
        _showToast('⏩ Advancing to next contact...');
    } catch (e) {
        console.error('Failed to advance send:', e);
    }
}

async function sendSelectedDirect() {
    const checkboxes = document.querySelectorAll('.row-checkbox:checked');
    if (checkboxes.length === 0) {
        alert('Please select at least one plant using the checkboxes to send WhatsApp messages.');
        return;
    }

    const selectedNames = Array.from(checkboxes).map(cb => cb.value);

    // Verify which have phone numbers
    let sendable = [];
    for (const name of selectedNames) {
        for (const list of Object.values(currentData.plants)) {
            const p = list.find(x => x.plant_name === name);
            if (p && p.phone && p.message) {
                sendable.push(name);
                break;
            }
        }
    }

    if (sendable.length === 0) {
        alert('None of the selected plants have verified phone numbers. Please add phone numbers using the ➕ Add button first.');
        return;
    }

    // Double-Send Protection: Detect already sent plants among the selection
    const alreadySent = sendable.filter(name => {
        let p = null;
        for (const list of Object.values(currentData.plants)) {
            p = list.find(x => x.plant_name === name);
            if (p) break;
        }
        return (p && p.message_status && p.message_status.toLowerCase() === 'done') || sentInSession.has(name);
    });

    if (alreadySent.length > 0) {
        const unsentCount = sendable.length - alreadySent.length;
        if (unsentCount === 0) {
            const reSendAll = confirm(
                `⚠️ Double-Send Warning:\n\n` +
                `All ${alreadySent.length} selected plants were ALREADY sent for this month.\n\n` +
                `Do you want to re-send to them again?`
            );
            if (!reSendAll) return;
        } else {
            const sendOnlyUnsent = confirm(
                `🛡 Anti Double-Send Filter:\n\n` +
                `${alreadySent.length} of the ${sendable.length} selected plants were ALREADY sent for this month.\n\n` +
                `• Click OK to send ONLY to the ${unsentCount} UNSENT plants (Recommended).\n` +
                `• Click Cancel to re-send to all ${sendable.length} plants.`
            );
            if (sendOnlyUnsent) {
                sendable = sendable.filter(name => !alreadySent.includes(name));
            }
        }
    }

    const gapSelect = document.getElementById('sendSpeedSelect');
    const modeVal = gapSelect ? gapSelect.value : 'manual';
    const isManual = (modeVal === 'manual');
    const gapSeconds = isManual ? 2 : (parseInt(modeVal, 10) || 14);

    _showSpinner(`Starting WhatsApp bulk send for ${sendable.length} plant(s) [${isManual ? 'Manual Mode: You press Enter' : 'Auto Mode'}]…`);

    try {
        const res = await fetch('/api/send', {
            method:  'POST',
            headers: _getHeaders({ 'Content-Type': 'application/json' }),
            body:    JSON.stringify({
                plants: sendable,
                view: currentView,
                gap_seconds: gapSeconds,
                manual_mode: isManual,
            }),
        });
        const result = await res.json();

        if (result.success && result.job_id) {
            _pollSendStatus(result.job_id, () => {
                document.querySelectorAll('.row-checkbox:checked').forEach(cb => cb.checked = false);
                const selectAll = document.getElementById('selectAll');
                if (selectAll) selectAll.checked = false;
                updateSelectedCount();
            });
        } else {
            _hideSpinner();
            alert(result.message || 'Something went wrong starting send.');
            renderTable();
        }

    } catch (e) {
        _hideSpinner();
        alert('Network error while sending. Check the server console.');
        console.error(e);
        renderTable();
    }
}

async function sendMessages(type) {
    const checkboxes = document.querySelectorAll(`.row-checkbox[data-status="${type}"]:checked`);
    if (checkboxes.length === 0) {
        alert(`No ${type} plants are checked. Check the boxes next to the plants you want to send to.`);
        return;
    }

    const selectedNames = Array.from(checkboxes).map(cb => cb.value);
    const gapSelect = document.getElementById('sendSpeedSelect');
    const modeVal = gapSelect ? gapSelect.value : 'manual';
    const isManual = (modeVal === 'manual');
    const gapSeconds = isManual ? 2 : (parseInt(modeVal, 10) || 14);

    _showSpinner(`Starting WhatsApp send for ${selectedNames.length} ${type.toLowerCase()} plant(s)…`);

    try {
        const res = await fetch('/api/send', {
            method:  'POST',
            headers: _getHeaders({ 'Content-Type': 'application/json' }),
            body:    JSON.stringify({
                plants: selectedNames,
                view: currentView,
                gap_seconds: gapSeconds,
                manual_mode: isManual,
            }),
        });
        const result = await res.json();

        if (result.success && result.job_id) {
            _pollSendStatus(result.job_id, () => {
                checkboxes.forEach(cb => cb.checked = false);
                updateSelectedCount();
            });
        } else {
            _hideSpinner();
            alert(result.message || 'Something went wrong.');
            renderTable();
        }

    } catch (e) {
        _hideSpinner();
        alert('Network error while sending. Check the server console.');
        console.error(e);
        renderTable();
    }
}

async function _pollSendStatus(jobId, onCompleteCallback) {
    try {
        const res = await fetch(`/api/send-status/${jobId}`, { headers: _getHeaders() });
        const result = await res.json();

        if (!result.success) {
            _showError('Failed to check send status.');
            return;
        }

        if (result.status === 'running' || result.status === 'queued' || result.status === 'paused') {
            const isPaused = (result.status === 'paused');
            const isManual = Boolean(result.manual_mode);
            let msg = isPaused ? 'Execution is paused. Click Resume to continue.' : 'Sending WhatsApp messages... Please wait.';
            if (result.total > 0) {
                const cur = result.current || 0;
                const remaining = result.total - cur;
                const pct = Math.round((cur / result.total) * 100);

                let headerTitle = '🛡 Anti-Ban WhatsApp Dispatcher';
                if (isManual) {
                    headerTitle = isPaused ? '⏸ Manual Dispatcher Paused' : '👤 Manual WhatsApp Mode (Press Enter to Send)';
                } else if (isPaused) {
                    headerTitle = '⏸ Dispatcher Paused';
                }

                const pausedBannerHtml = isPaused
                    ? `<div style="background: rgba(245, 158, 11, 0.18); border: 1px solid #f59e0b; color: #fbbf24; padding: 8px 12px; border-radius: 8px; font-size: 0.8rem; margin-bottom: 12px; text-align: left; line-height: 1.4;">
                         ⚠️ <b>Execution Paused (Queue preserved)</b><br>
                         When you are ready to continue, click <b>▶ Resume Sending</b> below!
                       </div>`
                    : '';

                const manualNoticeHtml = (!isPaused && isManual)
                    ? `<div style="background: rgba(14, 165, 233, 0.15); border: 1px solid #0284c7; color: #38bdf8; padding: 10px 14px; border-radius: 8px; font-size: 0.85rem; margin-bottom: 12px; text-align: left; line-height: 1.45;">
                         👉 <b>WhatsApp Web chat opened with message pasted!</b><br>
                         Press <b>ENTER</b> on your keyboard in WhatsApp to send.<br>
                         <span style="font-size: 0.76rem; color: #94a3b8;">(Solaron will detect your Enter key, close the tab, and open the next contact automatically.)</span>
                       </div>`
                    : '';

                let actionButtonsHtml = '';
                if (isPaused) {
                    actionButtonsHtml = `
                        <div style="display: flex; gap: 8px; justify-content: center; align-items: center; flex-wrap: wrap;">
                            <button class="btn btn-sm" onclick="resumeActiveSend()" style="background: #22c55e; color: #fff; font-weight: 700; padding: 6px 18px; border-radius: 6px; border: none; cursor: pointer; box-shadow: 0 2px 8px rgba(34, 197, 94, 0.4);">▶ Resume Sending</button>
                            <button class="btn btn-outline btn-xs" onclick="cancelActiveSend()" style="border-color: #ef4444; color: #ef4444; padding: 5px 12px; border-radius: 6px; cursor: pointer;">✕ Stop Queue</button>
                        </div>`;
                } else if (isManual) {
                    actionButtonsHtml = `
                        <div style="display: flex; gap: 8px; justify-content: center; align-items: center; flex-wrap: wrap;">
                            <button class="btn btn-sm" onclick="pauseActiveSend()" style="background: rgba(245, 158, 11, 0.25); border: 1px solid #f59e0b; color: #fbbf24; font-weight: 700; padding: 6px 14px; border-radius: 6px; cursor: pointer;" title="Pause execution">⏸ Pause</button>
                            <button class="btn btn-sm" onclick="skipActiveSend()" style="background: rgba(148, 163, 184, 0.2); border: 1px solid #64748b; color: #cbd5e1; font-weight: 600; padding: 6px 12px; border-radius: 6px; cursor: pointer;" title="Skip sending to this contact">⏭ Skip Plant</button>
                            <button class="btn btn-sm" onclick="advanceActiveSend()" style="background: rgba(56, 189, 248, 0.22); border: 1px solid #0284c7; color: #38bdf8; font-weight: 600; padding: 6px 12px; border-radius: 6px; cursor: pointer;" title="Click if you sent the message via mouse in WhatsApp">⏩ I Sent It / Next</button>
                            <button class="btn btn-outline btn-xs" onclick="cancelActiveSend()" style="border-color: rgba(239, 68, 68, 0.5); color: #f87171; padding: 6px 12px; border-radius: 6px; cursor: pointer;">✕ Stop</button>
                        </div>`;
                } else {
                    actionButtonsHtml = `
                        <div style="display: flex; gap: 8px; justify-content: center; align-items: center; flex-wrap: wrap;">
                            <button class="btn btn-sm" onclick="pauseActiveSend()" style="background: rgba(245, 158, 11, 0.25); border: 1px solid #f59e0b; color: #fbbf24; font-weight: 700; padding: 5px 14px; border-radius: 6px; cursor: pointer;" title="Pause execution without killing the process">⏸ Pause Execution</button>
                            <button class="btn btn-outline btn-xs" onclick="cancelActiveSend()" style="border-color: rgba(255,255,255,0.25); color: #94a3b8; padding: 5px 12px; border-radius: 6px; cursor: pointer;">✕ Stop</button>
                        </div>`;
                }

                const pacingText = isManual
                    ? `👤 Manual Pacing: Waits for your Enter key`
                    : `⏱ Auto Pacing: 12-16s human delays + breaks`;

                msg = `<div style="text-align: center; min-width: 330px; padding: 4px;">
                         <div style="font-weight: 700; font-size: 1.05rem; color: ${isPaused ? '#fbbf24' : '#38bdf8'}; margin-bottom: 6px;">
                           ${headerTitle}
                         </div>
                         ${pausedBannerHtml}
                         ${manualNoticeHtml}
                         <div style="font-size: 0.92rem; color: #38bdf8; margin-bottom: 8px;"><b>${cur}</b> of <b>${result.total}</b> plants processed (${pct}%)</div>
                         <div style="background: rgba(255,255,255,0.12); border-radius: 9999px; height: 10px; width: 100%; overflow: hidden; margin-bottom: 12px;">
                           <div style="background: ${isPaused ? 'linear-gradient(90deg, #f59e0b, #eab308)' : 'linear-gradient(90deg, #38bdf8, #22c55e)'}; height: 100%; width: ${pct}%; transition: width 0.3s ease; border-radius: 9999px;"></div>
                         </div>
                         <div style="font-size: 0.82rem; color: #cbd5e1; margin-bottom: 6px;"><b>Current:</b> ${result.current_plant || 'Opening WhatsApp...'}</div>
                         <div style="font-size: 0.76rem; color: #94a3b8; margin-bottom: 14px;">${pacingText}</div>
                         ${actionButtonsHtml}
                       </div>`;
            }
            _showSpinner(msg);
            setTimeout(() => _pollSendStatus(jobId, onCompleteCallback), 1000);
        } else if (result.status === 'done' || result.status === 'cancelled') {
            if (result.sent_plants) {
                result.sent_plants.forEach(name => sentInSession.add(name));
            }
            _hideSpinner();
            renderTable();
            if (onCompleteCallback) {
                try { onCompleteCallback(); } catch(err) { console.error(err); }
            }
            const skippedText = result.skipped ? `, ${result.skipped} skipped` : '';
            if (result.status === 'cancelled') {
                alert(`⚠️ Send batch stopped: ${result.sent} messages were sent${skippedText} before stopping.`);
            } else {
                alert(`✅ Batch send complete: ${result.sent} sent successfully${skippedText}, ${result.failed} failed.`);
            }
        } else if (result.status === 'error') {
            _showError(result.error || 'Background send failed.');
            renderTable();
        }
    } catch (e) {
        _showError('Network error checking send status.');
        console.error(e);
        renderTable();
    }
}


// ── Test WhatsApp Send ─────────────────────────────────────────────────────

async function testWhatsAppModal() {
    const testNum = config.test_phone_number || '';
    const userPhone = prompt("Enter the phone number to send a test WhatsApp message to:", testNum);
    if (!userPhone) return;

    const confirmed = confirm(
        `Send a test WhatsApp message to ${userPhone}?\n\n` +
        `Make sure Google Chrome is open and logged into WhatsApp Web.`
    );
    if (!confirmed) return;

    _showSpinner(`Sending test WhatsApp message to ${userPhone}...`);

    try {
        const res = await fetch('/api/test-send', {
            method: 'POST',
            headers: _getHeaders({ 'Content-Type': 'application/json' }),
            body: JSON.stringify({ phone: userPhone }),
        });
        const result = await res.json();

        renderTable();

        if (result.success && result.results?.sent > 0) {
            alert(`✅ Test message sent successfully to ${userPhone}!`);
        } else if (result.whatsapp_url) {
            const openNow = confirm(
                `Background send finished with ${result.results?.sent || 0} sent.\n` +
                `Would you like to open WhatsApp Web directly to verify delivery?`
            );
            if (openNow) {
                window.open(result.whatsapp_url, 'SolaronWhatsApp');
            }
        } else {
            alert(`Test send result: ${result.message || JSON.stringify(result)}`);
        }
    } catch (e) {
        alert(`Error during test send: ${e}`);
        console.error(e);
        renderTable();
    }
}


// ── Monsoon Alert ──────────────────────────────────────────────────────────

async function triggerMonsoon() {
    const confirmed = confirm(
        '⚠️  MONSOON ALERT\n\n' +
        'This will send the seasonal monsoon check message to ALL contacts\n' +
        'that have a phone number in the current data set.\n\n' +
        'Only use this during June or July. Proceed?'
    );
    if (!confirmed) return;

    _showSpinner('Sending monsoon alert to all contacts…');

    try {
        const res = await fetch('/api/monsoon', { 
            method: 'POST',
            headers: _getHeaders()
        });
        const result = await res.json();
        
        if (result.success && result.job_id) {
            _pollSendStatus(result.job_id);
        } else {
            alert(result.message || 'Something went wrong.');
            renderTable();
        }
    } catch (e) {
        alert('Network error. Check server console.');
        console.error(e);
        renderTable();
    }
}


// ── Helpers ────────────────────────────────────────────────────────────────

function _applyResult(result) {
    currentData.plants = result.data   || {};
    currentData.counts = result.counts || {};
    if (result.config) {
        config = result.config;
        const testBtn = document.getElementById('testSendBtn');
        if (testBtn && config.test_phone_number) {
            testBtn.textContent = `📱 Test Send (${config.test_phone_number})`;
        }
        if (config.year && config.month_name) {
            syncCalendarPickerState(config.year, config.month_name);
        }
    }
    updateStats();
    renderTable();
}

function _showSpinner(msgHtml) {
    const tbody = document.getElementById('plantsBody');
    if (tbody) {
        tbody.innerHTML = `
            <tr><td colspan="11">
                <div class="spinner-wrap">
                    <div class="spinner"></div>
                    <div>${msgHtml}</div>
                </div>
            </td></tr>`;
    }
}

function _showError(msg) {
    const tbody = document.getElementById('plantsBody');
    if (tbody) {
        tbody.innerHTML = `
            <tr><td colspan="11">
                <div class="empty-state">
                    <strong>Error</strong>
                    <p>${_esc(msg)}</p>
                </div>
            </td></tr>`;
    }
}

function _setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
}

function _esc(str) {
    return String(str ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/'/g, '&#039;');
}

function _getHeaders(extraHeaders = {}) {
    const headers = { ...extraHeaders };
    const metaApiKey = document.querySelector('meta[name="api-key"]');
    if (metaApiKey && metaApiKey.content) {
        headers['X-API-Key'] = metaApiKey.content;
    }
    return headers;
}

// ── Diagnostics & Automated Health Checks ──────────────────────────────────

let lastDiagnostics = null;

async function _fetchDiagnostics() {
    try {
        const res = await fetch('/api/diagnostics', { headers: _getHeaders() });
        const data = await res.json();
        if (data.success) {
            lastDiagnostics = data;
            const badge = document.getElementById('systemHealthBadge');
            if (badge) {
                if (data.status === 'healthy') {
                    badge.className = 'status-badge badge-active';
                    badge.textContent = '🟢 System Healthy';
                } else if (data.status === 'warning') {
                    badge.className = 'status-badge badge-nc';
                    badge.style.background = 'rgba(234, 179, 8, 0.2)';
                    badge.style.color = '#facc15';
                    badge.style.borderColor = 'rgba(234, 179, 8, 0.4)';
                    badge.textContent = `🟡 ${data.warnings.length} Notice(s)`;
                } else {
                    badge.className = 'status-badge badge-offline';
                    badge.textContent = '🔴 Attention Needed';
                }
            }
        }
    } catch (e) {
        console.debug('Diagnostics fetch note:', e);
    }
}

function showDiagnosticsModal() {
    const modal = document.getElementById('diagnosticsModal');
    if (!modal) return;

    if (!lastDiagnostics) {
        _fetchDiagnostics().then(() => renderDiagnosticsContent());
    } else {
        renderDiagnosticsContent();
    }
    modal.style.display = 'flex';
}

function closeDiagnosticsModal() {
    const modal = document.getElementById('diagnosticsModal');
    if (modal) modal.style.display = 'none';
}

function closeDiagnosticsOnBackdrop(event) {
    if (event.target === document.getElementById('diagnosticsModal')) {
        closeDiagnosticsModal();
    }
}

function renderDiagnosticsContent() {
    const diag = lastDiagnostics;
    const content = document.getElementById('diagContent');
    const summaryMsg = document.getElementById('diagSummaryMsg');

    if (!diag || !content) return;

    if (summaryMsg) summaryMsg.textContent = diag.status_message;

    let html = `
        <div style="background: rgba(15, 23, 42, 0.6); padding: 12px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.08);">
            <strong style="color: #38bdf8;">🌐 Portal Integrations & Local Cache</strong>
            <ul style="margin: 8px 0 0 0; padding-left: 20px; font-size: 0.85rem; color: #cbd5e1;">
                <li><b>Growatt:</b> ${diag.portals.growatt.configured ? '✅ Ready' : '❌ Credentials Missing'} — ${diag.portals.growatt.plant_count} plants cached (${diag.portals.growatt.cache_fresh_today ? 'Fresh today' : 'Cache stored'})</li>
                <li><b>iSolarCloud:</b> ${diag.portals.isolarcloud.configured ? '✅ Ready' : '❌ Credentials Missing'} — ${diag.portals.isolarcloud.plant_count} plants cached (${diag.portals.isolarcloud.cache_fresh_today ? 'Fresh today' : 'Cache stored'})</li>
                <li><b>SuryaLog:</b> ${diag.portals.suryalog.configured ? '✅ Ready' : '❌ Credentials Missing'} — ${diag.portals.suryalog.plant_count} plants cached (${diag.portals.suryalog.cache_fresh_today ? 'Fresh today' : 'Cache stored'})</li>
            </ul>
        </div>

        <div style="background: rgba(15, 23, 42, 0.6); padding: 12px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.08);">
            <strong style="color: #4ade80;">📱 Contact Resolution & Database Health</strong>
            <ul style="margin: 8px 0 0 0; padding-left: 20px; font-size: 0.85rem; color: #cbd5e1;">
                <li>Total Verified Contacts in Database: <b>${diag.contacts.total_cached_contacts}</b></li>
                <li>Fleet Plants with Verified Phone: <b style="color: #4ade80;">${diag.contacts.fleet_with_phone}</b></li>
                <li>Fleet Plants Missing Phone: <b style="color: ${diag.contacts.fleet_without_phone > 0 ? '#ef4444' : '#4ade80'};">${diag.contacts.fleet_without_phone}</b></li>
            </ul>
        </div>

        <div style="background: rgba(15, 23, 42, 0.6); padding: 12px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.08);">
            <strong style="color: #fb923c;">⚡ Automation & Background Scheduler</strong>
            <ul style="margin: 8px 0 0 0; padding-left: 20px; font-size: 0.85rem; color: #cbd5e1;">
                <li>Auto-Load on Startup: <b>${diag.automation.auto_load_on_startup ? 'Enabled (Zero Wait)' : 'Disabled'}</b></li>
                <li>Auto-Sync Scheduler: <b>${diag.automation.auto_sync_enabled ? 'Active Daemon' : 'Disabled'}</b></li>
                <li>Daily Generation Sync: <b>Daily at ${diag.automation.daily_sync_hour}:00 IST</b></li>
                <li>Monthly Report Sync: <b>Day ${diag.automation.monthly_sync_day} of month</b></li>
            </ul>
        </div>
    `;

    if (diag.warnings && diag.warnings.length > 0) {
        html += `
            <div style="background: rgba(234, 179, 8, 0.1); border: 1px solid rgba(234, 179, 8, 0.3); padding: 10px; border-radius: 8px; font-size: 0.82rem; color: #fde047;">
                <strong>⚠️ Active Notices:</strong>
                <ul style="margin: 4px 0 0 0; padding-left: 18px;">
                    ${diag.warnings.map(w => `<li>${_esc(w)}</li>`).join('')}
                </ul>
            </div>
        `;
    }

    content.innerHTML = html;
}


// ── Direct Contact Editing & CSV Import ────────────────────────────────────

let _editingPlantName = '';

function openEditContactModal(encodedPlantName, encodedPhone) {
    const plantName = decodeURIComponent(encodedPlantName || '');
    const phone = decodeURIComponent(encodedPhone || '');
    _editingPlantName = plantName;

    const plantEl = document.getElementById('editContactPlantName');
    const phoneEl = document.getElementById('editContactPhone');
    const hintEl = document.getElementById('editContactHint');

    if (plantEl) plantEl.value = plantName;
    if (phoneEl) {
        phoneEl.value = phone;
        phoneEl.style.borderColor = '';
    }
    if (hintEl) {
        hintEl.textContent = 'Must be a valid 10-digit Indian mobile number (starting with 6, 7, 8, or 9).';
        hintEl.style.color = '#64748b';
    }

    const modal = document.getElementById('contactModal');
    if (modal) {
        modal.style.display = 'flex';
        setTimeout(() => phoneEl?.focus(), 100);
    }
}

function closeContactModal() {
    const modal = document.getElementById('contactModal');
    if (modal) modal.style.display = 'none';
}

function closeContactModalOnBackdrop(event) {
    if (event.target === document.getElementById('contactModal')) {
        closeContactModal();
    }
}

async function saveContactDirect() {
    const phoneInput = document.getElementById('editContactPhone');
    const hintEl = document.getElementById('editContactHint');
    const saveBtn = document.getElementById('saveContactBtn');
    const rawPhone = (phoneInput?.value || '').trim();

    // Sanitize digits
    let digits = rawPhone.replace(/\D/g, '');
    if (digits.length === 12 && digits.startsWith('91')) digits = digits.slice(2);
    if (digits.length === 11 && digits.startsWith('0')) digits = digits.slice(1);

    if (digits.length !== 10 || !/^[6-9]\d{9}$/.test(digits)) {
        if (hintEl) {
            hintEl.textContent = '❌ Please enter a valid 10-digit Indian mobile number starting with 6, 7, 8, or 9.';
            hintEl.style.color = '#ef4444';
        }
        if (phoneInput) phoneInput.style.borderColor = '#ef4444';
        phoneInput?.focus();
        return;
    }

    if (saveBtn) {
        saveBtn.disabled = true;
        saveBtn.textContent = 'Saving...';
    }

    try {
        const res = await fetch('/api/contacts/update', {
            method: 'POST',
            headers: _getHeaders({ 'Content-Type': 'application/json' }),
            body: JSON.stringify({ plant_name: _editingPlantName, phone: digits })
        });
        const result = await res.json();

        if (result.success) {
            closeContactModal();
            // Update in local data
            for (const statusList of Object.values(currentData.plants)) {
                for (const p of statusList) {
                    if ((p.plant_name || '').trim().toLowerCase() === _editingPlantName.trim().toLowerCase()) {
                        p.phone = digits;
                        if (result.plant && result.plant.whatsapp_url) {
                            p.whatsapp_url = result.plant.whatsapp_url;
                            p.message = result.plant.message;
                        }
                    }
                }
            }
            renderTable();
            _fetchDiagnostics();
            alert(`✅ Phone number for ${_editingPlantName} set to ${digits}.`);
        } else {
            alert(result.error || 'Failed to update contact.');
        }
    } catch (e) {
        console.error(e);
        alert('Network error while saving contact.');
    } finally {
        if (saveBtn) {
            saveBtn.disabled = false;
            saveBtn.textContent = '💾 Save Contact';
        }
    }
}

let _selectedContactsCsvFile = null;

function openImportContactsModal() {
    _selectedContactsCsvFile = null;
    const fileInput = document.getElementById('contactsCsvFileInput');
    const nameEl = document.getElementById('selectedCsvFilename');
    const statusBox = document.getElementById('importStatusBox');
    const uploadBtn = document.getElementById('uploadContactsBtn');

    if (fileInput) fileInput.value = '';
    if (nameEl) nameEl.textContent = 'No file selected';
    if (statusBox) statusBox.style.display = 'none';
    if (uploadBtn) {
        uploadBtn.disabled = true;
        uploadBtn.textContent = '🚀 Import & Synchronize';
    }

    const modal = document.getElementById('importContactsModal');
    if (modal) modal.style.display = 'flex';
}

function closeImportContactsModal() {
    const modal = document.getElementById('importContactsModal');
    if (modal) modal.style.display = 'none';
}

function closeImportModalOnBackdrop(event) {
    if (event.target === document.getElementById('importContactsModal')) {
        closeImportContactsModal();
    }
}

function onContactsCsvSelected() {
    const input = document.getElementById('contactsCsvFileInput');
    const nameEl = document.getElementById('selectedCsvFilename');
    const uploadBtn = document.getElementById('uploadContactsBtn');

    if (input && input.files.length > 0) {
        _selectedContactsCsvFile = input.files[0];
        if (nameEl) nameEl.textContent = `📄 ${_selectedContactsCsvFile.name} (${Math.round(_selectedContactsCsvFile.size / 1024)} KB)`;
        if (uploadBtn) uploadBtn.disabled = false;
    } else {
        _selectedContactsCsvFile = null;
        if (nameEl) nameEl.textContent = 'No file selected';
        if (uploadBtn) uploadBtn.disabled = true;
    }
}

async function uploadContactsCsv() {
    if (!_selectedContactsCsvFile) return;

    const uploadBtn = document.getElementById('uploadContactsBtn');
    const statusBox = document.getElementById('importStatusBox');

    if (uploadBtn) {
        uploadBtn.disabled = true;
        uploadBtn.textContent = 'Importing...';
    }
    if (statusBox) {
        statusBox.style.display = 'block';
        statusBox.style.background = 'rgba(14, 165, 233, 0.15)';
        statusBox.style.color = '#38bdf8';
        statusBox.style.border = '1px solid rgba(14, 165, 233, 0.3)';
        statusBox.textContent = 'Processing CSV contacts and matching fleet plants...';
    }

    const form = new FormData();
    form.append('file', _selectedContactsCsvFile);

    try {
        const res = await fetch('/api/contacts/import-csv', {
            method: 'POST',
            body: form,
            headers: _getHeaders()
        });
        const result = await res.json();

        if (result.success) {
            if (statusBox) {
                statusBox.style.background = 'rgba(34, 197, 94, 0.15)';
                statusBox.style.color = '#4ade80';
                statusBox.style.border = '1px solid rgba(34, 197, 94, 0.3)';
                statusBox.innerHTML = `
                    <b>✅ Import Successful!</b><br>
                    ${result.message}<br>
                    <small>Fleet plants with phone: <strong>${result.fleet_with_phone || 0}</strong> / ${result.total_fleet || 0}</small>
                `;
            }
            if (result.data) {
                _applyResult(result);
            }
            _fetchDiagnostics();
            setTimeout(() => {
                closeImportContactsModal();
                alert(`✅ ${result.message}\nFleet plants with phone: ${result.fleet_with_phone || 0} / ${result.total_fleet || 0}`);
            }, 1200);
        } else {
            if (statusBox) {
                statusBox.style.background = 'rgba(239, 68, 68, 0.15)';
                statusBox.style.color = '#ef4444';
                statusBox.style.border = '1px solid rgba(239, 68, 68, 0.3)';
                statusBox.textContent = result.error || 'Failed to import contacts.';
            }
            if (uploadBtn) uploadBtn.disabled = false;
        }
    } catch (e) {
        console.error(e);
        if (statusBox) {
            statusBox.style.background = 'rgba(239, 68, 68, 0.15)';
            statusBox.style.color = '#ef4444';
            statusBox.style.border = '1px solid rgba(239, 68, 68, 0.3)';
            statusBox.textContent = 'Network error during CSV upload.';
        }
        if (uploadBtn) uploadBtn.disabled = false;
    }
}

/* ==========================================================================
   SOLARON CRM & MESSAGING HUB CLIENT LOGIC
   Directory • Monthly Statements • Yearly Milestones • Campaigns • Alerts
   ========================================================================== */

let _currentHubMode = 'telemetry';
let _crmCustPage = 1;
const _crmCustPageSize = 50;
let _crmYearlyChart = null;
let _selectedCampaignId = null;

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    // Check CRM health in background
    setTimeout(loadDataHealth, 800);

    // Set default month/year for CRM pickers
    const now = new Date();
    const curMonthStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
    const stmtMonthInput = document.getElementById('crmStatementMonth');
    if (stmtMonthInput && !stmtMonthInput.value) {
        stmtMonthInput.value = curMonthStr;
    }
});

/** Switch between Telemetry (Fleet) and CRM Hub Views */
function switchHubMode(mode) {
    _currentHubMode = mode;

    // Reset button active states
    const navButtons = {
        'telemetry': 'hubTabTelemetry',
        'directory': 'hubTabDirectory',
        'monthly': 'hubTabMonthly',
        'yearly': 'hubTabYearly',
        'campaigns': 'hubTabCampaigns',
        'alerts': 'hubTabAlerts'
    };

    Object.keys(navButtons).forEach(m => {
        const btn = document.getElementById(navButtons[m]);
        if (btn) btn.classList.toggle('active', m === mode);
    });

    // Hide/show sections
    const telemetrySec = document.getElementById('telemetryViewSection');
    const sections = {
        'directory': 'crmDirectorySection',
        'monthly': 'crmMonthlySection',
        'yearly': 'crmYearlySection',
        'campaigns': 'crmCampaignsSection',
        'alerts': 'crmAlertsSection'
    };

    if (telemetrySec) {
        telemetrySec.style.display = (mode === 'telemetry') ? 'block' : 'none';
    }

    Object.keys(sections).forEach(s => {
        const el = document.getElementById(sections[s]);
        if (el) {
            el.classList.toggle('active', s === mode);
        }
    });

    // Load data for selected mode
    if (mode === 'directory') {
        loadDataHealth();
        loadCrmOverviewStats();
        loadCustomersList(_crmCustPage);
    } else if (mode === 'monthly') {
        loadMonthlyStatements();
    } else if (mode === 'yearly') {
        loadYearlyMilestones();
    } else if (mode === 'campaigns') {
        loadCampaignsList();
    } else if (mode === 'alerts') {
        loadOfflineAlerts();
    }
}

/** Fetch live Data Health Audit from /api/crm/health */
async function loadDataHealth() {
    try {
        const res = await fetch('/api/crm/health', {
            headers: API_KEY ? { 'X-API-Key': API_KEY } : {}
        });
        if (!res.ok) return;
        const data = await res.json();

        // Update badge
        const badgeBtn = document.getElementById('crmDataHealthBadge');
        const badgeTxt = document.getElementById('dataHealthBadgeText');
        if (badgeBtn && badgeTxt) {
            if (data.total_issues > 0) {
                badgeBtn.className = 'data-health-badge-btn';
                badgeTxt.textContent = `⚠️ Data Health: ${data.total_issues} Issues`;
            } else {
                badgeBtn.className = 'data-health-badge-btn healthy';
                badgeTxt.textContent = `🟢 Data Health: Perfect (0 Issues)`;
            }
        }

        // Update widget metrics
        const elTotal = document.getElementById('dhTotalCustomers');
        const elReady = document.getElementById('dhReady');
        const elMissing = document.getElementById('dhMissingPhones');
        const elOptedOut = document.getElementById('dhOptedOut');
        const elUnmapped = document.getElementById('dhUnmapped');

        if (elTotal) elTotal.textContent = data.total_customers || 0;
        if (elReady) elReady.textContent = `${data.ready_to_message || 0} ✓`;
        if (elMissing) elMissing.textContent = data.missing_phones || 0;
        if (elOptedOut) elOptedOut.textContent = data.opted_out || 0;
        if (elUnmapped) elUnmapped.textContent = data.unmapped_plants || 0;
    } catch (e) {
        console.warn('Data health check note:', e);
    }
}

/** Quick filter helper from Data Health widget */
function filterDirectory(type) {
    switchHubMode('directory');
    const optInFilter = document.getElementById('crmOptInFilter');
    const phoneFilter = document.getElementById('crmPhoneFilter');
    const searchInput = document.getElementById('crmSearchInput');

    if (searchInput) searchInput.value = '';

    if (type === 'ready') {
        if (optInFilter) optInFilter.value = 'active';
        if (phoneFilter) phoneFilter.value = 'true';
    } else if (type === 'missing_phone') {
        if (optInFilter) optInFilter.value = '';
        if (phoneFilter) phoneFilter.value = 'false';
    } else if (type === 'opted_out') {
        if (optInFilter) optInFilter.value = 'do_not_send';
        if (phoneFilter) phoneFilter.value = '';
    } else if (type === 'unmapped') {
        loadUnmappedDirectory();
        return;
    } else {
        if (optInFilter) optInFilter.value = '';
        if (phoneFilter) phoneFilter.value = '';
    }
    loadCustomersList(1);
}

/** Load Customer Directory */
async function loadCustomersList(page = 1) {
    _crmCustPage = page;
    const search = document.getElementById('crmSearchInput')?.value || '';
    const platform = document.getElementById('crmPlatformFilter')?.value || '';
    const optIn = document.getElementById('crmOptInFilter')?.value || '';
    const hasPhone = document.getElementById('crmPhoneFilter')?.value || '';

    const params = new URLSearchParams({
        page: page,
        page_size: _crmCustPageSize
    });
    if (search) params.append('search', search);
    if (platform) params.append('platform', platform);
    if (optIn) params.append('opt_in_status', optIn);
    if (hasPhone) params.append('has_phone', hasPhone);

    const tbody = document.getElementById('crmCustomersBody');
    if (tbody) tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding:24px; color:var(--text-muted);">Loading customers...</td></tr>`;

    try {
        const res = await fetch(`/api/crm/customers?${params.toString()}`, {
            headers: API_KEY ? { 'X-API-Key': API_KEY } : {}
        });
        const data = await res.json();
        renderCustomersTable(data.customers || [], data.total || 0, data.page || 1, data.page_size || 50);
    } catch (e) {
        console.error('Failed to load customers:', e);
        if (tbody) tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding:24px; color:#ef4444;">Failed to load customers from server.</td></tr>`;
    }
}

/** Load Unmapped Plants List */
async function loadUnmappedDirectory() {
    const tbody = document.getElementById('crmCustomersBody');
    if (tbody) tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding:24px; color:var(--text-muted);">Checking unmapped plants...</td></tr>`;

    try {
        const res = await fetch('/api/crm/customers?unmapped_only=true', {
            headers: API_KEY ? { 'X-API-Key': API_KEY } : {}
        });
        const data = await res.json();
        const unmapped = data.customers || [];
        if (unmapped.length === 0) {
            tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding:30px; color:#22c55e;">🎉 All plants in metadata have matching customer records! (0 unmapped)</td></tr>`;
            document.getElementById('crmPaginationInfo').textContent = 'Showing 0 unmapped plants';
            return;
        }

        let html = '';
        unmapped.forEach((u, i) => {
            html += `
                <tr>
                    <td style="color:#ef4444; font-weight:700;">(Unmapped Plant)</td>
                    <td><strong>${_escapeHtml(u.plant_name)}</strong> <small style="color:var(--text-muted)">(${_escapeHtml(u.plant_id)})</small></td>
                    <td><span class="p-chip p-${_escapeHtml(u.platform)}">${_escapeHtml(u.platform)}</span></td>
                    <td style="color:var(--text-muted); font-style:italic;">No phone record</td>
                    <td><span class="crm-badge pending">UNMAPPED</span></td>
                    <td>English</td>
                    <td><small style="color:var(--text-muted)">${_escapeHtml(u.city || '')} (${u.capacity_kwp} kWp)</small></td>
                    <td>
                        <button class="btn btn-primary btn-sm" onclick="mapCustomerDirectly('${_escapeHtml(u.plant_id)}', '${_escapeHtml(u.plant_name)}', '${_escapeHtml(u.platform)}')">
                            + Map Customer
                        </button>
                    </td>
                </tr>
            `;
        });
        tbody.innerHTML = html;
        document.getElementById('crmPaginationInfo').textContent = `Showing ${unmapped.length} unmapped plants`;
    } catch (e) {
        console.error(e);
    }
}

/** Render Customers Table Rows */
function renderCustomersTable(customers, total, page, pageSize) {
    const tbody = document.getElementById('crmCustomersBody');
    if (!tbody) return;

    if (customers.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding:30px; color:var(--text-muted);">No matching customers found.</td></tr>`;
        document.getElementById('crmPaginationInfo').textContent = 'Showing 0 of 0 customers';
        return;
    }

    let html = '';
    customers.forEach(c => {
        const optBadgeClass = c.opt_in_status === 'active' ? 'active' : (c.opt_in_status === 'do_not_send' ? 'opted-out' : 'pending');
        const optLabel = c.opt_in_status === 'active' ? 'Active' : (c.opt_in_status === 'do_not_send' ? 'Opted Out' : 'Pending');
        const phoneFormatted = c.phone_number ? `<span style="font-family:'JetBrains Mono',monospace; color:#38bdf8;">${_escapeHtml(c.phone_number)}</span>` : `<span style="color:#f59e0b; font-style:italic;">⚠️ Missing Phone</span>`;

        html += `
            <tr id="custRow-${c.customer_id}" ondblclick="startInlineEditCustomer(${c.customer_id})">
                <td id="cell-name-${c.customer_id}" style="font-weight:700; color:var(--text-primary);">
                    ${_escapeHtml(c.customer_name || 'UNMAPPED')}
                </td>
                <td id="cell-plant-${c.customer_id}">
                    <strong>${_escapeHtml(c.plant_name || '')}</strong>
                    <div style="font-size:0.72rem; color:var(--text-muted)">ID: ${_escapeHtml(c.plant_id || '')}</div>
                </td>
                <td>
                    <span class="p-chip p-${_escapeHtml(c.platform || 'growatt')}">${_escapeHtml(c.platform || 'growatt')}</span>
                </td>
                <td id="cell-phone-${c.customer_id}">
                    ${phoneFormatted}
                </td>
                <td id="cell-optin-${c.customer_id}">
                    <span class="crm-badge ${optBadgeClass}">${optLabel}</span>
                </td>
                <td id="cell-lang-${c.customer_id}" style="text-transform:capitalize; color:var(--text-secondary);">
                    ${_escapeHtml(c.preferred_lang || 'english')}
                </td>
                <td id="cell-notes-${c.customer_id}" style="font-size:0.78rem; color:var(--text-muted); max-width:180px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${_escapeHtml(c.notes || '')}">
                    ${_escapeHtml(c.notes || '—')}
                </td>
                <td id="cell-actions-${c.customer_id}">
                    <div style="display:flex; gap:4px; flex-wrap:wrap;">
                        <button class="btn btn-primary btn-sm" onclick="openCustomerFullProfile(${c.customer_id})" title="View full customer profile & history" style="padding:3px 8px; font-size:0.75rem;">
                            📊 Profile
                        </button>
                        <button class="btn btn-secondary btn-sm" onclick="startInlineEditCustomer(${c.customer_id})" title="Inline edit customer details" style="padding:3px 8px; font-size:0.75rem;">
                            ✏️ Edit
                        </button>
                    </div>
                </td>
            </tr>
        `;
    });

    tbody.innerHTML = html;

    // Pagination display
    const startIdx = (page - 1) * pageSize + 1;
    const endIdx = Math.min(total, page * pageSize);
    const infoEl = document.getElementById('crmPaginationInfo');
    if (infoEl) infoEl.textContent = `Showing ${startIdx}–${endIdx} of ${total} customers`;

    const badgeEl = document.getElementById('crmCurrentPageBadge');
    if (badgeEl) badgeEl.textContent = `Page ${page} / ${Math.ceil(total / pageSize) || 1}`;

    const prevBtn = document.getElementById('crmPrevPageBtn');
    const nextBtn = document.getElementById('crmNextPageBtn');
    if (prevBtn) prevBtn.disabled = (page <= 1);
    if (nextBtn) nextBtn.disabled = (endIdx >= total);
}

function changeCustomerPage(delta) {
    const target = _crmCustPage + delta;
    if (target >= 1) {
        loadCustomersList(target);
    }
}

/** Inline Editing for Customer Row */
function startInlineEditCustomer(custId) {
    const row = document.getElementById(`custRow-${custId}`);
    if (!row || row.dataset.isEditing === 'true') return;
    row.dataset.isEditing = 'true';

    const cellName = document.getElementById(`cell-name-${custId}`);
    const cellPhone = document.getElementById(`cell-phone-${custId}`);
    const cellOptIn = document.getElementById(`cell-optin-${custId}`);
    const cellActions = document.getElementById(`cell-actions-${custId}`);

    const curName = cellName.textContent.trim();
    const curPhoneRaw = cellPhone.textContent.includes('+') ? cellPhone.textContent.trim() : (cellPhone.textContent.match(/\d{10,12}/) ? cellPhone.textContent.match(/\d{10,12}/)[0] : '');

    row.dataset.origName = curName;
    row.dataset.origPhone = curPhoneRaw;

    cellName.innerHTML = `<input type="text" id="inlineName-${custId}" class="crm-inline-input" value="${_escapeHtml(curName)}">`;
    cellPhone.innerHTML = `<input type="text" id="inlinePhone-${custId}" class="crm-inline-input" placeholder="+91XXXXXXXXXX" value="${_escapeHtml(curPhoneRaw)}">`;
    cellOptIn.innerHTML = `
        <select id="inlineOptIn-${custId}" class="crm-inline-input">
            <option value="active">Active</option>
            <option value="pending">Pending</option>
            <option value="do_not_send">Do Not Send</option>
        </select>
    `;
    cellActions.innerHTML = `
        <div style="display:flex; gap:4px;">
            <button class="btn btn-emerald btn-sm" onclick="saveInlineEditCustomer(${custId})" style="padding:2px 6px; font-size:0.75rem;">💾</button>
            <button class="btn btn-ghost btn-sm" onclick="cancelInlineEditCustomer(${custId})" style="padding:2px 6px; font-size:0.75rem;">✕</button>
        </div>
    `;
}

async function saveInlineEditCustomer(custId) {
    const name = document.getElementById(`inlineName-${custId}`)?.value.trim();
    const phone = document.getElementById(`inlinePhone-${custId}`)?.value.trim();
    const optIn = document.getElementById(`inlineOptIn-${custId}`)?.value;

    try {
        const res = await fetch(`/api/crm/customers/${custId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...(API_KEY ? { 'X-API-Key': API_KEY } : {})
            },
            body: JSON.stringify({
                customer_name: name,
                phone_number: phone,
                opt_in_status: optIn
            })
        });

        if (res.ok) {
            loadDataHealth();
            loadCustomersList(_crmCustPage);
        } else {
            alert('Failed to update customer.');
        }
    } catch (e) {
        console.error(e);
        alert('Error updating customer.');
    }
}

function cancelInlineEditCustomer(custId) {
    loadCustomersList(_crmCustPage);
}

/** Add Customer Modal */
function openAddCustomerModal() {
    document.getElementById('crmModalTitle').textContent = '+ Add Customer';
    document.getElementById('crmFormCustId').value = '';
    document.getElementById('crmCustomerForm').reset();
    document.getElementById('crmCustomerModal').style.display = 'flex';
}

function mapCustomerDirectly(plantId, plantName, platform) {
    openAddCustomerModal();
    document.getElementById('crmFormPlantId').value = plantId;
    document.getElementById('crmFormPlantName').value = plantName;
    document.getElementById('crmFormName').value = plantName;
    document.getElementById('crmFormPlatform').value = platform || 'growatt';
}

function closeCustomerModal() {
    document.getElementById('crmCustomerModal').style.display = 'none';
}

async function saveCustomerForm(e) {
    e.preventDefault();
    const custId = document.getElementById('crmFormCustId').value;
    const name = document.getElementById('crmFormName').value.trim();
    const plantId = document.getElementById('crmFormPlantId').value.trim();
    const plantName = document.getElementById('crmFormPlantName').value.trim();
    const platform = document.getElementById('crmFormPlatform').value;
    const phone = document.getElementById('crmFormPhone').value.trim();
    const optIn = document.getElementById('crmFormOptIn').value;
    const lang = document.getElementById('crmFormLang').value;
    const notes = document.getElementById('crmFormNotes').value.trim();

    const payload = {
        customer_name: name,
        plant_id: plantId,
        plant_name: plantName,
        platform: platform,
        phone_number: phone,
        opt_in_status: optIn,
        preferred_lang: lang,
        notes: notes
    };

    try {
        const url = custId ? `/api/crm/customers/${custId}` : '/api/crm/customers';
        const res = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...(API_KEY ? { 'X-API-Key': API_KEY } : {})
            },
            body: JSON.stringify(payload)
        });

        const data = await res.json();
        if (res.ok && data.success) {
            closeCustomerModal();
            loadDataHealth();
            loadCustomersList(_crmCustPage);
        } else {
            alert(data.detail || data.error || 'Failed to save customer.');
        }
    } catch (err) {
        console.error(err);
        alert('Network error saving customer.');
    }
}

function exportCustomersCsv() {
    window.location.href = '/api/crm/customers/export';
}

function exportCustomersFullCsv() {
    window.location.href = '/api/crm/export/customers-full';
}

function exportCampaignPerformanceCsv() {
    window.location.href = '/api/crm/export/campaign-performance';
}

function exportGenerationByCustomerCsv() {
    const month = document.getElementById('crmStatementMonth')?.value || '';
    const query = month ? `?month=${encodeURIComponent(month)}` : '';
    window.location.href = `/api/crm/export/generation-by-customer${query}`;
}

/** ── Customer Drill-down Full Profile Modal ── */
async function openCustomerFullProfile(customerId) {
    const modal = document.getElementById('crmCustomerProfileModal');
    if (!modal) return;

    document.getElementById('profCustomerName').textContent = 'Loading...';
    document.getElementById('profPlantName').textContent = '--';
    document.getElementById('profPhone').textContent = '--';
    document.getElementById('profLifetimeGen').textContent = '— kWh';
    document.getElementById('profLifetimeSavings').textContent = '₹—';
    document.getElementById('profLifetimeCo2').textContent = '— kg';
    document.getElementById('profTotalSent').textContent = '—';
    document.getElementById('profMonthsRecorded').textContent = '— months recorded';
    document.getElementById('profDeliveryRate').textContent = 'Delivery: —%';
    document.getElementById('profMonthlyBody').innerHTML = `<tr><td colspan="5" style="text-align:center; padding:15px; color:var(--text-muted);">Loading monthly generation history...</td></tr>`;
    document.getElementById('profMessageBody').innerHTML = `<tr><td colspan="5" style="text-align:center; padding:15px; color:var(--text-muted);">Loading message logs...</td></tr>`;

    modal.style.display = 'flex';

    try {
        const res = await fetch(`/api/crm/customers/${customerId}/full-profile`, {
            headers: API_KEY ? { 'X-API-Key': API_KEY } : {}
        });
        if (!res.ok) {
            alert('Failed to load customer profile.');
            return;
        }
        const data = await res.json();
        const c = data.customer || {};
        const gt = data.generation_totals || {};
        const mt = data.messaging_totals || {};
        const mHist = data.monthly_history || [];
        const msgHist = data.message_history || [];

        document.getElementById('profCustomerName').textContent = c.customer_name || 'UNMAPPED';
        document.getElementById('profPlantName').textContent = c.plant_name || `Plant-${c.plant_id || ''}`;
        document.getElementById('profPhone').textContent = c.phone_number || 'No Phone Number';

        const platBadge = document.getElementById('profPlatformBadge');
        if (platBadge) {
            platBadge.className = `platform-chip chip-${c.platform || 'growatt'}`;
            platBadge.textContent = c.platform || 'growatt';
        }

        const optBadge = document.getElementById('profOptInBadge');
        if (optBadge) {
            const optClass = c.opt_in_status === 'active' ? 'badge-active' : (c.opt_in_status === 'do_not_send' ? 'badge-offline' : 'badge-nc');
            optBadge.className = `status-badge ${optClass}`;
            optBadge.textContent = c.opt_in_status || 'pending';
        }

        const langBadge = document.getElementById('profLangBadge');
        if (langBadge) {
            langBadge.textContent = (c.preferred_lang || 'english').toUpperCase();
        }

        document.getElementById('profLifetimeGen').textContent = `${(gt.total_kwh || 0).toLocaleString()} kWh`;
        document.getElementById('profLifetimeSavings').textContent = `₹ ${(gt.total_savings_inr || 0).toLocaleString()}`;
        document.getElementById('profLifetimeCo2').textContent = `${(gt.total_co2_kg || 0).toLocaleString()} kg`;
        document.getElementById('profMonthsRecorded').textContent = `${gt.months_recorded || 0} months recorded`;

        document.getElementById('profTotalSent').textContent = mt.total_sent || 0;
        document.getElementById('profDeliveryRate').textContent = `Delivery: ${mt.delivery_rate_pct || 0}%`;

        // Monthly history table
        if (mHist.length === 0) {
            document.getElementById('profMonthlyBody').innerHTML = `<tr><td colspan="5" style="text-align:center; padding:15px; color:var(--text-muted);">No generation history found.</td></tr>`;
        } else {
            document.getElementById('profMonthlyBody').innerHTML = mHist.map(m => `
                <tr>
                    <td style="font-weight:700;">${_escapeHtml(m.month || '')}</td>
                    <td style="color:var(--amber); font-weight:700;">${(m.energy_kwh || 0).toLocaleString()} kWh</td>
                    <td>${m.specific_yield_kwh_kwp != null ? Number(m.specific_yield_kwh_kwp).toFixed(2) : '—'}</td>
                    <td>${m.cuf_pct != null ? (Number(m.cuf_pct) * 100).toFixed(1) + '%' : '—'}</td>
                    <td>${m.avg_daily_kwh != null ? Number(m.avg_daily_kwh).toFixed(1) + ' kWh' : '—'}</td>
                </tr>
            `).join('');
        }

        // Messaging history table
        if (msgHist.length === 0) {
            document.getElementById('profMessageBody').innerHTML = `<tr><td colspan="5" style="text-align:center; padding:15px; color:var(--text-muted);">No messaging history recorded.</td></tr>`;
        } else {
            document.getElementById('profMessageBody').innerHTML = msgHist.map(msg => {
                const isSent = msg.status === 'SENT';
                const statusColor = isSent ? '#22c55e' : (msg.status === 'FAILED' ? '#ef4444' : '#f59e0b');
                return `
                    <tr>
                        <td>${_escapeHtml(msg.month_year || msg.sent_at || '—')}</td>
                        <td><span style="font-family:'JetBrains Mono',monospace; font-size:0.75rem;">${_escapeHtml(msg.template_used || 'custom')}</span></td>
                        <td>${msg.campaign_id ? '#' + msg.campaign_id : 'Manual'}</td>
                        <td><strong style="color:${statusColor};">${_escapeHtml(msg.status || 'QUEUED')}</strong></td>
                        <td style="color:var(--text-muted); font-size:0.75rem;">${_escapeHtml(msg.error_reason || (isSent ? 'Delivered successfully' : 'Pending'))}</td>
                    </tr>
                `;
            }).join('');
        }
    } catch (e) {
        console.error('Error loading full customer profile:', e);
        alert('Error loading full customer profile.');
    }
}

function closeCustomerProfileModal() {
    const modal = document.getElementById('crmCustomerProfileModal');
    if (modal) modal.style.display = 'none';
}

/** ── Load CRM Overview Metrics Banner ── */
async function loadCrmOverviewStats() {
    try {
        const res = await fetch('/api/crm/analytics/overview', {
            headers: API_KEY ? { 'X-API-Key': API_KEY } : {}
        });
        if (!res.ok) return;
        const data = await res.json();
        const cov = data.coverage || {};
        const msg = data.messaging || {};

        const elTot = document.getElementById('crmStatTotalCust');
        if (elTot) elTot.textContent = cov.total_customers || 0;

        const elAct = document.getElementById('crmStatActiveOpt');
        if (elAct) elAct.textContent = `Active: ${cov.active_opt_in || 0}`;

        const elCov = document.getElementById('crmStatPhoneCov');
        if (elCov) elCov.textContent = `${cov.coverage_pct || 0}%`;

        const elWithPhone = document.getElementById('crmStatWithPhone');
        if (elWithPhone) elWithPhone.textContent = `${cov.with_phone_number || 0} / ${cov.total_customers || 0} with mobile`;

        const elSent = document.getElementById('crmStatTotalSent');
        if (elSent) elSent.textContent = (msg.total_messages_sent || 0).toLocaleString();

        const elCamp = document.getElementById('crmStatCampaignsCount');
        if (elCamp) elCamp.textContent = `${msg.total_campaigns || 0} campaigns executed`;

        const elRate = document.getElementById('crmStatDeliveryRate');
        if (elRate) elRate.textContent = `${msg.delivery_rate_pct || 0}%`;

        const elFail = document.getElementById('crmStatFailedCount');
        if (elFail) elFail.textContent = `${msg.total_failed || 0} failed`;
    } catch (e) {
        console.debug('Failed to load CRM overview stats:', e);
    }
}

/** ── Monthly Statements Logic ── */
async function loadMonthlyStatements() {
    const monthInput = document.getElementById('crmStatementMonth');
    let month = monthInput?.value;
    if (!month) {
        const now = new Date();
        month = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
        if (monthInput) monthInput.value = month;
    }

    const monthLabel = document.getElementById('crmStatementMonthLabel');
    if (monthLabel) {
        const [y, m] = month.split('-');
        const d = new Date(parseInt(y), parseInt(m) - 1, 1);
        monthLabel.textContent = d.toLocaleString('en-US', { month: 'long', year: 'numeric' });
    }

    const tbody = document.getElementById('crmStatementsBody');
    if (tbody) tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; padding:24px; color:var(--text-muted);">Generating statements for ${month}...</td></tr>`;

    try {
        const res = await fetch(`/api/crm/statements?month=${month}`, {
            headers: API_KEY ? { 'X-API-Key': API_KEY } : {}
        });
        const data = await res.json();
        const stmts = data.statements || [];
        const summary = data.summary || {};

        // Update cards
        document.getElementById('crmStmtTotalGen').textContent = `${(summary.total_generation_kwh || 0).toLocaleString()} kWh`;
        document.getElementById('crmStmtTotalSavings').textContent = `₹${Math.round(summary.total_savings_inr || 0).toLocaleString()}`;
        document.getElementById('crmStmtReady').textContent = `${summary.customers_ready || 0} ✓`;
        document.getElementById('crmStmtPending').textContent = summary.reports_pending || 0;

        if (stmts.length === 0) {
            tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; padding:30px; color:var(--text-muted);">No generation records found for ${month}.</td></tr>`;
            return;
        }

        let html = '';
        stmts.forEach(s => {
            // Specific yield badge class
            let yieldClass = 'yield-mid';
            if (s.specific_yield >= 4.0) yieldClass = 'yield-high';
            else if (s.specific_yield < 3.0) yieldClass = 'yield-low';

            // Message status badge
            let msgBadge = `<span class="crm-badge pending">${_escapeHtml(s.message_status)}</span>`;
            if (s.message_status === 'SENT' || s.message_status === 'SIMULATED') {
                msgBadge = `<span class="crm-badge active">${s.message_status}</span>`;
            } else if (s.message_status === 'Opted Out') {
                msgBadge = `<span class="crm-badge opted-out">Opted Out</span>`;
            } else if (s.message_status === 'No Phone') {
                msgBadge = `<span class="crm-badge no-phone">No Phone</span>`;
            }

            const previewText = `Hello ${s.customer_name}! 🌞 Your solar plant ${s.plant_name} generated ${s.generation_kwh.toFixed(1)} kWh in ${month}, saving you ₹${s.savings_inr.toFixed(0)}. CO₂ saved: ${s.co2_saved_kg.toFixed(1)} kg 🌱 — Solaron Homes`;

            html += `
                <tr>
                    <td style="font-weight:700; color:var(--text-primary);">${_escapeHtml(s.customer_name)}</td>
                    <td><strong>${_escapeHtml(s.plant_name)}</strong></td>
                    <td><span class="p-chip p-${_escapeHtml(s.platform)}">${_escapeHtml(s.platform)}</span></td>
                    <td style="font-weight:700;">${s.generation_kwh.toFixed(1)}</td>
                    <td style="font-weight:700; color:#22c55e;">₹${s.savings_inr.toLocaleString()}</td>
                    <td>${s.co2_saved_kg.toFixed(1)} kg</td>
                    <td class="${yieldClass}">${s.specific_yield > 0 ? s.specific_yield.toFixed(2) + ' kWh/kWp' : '—'}</td>
                    <td>${msgBadge}</td>
                    <td>
                        <button class="btn btn-secondary btn-sm" onclick="openMsgPreview('${_escapeHtml(s.customer_name)}', '${_escapeHtml(s.phone_number || '')}', '${_escapeHtml(s.message_status)}', '${_escapeHtml(previewText)}')" style="padding:2px 8px; font-size:0.75rem;">
                            💬 Preview
                        </button>
                    </td>
                </tr>
            `;
        });
        tbody.innerHTML = html;
    } catch (e) {
        console.error('Failed to load statements:', e);
        if (tbody) tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; padding:24px; color:#ef4444;">Failed to calculate monthly statements.</td></tr>`;
    }
}

function stepStatementMonth(delta) {
    const input = document.getElementById('crmStatementMonth');
    if (!input || !input.value) return;
    const [y, m] = input.value.split('-').map(Number);
    const d = new Date(y, m - 1 + delta, 1);
    input.value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
    loadMonthlyStatements();
}

async function prepareMonthlyCampaignFromStatements() {
    const month = document.getElementById('crmStatementMonth')?.value;
    if (!confirm(`Prepare monthly billing campaign for ${month}?\nThis will generate customized statements and queue messages in crm_data.db.`)) {
        return;
    }

    try {
        const res = await fetch('/api/crm/campaigns/prepare', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...(API_KEY ? { 'X-API-Key': API_KEY } : {})
            },
            body: JSON.stringify({ month: month })
        });
        const data = await res.json();
        if (res.ok && data.success) {
            alert(`✅ Campaign #${data.campaign_id} Prepared Successfully!\nQueued: ${data.queued} messages\nSkipped: ${data.skipped}`);
            switchHubMode('campaigns');
        } else {
            alert('Failed to prepare campaign: ' + (data.detail || 'Error'));
        }
    } catch (e) {
        console.error(e);
        alert('Network error preparing campaign.');
    }
}

function exportStatementsCsv() {
    const month = document.getElementById('crmStatementMonth')?.value || 'current';
    const rows = [];
    const table = document.getElementById('crmStatementsTable');
    if (!table) return;

    for (let r of table.rows) {
        let rowData = [];
        for (let c of r.cells) {
            rowData.push('"' + c.innerText.replace(/"/g, '""').trim() + '"');
        }
        rows.push(rowData.join(','));
    }

    const csvContent = 'data:text/csv;charset=utf-8,' + encodeURIComponent(rows.join('\n'));
    const link = document.createElement('a');
    link.setAttribute('href', csvContent);
    link.setAttribute('download', `monthly_statements_${month}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

/** ── Yearly Milestones Logic ── */
async function loadYearlyMilestones() {
    const yearSelect = document.getElementById('crmYearSelect');
    const year = parseInt(yearSelect?.value || 2026);
    document.getElementById('crmYearLabel').textContent = `Year ${year}`;

    const tbody = document.getElementById('crmYearlyBody');
    if (tbody) tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding:24px; color:var(--text-muted);">Calculating yearly milestone metrics for ${year}...</td></tr>`;

    try {
        const res = await fetch(`/api/crm/statements?year=${year}`, {
            headers: API_KEY ? { 'X-API-Key': API_KEY } : {}
        });
        const data = await res.json();
        const stmts = data.statements || [];
        const summary = data.summary || {};

        document.getElementById('crmYearTotalGen').textContent = `${(summary.total_generation_kwh || 0).toLocaleString()} kWh`;
        document.getElementById('crmYearTotalSavings').textContent = `₹${Math.round(summary.total_savings_inr || 0).toLocaleString()}`;
        const daysPowered = Math.round((summary.total_generation_kwh || 0) / 30);
        document.getElementById('crmYearDaysPowered').textContent = `${daysPowered.toLocaleString()} days`;
        document.getElementById('crmYearTotalPlants').textContent = summary.total_customers || stmts.length;

        renderYearlyChart(stmts.slice(0, 10));

        if (stmts.length === 0) {
            tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding:30px; color:var(--text-muted);">No recorded generation for ${year}.</td></tr>`;
            return;
        }

        let html = '';
        stmts.forEach(s => {
            html += `
                <tr>
                    <td style="font-weight:700; color:var(--text-primary);">${_escapeHtml(s.customer_name)}</td>
                    <td><strong>${_escapeHtml(s.plant_name)}</strong></td>
                    <td><span class="p-chip p-${_escapeHtml(s.platform)}">${_escapeHtml(s.platform)}</span></td>
                    <td style="font-weight:700;">${s.total_kwh.toLocaleString()} kWh</td>
                    <td style="font-weight:700; color:#22c55e;">₹${s.total_savings.toLocaleString()}</td>
                    <td style="color:#38bdf8;">${_escapeHtml(s.best_month || 'N/A')}</td>
                    <td><strong>${s.days_powered}</strong> days</td>
                    <td><span class="crm-badge active">Milestone Met</span></td>
                </tr>
            `;
        });
        tbody.innerHTML = html;
    } catch (e) {
        console.error(e);
        if (tbody) tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding:24px; color:#ef4444;">Failed to load yearly milestones.</td></tr>`;
    }
}

function renderYearlyChart(topPlants) {
    const canvas = document.getElementById('crmYearlyChartCanvas');
    if (!canvas || typeof Chart === 'undefined') return;

    if (_crmYearlyChart) {
        _crmYearlyChart.destroy();
    }

    const labels = topPlants.map(p => p.plant_name.length > 18 ? p.plant_name.slice(0, 18) + '...' : p.plant_name);
    const dataGen = topPlants.map(p => p.total_kwh);
    const dataSavings = topPlants.map(p => p.total_savings);

    _crmYearlyChart = new Chart(canvas, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Annual Generation (kWh)',
                    data: dataGen,
                    backgroundColor: 'rgba(56, 189, 248, 0.75)',
                    borderRadius: 4,
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { labels: { color: '#94a3b8' } }
            },
            scales: {
                x: { ticks: { color: '#94a3b8', font: { size: 10 } }, grid: { display: false } },
                y: { ticks: { color: '#94a3b8' }, grid: { color: 'rgba(255, 255, 255, 0.05)' } }
            }
        }
    });
}

function stepYearlyReport(delta) {
    const select = document.getElementById('crmYearSelect');
    if (!select) return;
    const curYear = parseInt(select.value);
    const target = curYear + delta;
    if (target >= 2020 && target <= 2030) {
        select.value = String(target);
        loadYearlyMilestones();
    }
}

async function prepareYearlyRecapMessages() {
    const yearSelect = document.getElementById('crmYearSelect');
    const year = parseInt(yearSelect?.value || 2026);
    if (!confirm(`Prepare yearly milestone recap campaign for Year ${year}?\nThis will queue milestone celebration messages in crm_data.db.`)) {
        return;
    }

    try {
        const res = await fetch(`/api/crm/campaigns/prepare-yearly?year=${year}`, {
            method: 'POST',
            headers: API_KEY ? { 'X-API-Key': API_KEY } : {}
        });
        const data = await res.json();
        if (res.ok && data.success) {
            alert(`🏆 Yearly Milestone Campaign #${data.campaign_id} Prepared!\nQueued: ${data.queued} messages\nSkipped: ${data.skipped}`);
            switchHubMode('campaigns');
        } else {
            alert('Failed to prepare yearly campaign: ' + (data.detail || 'Error'));
        }
    } catch (e) {
        console.error(e);
        alert('Network error preparing yearly recap campaign.');
    }
}

function exportYearlyCsv() {
    const year = document.getElementById('crmYearSelect')?.value || '2026';
    const rows = [];
    const table = document.getElementById('crmYearlyTable');
    if (!table) return;

    for (let r of table.rows) {
        let rowData = [];
        for (let c of r.cells) {
            rowData.push('"' + c.innerText.replace(/"/g, '""').trim() + '"');
        }
        rows.push(rowData.join(','));
    }

    const csvContent = 'data:text/csv;charset=utf-8,' + encodeURIComponent(rows.join('\n'));
    const link = document.createElement('a');
    link.setAttribute('href', csvContent);
    link.setAttribute('download', `yearly_milestones_${year}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

/** ── Campaign Manager Logic ── */
async function loadCampaignsList() {
    const select = document.getElementById('crmCampaignSelect');
    if (!select) return;

    try {
        const res = await fetch('/api/crm/campaigns', {
            headers: API_KEY ? { 'X-API-Key': API_KEY } : {}
        });
        const data = await res.json();
        const campaigns = data.campaigns || [];

        if (campaigns.length === 0) {
            select.innerHTML = `<option value="">No campaigns yet — click 'Prepare Campaign' in Monthly tab</option>`;
            return;
        }

        let html = '';
        campaigns.forEach((c, idx) => {
            html += `<option value="${c.campaign_id}">${c.campaign_name} (${c.status})</option>`;
        });
        select.innerHTML = html;

        // Auto-select latest
        _selectedCampaignId = campaigns[0].campaign_id;
        loadCampaignDetails(_selectedCampaignId);
    } catch (e) {
        console.error('Failed to load campaigns:', e);
    }
}

function onCampaignSelected(campaignId) {
    if (!campaignId) return;
    _selectedCampaignId = parseInt(campaignId);
    loadCampaignDetails(_selectedCampaignId);
}

async function loadCampaignDetails(campaignId) {
    const tbody = document.getElementById('crmMessagesBody');
    if (tbody) tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:24px; color:var(--text-muted);">Loading campaign #${campaignId} messages...</td></tr>`;

    try {
        const res = await fetch(`/api/crm/campaigns/${campaignId}`, {
            headers: API_KEY ? { 'X-API-Key': API_KEY } : {}
        });
        const data = await res.json();
        const camp = data.campaign || {};
        const messages = data.messages || [];

        // Update summary
        document.getElementById('campSummaryTitle').textContent = camp.campaign_name || 'Campaign Details';
        document.getElementById('campSummaryMonth').textContent = `Period: ${camp.month_year || 'N/A'}`;
        const badge = document.getElementById('campSummaryStatusBadge');
        if (badge) {
            badge.textContent = camp.status || 'DRAFT';
            badge.className = `crm-badge ${camp.status === 'COMPLETED' ? 'active' : 'pending'}`;
        }

        // Count metrics
        let total = messages.length;
        let sent = messages.filter(m => m.status === 'SENT' || m.status === 'SIMULATED').length;
        let failed = messages.filter(m => m.status === 'FAILED').length;
        let skipped = messages.filter(m => m.status === 'SKIPPED').length;
        let pending = messages.filter(m => m.status === 'PENDING').length;

        document.getElementById('campCountTotal').textContent = total;
        document.getElementById('campCountSent').textContent = sent;
        document.getElementById('campCountFailed').textContent = failed;
        document.getElementById('campCountSkipped').textContent = skipped;
        document.getElementById('campCountPending').textContent = pending;

        // Update progress bar
        if (total > 0) {
            document.getElementById('campProgSent').style.width = `${(sent / total) * 100}%`;
            document.getElementById('campProgFailed').style.width = `${(failed / total) * 100}%`;
            document.getElementById('campProgSkipped').style.width = `${(skipped / total) * 100}%`;
            document.getElementById('campProgPending').style.width = `${(pending / total) * 100}%`;
        }

        if (messages.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:30px; color:var(--text-muted);">No messages queued in this campaign.</td></tr>`;
            return;
        }

        let html = '';
        messages.forEach((m, idx) => {
            let statusBadge = `<span class="crm-badge pending">${m.status}</span>`;
            if (m.status === 'SENT' || m.status === 'SIMULATED') {
                statusBadge = `<span class="crm-badge active">${m.status}</span>`;
            } else if (m.status === 'SKIPPED') {
                statusBadge = `<span class="crm-badge opted-out" title="${_escapeHtml(m.error_reason || '')}">SKIPPED</span>`;
            }

            const previewSnippet = m.message_text ? (m.message_text.slice(0, 65) + '...') : '—';

            html += `
                <tr>
                    <td>${idx + 1}</td>
                    <td style="font-weight:700; color:var(--text-primary);">${_escapeHtml(m.customer_name)}</td>
                    <td><strong>${_escapeHtml(m.plant_name)}</strong></td>
                    <td style="font-family:'JetBrains Mono',monospace;">${_escapeHtml(m.phone_number || '—')}</td>
                    <td style="font-size:0.82rem; color:var(--text-secondary);">${_escapeHtml(previewSnippet)}</td>
                    <td>${statusBadge}</td>
                    <td>
                        <button class="btn btn-secondary btn-sm" onclick="openMsgPreview('${_escapeHtml(m.customer_name)}', '${_escapeHtml(m.phone_number || '')}', '${_escapeHtml(m.status)}', '${_escapeHtml(m.message_text || '')}')" style="padding:2px 8px; font-size:0.75rem;">
                            Preview ▼
                        </button>
                    </td>
                </tr>
            `;
        });
        tbody.innerHTML = html;
    } catch (e) {
        console.error(e);
        if (tbody) tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:24px; color:#ef4444;">Failed to load campaign messages.</td></tr>`;
    }
}

function exportSelectedCampaignCsv() {
    if (!_selectedCampaignId) {
        alert('Please select a campaign first.');
        return;
    }
    window.location.href = `/api/crm/campaigns/${_selectedCampaignId}/export`;
}

async function dryRunSelectedCampaign() {
    if (!_selectedCampaignId) {
        alert('Please select a campaign first.');
        return;
    }
    if (!confirm(`Run Console Dry-Run simulation for Campaign #${_selectedCampaignId}?\nThis will print all pending messages to the server terminal and mark them SIMULATED.`)) {
        return;
    }

    try {
        const res = await fetch(`/api/crm/campaigns/${_selectedCampaignId}/dry-run`, {
            method: 'POST',
            headers: API_KEY ? { 'X-API-Key': API_KEY } : {}
        });
        const data = await res.json();
        if (res.ok && data.success) {
            alert(`🧪 Dry-run simulation completed!\nSimulated ${data.simulated_count} messages.`);
            loadCampaignDetails(_selectedCampaignId);
        } else {
            alert('Dry-run failed: ' + (data.detail || 'Error'));
        }
    } catch (e) {
        console.error(e);
        alert('Network error during dry-run.');
    }
}

/** ── Offline Alerts Logic ── */
async function loadOfflineAlerts() {
    const threshold = document.getElementById('crmAlertThresholdSelect')?.value || 24;
    const tbody = document.getElementById('crmOfflineBody');
    if (tbody) tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding:24px; color:var(--text-muted);">Querying inverter snapshots for plants offline > ${threshold}h...</td></tr>`;

    try {
        const res = await fetch(`/api/crm/offline?threshold_hours=${threshold}`, {
            headers: API_KEY ? { 'X-API-Key': API_KEY } : {}
        });
        const data = await res.json();
        const plants = data.plants || [];

        document.getElementById('crmOfflineCountLabel').textContent = `Found ${plants.length} offline plants (> ${threshold}h)`;

        if (plants.length === 0) {
            tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding:30px; color:#22c55e;">🟢 Excellent! No plants are currently offline beyond ${threshold} hours.</td></tr>`;
            return;
        }

        let html = '';
        plants.forEach(p => {
            const hasPhone = Boolean(p.phone_number);
            const alertBadge = hasPhone ? `<span class="crm-badge pending">Ready for Alert</span>` : `<span class="crm-badge no-phone">No Customer / Phone</span>`;

            html += `
                <tr>
                    <td style="font-weight:700; color:var(--text-primary);">${_escapeHtml(p.plant_name)}</td>
                    <td><span class="p-chip p-${_escapeHtml(p.platform)}">${_escapeHtml(p.platform)}</span></td>
                    <td>${_escapeHtml(p.customer_name)}</td>
                    <td style="font-family:'JetBrains Mono',monospace;">${_escapeHtml(p.phone_number || '—')}</td>
                    <td><span class="crm-badge opted-out">${_escapeHtml(p.device_status)}</span></td>
                    <td style="font-size:0.78rem; color:var(--text-muted);">${_escapeHtml(p.last_update)}</td>
                    <td style="font-weight:700; color:#ef4444;">${p.hours_offline}h</td>
                    <td>${alertBadge}</td>
                </tr>
            `;
        });
        tbody.innerHTML = html;
    } catch (e) {
        console.error(e);
        if (tbody) tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding:24px; color:#ef4444;">Failed to query offline plants.</td></tr>`;
    }
}

async function prepareOfflineAlertCampaign() {
    const threshold = document.getElementById('crmAlertThresholdSelect')?.value || 24;
    if (!confirm(`Prepare offline alert messages for all plants offline > ${threshold} hours?`)) {
        return;
    }

    try {
        const res = await fetch(`/api/crm/offline/prepare-alerts?threshold_hours=${threshold}`, {
            method: 'POST',
            headers: API_KEY ? { 'X-API-Key': API_KEY } : {}
        });
        const data = await res.json();
        if (res.ok && data.success) {
            alert(`🚨 Offline Alert Campaign Prepared!\nQueued: ${data.queued} messages\nSkipped: ${data.skipped}`);
            switchHubMode('campaigns');
        } else {
            alert('Failed to prepare offline alerts.');
        }
    } catch (e) {
        console.error(e);
        alert('Network error preparing offline alerts.');
    }
}

/** Message Modal Preview */
function openMsgPreview(custName, phone, status, text) {
    document.getElementById('crmMsgRecipient').textContent = `${custName} (${phone || 'No Phone'})`;
    document.getElementById('crmMsgStatus').textContent = status;
    document.getElementById('crmMsgFullText').textContent = text;
    document.getElementById('crmMsgModal').style.display = 'flex';
}

function closeMsgModal() {
    document.getElementById('crmMsgModal').style.display = 'none';
}

function copyMsgModalText() {
    const txt = document.getElementById('crmMsgFullText').textContent;
    navigator.clipboard.writeText(txt).then(() => {
        alert('📋 Message text copied to clipboard!');
    });
}
