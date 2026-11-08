'use strict';

/* ============================================================
   Dashboard: customizable widgets
   ============================================================ */

function renderDashboard() {
  const widgets = state.data.widgets || [];
  const available = availableWidgets();
  return `
  <div class="page-head">
    <div>
      <h2>แดชบอร์ดของฉัน</h2>
      <p>ปรับแต่งการ์ด เพิ่ม ลบ และลากจัดลำดับได้ตามใจชอบ</p>
    </div>
    <div class="head-actions">
      <button class="btn" data-action="run-agents">✨ ให้ทีม AI อัปเดต</button>
    </div>
  </div>

  <div class="dash-toolbar">
    <span class="hint-text">${state.dashEdit
      ? 'โหมดปรับแต่ง: ลากการ์ดเพื่อจัดลำดับ · กดไอคอนขนาดเพื่อสลับความกว้าง'
      : 'ทุกการ์ดเลือกแสดงได้ตามต้องการ และบันทึกอัตโนมัติ'}</span>
    <button class="btn btn-sm ${state.dashEdit ? 'btn-primary' : ''}" data-action="toggle-dash-edit">
      ${state.dashEdit ? '✓ เสร็จสิ้น' : '⚙️ ปรับแต่ง'}
    </button>
    ${state.dashEdit && available.length ? `
      <select id="widgetAddSelect" style="padding:7px 10px;border-radius:10px;border:1px solid var(--line);background:var(--card);font-size:12px">
        ${available.map((t) => `<option value="${t}">${WIDGET_TITLES[t]}</option>`).join('')}
      </select>
      <button class="btn btn-sm btn-soft" data-action="add-widget">${I.plus} เพิ่มการ์ด</button>` : ''}
  </div>

  ${widgets.length
    ? `<div class="widget-grid" id="widgetGrid">${widgets.map(widgetHTML).join('')}</div>`
    : `<div class="empty-state"><span class="emoji">🧩</span><strong>แดชบอร์ดยังว่างอยู่</strong><p>กด “ปรับแต่ง” แล้วเพิ่มการ์ดที่ต้องการได้เลย</p></div>`}`;
}

function widgetHTML(w) {
  const size = ['third', 'half', 'full'].includes(w.size) ? w.size : 'half';
  return `<section class="widget span-${size}" data-widget-id="${w.id}" draggable="${state.dashEdit ? 'true' : 'false'}">
    <div class="widget-head">
      ${state.dashEdit ? '<span class="drag-handle" title="ลากเพื่อจัดลำดับ">⠿</span>' : ''}
      <h4>${esc(w.title)}</h4>
      ${state.dashEdit ? `
        <button class="icon-btn" data-action="resize-widget" data-id="${w.id}" title="สลับขนาด">${I.expand}</button>
        <button class="icon-btn del" data-action="remove-widget" data-id="${w.id}" title="ซ่อนการ์ด">${I.trash}</button>` : ''}
    </div>
    <div class="widget-body">${widgetBody(w.widget_type)}</div>
  </section>`;
}

function miniTaskListHTML(tasks, emptyText) {
  if (!tasks.length) return `<div class="mini-empty">${emptyText}</div>`;
  return `<div class="mini-list">${tasks.slice(0, 6).map((t) => `
    <div class="mini-task">
      <button class="check" data-action="toggle-task" data-id="${t.id}" title="ทำเครื่องหมายว่าเสร็จ">${I.check}</button>
      <span class="dot" style="background:${esc(t.dept_color || '#0f766e')}"></span>
      <span class="t">${esc(t.title)}</span>
      <span class="d">${dueInfo(t).text}</span>
    </div>`).join('')}</div>`;
}

function miniCalendarHTML() {
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth();
  const matrix = calendarMatrix(year, month);
  const map = {};
  state.data.tasks.forEach((t) => {
    if (t.due_date) (map[t.due_date] = map[t.due_date] || []).push(t);
  });
  return `<div class="mini-cal">
    ${WEEKDAYS_SHORT.map((w) => `<span class="dow">${w}</span>`).join('')}
    ${matrix.map((d) => {
      const key = ymd(d);
      return `<span class="d ${d.getMonth() !== month ? 'other' : ''} ${key === todayYMD() ? 'today' : ''} ${(map[key] || []).length ? 'has' : ''}">${d.getDate()}</span>`;
    }).join('')}
  </div>`;
}

function widgetBody(type) {
  const s = state.data.stats;
  const today = todayYMD();
  const open = openTasks();

  if (type === 'overview') {
    return `<div class="mini-stat-grid">
      <div class="mini-stat"><b>${s.open}</b><span>งานค้าง</span></div>
      <div class="mini-stat amber"><b>${s.today}</b><span>ครบวันนี้</span></div>
      <div class="mini-stat red"><b>${s.overdue}</b><span>เกินกำหนด</span></div>
      <div class="mini-stat green"><b>${s.done_week}</b><span>เสร็จ 7 วัน</span></div>
    </div>`;
  }

  if (type === 'today') {
    const list = open.filter((t) => t.due_date === today)
      .sort((a, b) => String(a.due_time || '23:59').localeCompare(String(b.due_time || '23:59')));
    return miniTaskListHTML(list, 'ไม่มีงานครบกำหนดวันนี้ 🎉');
  }

  if (type === 'overdue') {
    const list = open.filter((t) => t.due_date && t.due_date < today)
      .sort((a, b) => String(a.due_date).localeCompare(String(b.due_date)));
    return miniTaskListHTML(list, 'เยี่ยม! ไม่มีงานเกินกำหนด');
  }

  if (type === 'upcoming') {
    const limit = new Date();
    limit.setDate(limit.getDate() + 7);
    const limitKey = ymd(limit);
    const list = open.filter((t) => t.due_date && t.due_date > today && t.due_date <= limitKey)
      .sort((a, b) => String(a.due_date).localeCompare(String(b.due_date)));
    return miniTaskListHTML(list, 'ยังไม่มีงานใน 7 วันข้างหน้า');
  }

  if (type === 'workload') {
    const depts = [...state.data.departments].sort((a, b) => b.open_tasks - a.open_tasks);
    const max = Math.max(1, ...depts.map((d) => d.open_tasks));
    return depts.map((d) => `<div class="bar-row">
      <span class="bl">${d.icon} ${esc(d.name)}</span>
      <span class="bar"><i style="width:${Math.round((d.open_tasks / max) * 100)}%;--c:${esc(d.color)}"></i></span>
      <b>${d.open_tasks}</b>
    </div>`).join('');
  }

  if (type === 'team') {
    return `<div class="team-mini">${state.data.agents.map((a) => `
      <button class="team-chip" data-action="open-agent" data-id="${a.id}" title="คุยกับ ${esc(a.name)}">
        <span class="em">${a.emoji}</span>
        <span class="st ${esc(a.status)}"></span>
        <span>${esc(a.name)}</span>
        <span style="color:var(--muted)">${a.open_tasks}</span>
      </button>`).join('')}</div>`;
  }

  if (type === 'docs') {
    const docs = state.data.documents.slice(0, 5);
    if (!docs.length) return '<div class="mini-empty">ยังไม่มีเอกสารในคลัง</div>';
    return `<div class="mini-list">${docs.map((d) => {
      const meta = fileMeta(d.filename);
      return `<div class="mini-task" data-action="nav" data-view="docs" style="cursor:pointer">
        <span>${meta.icon}</span>
        <span class="t">${esc(d.title)}</span>
        <span class="d">${timeAgo(d.created_at)}</span>
      </div>`;
    }).join('')}</div>`;
  }

  if (type === 'quickadd') {
    return `<form id="quickForm" class="quick-form">
      <input name="title" placeholder="ชื่องานใหม่…" maxlength="120" required>
      <div class="row">
        <select name="agent_id">
          <option value="">เลือกผู้ช่วย (ไม่บังคับ)</option>
          ${agentSelectOptions('', '')}
        </select>
        <button class="btn btn-primary btn-sm" type="submit">เพิ่ม</button>
      </div>
    </form>`;
  }

  if (type === 'calendar') {
    return miniCalendarHTML();
  }

  if (type === 'activity') {
    const list = (state.data.activity || []).slice(0, 6);
    if (!list.length) return '<div class="mini-empty">ยังไม่มีกิจกรรม</div>';
    return `<div class="mini-list">${list.map((a) => `
      <div class="mini-task">
        <span class="dot" style="background:${a.actor === 'ทีม AI' ? '#f0b429' : '#0f766e'}"></span>
        <span class="t"><b style="font-weight:600">${esc(a.actor)}</b> ${esc(a.action)}</span>
        <span class="d">${timeAgo(a.created_at)}</span>
      </div>`).join('')}</div>`;
  }

  return '<div class="mini-empty">ไม่รู้จักการ์ดนี้</div>';
}

function setupWidgetDnD() {
  if (!state.dashEdit) return;
  const grid = document.getElementById('widgetGrid');
  if (!grid) return;
  let dragId = null;

  $$('.widget', grid).forEach((el) => {
    el.addEventListener('dragstart', (e) => {
      dragId = Number(el.dataset.widgetId);
      el.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', String(dragId));
    });
    el.addEventListener('dragend', () => {
      el.classList.remove('dragging');
      $$('.widget', grid).forEach((x) => x.classList.remove('drag-over'));
    });
    el.addEventListener('dragover', (e) => {
      e.preventDefault();
      if (Number(el.dataset.widgetId) !== dragId) el.classList.add('drag-over');
    });
    el.addEventListener('dragleave', () => el.classList.remove('drag-over'));
    el.addEventListener('drop', async (e) => {
      e.preventDefault();
      const targetId = Number(el.dataset.widgetId);
      el.classList.remove('drag-over');
      if (!dragId || dragId === targetId) return;
      const list = state.data.widgets;
      const from = list.findIndex((w) => w.id === dragId);
      const to = list.findIndex((w) => w.id === targetId);
      if (from < 0 || to < 0) return;
      const [item] = list.splice(from, 1);
      list.splice(to, 0, item);
      render();
      try {
        await api('/api/widgets/reorder', { method: 'POST', body: { ids: list.map((w) => w.id) } });
      } catch (err) {
        toast(err.message, 'error');
      }
    });
  });
}
