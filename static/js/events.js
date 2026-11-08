'use strict';

/* ============================================================
   Event bindings + bootstrap
   ============================================================ */

function bindEvents() {
  document.addEventListener('click', onDocumentClick);
  document.addEventListener('submit', onDocumentSubmit);
  document.addEventListener('input', onDocumentInput);
  document.addEventListener('change', onDocumentChange);
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && String(e.key).toLowerCase() === 'k') {
      e.preventDefault();
      const modalRoot = document.getElementById('modalRoot');
      if (modalRoot && modalRoot.innerHTML.trim()) closeModal();
      let input = document.getElementById('commandText');
      if (!input) {
        state.view = 'office';
        render();
        input = document.getElementById('commandText');
      }
      if (input) {
        input.focus();
        input.select();
      }
      return;
    }
    if (e.key === 'Escape') {
      closeModal();
      const notif = document.getElementById('notifPop');
      const profile = document.getElementById('profilePop');
      if (notif) notif.hidden = true;
      if (profile) profile.hidden = true;
    }
  });
  document.addEventListener('dragover', (e) => {
    const dz = e.target.closest && e.target.closest('.dropzone');
    if (dz) { e.preventDefault(); dz.classList.add('dragover'); }
  });
  document.addEventListener('dragleave', (e) => {
    const dz = e.target.closest && e.target.closest('.dropzone');
    if (dz) dz.classList.remove('dragover');
  });
  document.addEventListener('drop', (e) => {
    const dz = e.target.closest && e.target.closest('.dropzone');
    if (!dz) return;
    e.preventDefault();
    dz.classList.remove('dragover');
    const file = e.dataTransfer.files && e.dataTransfer.files[0];
    if (file) openUploadModal(file);
  });
}

async function onDocumentClick(e) {
  const el = e.target.closest && e.target.closest('[data-action]');
  if (!el) {
    closePopoversOutside(e);
    return;
  }
  const action = el.dataset.action;

  if (action === 'modal-backdrop') {
    if (e.target === el) closeModal();
    return;
  }

  switch (action) {
    case 'nav': {
      state.view = el.dataset.view;
      if (state.view !== 'dashboard') state.dashEdit = false;
      closeModal();
      closePopovers();
      document.body.classList.remove('sidebar-open');
      const scrim = document.getElementById('sidebarScrim');
      if (scrim) scrim.hidden = true;
      render();
      window.scrollTo({ top: 0, behavior: 'smooth' });
      break;
    }
    case 'toggle-sidebar': {
      const open = document.body.classList.toggle('sidebar-open');
      const scrim = document.getElementById('sidebarScrim');
      if (scrim) scrim.hidden = !open;
      break;
    }
    case 'toggle-notifications': {
      const pop = document.getElementById('notifPop');
      const profile = document.getElementById('profilePop');
      if (profile) profile.hidden = true;
      if (pop) {
        const show = pop.hidden;
        renderNotifList();
        pop.hidden = !show;
      }
      break;
    }
    case 'profile-menu': {
      const pop = document.getElementById('profilePop');
      const notif = document.getElementById('notifPop');
      if (notif) notif.hidden = true;
      if (pop) pop.hidden = !pop.hidden;
      break;
    }
    case 'mark-all-read': {
      try {
        await api('/api/notifications/read-all', { method: 'POST' });
        (state.data.notifications || []).forEach((n) => { n.is_read = 1; });
        state.data.stats.unread = 0;
        updateNotifBadge();
        renderNotifList();
        toast('อ่านการแจ้งเตือนทั้งหมดแล้ว');
      } catch (err) { toast(err.message, 'error'); }
      break;
    }
    case 'enable-browser-notif': {
      closePopovers();
      await enableBrowserNotifications();
      break;
    }
    case 'change-password': {
      closePopovers();
      openPasswordModal();
      break;
    }
    case 'logout': {
      try { await api('/api/logout', { method: 'POST' }); } catch (err) { /* ignore */ }
      location.href = '/login';
      break;
    }
    case 'close-modal':
      state.pendingFile = null;
      closeModal();
      break;
    case 'confirm-run': {
      const fn = state.confirmFn;
      state.confirmFn = null;
      closeModal();
      if (fn) await fn();
      break;
    }
    case 'reload':
      load(true).catch((err) => toast(err.message, 'error'));
      break;

    case 'add-task': {
      openTaskModal(null, {
        department_id: el.dataset.dept || '',
        agent_id: el.dataset.agent || '',
        due_date: el.dataset.date || '',
      });
      break;
    }
    case 'edit-task': {
      const t = taskById(el.dataset.id);
      if (t) openTaskModal(t);
      break;
    }
    case 'toggle-task': {
      const t = taskById(el.dataset.id);
      if (!t) return;
      const next = t.status === 'done' ? 'todo' : 'done';
      try {
        await api(`/api/tasks/${t.id}`, { method: 'PATCH', body: { status: next } });
        toast(next === 'done' ? `ปิดงาน “${t.title}” แล้ว ✅` : 'เปิดงานอีกครั้งแล้ว');
        if (document.getElementById('modalRoot').innerHTML.trim()) closeModal();
        await load();
      } catch (err) { toast(err.message, 'error'); }
      break;
    }
    case 'delete-task': {
      const t = taskById(el.dataset.id);
      if (!t) return;
      confirmDialog(`ต้องการลบงาน “${t.title}” หรือไม่? การลบไม่สามารถย้อนกลับได้`, async () => {
        try {
          await api(`/api/tasks/${t.id}`, { method: 'DELETE' });
          toast('ลบงานเรียบร้อยแล้ว');
          await load();
        } catch (err) { toast(err.message, 'error'); }
      }, { title: 'ลบงาน', confirmText: 'ลบงาน' });
      break;
    }
    case 'task-filter':
      state.taskFilter = el.dataset.filter;
      render();
      break;

    case 'cal-prev':
      state.calCursor = new Date(state.calCursor.getFullYear(), state.calCursor.getMonth() - 1, 1);
      render();
      break;
    case 'cal-next':
      state.calCursor = new Date(state.calCursor.getFullYear(), state.calCursor.getMonth() + 1, 1);
      render();
      break;
    case 'cal-today':
      state.calCursor = new Date(new Date().getFullYear(), new Date().getMonth(), 1);
      render();
      break;
    case 'open-day':
      openDayModal(el.dataset.date);
      break;

    case 'open-dept':
      openDeptModal(el.dataset.id);
      break;
    case 'dept-integrations':
      openDeptIntegrations(Number(el.dataset.id));
      break;
    case 'test-integration':
      await testIntegration(Number(el.dataset.id), el.dataset.provider);
      break;
    case 'sync-sheets': {
      el.disabled=true; try { const r=await api(`/api/departments/${Number(el.dataset.id)}/integrations/sheets/sync`, {method:'POST'}); toast(`ซิงก์ Google Sheets แล้ว ${r.rows||0} แถว ✅`); } catch(e){ toast(e.message,'error'); } finally{ el.disabled=false; } break; }
    case 'open-agent':
      openAgentModal(el.dataset.id);
      break;

    case 'run-agents': {
      el.disabled = true;
      try {
        const res = await api('/api/agents/run', { method: 'POST' });
        toast(`ทีม AI ตรวจงานแล้ว · แจ้งเตือนใหม่ ${res.created || 0} รายการ`, 'ok', '🤖');
        await load();
      } catch (err) {
        toast(err.message, 'error');
      } finally {
        el.disabled = false;
      }
      break;
    }

    case 'doc-cat':
      state.docCategory = el.dataset.cat;
      render();
      break;
    case 'upload-doc':
      openUploadModal();
      break;
    case 'preview-doc':
      openDocPreview(Number(el.dataset.id));
      break;
    case 'delete-doc': {
      const doc = (state.data.documents || []).find((d) => d.id === Number(el.dataset.id));
      if (!doc) return;
      confirmDialog(`ต้องการลบเอกสาร “${doc.title}” และไฟล์ออกจากระบบหรือไม่?`, async () => {
        try {
          await api(`/api/documents/${doc.id}`, { method: 'DELETE' });
          toast('ลบเอกสารเรียบร้อยแล้ว');
          await load();
        } catch (err) { toast(err.message, 'error'); }
      }, { title: 'ลบเอกสาร', confirmText: 'ลบเอกสาร' });
      break;
    }

    case 'toggle-dash-edit':
      state.dashEdit = !state.dashEdit;
      render();
      break;
    case 'add-widget': {
      const select = document.getElementById('widgetAddSelect');
      if (!select || !select.value) return;
      try {
        await api('/api/widgets', { method: 'POST', body: { widget_type: select.value } });
        toast('เพิ่มการ์ดแล้ว');
        await load();
      } catch (err) { toast(err.message, 'error'); }
      break;
    }
    case 'resize-widget': {
      const w = (state.data.widgets || []).find((x) => x.id === Number(el.dataset.id));
      if (!w) return;
      const sizes = ['third', 'half', 'full'];
      const next = sizes[(sizes.indexOf(w.size) + 1) % sizes.length];
      w.size = next;
      render();
      try { await api(`/api/widgets/${w.id}`, { method: 'PATCH', body: { size: next } }); }
      catch (err) { toast(err.message, 'error'); }
      break;
    }
    case 'remove-widget': {
      try {
        await api(`/api/widgets/${el.dataset.id}`, { method: 'DELETE' });
        toast('ซ่อนการ์ดแล้ว · เพิ่มกลับได้ในโหมดปรับแต่ง');
        await load();
      } catch (err) { toast(err.message, 'error'); }
      break;
    }

    case 'agent-status':
      await setAgentStatus(el.dataset.id, el.dataset.status);
      break;
    case 'chat-suggest': {
      const input = document.getElementById('chatText');
      if (input) input.value = '';
      await sendChat(el.dataset.id, el.dataset.text);
      break;
    }
    case 'chat-prefill': {
      const input = document.getElementById('chatText');
      if (input) {
        input.value = el.dataset.text || '';
        input.focus();
        try { input.setSelectionRange(input.value.length, input.value.length); } catch (err) { /* ignore */ }
      }
      break;
    }
    case 'command-suggest':
      await runCommand(el.dataset.text);
      break;
    case 'command-run': {
      const input = document.getElementById('commandText');
      if (input) input.value = el.dataset.text || '';
      await runCommand(el.dataset.text);
      break;
    }

    case 'toggle-layout-edit': {
      if (state.layoutEdit) {
        // save current ui_config (positions already updated during drag)
        try {
          const res = await api('/api/ui-config', { method: 'PUT', body: state.data.ui_config || {} });
          state.data.ui_config = res.config || state.data.ui_config;
          toast('บันทึกเลเอาต์แล้ว');
        } catch (err) { toast(err.message, 'error'); }
      }
      state.layoutEdit = !state.layoutEdit;
      render();
      break;
    }
    case 'reset-layout': {
      const cfg = state.data.ui_config || (state.data.ui_config = {});
      if (cfg.rooms) Object.keys(cfg.rooms).forEach(k => { delete cfg.rooms[k].x; delete cfg.rooms[k].y; delete cfg.rooms[k].w; });
      try {
        const res = await api('/api/ui-config', { method: 'PUT', body: cfg });
        state.data.ui_config = res.config || cfg;
        toast('รีเซ็ตตำแหน่งแล้ว');
        render();
      } catch (err) { toast(err.message, 'error'); }
      break;
    }
    case 'ui-config':
      await openUiConfigModal();
      break;
    case 'ui-token-regen': {
      try {
        const res = await api('/api/ui-config/token/regenerate', { method: 'POST' });
        const t = document.getElementById('uiToken');
        if (t) t.value = res.token || '';
        toast('สร้าง API token ใหม่แล้ว — อย่าลืมอัปเดตให้ AI/ระบบที่ใช้งาน');
      } catch (err) { toast(err.message, 'error'); }
      break;
    }
    case 'ui-config-reset': {
      confirmDialog('รีเซ็ตการตั้งค่าหน้าแอปกลับค่าเริ่มต้นหรือไม่?', async () => {
        try {
          const res = await api('/api/ui-config/reset', { method: 'POST' });
          state.data.ui_config = res.config;
          toast('รีเซ็ตการตั้งค่าหน้าแอปแล้ว');
          closeModal();
          render();
        } catch (err) { toast(err.message, 'error'); }
      }, { title: 'รีเซ็ตค่าเริ่มต้น', confirmText: 'รีเซ็ต' });
      break;
    }

    case 'notif-click': {
      const id = Number(el.dataset.id);
      const ref = el.dataset.ref;
      const refId = Number(el.dataset.refid);
      await markNotifRead(id);
      const pop = document.getElementById('notifPop');
      if (pop) pop.hidden = true;
      if (ref === 'task' && refId) {
        const t = taskById(refId);
        if (t) openTaskModal(t);
        else await load();
      } else if (ref === 'document') {
        state.view = 'docs';
        render();
      }
      break;
    }
    default:
      break;
  }
}

function closePopovers() {
  const notif = document.getElementById('notifPop');
  const profile = document.getElementById('profilePop');
  if (notif) notif.hidden = true;
  if (profile) profile.hidden = true;
}

function closePopoversOutside(e) {
  const notif = document.getElementById('notifPop');
  const profile = document.getElementById('profilePop');
  if (notif && !notif.hidden && !e.target.closest('.bell-wrap')) notif.hidden = true;
  if (profile && !profile.hidden && !e.target.closest('.profile-chip') && !e.target.closest('.profile-pop')) {
    profile.hidden = true;
  }
}

async function onDocumentSubmit(e) {
  const form = e.target;
  if (!form || !form.id) return;
  if (form.id === 'taskForm') {
    e.preventDefault();
    await saveTask(form);
  } else if (form.id === 'uploadForm') {
    e.preventDefault();
    await saveUpload(form);
  } else if (form.id === 'passwordForm') {
    e.preventDefault();
    await savePassword(form);
  } else if (form.id === 'quickForm') {
    e.preventDefault();
    await saveQuick(form);
  } else if (form.id === 'chatForm') {
    e.preventDefault();
    const input = form.querySelector('#chatText');
    const text = input ? input.value : '';
    await sendChat(Number(form.dataset.agent), text);
    if (input) input.focus();
  } else if (form.id === 'commandForm') {
    e.preventDefault();
    const input = form.querySelector('#commandText');
    await runCommand(input ? input.value : '');
  } else if (form.id === 'uiConfigForm') {
    e.preventDefault();
    await saveUiConfig(form);
  } else if (form.id === 'integForm') {
    e.preventDefault();
    await saveIntegrations(form);
  }
}

function onDocumentInput(e) {
  if (e.target.id === 'taskSearch') {
    state.taskSearch = e.target.value;
    refreshTaskList();
  } else if (e.target.id === 'docSearch') {
    state.docSearch = e.target.value;
    refreshDocGrid();
  }
}

function onDocumentChange(e) {
  if (e.target.id === 'f_dept') {
    syncAgentSelect(e.target, document.getElementById('f_agent'));
  } else if (e.target.id === 'u_dept') {
    syncAgentSelect(e.target, document.getElementById('u_agent'));
  } else if (e.target.id === 'docDeptFilter') {
    state.docDept = e.target.value;
    refreshDocGrid();
  }
}

/* ---------------- polling ---------------- */
async function poll() {
  if (!state.data) return;
  try {
    const data = await api('/api/notifications');
    state.data.notifications = data.notifications;
    state.data.stats = data.stats;
    updateChrome();
    renderNotifList();
    const maxId = data.notifications.reduce((m, n) => Math.max(m, n.id), 0);
    if (maxId > state.lastNotifId) {
      const newest = data.notifications.find((n) => n.id === maxId);
      if (newest) {
        if (state.lastNotifId) showBrowserNotif(newest);
        toast(newest.title, 'ok', '🔔');
      }
      state.lastNotifId = maxId;
      localStorage.setItem('vo_last_notif', String(maxId));
    }
  } catch (err) { /* silent */ }
}


// layout drag (free arrange)
(function(){
  let drag=null;
  document.addEventListener('pointerdown', (e)=>{
    if(!state.layoutEdit) return;
    const card = e.target.closest && e.target.closest('[data-drag="dept"]');
    if(!card) return;
    const scene = card.closest('.proto-scene');
    if(!scene) return;
    e.preventDefault();
    const sr = scene.getBoundingClientRect(), cr = card.getBoundingClientRect();
    drag = {card, scene, key: card.dataset.deptKey, ox: e.clientX-cr.left, oy: e.clientY-cr.top, moved:false};
    card.setPointerCapture && card.setPointerCapture(e.pointerId);
    card.classList.add('dragging');
  });
  document.addEventListener('pointermove', (e)=>{
    if(!drag) return;
    const sr = drag.scene.getBoundingClientRect();
    let x = ((e.clientX - sr.left - drag.ox) / sr.width) * 100;
    let y = ((e.clientY - sr.top - drag.oy) / sr.height) * 100;
    x = Math.max(0, Math.min(88, x)); y = Math.max(0, Math.min(88, y));
    drag.card.style.left = x+'%'; drag.card.style.top = y+'%'; drag.card.style.right='auto'; drag.card.style.transform='none';
    drag.x=x; drag.y=y; drag.moved=true;
  });
  function endDrag(e){
    if(!drag) return;
    drag.card.classList.remove('dragging');
    if(drag.moved && drag.key && state.data && state.data.ui_config){
      const cfg = state.data.ui_config; cfg.rooms = cfg.rooms || {}; cfg.rooms[drag.key] = cfg.rooms[drag.key] || {};
      cfg.rooms[drag.key].x = Math.round(drag.x*100)/100; cfg.rooms[drag.key].y = Math.round(drag.y*100)/100;
    }
    drag=null;
  }
  document.addEventListener('pointerup', endDrag);
  document.addEventListener('pointercancel', endDrag);
})();

/* ---------------- init ---------------- */
async function init() {
  bindEvents();
  registerSW();
  try {
    await load(true);
  } catch (err) {
    const view = document.getElementById('view');
    if (view) {
      view.innerHTML = `<div class="empty-state" style="margin-top:40px">
        <span class="emoji">🔌</span>
        <strong>โหลดข้อมูลไม่สำเร็จ</strong>
        <p>${esc(err.message)}</p>
        <button class="btn btn-primary" style="margin-top:14px" data-action="reload">ลองอีกครั้ง</button>
      </div>`;
    }
  }
  setInterval(poll, 45000);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
