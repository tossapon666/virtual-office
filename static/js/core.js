'use strict';

/* ============================================================
   Virtual Office — core helpers, state, API, notifications
   ============================================================ */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const MONTHS_SHORT = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.',
  'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.'];
const WEEKDAYS_SHORT = ['จ', 'อ', 'พ', 'พฤ', 'ศ', 'ส', 'อา'];

const PRIORITY_LABEL = { urgent: 'ด่วนมาก', high: 'สูง', normal: 'ปกติ', low: 'ต่ำ' };
const STATUS_LABEL = { todo: 'ต้องทำ', doing: 'กำลังทำ', done: 'เสร็จแล้ว', cancelled: 'ยกเลิก' };
const AGENT_STATUS = { working: 'กำลังทำงาน', idle: 'ว่าง', meeting: 'ประชุม', offline: 'ออฟไลน์' };
const REPEAT_LABEL = { none: 'ไม่ทำซ้ำ', daily: 'ทุกวัน', weekly: 'ทุกสัปดาห์', monthly: 'ทุกเดือน', yearly: 'ทุกปี' };
const CATEGORIES = ['สัญญา', 'การเงิน', 'เอกสารทั่วไป', 'รายงาน', 'คู่มือ', 'ยังไม่จัดหมวด'];
const WIDGET_TITLES = {
  overview: 'ภาพรวมวันนี้', today: 'งานที่ต้องทำวันนี้', overdue: 'งานเกินกำหนด',
  upcoming: 'งานกำลังจะถึง', workload: 'ภาระงานแต่ละแผนก', team: 'สถานะทีม AI',
  docs: 'เอกสารล่าสุด', quickadd: 'เพิ่มงานเร็ว', calendar: 'ปฏิทินย่อ', activity: 'กิจกรรมล่าสุด',
};
const VIEW_TITLES = {
  office: 'ศูนย์บัญชาการไซไฟ', tasks: 'งานและแจ้งเตือน', calendar: 'ปฏิทินงาน',
  docs: 'ศูนย์เอกสารและไฟล์', dashboard: 'แดชบอร์ดของฉัน', activity: 'บันทึกกิจกรรม',
};

const I = {
  check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6"><path d="m5 12 4.5 4.5L19 7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  edit: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M4 20h4l10-10a2.5 2.5 0 0 0-3.5-3.5L4 16.5V20Z" stroke-linejoin="round"/><path d="m13.5 7.5 3 3" stroke-linecap="round"/></svg>',
  trash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M4 7h16M9 7V5h6v2M6 7l1 13h10l1-13M10 11v6M14 11v6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  plus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14" stroke-linecap="round"/></svg>',
  search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5" stroke-linecap="round"/></svg>',
  download: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 4v11m0 0 4-4m-4 4-4-4M5 20h14" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  send: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="m4 12 16-8-6 16-2.5-6.5L4 12Z" stroke-linejoin="round"/></svg>',
  arrowL: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"><path d="m14 6-6 6 6 6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  arrowR: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"><path d="m10 6 6 6-6 6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  upload: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 16V5m0 0 4 4m-4-4L8 9M5 20h14" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  expand: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M9 4H4v5M15 4h5v5M9 20H4v-5M15 20h5v-5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
};

const state = {
  layoutEdit: false,
  data: null,
  view: 'office',
  taskFilter: 'open',
  taskSearch: '',
  docSearch: '',
  docCategory: 'all',
  docDept: 'all',
  calCursor: new Date(new Date().getFullYear(), new Date().getMonth(), 1),
  dashEdit: false,
  chat: {},
  chatBusy: {},
  pendingFile: null,
  lastNotifId: Number(localStorage.getItem('vo_last_notif') || 0),
  confirmFn: null,
};

/* ---------------- formatting ---------------- */
function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (ch) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]
  ));
}

function pad(n) { return String(n).padStart(2, '0'); }
function ymd(d) { return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`; }
function parseYMD(s) {
  const [y, m, d] = String(s).split('-').map(Number);
  return new Date(y, (m || 1) - 1, d || 1);
}
function startOfDay(d) { return new Date(d.getFullYear(), d.getMonth(), d.getDate()); }
function todayYMD() { return ymd(new Date()); }

function thaiDate(value, opts = { day: 'numeric', month: 'long', year: 'numeric' }) {
  try {
    return new Intl.DateTimeFormat('th-TH', opts).format(value);
  } catch (e) {
    const d = new Date(value);
    return `${d.getDate()} ${MONTHS_SHORT[d.getMonth()]} ${d.getFullYear() + 543}`;
  }
}

function dueInfo(task) {
  if (!task.due_date) return { text: 'ไม่กำหนด', cls: '' };
  const due = parseYMD(task.due_date);
  const diff = Math.round((due - startOfDay(new Date())) / 86400000);
  let text;
  if (diff < 0) text = `เกิน ${-diff} วัน`;
  else if (diff === 0) text = 'วันนี้';
  else if (diff === 1) text = 'พรุ่งนี้';
  else if (diff <= 6) text = `อีก ${diff} วัน`;
  else text = `${due.getDate()} ${MONTHS_SHORT[due.getMonth()]}`;
  if (task.due_time) text += ` · ${task.due_time}`;
  return { text, cls: diff < 0 ? 'overdue' : diff === 0 ? 'today' : '' };
}

function timeAgo(value) {
  if (!value) return '';
  const then = new Date(String(value).replace(' ', 'T'));
  if (Number.isNaN(then.getTime())) return '';
  const mins = Math.floor((Date.now() - then.getTime()) / 60000);
  if (mins < 1) return 'เมื่อสักครู่';
  if (mins < 60) return `${mins} นาทีที่แล้ว`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} ชั่วโมงที่แล้ว`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days} วันที่แล้ว`;
  return thaiDate(then, { day: 'numeric', month: 'short' });
}

function fileSize(bytes) {
  const n = Number(bytes) || 0;
  if (n < 1024) return `${n} B`;
  if (n < 1048576) return `${Math.round(n / 1024)} KB`;
  return `${(n / 1048576).toFixed(1)} MB`;
}

function fileMeta(name) {
  const ext = String(name || '').split('.').pop().toLowerCase();
  if (ext === 'pdf') return { icon: '📕', cls: 'pdf', label: 'PDF' };
  if (['doc', 'docx'].includes(ext)) return { icon: '📘', cls: 'doc', label: 'DOC' };
  if (['xls', 'xlsx', 'csv'].includes(ext)) return { icon: '📗', cls: 'xls', label: 'XLS' };
  if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'].includes(ext)) return { icon: '🖼️', cls: 'img', label: 'IMG' };
  if (['zip', 'rar', '7z'].includes(ext)) return { icon: '🗜️', cls: 'zip', label: 'ZIP' };
  return { icon: '📄', cls: '', label: ext.toUpperCase() || 'FILE' };
}

/* ---------------- selectors ---------------- */
function agentById(id) { return (state.data?.agents || []).find((a) => a.id === Number(id)); }
function taskById(id) { return (state.data?.tasks || []).find((t) => t.id === Number(id)); }
function deptById(id) { return (state.data?.departments || []).find((d) => d.id === Number(id)); }
function openTasks() { return (state.data?.tasks || []).filter((t) => ['todo', 'doing'].includes(t.status)); }
function availableWidgets() {
  const used = new Set((state.data?.widgets || []).map((w) => w.widget_type));
  return Object.keys(WIDGET_TITLES).filter((t) => !used.has(t));
}
function agentSelectOptions(deptId = '', selected = '') {
  return (state.data?.agents || [])
    .filter((a) => !deptId || String(a.department_id) === String(deptId))
    .map((a) => `<option value="${a.id}" data-dept="${a.department_id}" ${String(selected) === String(a.id) ? 'selected' : ''}>${a.emoji} ${esc(a.name)} — ${esc(a.role)}</option>`)
    .join('');
}
function deptSelectOptions(selected = '') {
  return (state.data?.departments || [])
    .map((d) => `<option value="${d.id}" ${String(selected) === String(d.id) ? 'selected' : ''}>${d.icon} ${esc(d.name)}</option>`)
    .join('');
}

/* ---------------- API ---------------- */
async function api(url, options = {}) {
  const opts = { ...options };
  if (opts.body && !(opts.body instanceof FormData)) {
    opts.headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
    if (typeof opts.body !== 'string') opts.body = JSON.stringify(opts.body);
  }
  const res = await fetch(url, opts);
  if (res.status === 401) {
    location.href = '/login';
    throw new Error('กรุณาเข้าสู่ระบบใหม่');
  }
  const type = res.headers.get('content-type') || '';
  let data;
  if (type.includes('application/json')) data = await res.json();
  else data = await res.text();
  if (!res.ok) throw new Error((data && data.error) || 'เกิดข้อผิดพลาด กรุณาลองใหม่');
  return data;
}

function loadingHTML() {
  return '<div class="loading"><div class="spinner"></div><span>กำลังโหลดออฟฟิศ…</span></div>';
}

async function load(showLoader = false) {
  if (showLoader && !state.data) {
    const view = $('#view');
    if (view) view.innerHTML = loadingHTML();
  }
  const data = await api('/api/bootstrap');
  state.data = data;
  if (!state.lastNotifId) {
    const max = data.notifications.reduce((m, n) => Math.max(m, n.id), 0);
    state.lastNotifId = max;
    localStorage.setItem('vo_last_notif', String(max));
  }
  updateChrome();
  render();
  renderNotifList();
}

/* ---------------- chrome ---------------- */
function updateChrome() {
  if (!state.data) return;
  const { me, stats, ai } = state.data;
  const initial = (me.display_name || 'ผ').trim().charAt(0) || 'ผ';

  $$('.user-avatar').forEach((el) => { el.textContent = initial; });
  const names = ['sideUserName', 'topUserName', 'popUserName'];
  names.forEach((id) => { const el = document.getElementById(id); if (el) el.textContent = me.display_name; });
  const popRole = document.getElementById('popUserRole');
  if (popRole) popRole.textContent = me.role === 'owner' ? 'เจ้าของออฟฟิศ' : me.role;

  const team = document.getElementById('sideTeamCount');
  if (team) team.textContent = `ทีม AI ${stats.agents} คน`;
  const aiChip = document.getElementById('aiModeChip');
  if (aiChip) aiChip.textContent = ai.enabled ? `AI จริง · ${ai.model}` : 'โหมดอัตโนมัติ';

  const navBadge = document.getElementById('navTaskBadge');
  if (navBadge) {
    navBadge.textContent = stats.open;
    navBadge.hidden = !stats.open;
  }
  const bellBadge = document.getElementById('bellBadge');
  if (bellBadge) {
    bellBadge.textContent = stats.unread;
    bellBadge.hidden = !stats.unread;
  }

  const now = new Date();
  const topDate = document.getElementById('topDate');
  if (topDate) topDate.textContent = thaiDate(now, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
  const todayChip = document.getElementById('todayChip');
  if (todayChip) todayChip.textContent = `วันนี้ ${now.getDate()} ${MONTHS_SHORT[now.getMonth()]}`;

  const title = document.getElementById('topTitle');
  if (title) title.textContent = VIEW_TITLES[state.view] || 'Virtual Office';
  $$('.nav-item').forEach((el) => el.classList.toggle('active', el.dataset.view === state.view));
}

/* ---------------- notifications ---------------- */
const NOTIF_ICON = {
  overdue: '⚠️', reminder: '⏰', briefing: '🗒️', done: '✅', document: '📄', agent: '🤖',
};

function notifHTML(n) {
  return `<div class="notif-item ${n.is_read ? '' : 'unread'} kind-${esc(n.kind)}"
      data-action="notif-click" data-id="${n.id}" data-ref="${esc(n.ref_type || '')}" data-refid="${n.ref_id || ''}">
      <div class="notif-icon">${NOTIF_ICON[n.kind] || '🔔'}</div>
      <div class="notif-body">
        <strong>${esc(n.title)}</strong>
        ${n.body ? `<p>${esc(n.body)}</p>` : ''}
        <time>${timeAgo(n.created_at)}</time>
      </div>
    </div>`;
}

function renderNotifList() {
  const box = document.getElementById('notifList');
  if (!box || !state.data) return;
  const list = state.data.notifications || [];
  box.innerHTML = list.length
    ? list.map(notifHTML).join('')
    : '<div class="notif-empty">ยังไม่มีการแจ้งเตือน<br>ทีม AI จะแจ้งเมื่อมีงานถึงกำหนด</div>';
}

function updateNotifBadge() {
  const badge = document.getElementById('bellBadge');
  if (!badge || !state.data) return;
  badge.textContent = state.data.stats.unread;
  badge.hidden = !state.data.stats.unread;
}

async function markNotifRead(id) {
  try {
    await api(`/api/notifications/${id}/read`, { method: 'POST' });
    const item = (state.data.notifications || []).find((n) => n.id === Number(id));
    if (item && !item.is_read) {
      item.is_read = 1;
      state.data.stats.unread = Math.max(0, state.data.stats.unread - 1);
      updateNotifBadge();
      renderNotifList();
    }
  } catch (e) { /* silent */ }
}

function showBrowserNotif(n) {
  if (!('Notification' in window) || Notification.permission !== 'granted') return;
  try {
    new Notification(n.title, {
      body: n.body || '',
      icon: '/static/icon-192.png',
      tag: `vo-${n.id}`,
    });
  } catch (e) { /* ignore */ }
}

async function enableBrowserNotifications() {
  if (!('Notification' in window)) {
    toast('เบราว์เซอร์นี้ไม่รองรับการแจ้งเตือน', 'error');
    return;
  }
  const permission = await Notification.requestPermission();
  if (permission === 'granted') toast('เปิดการแจ้งเตือนบนเบราว์เซอร์แล้ว 🔔');
  else toast('ยังไม่ได้อนุญาตการแจ้งเตือน', 'error');
}

/* ---------------- toast ---------------- */
function toast(message, type = 'ok', emoji = '') {
  const root = document.getElementById('toastRoot');
  if (!root) return;
  const el = document.createElement('div');
  el.className = `toast ${type === 'error' ? 'error' : ''}`;
  el.innerHTML = `<span class="t-emoji">${emoji || (type === 'error' ? '⚠️' : '✨')}</span><span>${esc(message)}</span>`;
  root.appendChild(el);
  setTimeout(() => {
    el.classList.add('out');
    setTimeout(() => el.remove(), 220);
  }, 3200);
}

/* ---------------- service worker ---------------- */
function registerSW() {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  }
}
