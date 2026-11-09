'use strict';

/* ============================================================
   Modals: task, upload, department, day, password, confirm
   ============================================================ */

function openModal(html, size = '') {
  const root = document.getElementById('modalRoot');
  if (!root) return;
  root.innerHTML = `<div class="modal-overlay" data-action="modal-backdrop">
    <div class="modal ${size}" role="dialog" aria-modal="true">${html}</div>
  </div>`;
  document.body.style.overflow = 'hidden';
  setTimeout(() => {
    const first = root.querySelector('.modal-body input:not([type=file]), .modal-body textarea, .modal-body select');
    if (first) first.focus();
  }, 60);
}

function closeModal() {
  const root = document.getElementById('modalRoot');
  if (root) root.innerHTML = '';
  document.body.style.overflow = '';
}

function modalHead(title, subtitle = '') {
  return `<div class="modal-head">
    <div><h3>${title}</h3>${subtitle ? `<p>${subtitle}</p>` : ''}</div>
    <button class="modal-close" data-action="close-modal" aria-label="ปิด">✕</button>
  </div>`;
}

function confirmDialog(message, onConfirm, opts = {}) {
  state.confirmFn = onConfirm;
  openModal(`
    ${modalHead(opts.title || 'ยืนยันการทำรายการ')}
    <div class="modal-body">
      <p style="font-size:13.5px;line-height:1.75;color:#44564f;margin:0">${esc(message)}</p>
    </div>
    <div class="modal-foot">
      <button class="btn" data-action="close-modal">ยกเลิก</button>
      <button class="btn ${opts.danger === false ? 'btn-primary' : 'btn-danger'}" data-action="confirm-run">
        ${esc(opts.confirmText || 'ยืนยัน')}
      </button>
    </div>`);
}

/* ---------------- task ---------------- */
function openTaskModal(task = null, preset = {}) {
  const editing = Boolean(task);
  const t = task || {
    title: '', detail: '', department_id: preset.department_id || '', agent_id: preset.agent_id || '',
    due_date: preset.due_date || '', due_time: '', priority: 'normal', repeat_rule: 'none', status: 'todo',
  };
  const deptId = t.department_id || '';
  const agentId = t.agent_id || '';

  openModal(`
    ${modalHead(editing ? 'แก้ไขงาน' : 'เพิ่มงานใหม่',
      editing ? 'ปรับรายละเอียด กำหนดส่ง หรือผู้รับผิดชอบ' : 'มอบหมายงานให้ทีม AI และกำหนดวันครบกำหนด')}
    <form id="taskForm" data-id="${editing ? t.id : ''}">
      <div class="modal-body">
        <div class="form-grid">
          <div class="field span-2">
            <label>ชื่องาน *</label>
            <input name="title" maxlength="180" required value="${esc(t.title)}" placeholder="เช่น สรุปยอดขายประจำเดือน">
          </div>
          <div class="field span-2">
            <label>รายละเอียด</label>
            <textarea name="detail" placeholder="รายละเอียดเพิ่มเติม ขั้นตอน หรือสิ่งที่ต้องส่งมอบ">${esc(t.detail || '')}</textarea>
          </div>
          <div class="field">
            <label>แผนก</label>
            <select name="department_id" id="f_dept">
              <option value="">ไม่ระบุแผนก</option>
              ${deptSelectOptions(deptId)}
            </select>
          </div>
          <div class="field">
            <label>ผู้รับผิดชอบ</label>
            <select name="agent_id" id="f_agent">
              <option value="">ไม่ระบุผู้ช่วย</option>
              ${agentSelectOptions(deptId, agentId)}
            </select>
          </div>
          <div class="field">
            <label>วันครบกำหนด</label>
            <input type="date" name="due_date" value="${esc(t.due_date || '')}">
          </div>
          <div class="field">
            <label>เวลา</label>
            <input type="time" name="due_time" value="${esc(t.due_time || '')}">
          </div>
          <div class="field">
            <label>ความสำคัญ</label>
            <select name="priority">
              ${Object.entries(PRIORITY_LABEL).map(([k, v]) => `<option value="${k}" ${t.priority === k ? 'selected' : ''}>${v}</option>`).join('')}
            </select>
          </div>
          <div class="field">
            <label>ทำซ้ำ</label>
            <select name="repeat_rule">
              ${Object.entries(REPEAT_LABEL).map(([k, v]) => `<option value="${k}" ${t.repeat_rule === k ? 'selected' : ''}>${v}</option>`).join('')}
            </select>
          </div>
          ${editing ? `<div class="field">
            <label>สถานะ</label>
            <select name="status">
              ${Object.entries(STATUS_LABEL).map(([k, v]) => `<option value="${k}" ${t.status === k ? 'selected' : ''}>${v}</option>`).join('')}
            </select>
          </div>` : ''}
        </div>
      </div>
      <div class="modal-foot">
        <button type="button" class="btn" data-action="close-modal">ยกเลิก</button>
        <button type="submit" class="btn btn-primary">${editing ? 'บันทึกการแก้ไข' : 'เพิ่มงาน'}</button>
      </div>
    </form>`, editing ? '' : '');
}

function syncAgentSelect(deptSel, agentSel) {
  if (!deptSel || !agentSel) return;
  const dept = deptSel.value;
  [...agentSel.options].forEach((o) => {
    if (!o.value) return;
    const ok = !dept || String(o.dataset.dept) === String(dept);
    o.hidden = !ok;
    o.disabled = !ok;
    if (!ok && o.selected) agentSel.value = '';
  });
}

async function saveTask(form) {
  const fd = new FormData(form);
  const val = (k) => String(fd.get(k) || '').trim();
  const payload = {
    title: val('title'),
    detail: val('detail'),
    department_id: val('department_id') || null,
    agent_id: val('agent_id') || null,
    due_date: val('due_date') || null,
    due_time: val('due_time') || null,
    priority: val('priority') || 'normal',
    repeat_rule: val('repeat_rule') || 'none',
  };
  if (!payload.title) { toast('กรุณาระบุชื่องาน', 'error'); return; }
  const id = form.dataset.id;
  if (id) payload.status = val('status') || 'todo';
  const btn = form.querySelector('button[type=submit]');
  if (btn) btn.disabled = true;
  try {
    if (id) await api(`/api/tasks/${id}`, { method: 'PATCH', body: payload });
    else await api('/api/tasks', { method: 'POST', body: payload });
    closeModal();
    toast(id ? 'อัปเดตงานเรียบร้อยแล้ว' : 'เพิ่มงานเรียบร้อยแล้ว');
    await load();
  } catch (err) {
    toast(err.message, 'error');
    if (btn) btn.disabled = false;
  }
}

/* ---------------- upload ---------------- */
function openUploadModal(file = null) {
  state.pendingFile = file || null;
  openModal(`
    ${modalHead('อัปโหลดเอกสาร', 'จัดเก็บไฟล์เข้าศูนย์เอกสารและมอบหมายผู้ดูแล')}
    <form id="uploadForm">
      <div class="modal-body">
        <div class="form-grid">
          <div class="field span-2">
            <label>ไฟล์ *</label>
            <input id="u_file" type="file"
              accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.csv,.md,.png,.jpg,.jpeg,.gif,.webp,.svg,.zip,.rar,.7z,.json">
            ${file ? `<span class="hint">ไฟล์ที่เลือก: ${esc(file.name)} (${fileSize(file.size)})</span>`
                   : '<span class="hint">ขนาดไม่เกิน 25 MB</span>'}
          </div>
          <div class="field span-2">
            <label>ชื่อเอกสาร</label>
            <input name="title" maxlength="180" placeholder="เว้นว่างเพื่อใช้ชื่อไฟล์">
          </div>
          <div class="field">
            <label>หมวดหมู่</label>
            <select name="category">
              ${CATEGORIES.map((c) => `<option value="${esc(c)}" ${c === 'ยังไม่จัดหมวด' ? 'selected' : ''}>${esc(c)}</option>`).join('')}
            </select>
          </div>
          <div class="field">
            <label>แผนก</label>
            <select name="department_id" id="u_dept">
              <option value="">ไม่ระบุแผนก</option>
              ${deptSelectOptions('')}
            </select>
          </div>
          <div class="field">
            <label>ผู้ดูแลเอกสาร</label>
            <select name="agent_id" id="u_agent">
              <option value="">ไม่ระบุผู้ช่วย</option>
              ${agentSelectOptions('', '')}
            </select>
          </div>
          <div class="field">
            <label>หมายเหตุ</label>
            <input name="notes" maxlength="200" placeholder="เช่น ใช้แนบกับสัญญาลูกค้า A">
          </div>
        </div>
      </div>
      <div class="modal-foot">
        <button type="button" class="btn" data-action="close-modal">ยกเลิก</button>
        <button type="submit" class="btn btn-primary">อัปโหลด</button>
      </div>
    </form>`);
}

async function saveUpload(form) {
  const file = form.querySelector('#u_file')?.files[0] || state.pendingFile;
  if (!file) { toast('กรุณาเลือกไฟล์ก่อนอัปโหลด', 'error'); return; }
  const fd = new FormData();
  fd.append('file', file, file.name);
  ['title', 'category', 'department_id', 'agent_id', 'notes'].forEach((k) => {
    const el = form.querySelector(`[name="${k}"]`);
    fd.append(k, el ? el.value : '');
  });
  const btn = form.querySelector('button[type=submit]');
  if (btn) { btn.disabled = true; btn.textContent = 'กำลังอัปโหลด…'; }
  try {
    await api('/api/documents', { method: 'POST', body: fd });
    state.pendingFile = null;
    closeModal();
    state.view = 'docs';
    toast('อัปโหลดเอกสารเรียบร้อยแล้ว');
    await load();
  } catch (err) {
    toast(err.message, 'error');
    if (btn) { btn.disabled = false; btn.textContent = 'อัปโหลด'; }
  }
}

/* ---------------- department ---------------- */
function openDeptModal(id) {
  const d = deptById(id);
  if (!d) return;
  const agents = state.data.agents.filter((a) => a.department_id === d.id);
  const tasks = state.data.tasks.filter((t) => t.department_id === d.id && ['todo', 'doing'].includes(t.status));
  const docs = state.data.documents.filter((x) => x.department_id === d.id);

  openModal(`
    ${modalHead(esc(d.name + (d.name_en ? ' / '+d.name_en : '')), esc(d.tagline))}
    <div class="modal-body">
      <div class="dept-hero" style="--c:${esc(d.color)}">
        <div class="room-icon" style="background:color-mix(in srgb, ${esc(d.color)} 14%, #fff);border-color:color-mix(in srgb, ${esc(d.color)} 28%, #fff)">${d.icon}</div>
        <div>
          <h3>${esc(d.name)}${d.name_en ? ` <span class="sub-en">/ ${esc(d.name_en)}</span>` : ""}</h3>
          <p>${esc(d.description || d.tagline)}</p>
        </div>
        <div class="dept-stats">
          <div class="dept-stat"><b>${agents.length}</b><span>ทีม AI</span></div>
          <div class="dept-stat"><b>${tasks.length}</b><span>งานค้าง</span></div>
          <div class="dept-stat"><b>${docs.length}</b><span>เอกสาร</span></div>
        </div>
      </div>

      <div class="agent-section">
        <h4>ทีม AI ในแผนก</h4>
        <div class="dept-agent-grid">
          ${agents.map((a) => `<button class="dept-agent" style="--c:${esc(a.color)}" data-action="open-agent" data-id="${a.id}">
            <span class="em">${a.emoji}</span>
            <span><strong>${esc(a.name)}</strong><span>${esc(a.role)}</span></span>
            <span class="cnt">${a.open_tasks} งาน</span>
          </button>`).join('')}
        </div>
      </div>

      <div class="agent-section">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:7px">
          <h4 style="margin:0">งานค้างในแผนก (${tasks.length})</h4>
          <button class="btn btn-sm" data-action="add-task" data-dept="${d.id}">${I.plus} มอบหมายงาน</button>
        </div>
        ${tasks.length
          ? `<div class="task-list">${tasks.slice(0, 6).map(taskRowHTML).join('')}</div>`
          : '<div class="mini-empty">ไม่มีงานค้างในแผนกนี้</div>'}
      </div>

      <div class="agent-section">
        <h4>เอกสารในแผนก (${docs.length})</h4>
        ${docs.length ? `<div class="mini-list">${docs.slice(0, 5).map((doc) => {
          const meta = fileMeta(doc.filename);
          return `<div class="mini-task">
            <span>${meta.icon}</span>
            <span class="t">${esc(doc.title)}</span>
            <span class="d">${esc(doc.category || '')}</span>
          </div>`;
        }).join('')}</div>` : '<div class="mini-empty">ยังไม่มีเอกสารในแผนกนี้</div>'}
      </div>

      <div class="agent-section" style="margin-bottom:0">
        <h4>🔌 การเชื่อมต่อของแผนก</h4>
        <div class="mini-empty">เชื่อม LINE / Google Sheets / Webhook เฉพาะแผนกนี้</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px">
          <button class="btn btn-sm btn-soft" data-action="dept-integrations" data-id="${d.id}">🔌 ตั้งค่า LINE / Sheets / Webhook</button>
          <a class="btn btn-sm" href="/api/departments/${d.id}/export/tasks.csv">⬇️ ส่งออกงาน (CSV)</a>
        </div>
      </div>
    </div>
    <div class="modal-foot">
      <button class="btn" data-action="close-modal">ปิด</button>
      <button class="btn btn-primary" data-action="add-task" data-dept="${d.id}">${I.plus} เพิ่มงานให้แผนก</button>
    </div>`, 'wide');
}

/* ---------------- day ---------------- */
function openDayModal(dateStr) {
  const tasks = state.data.tasks.filter((t) => t.due_date === dateStr);
  const dateLabel = thaiDate(parseYMD(dateStr), { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
  openModal(`
    ${modalHead(dateLabel, `${tasks.length} งานในวันนี้`)}
    <div class="modal-body">
      ${tasks.length
        ? `<div class="task-list">${tasks.map(taskRowHTML).join('')}</div>`
        : '<div class="empty-state" style="padding:36px 16px"><span class="emoji">📅</span><strong>ไม่มีงานในวันนี้</strong><p>เพิ่มงานใหม่หรือเลือกวันอื่นจากปฏิทิน</p></div>'}
    </div>
    <div class="modal-foot">
      <button class="btn" data-action="close-modal">ปิด</button>
      <button class="btn btn-primary" data-action="add-task" data-date="${dateStr}">${I.plus} เพิ่มงานวันนี้</button>
    </div>`, 'wide');
}

/* ---------------- password ---------------- */
function openPasswordModal() {
  openModal(`
    ${modalHead('เปลี่ยนรหัสผ่าน', 'ตั้งรหัสใหม่ที่มีความยาวอย่างน้อย 6 ตัวอักษร')}
    <form id="passwordForm">
      <div class="modal-body">
        <div class="form-grid">
          <div class="field span-2">
            <label>รหัสผ่านปัจจุบัน</label>
            <input type="password" name="current" autocomplete="current-password" required>
          </div>
          <div class="field">
            <label>รหัสผ่านใหม่</label>
            <input type="password" name="new" autocomplete="new-password" minlength="6" required>
          </div>
          <div class="field">
            <label>ยืนยันรหัสผ่านใหม่</label>
            <input type="password" name="confirm" autocomplete="new-password" minlength="6" required>
          </div>
        </div>
      </div>
      <div class="modal-foot">
        <button type="button" class="btn" data-action="close-modal">ยกเลิก</button>
        <button type="submit" class="btn btn-primary">บันทึกรหัสใหม่</button>
      </div>
    </form>`);
}

async function savePassword(form) {
  const fd = new FormData(form);
  const current = String(fd.get('current') || '');
  const next = String(fd.get('new') || '');
  const confirm = String(fd.get('confirm') || '');
  if (next !== confirm) { toast('รหัสผ่านใหม่ทั้งสองช่องไม่ตรงกัน', 'error'); return; }
  try {
    await api('/api/password', { method: 'POST', body: { current, new: next } });
    closeModal();
    toast('เปลี่ยนรหัสผ่านเรียบร้อยแล้ว');
  } catch (err) {
    toast(err.message, 'error');
  }
}

/* ---------------- quick add ---------------- */
async function saveQuick(form) {
  const fd = new FormData(form);
  const title = String(fd.get('title') || '').trim();
  const agentId = String(fd.get('agent_id') || '');
  if (!title) { toast('กรุณาระบุชื่องาน', 'error'); return; }
  const agent = agentById(agentId);
  try {
    await api('/api/tasks', {
      method: 'POST',
      body: {
        title,
        agent_id: agentId || null,
        department_id: agent ? agent.department_id : null,
        priority: 'normal',
      },
    });
    form.reset();
    toast('เพิ่มงานเรียบร้อยแล้ว');
    await load();
  } catch (err) {
    toast(err.message, 'error');
  }
}


/* ---------------- UI config (จัดการหน้าแอป + API สำหรับ AI ตัวอื่น) ---------------- */
async function openUiConfigModal() {
  const cfg = (state.data && state.data.ui_config) ? state.data.ui_config : {};
  let token = '';
  try { token = (await api('/api/ui-config/token')).token || ''; } catch (e) { token = '(โหลด token ไม่สำเร็จ)'; }
  const origin = location.origin;
  const example = JSON.stringify({
    floor: { title: '🏢 ผังออฟฟิศของฉัน', subtitle: 'คำอธิบาย...', showStats: true },
    manager: { label: 'ห้องผู้จัดการ', visible: true },
    note: 'ข้อความด้านล่าง...',
    rooms: { 'สำนักเลขา': { label: 'สำนักเลขา', visible: true, color: '#d97706' } }
  }, null, 2);
  const depts = (state.data && state.data.departments) || [];
  const deptRows = depts.map((d) => `
    <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;padding:6px 0;border-bottom:1px solid rgba(124,196,255,.08)">
      <b style="min-width:150px">${esc(d.name)}${d.name_en ? ` <small style="opacity:.6">${esc(d.name_en)}</small>` : ''}</b>
      <button class="btn btn-sm btn-soft" data-action="dept-integrations" data-id="${d.id}">🔌 ตั้งค่าการเชื่อมต่อ</button>
      <a class="btn btn-sm" href="/api/departments/${d.id}/export/tasks.csv">⬇️ ส่งออกงาน (CSV/Sheets)</a>
    </div>`).join('');
  openModal(`
    ${modalHead('จัดการหน้าแอป / API สำหรับ AI', 'AI ตัวอื่นหรือระบบภายนอกสามารถแก้ไขการแสดงผลหน้าแอปได้ผ่าน API (ปลอดภัย: ใช้ config ที่ตรวจสอบแล้ว)')}
    <form id="uiConfigForm">
      <div class="modal-body">
        <div class="field">
          <label>API Endpoint (ให้ AI ตัวอื่นเรียก)</label>
          <input readonly value="${origin}/api/ui-config" onclick="this.select()">
          <div class="hint">Auth: <code>Authorization: Bearer &lt;token&gt;</code> หรือ header <code>X-Office-Token</code>. รองรับ <code>GET</code> (อ่าน), <code>PUT</code> (อัปเดต), <code>POST /api/ui-config/reset</code> (รีเซ็ต).</div>
        </div>
        <div class="field">
          <label>API Token (เก็บเป็นความลับ)</label>
          <div style="display:flex;gap:8px;align-items:center">
            <input id="uiToken" readonly value="${esc(token)}" style="flex:1;font-family:monospace;font-size:12px" onclick="this.select()">
            <button type="button" class="btn btn-sm" data-action="ui-token-regen">สร้างใหม่</button>
          </div>
        </div>
        <div class="field span-2">
          <label>UI Config (JSON) — แก้ไขแล้วกดบันทึก</label>
          <textarea id="uiConfigJson" style="min-height:220px;font-family:monospace;font-size:12px;line-height:1.45">${esc(JSON.stringify(cfg, null, 2))}</textarea>
          <div class="hint">ฟิลด์ที่รองรับ: <code>floor.title/subtitle/showStats</code>, <code>manager.label/visible</code>, <code>note</code>, <code>rooms.&lt;ชื่อแผนก&gt;.{label,subtitle,color,visible}</code>. ระบบจะตรวจสอบ/ตัดค่าที่ไม่ปลอดภัยให้อัตโนมัติ</div>
        </div>
        <details style="margin-top:6px"><summary style="cursor:pointer;color:var(--muted);font-size:12px">ตัวอย่าง config</summary>
          <pre style="margin:8px 0 0;padding:10px;border-radius:10px;background:rgba(124,196,255,.06);border:1px solid rgba(124,196,255,.14);font-size:11px;overflow:auto;white-space:pre-wrap">${esc(example)}</pre>
        </details>
      </div>
        <div class="agent-section" style="margin-bottom:0">
        <h4>🔌 การเชื่อมต่อ (Integrations) — นำไปทำต่อได้</h4>
        <div class="mini-empty">เชื่อม LINE / Google Sheets / Webhook แยกตามแผนก · ส่งออก CSV งานของแผนกได้</div>
        <div style="margin-top:8px">${deptRows || '<div class="muted">ยังไม่มีแผนก</div>'}</div>
      </div>
    <div class="modal-foot">
        <button type="button" class="btn btn-ghost" data-action="close-modal">ปิด</button>
        <button type="button" class="btn" data-action="ui-config-reset">รีเซ็ตค่าเริ่มต้น</button>
        <button type="submit" class="btn btn-primary">บันทึก config</button>
      </div>
    </form>`, 'wide');
}

async function saveUiConfig(form) {
  const ta = form.querySelector('#uiConfigJson');
  let parsed;
  try { parsed = JSON.parse(ta.value || '{}'); } catch (e) { toast('JSON ไม่ถูกต้อง: ' + e.message, 'error'); return; }
  try {
    const res = await api('/api/ui-config', { method: 'PUT', body: parsed });
    state.data.ui_config = res.config;
    toast('บันทึกการตั้งค่าหน้าแอปแล้ว — AI/หน้าเว็บใช้ค่าใหม่นี้ทันที');
    closeModal();
    render();
  } catch (err) { toast(err.message, 'error'); }
}


async function openDocPreview(id) {
  openModal(`<div class="modal-head"><div><h3>📊 กำลังโหลดข้อมูลไฟล์…</h3><p class="sub">กำลังอ่าน Excel/CSV</p></div><button class="icon-btn" data-action="close-modal">${I.x}</button></div><div class="modal-body"><div class="muted">กรุณารอสักครู่…</div></div>`, 'modal-lg');
  try {
    const res = await api(`/api/documents/${id}/preview`);
    const cols = res.columns || [];
    const rows = res.rows || [];
    const head = cols.map(c => `<th>${esc(c)}</th>`).join('');
    const body = rows.map(r => `<tr>${(r||[]).map(c => `<td>${esc(c)}</td>`).join('')}</tr>`).join('') || '<tr><td colspan="99" class="muted">ไม่มีข้อมูล</td></tr>';
    const note = `${esc(res.sheet ? 'ชีต: '+res.sheet+' · ' : '')}${res.total_rows||0} แถวข้อมูล${res.truncated ? ` (แสดง ${rows.length} แถวแรก)` : ''}`;
    openModal(`<div class="modal-head"><div><h3>📊 ${esc(res.title || res.filename || 'ตัวอย่างไฟล์')}</h3><p class="sub">${note}</p></div><div class="head-actions"><a class="btn btn-sm" href="/api/documents/${id}/download">${I.download} ดาวน์โหลด</a><button class="icon-btn" data-action="close-modal">${I.x}</button></div></div><div class="modal-body"><div class="table-wrap"><table class="data-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div></div>`, 'modal-xl');
  } catch (e) {
    openModal(`<div class="modal-head"><div><h3>📊 โหลดข้อมูลไม่ได้</h3></div><button class="icon-btn" data-action="close-modal">${I.x}</button></div><div class="modal-body"><p class="error">${esc(e.message || 'เกิดข้อผิดพลาด')}</p><p class="muted">ลองกดดาวน์โหลดไฟล์ หรือบันทึกเป็น .xlsx / .csv แล้วอัปโหลดใหม่</p></div>`);
  }
}


async function openDeptIntegrations(deptId) {
  openModal(`<div class="modal-head"><div><h3>🔌 กำลังโหลดการเชื่อมต่อ…</h3></div><button class="icon-btn" data-action="close-modal">${I.x}</button></div><div class="modal-body"><div class="muted">กรุณารอสักครู่…</div></div>`);
  try {
    const res = await api(`/api/departments/${deptId}/integrations`);
    const ig = res.integrations || {};
    const L = ig.line||{}, G = ig.google_sheets||{}, W = ig.webhook||{};
    openModal(`<div class="modal-head"><div><h3>🔌 การเชื่อมต่อ: ${esc(res.department?.name||'')}</h3><p class="sub">ตั้งค่าแยกตามแผนก (เก็บในระบบ) · ค่า secret ที่บันทึกแล้วจะแสดงเป็น ********</p></div><button class="icon-btn" data-action="close-modal">${I.x}</button></div>
    <div class="modal-body"><form id="integForm" data-dept="${deptId}">
      <div class="agent-section"><h4>LINE Messaging API (แจ้งเตือน + รับข้อความเข้า ใช้งานจริง)</h4>
        <label class="check"><input type="checkbox" name="line_enabled" ${L.enabled?'checked':''}> เปิดใช้งาน LINE</label>
        <label class="check"><input type="checkbox" name="line_notify" ${L.notify_events!==false?'checked':''}> แจ้งเตือนอัตโนมัติเมื่อมีงานใหม่/อัปเดตในแผนกนี้</label>
        <label class="field"><span>Channel access token</span><input name="line_token" value="${esc(L.channel_access_token||'')}" placeholder="วาง token (หรือเว้น ******** เพื่อคงค่าเดิม)"></label>
        <label class="field"><span>Channel secret (สำหรับรับข้อความเข้า/Webhook)</span><input name="line_secret" value="${esc(L.channel_secret||'')}" placeholder="วาง channel secret (หรือเว้น ******** เพื่อคงค่าเดิม)"></label>
        <label class="field"><span>To (userId / groupId / roomId) — สำหรับ push แจ้งเตือน</span><input name="line_to" value="${esc(L.to||'')}"></label>
        <label class="field"><span>Webhook URL (นำไปใส่ใน LINE Developers → Messaging API)</span><input readonly value="${esc(res.line_callback_url||'')}" onclick="this.select()"></label>
        <div class="hint">ส่งออก (push): ใส่ token + To แล้วทดสอบ. รับข้อความเข้า: ใส่ token + Channel secret, นำ Webhook URL ไปวางใน LINE Developers และเปิด Use webhook — จากนั้นพิมพ์หาแผนกนี้ใน LINE ได้ (ระบบจะตอบกลับ/สั่งงานผ่านผู้ช่วยของแผนก)</div>
        <button type="button" class="btn btn-sm" data-action="test-integration" data-provider="line" data-id="${deptId}">ทดสอบ LINE Push</button>
      </div>
      <div class="agent-section"><h4>Google Sheets (ซิงก์/นำไปทำต่อ)</h4>
        <label class="check"><input type="checkbox" name="gs_enabled" ${G.enabled?'checked':''}> เปิดใช้งาน Google Sheets</label>
        <label class="field"><span>Spreadsheet ID</span><input name="gs_id" value="${esc(G.spreadsheet_id||'')}" placeholder="เช่น 1AbC... จาก URL ของชีต"></label>
        <label class="field"><span>ชื่อชีต (Sheet name)</span><input name="gs_sheet" value="${esc(G.sheet_name||'Stock')}"></label>
        <label class="field"><span>Service account JSON (วางทั้งหมด) — ทางเลือก</span><textarea name="gs_sa" rows="3" placeholder='{"type":"service_account",...} (เว้น ******** เพื่อคงค่าเดิม)'>${esc(G.service_account_json||'')}</textarea></label>
        <div class="hint">วิธีเร็ว: กด “ส่งออกงาน (CSV/Sheets)” แล้วนำเข้า Google Sheets. วิธีอัตโนมัติ: สร้าง Service Account ใน Google Cloud, เปิด Google Sheets API, แชร์ชีตให้ service account แล้ววาง JSON จากนั้นกดซิงก์</div>
        <button type="button" class="btn btn-sm" data-action="sync-sheets" data-id="${deptId}">ซิงก์ไป Google Sheets</button>
      </div>
      <div class="agent-section"><h4>Webhook (เชื่อมแอปอื่น/Make/Zapier/n8n)</h4>
        <label class="check"><input type="checkbox" name="wh_enabled" ${W.enabled?'checked':''}> เปิดใช้งาน Webhook</label>
        <label class="field"><span>Webhook URL</span><input name="wh_url" value="${esc(W.url||'')}" placeholder="https://..."></label>
        <label class="field"><span>Secret header (X-Office-Secret) — ทางเลือก</span><input name="wh_secret" value="${esc(W.secret||'')}" placeholder="เว้น ******** เพื่อคงค่าเดิม"></label>
        <button type="button" class="btn btn-sm" data-action="test-integration" data-provider="webhook" data-id="${deptId}">ทดสอบ Webhook</button>
      </div>
      <div class="modal-foot"><button type="button" class="btn" data-action="close-modal">ปิด</button><button type="submit" class="btn btn-primary">บันทึกการเชื่อมต่อ</button></div>
    </form></div>`, 'wide');
  } catch (e) { toast(e.message, 'error'); closeModal(); }
}

async function saveIntegrations(form) {
  const id = Number(form.dataset.dept);
  const v = n => form.querySelector(`[name="${n}"]`)?.value ?? '';
  const c = n => !!form.querySelector(`[name="${n}"]`)?.checked;
  const payload = {
    line: {enabled:c('line_enabled'), notify_events:c('line_notify'), channel_access_token:v('line_token'), channel_secret:v('line_secret'), to:v('line_to')},
    google_sheets: {enabled:c('gs_enabled'), spreadsheet_id:v('gs_id'), sheet_name:v('gs_sheet'), service_account_json:v('gs_sa')},
    webhook: {enabled:c('wh_enabled'), url:v('wh_url'), secret:v('wh_secret')}
  };
  try { await api(`/api/departments/${id}/integrations`, {method:'PUT', body: payload}); toast('บันทึกการเชื่อมต่อแล้ว'); }
  catch(e){ toast(e.message,'error'); }
}

async function testIntegration(id, provider) {
  try { const res = await api(`/api/departments/${id}/integrations/test`, {method:'POST', body:{provider}});
    if (res.ok) toast('ทดสอบสำเร็จ ✅'); else toast('ทดสอบไม่สำเร็จ: '+JSON.stringify(res.results||{}), 'error');
  } catch(e){ toast(e.message,'error'); }
}

/* ---------------- storage (Turso + Google Drive) ---------------- */
async function openStorageModal() {
  let status = null;
  let storage = null;
  try { status = await api('/api/system/status'); } catch (e) { status = null; }
  try { const r = await api('/api/storage'); storage = r.storage; }
  catch (e) { toast(e.message, 'error'); }
  const db = (status && status.db) || { mode: 'local', label: 'ไม่ทราบสถานะ', persistent: false };
  const S = storage || {
    enabled: false, folder_id: '', service_account_json: '',
    service_account_set: false, sa_email: '', note: '',
  };
  const dbBadge = db.persistent
    ? '<span class="pill" style="background:rgba(34,197,94,.16);color:#16a34a">✅ Turso (ถาวร)</span>'
    : '<span class="pill" style="background:rgba(245,158,11,.16);color:#d97706">⚠️ SQLite (ชั่วคราว)</span>';
  openModal(`
    ${modalHead('ที่เก็บข้อมูลถาวร', 'ย้ายฐานข้อมูลไป Turso และไฟล์อัปโหลดไป Google Drive เพื่อให้ข้อมูลอยู่ถาวรแม้เซิร์ฟเวอร์รีสตาร์ท')}
    <form id="storageForm">
      <div class="modal-body">
        <div class="field span-2">
          <label>ฐานข้อมูล (Database)</label>
          <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
            ${dbBadge}
            <span class="muted" style="font-size:12px">โหมด: ${esc(db.label || db.mode)}</span>
          </div>
          <div class="hint">เปิดโหมด Turso โดยตั้ง env <code>TURSO_DATABASE_URL</code> + <code>TURSO_AUTH_TOKEN</code> บนเซิร์ฟเวอร์ (Render) แล้ว Deploy ใหม่ — ดูวิธีใน <code>DEPLOY_OPTIONS.md</code></div>
        </div>

        <div class="field span-2">
          <label class="check"><input type="checkbox" name="enabled" ${S.enabled ? 'checked' : ''}> เปิดใช้งาน Google Drive สำหรับเก็บไฟล์</label>
          <div class="hint">เมื่อเปิด ไฟล์อัปโหลดใหม่จะถูกเก็บขึ้น Drive (และเก็บสำเนาในเครื่องด้วย) ดาวน์โหลด/พรีวิว/ลบ จะดึงจาก Drive อัตโนมัติถ้าไฟล์ในเครื่องหาย</div>
        </div>

        <div class="field span-2">
          <label>Google Drive Folder ID (ทางเลือก)</label>
          <input name="folder_id" value="${esc(S.folder_id || '')}" placeholder="เช่น 1AbCdEfGhIjKlMnOpQrStUvWxYz">
          <div class="hint">สร้างโฟลเดอร์ใน Drive แล้วแชร์ให้ <code>client_email</code> ของ service account เป็น Editor · ถ้าเว้นว่างจะเก็บที่ My Drive ของ service account</div>
        </div>

        <div class="field span-2">
          <label>Service account JSON ${S.service_account_set ? `(ตั้งค่าแล้ว: ${esc(S.sa_email || '')})` : ''}</label>
          <textarea name="service_account_json" style="min-height:170px;font-family:monospace;font-size:11px;line-height:1.4" placeholder='วาง JSON ทั้งก้อน เช่น {"type":"service_account", ...}'>${S.service_account_set ? '********' : ''}</textarea>
          <div class="hint">วางเฉพาะเมื่อต้องการเปลี่ยน · ค่า <code>********</code> หมายถึงใช้ค่าเดิมที่บันทึกไว้</div>
        </div>

        <div class="field span-2">
          <label>หมายเหตุ</label>
          <input name="note" value="${esc(S.note || '')}" maxlength="200" placeholder="เช่น โฟลเดอร์เอกสารบริษัท">
        </div>

        <div class="agent-section" style="margin-bottom:0">
          <h4>เครื่องมือ</h4>
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            <button type="button" class="btn btn-sm" data-action="storage-test">🔍 ทดสอบการเชื่อมต่อ Drive</button>
            <button type="button" class="btn btn-sm" data-action="storage-migrate">⬆️ อัปโหลดไฟล์เดิมขึ้น Drive</button>
          </div>
          <div class="mini-empty" style="margin-top:8px">“อัปโหลดไฟล์เดิม” จะทยอยส่งไฟล์ที่มีในเครื่องแต่ยังไม่มีบน Drive (ครั้งละไม่เกิน 100 ไฟล์) — กดซ้ำได้</div>
        </div>
      </div>
      <div class="modal-foot">
        <button type="button" class="btn btn-ghost" data-action="close-modal">ปิด</button>
        <button type="submit" class="btn btn-primary">บันทึกที่เก็บข้อมูล</button>
      </div>
    </form>`, 'wide');
}

function storagePayload(form) {
  const v = (n) => form.querySelector(`[name="${n}"]`)?.value ?? '';
  return {
    enabled: !!form.querySelector('[name="enabled"]')?.checked,
    folder_id: v('folder_id').trim(),
    service_account_json: v('service_account_json').trim(),
    note: v('note').trim(),
  };
}

async function saveStorage(form) {
  try {
    await api('/api/storage', { method: 'PUT', body: storagePayload(form) });
    toast('บันทึกที่เก็บข้อมูลแล้ว');
    closeModal();
  } catch (e) { toast(e.message, 'error'); }
}

async function testStorage() {
  const form = document.getElementById('storageForm');
  try {
    if (form) await api('/api/storage', { method: 'PUT', body: storagePayload(form) });
    const res = await api('/api/storage/test', { method: 'POST' });
    if (res.ok) {
      const folder = res.folder ? ` · โฟลเดอร์: ${res.folder.name || res.folder.id}` : '';
      toast(`เชื่อมต่อ Google Drive สำเร็จ ✅${folder}`, 'ok');
    } else {
      toast('ทดสอบไม่สำเร็จ: ' + (res.error || 'ไม่ทราบสาเหตุ'), 'error');
    }
  } catch (e) { toast(e.message, 'error'); }
}

async function migrateUploads() {
  try {
    const res = await api('/api/storage/migrate-uploads', { method: 'POST' });
    if (res.ok) {
      toast(`อัปโหลดขึ้น Drive สำเร็จ ${res.uploaded} ไฟล์ · ล้มเหลว ${res.failed} · เหลือ ${res.remaining}`,
        res.failed ? 'error' : 'ok');
      if (res.errors && res.errors.length) console.warn('migrate uploads:', res.errors);
    } else {
      toast(res.error || 'อัปโหลดไม่สำเร็จ', 'error');
    }
  } catch (e) { toast(e.message, 'error'); }
}
