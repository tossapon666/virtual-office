'use strict';

/* ============================================================
   Views: office, tasks, calendar, documents, activity
   ============================================================ */

function render() {
  if (!state.data) return;
  updateChrome();
  const view = document.getElementById('view');
  if (!view) return;
  const map = {
    office: renderOffice,
    tasks: renderTasks,
    calendar: renderCalendar,
    docs: renderDocs,
    dashboard: renderDashboard,
    activity: renderActivity,
  };
  view.innerHTML = (map[state.view] || renderOffice)();
  if (state.view === 'dashboard' && typeof setupWidgetDnD === 'function') setupWidgetDnD();
}

/* ---------------- office (ตามไฟล์แนบ: scene + dept cards, ผูกข้อมูลจริง) ---------------- */
function kpiHTML(emoji, value, label, cls = '') {
  return `<div class="kpi ${cls}">
    <div class="kpi-icon">${emoji}</div>
    <div><div class="kpi-value">${value}</div><div class="kpi-label">${label}</div></div>
  </div>`;
}

function efficiencyPct() {
  const s = state.data.stats;
  const total = (s.open || 0) + (s.done_week || 0);
  if (!total) return 100;
  return Math.max(0, Math.min(100, Math.round((s.done_week / total) * 100)));
}

const ROOM_META = {
  'สำนักเลขา':         { pos: 'pos-secretary',  file: 'secretary',  sign: 'สำนักเลขา<br><small>秘書室</small>' },
  'ฝ่ายบัญชี':         { pos: 'pos-accounting', file: 'accounting', sign: 'ฝ่ายบัญชี<br><small>会計部</small>' },
  'ฝ่ายเอกสาร':        { pos: 'pos-documents',  file: 'documents',  sign: 'ฝ่ายเอกสาร<br><small>文書部</small>' },
  'คลังเอกสารและไฟล์': { pos: 'pos-archive',    file: 'archive',    sign: 'คลังเอกสารและไฟล์<br><small>แฟ้มจัดเก็บ</small>' },
  'ฝ่ายปฏิบัติการ':    { pos: 'pos-operations', file: 'operations', sign: 'ฝ่ายปฏิบัติการ<br><small>ปฏิบัติการ</small>' },
};

function uiCfg() { return (state.data && state.data.ui_config) || {}; }
function roomCfg(dept) { const rooms = (uiCfg().rooms || {}); return rooms[dept.name] || rooms[String(dept.id)] || {}; }

function protoImgHTML(fileBase, alt, emoji, agentId, status) {
  const base = esc(fileBase || 'member');
  const action = agentId ? ` data-action="open-agent" data-id="${agentId}" title="คุยกับ ${esc(alt)}"` : '';
  const cls = agentId ? 'chara clickable' : 'chara';
  const badge = status ? `<span class="st-badge ${esc(status)}"></span>` : '';
  const onerr = "var b='" + base + "',p='/static/characters/';if(!this.dataset.t){this.dataset.t='1';this.src=p+b+'.png';}else if(this.dataset.t==='1'){this.dataset.t='2';this.src=p+b+'.webp';}else{this.style.display='none';var fb=this.nextElementSibling;if(fb)fb.style.display='grid';}";
  return `<div class="${cls}"${action}>
    <img src="/static/characters/${base}.jpg" alt="${esc(alt)}" loading="lazy" onerror="${onerr}">
    <span class="chara-fb" aria-hidden="true">${emoji || '👤'}</span>
    ${badge}
  </div>`;
}

function protoDeptHTML(dept) {
  const cfg = roomCfg(dept);
  if (cfg.visible === false) return '';
  const meta = ROOM_META[dept.name] || { pos: 'pos-operations', file: 'operations', sign: esc(dept.name) };
  const color = cfg.color || dept.color;
  const sign = cfg.label ? esc(cfg.label) : `${esc(dept.name)}${dept.name_en ? `<br><small>${esc(dept.name_en)}</small>` : ""}`;
  const agents = state.data.agents.filter((a) => a.department_id === dept.id);
  const a = agents[0];
  const overdue = state.data.tasks.filter((t) => t.department_id === dept.id && ['todo','doing'].includes(t.status) && t.due_date && t.due_date < todayYMD()).length;
  const cap = a
    ? `<div class="cap"><b>${esc(a.name)}</b><span>${esc(a.role)} · งาน ${a.open_tasks}${overdue ? ` · เร่งด่วน ${overdue}` : ''}</span></div>`
    : `<div class="cap"><b>${esc(dept.name)}</b><span>${dept.name_en ? esc(dept.name_en)+" · " : ""}งาน ${dept.open_tasks}</span></div>`;
  const posStyle = (cfg.x!=null||cfg.y!=null||cfg.w!=null) ? `;left:${cfg.x!=null?cfg.x+'%':''};top:${cfg.y!=null?cfg.y+'%':''};right:auto;${cfg.w!=null?('width:'+cfg.w+'%') : ''};transform:none` : '';
  const editCls = (typeof state!=='undefined' && state.layoutEdit) ? ' layout-editable' : '';
  const dragAct = (typeof state!=='undefined' && state.layoutEdit) ? ' data-drag="dept"' : ' data-action="open-dept"';
  return `<div class="dept ${meta.pos}${editCls}" style="--dc:${esc(color)}${posStyle}"${dragAct} data-id="${dept.id}" data-dept-key="${esc(dept.name)}">
    <div class="dept-sign">${sign}</div>
    ${protoImgHTML(meta.file, a ? a.name : dept.name, a ? a.emoji : dept.icon, a ? a.id : null, a ? a.status : null)}
    <div class="desk"></div>
    ${cap}
  </div>`;
}

function renderOffice() {
  const { stats, departments, me } = state.data;
  const cfg = uiCfg();
  const floor = cfg.floor || {};
  const mcfg = cfg.manager || {};
  const hour = new Date().getHours();
  const greet = hour < 12 ? 'สวัสดีตอนเช้า' : hour < 17 ? 'สวัสดีตอนบ่าย' : 'สวัสดีตอนเย็น';
  const eff = efficiencyPct();
  const showStats = floor.showStats !== false;
  const note = cfg.note || '💡 คลิกตัวละครเพื่อคุย/สั่งงานผู้ช่วย AI · คลิกการ์ดแผนกเพื่อดูรายละเอียด · คลิก “ผู้จัดการ” เพื่อเปิดแดชบอร์ด';
  const managerVisible = mcfg.visible !== false;
  const managerLabel = mcfg.label || 'ผู้จัดการ';
  return `
  <div class="page-head">
    <div>
      <h2>${greet} ผู้จัดการ ${esc(me.display_name)}</h2>
      <p>ออฟฟิศเสมือน Sci-Fi Anime · ทีม AI ${stats.agents} คน · ${departments.length} แผนก ·
         ${thaiDate(new Date(), { day: 'numeric', month: 'long' })}</p>
    </div>
    <div class="head-actions">
      <button class="btn btn-ghost btn-sm" data-action="toggle-layout-edit" title="จัดวางตำแหน่งแผนกได้อิสระ">${(typeof state!=='undefined'&&state.layoutEdit)?'✅ บันทึกเลเอาต์':'↔️ จัดวางอิสระ'}</button>
      <button class="btn btn-ghost btn-sm" data-action="ui-config" title="จัดการหน้าแอป / API สำหรับ AI">🛠️ UI/API</button>
      <button class="btn btn-soft" data-action="run-agents">✨ สแกนงานอัตโนมัติ</button>
      <button class="btn btn-primary" data-action="add-task">${I.plus} มอบหมายงาน</button>
    </div>
  </div>

  <div class="command-bar">
    <form class="command-form" id="commandForm" autocomplete="off">
      <span class="command-spark">⚡</span>
      <input id="commandText" maxlength="500" placeholder="สั่งงานด้วยภาษาธรรมชาติ… เช่น เพิ่มงาน ตรวจสต็อกพรุ่งนี้ 10:00 ให้พี่บี">
      <button type="submit" class="btn btn-primary" id="commandSend">สั่งงาน</button>
    </form>
    <div class="command-chips">
      <button type="button" data-action="command-suggest" data-text="สรุปงานวันนี้">สรุปงานวันนี้</button>
      <button type="button" data-action="command-suggest" data-text="งานไหนด่วนที่สุด">งานด่วน</button>
      <button type="button" data-action="command-suggest" data-text="ช่วยอะไรได้บ้าง">คำสั่งที่ใช้ได้</button>
      <span class="command-hint">กด <kbd>Ctrl</kbd> + <kbd>K</kbd> เพื่อโฟกัสช่องสั่งงาน</span>
    </div>
    <div class="command-result" id="commandResult" hidden></div>
  </div>

  <div class="proto-scene-wrap">
    <div class="proto-scene" id="scene">
      <div class="main-dashboard">
        <h2>${esc(floor.title || 'ภาพรวมออฟฟิศ')}</h2>
        ${floor.subtitle ? `<div class="sub">${esc(floor.subtitle)}</div>` : `<div class="sub">ข้อมูลจริงจากระบบ</div>`}
        ${showStats ? `<div class="dash-stats">
          <div>ทีม AI<br><b>${stats.agents}/${stats.agents}</b></div>
          <div>งานค้าง<br><b>${stats.open}</b></div>
          <div>เสร็จ 7 วัน<br><b>${stats.done_week}</b></div>
          <div>ประสิทธิภาพ<br><b>${eff}%</b></div>
        </div>` : ''}
      </div>

      ${managerVisible ? `<div class="dept pos-manager" style="--dc:#22d3ee" data-action="nav" data-view="dashboard" title="เปิดแดชบอร์ดผู้จัดการ">
        <div class="dept-sign">${esc(managerLabel)}</div>
        ${protoImgHTML('manager', me.display_name || 'ผู้จัดการ', '👩‍💼', null, null)}
        <div class="desk"></div>
        <div class="cap"><b>Dashboard หลัก</b><span>งานวันนี้ ${stats.today} · เกินกำหนด ${stats.overdue}</span></div>
      </div>` : ''}

      ${departments.map(protoDeptHTML).join('')}
    </div>
  </div>

  ${state.layoutEdit ? `<div class="office-note" style="margin-top:14px">↔️ <b>โหมดจัดวางอิสระ:</b> ลากการ์ดแผนกเพื่อย้ายตำแหน่ง แล้วกด “✅ บันทึกเลเอาต์” · <button class="btn btn-sm btn-ghost" data-action="reset-layout" style="margin-left:6px">รีเซ็ตตำแหน่ง</button></div>` : `<div class="office-note" style="margin-top:14px">${esc(note)}</div>`}`;
}

/* ---------------- tasks ---------------- */
function taskCounts() {
  const all = state.data.tasks;
  const today = todayYMD();
  const isOpen = (t) => ['todo', 'doing'].includes(t.status);
  return {
    open: all.filter(isOpen).length,
    today: all.filter((t) => isOpen(t) && t.due_date === today).length,
    overdue: all.filter((t) => isOpen(t) && t.due_date && t.due_date < today).length,
    done: all.filter((t) => t.status === 'done').length,
    all: all.length,
  };
}

function filteredTasks() {
  const f = state.taskFilter;
  const today = todayYMD();
  let list = state.data.tasks;
  if (f === 'open') list = list.filter((t) => ['todo', 'doing'].includes(t.status));
  else if (f === 'today') list = list.filter((t) => ['todo', 'doing'].includes(t.status) && t.due_date === today);
  else if (f === 'overdue') list = list.filter((t) => ['todo', 'doing'].includes(t.status) && t.due_date && t.due_date < today);
  else if (f === 'done') list = list.filter((t) => t.status === 'done');
  const q = state.taskSearch.trim().toLowerCase();
  if (q) {
    list = list.filter((t) => [t.title, t.detail, t.dept_name, t.agent_name, t.tags]
      .join(' ').toLowerCase().includes(q));
  }
  if (f === 'done') {
    list = [...list].sort((a, b) => String(b.completed_at || '').localeCompare(String(a.completed_at || '')));
  }
  return list;
}

function taskRowHTML(t) {
  const due = dueInfo(t);
  const isOpen = ['todo', 'doing'].includes(t.status);
  const overdue = isOpen && t.due_date && t.due_date < todayYMD();
  const done = t.status === 'done';
  return `<div class="task-row ${done ? 'done' : ''} ${t.status === 'doing' ? 'doing' : ''} ${overdue ? 'overdue' : ''}" data-id="${t.id}">
    <button class="check" data-action="toggle-task" data-id="${t.id}" title="${done ? 'เปิดงานอีกครั้ง' : 'ทำเครื่องหมายว่าเสร็จ'}">${I.check}</button>
    <div class="task-main" data-action="edit-task" data-id="${t.id}" style="cursor:pointer">
      <p class="task-title">${esc(t.title)}</p>
      <div class="task-meta">
        <span class="priority ${esc(t.priority)}">${PRIORITY_LABEL[t.priority] || t.priority}</span>
        ${t.due_date ? `<span class="meta-chip due ${done ? '' : due.cls}">📅 ${due.text}</span>` : ''}
        ${t.dept_name ? `<span class="meta-chip dept" style="--dc:${esc(t.dept_color)}">${t.dept_icon || '🏢'} ${esc(t.dept_name)}</span>` : ''}
        ${t.agent_name ? `<span class="meta-chip agent">${t.agent_emoji || '🤖'} ${esc(t.agent_name)}</span>` : ''}
        ${t.repeat_rule && t.repeat_rule !== 'none' ? `<span class="meta-chip">🔁 ${REPEAT_LABEL[t.repeat_rule] || t.repeat_rule}</span>` : ''}
      </div>
    </div>
    <div class="task-actions">
      <button class="icon-btn" data-action="edit-task" data-id="${t.id}" title="แก้ไข">${I.edit}</button>
      <button class="icon-btn del" data-action="delete-task" data-id="${t.id}" title="ลบ">${I.trash}</button>
    </div>
  </div>`;
}

function taskListHTML() {
  const list = filteredTasks();
  if (!list.length) {
    const text = state.taskSearch ? 'ไม่พบงานที่ตรงกับคำค้น' : 'ยังไม่มีงานในหมวดนี้';
    return `<div class="empty-state"><span class="emoji">🗂️</span>
      <strong>${text}</strong><p>กดปุ่ม “เพิ่มงาน” เพื่อมอบหมายงานให้ทีม AI</p></div>`;
  }
  return `<div class="task-list">${list.map(taskRowHTML).join('')}</div>`;
}

function refreshTaskList() {
  const wrap = document.getElementById('taskListWrap');
  if (wrap) wrap.innerHTML = taskListHTML();
}

function renderTasks() {
  const c = taskCounts();
  const tabs = [
    ['open', 'งานค้าง', c.open],
    ['today', 'วันนี้', c.today],
    ['overdue', 'เกินกำหนด', c.overdue],
    ['done', 'เสร็จแล้ว', c.done],
    ['all', 'ทั้งหมด', c.all],
  ];
  return `
  <div class="page-head">
    <div>
      <h2>งานและแจ้งเตือน</h2>
      <p>มอบหมายงานให้ทีม AI ติดตามกำหนดส่ง และปิดงานได้ในที่เดียว</p>
    </div>
    <div class="head-actions">
      <button class="btn" data-action="run-agents">✨ ตรวจงานอัตโนมัติ</button>
      <button class="btn btn-primary" data-action="add-task">${I.plus} เพิ่มงาน</button>
    </div>
  </div>
  <div class="toolbar">
    <div class="tabs">
      ${tabs.map(([key, label, count]) => `<button class="tab ${state.taskFilter === key ? 'active' : ''}"
        data-action="task-filter" data-filter="${key}">${label} <span style="opacity:.55">${count}</span></button>`).join('')}
    </div>
    <div class="search-box">
      ${I.search}
      <input id="taskSearch" type="search" placeholder="ค้นหางาน แผนก หรือผู้รับผิดชอบ…" value="${esc(state.taskSearch)}">
    </div>
  </div>
  <div id="taskListWrap">${taskListHTML()}</div>`;
}

/* ---------------- calendar ---------------- */
function calendarMatrix(year, month) {
  const first = new Date(year, month, 1);
  const offset = (first.getDay() + 6) % 7;
  const start = new Date(year, month, 1 - offset);
  return Array.from({ length: 42 }, (_, i) => new Date(start.getFullYear(), start.getMonth(), start.getDate() + i));
}

function calendarMap() {
  const map = {};
  state.data.tasks.forEach((t) => {
    if (!t.due_date) return;
    (map[t.due_date] = map[t.due_date] || []).push(t);
  });
  return map;
}

function calCellHTML(d, cursorMonth, map) {
  const key = ymd(d);
  const list = (map[key] || []).slice().sort((a, b) => {
    const rank = (t) => (t.status === 'done' ? 2 : t.status === 'cancelled' ? 3 : 1);
    return rank(a) - rank(b);
  });
  const other = d.getMonth() !== cursorMonth;
  const isToday = key === todayYMD();
  const chips = list.slice(0, 3).map((t) => {
    const overdue = ['todo', 'doing'].includes(t.status) && key < todayYMD();
    return `<span class="cal-chip ${t.status === 'done' ? 'done' : ''} ${overdue ? 'overdue' : ''}"
      style="--dc:${esc(t.dept_color || '#0f766e')}" title="${esc(t.title)}">${esc(t.title)}</span>`;
  }).join('');
  const more = list.length > 3 ? `<span class="cal-more">+${list.length - 3} งาน</span>` : '';
  return `<div class="cal-cell ${other ? 'other' : ''} ${isToday ? 'today' : ''}"
      data-action="open-day" data-date="${key}">
    <span class="cal-date">${d.getDate()}</span>
    ${chips}${more}
  </div>`;
}

function renderCalendar() {
  const cursor = state.calCursor;
  const year = cursor.getFullYear();
  const month = cursor.getMonth();
  const matrix = calendarMatrix(year, month);
  const map = calendarMap();
  const monthLabel = thaiDate(new Date(year, month, 1), { month: 'long', year: 'numeric' });
  const monthTaskCount = state.data.tasks.filter((t) => t.due_date && parseYMD(t.due_date).getMonth() === month && parseYMD(t.due_date).getFullYear() === year).length;

  return `
  <div class="page-head">
    <div>
      <h2>ปฏิทินงาน</h2>
      <p>ภาพรวมกำหนดส่งทั้งเดือน · ${monthTaskCount} งานในเดือนนี้</p>
    </div>
    <div class="head-actions">
      <button class="btn btn-primary" data-action="add-task">${I.plus} เพิ่มงาน</button>
    </div>
  </div>
  <div class="cal-wrap">
    <div class="cal-head">
      <h3>${monthLabel}</h3>
      <div class="cal-nav">
        <button class="icon-btn" data-action="cal-prev" title="เดือนก่อน">${I.arrowL}</button>
        <button class="btn btn-sm" data-action="cal-today">วันนี้</button>
        <button class="icon-btn" data-action="cal-next" title="เดือนถัดไป">${I.arrowR}</button>
      </div>
    </div>
    <div class="cal-grid">
      ${WEEKDAYS_SHORT.map((w, i) => `<div class="cal-dow ${i === 6 ? 'sun' : ''}">${w}</div>`).join('')}
      ${matrix.map((d) => calCellHTML(d, month, map)).join('')}
    </div>
    <div class="cal-legend">
      <span><i style="background:#0f766e"></i> งานตามแผนก</span>
      <span><i style="background:#dc2626"></i> เกินกำหนด</span>
      <span><i style="background:#cbd5cf"></i> เสร็จแล้ว</span>
      <span style="margin-left:auto">คลิกที่วันเพื่อดูงานทั้งหมด</span>
    </div>
  </div>`;
}

/* ---------------- documents ---------------- */
function docCategories() {
  const set = new Set((state.data.documents || []).map((d) => d.category || 'ยังไม่จัดหมวด'));
  return [...set];
}

function filteredDocs() {
  let list = state.data.documents || [];
  if (state.docCategory !== 'all') list = list.filter((d) => (d.category || 'ยังไม่จัดหมวด') === state.docCategory);
  if (state.docDept !== 'all') list = list.filter((d) => String(d.department_id) === String(state.docDept));
  const q = state.docSearch.trim().toLowerCase();
  if (q) {
    list = list.filter((d) => [d.title, d.filename, d.category, d.dept_name, d.agent_name, d.notes]
      .join(' ').toLowerCase().includes(q));
  }
  return list;
}

function docCardHTML(doc) {
  const meta = fileMeta(doc.filename);
  return `<article class="doc-card">
    <div class="doc-top">
      <div class="doc-icon ${meta.cls}">${meta.icon}</div>
      <div class="doc-name">
        <strong>${esc(doc.title)}</strong>
        <span>${meta.label} · ${fileSize(doc.size)} · ${timeAgo(doc.created_at)}</span>
      </div>
    </div>
    <div class="doc-meta">
      <span class="meta-chip">${esc(doc.category || 'ยังไม่จัดหมวด')}</span>
      ${doc.dept_name ? `<span class="meta-chip dept" style="--dc:${esc(doc.dept_color)}">${doc.dept_icon || '🏢'} ${esc(doc.dept_name)}</span>` : ''}
      ${doc.agent_name ? `<span class="meta-chip">${doc.agent_emoji || '🤖'} ${esc(doc.agent_name)}</span>` : ''}
    </div>
    <div class="doc-actions">
      ${['xls','xlsx','csv'].includes((doc.filename||'').split('.').pop().toLowerCase()) ? `<button class="btn btn-sm btn-soft" data-action="preview-doc" data-id="${doc.id}">📊 โหลด/ดูข้อมูล</button>` : ''}
      <a class="btn btn-sm" href="/api/documents/${doc.id}/download">${I.download} ดาวน์โหลด</a>
      <button class="icon-btn del" data-action="delete-doc" data-id="${doc.id}" title="ลบเอกสาร">${I.trash}</button>
    </div>
  </article>`;
}

function docGridHTML() {
  const list = filteredDocs();
  if (!list.length) {
    return `<div class="empty-state"><span class="emoji">📂</span>
      <strong>ยังไม่มีเอกสารในหมวดนี้</strong><p>ลากไฟล์มาวาง หรือกดปุ่มอัปโหลดเพื่อเริ่มจัดเก็บ</p></div>`;
  }
  return `<div class="doc-grid">${list.map(docCardHTML).join('')}</div>`;
}

function refreshDocGrid() {
  const wrap = document.getElementById('docGrid');
  if (wrap) wrap.innerHTML = docGridHTML();
}

function renderDocs() {
  const cats = docCategories();
  const depts = state.data.departments;
  return `
  <div class="page-head">
    <div>
      <h2>ศูนย์เอกสารและไฟล์</h2>
      <p>จัดเก็บ ค้นหา และดาวน์โหลดเอกสารทั้งหมด · ${state.data.documents.length} รายการ</p>
    </div>
    <div class="head-actions">
      <button class="btn btn-primary" data-action="upload-doc">${I.upload} อัปโหลดเอกสาร</button>
    </div>
  </div>

  <div class="dropzone" data-action="upload-doc">
    <div class="dropzone-icon">📥</div>
    <div>
      <strong>ลากไฟล์มาวางที่นี่เพื่ออัปโหลด</strong>
      <span>รองรับ PDF, Word, Excel, รูปภาพ, ZIP และไฟล์ข้อความ ขนาดไม่เกิน 25 MB</span>
    </div>
  </div>

  <div class="toolbar">
    <div class="tabs">
      <button class="tab ${state.docCategory === 'all' ? 'active' : ''}" data-action="doc-cat" data-cat="all">ทั้งหมด</button>
      ${cats.map((c) => `<button class="tab ${state.docCategory === c ? 'active' : ''}" data-action="doc-cat" data-cat="${esc(c)}">${esc(c)}</button>`).join('')}
    </div>
    <select id="docDeptFilter" style="padding:8px 11px;border-radius:10px;border:1px solid var(--line);background:var(--card);font-size:12px;color:var(--ink)">
      <option value="all">ทุกแผนก</option>
      ${depts.map((d) => `<option value="${d.id}" ${String(state.docDept) === String(d.id) ? 'selected' : ''}>${d.icon} ${esc(d.name)}</option>`).join('')}
    </select>
    <div class="search-box">
      ${I.search}
      <input id="docSearch" type="search" placeholder="ค้นหาเอกสาร…" value="${esc(state.docSearch)}">
    </div>
  </div>

  <div id="docGrid">${docGridHTML()}</div>`;
}

/* ---------------- activity ---------------- */
function activityItemHTML(a) {
  return `<div class="tl-item ${a.actor === 'ทีม AI' ? 'ai' : ''}">
    <h4><span class="tl-actor">${esc(a.actor)}</span>${esc(a.action)}</h4>
    ${a.detail ? `<p>${esc(a.detail)}</p>` : ''}
    <time>${timeAgo(a.created_at)}</time>
  </div>`;
}

function renderActivity() {
  const list = state.data.activity || [];
  return `
  <div class="page-head">
    <div>
      <h2>บันทึกกิจกรรม</h2>
      <p>ทุกการเคลื่อนไหวในออฟฟิศ ทั้งจากคุณและทีม AI</p>
    </div>
  </div>
  ${list.length
    ? `<div class="timeline">${list.map(activityItemHTML).join('')}</div>`
    : `<div class="empty-state"><span class="emoji">📜</span><strong>ยังไม่มีกิจกรรม</strong><p>เริ่มเพิ่มงานหรืออัปโหลดเอกสาร แล้วกิจกรรมจะแสดงที่นี่</p></div>`}`;
}
