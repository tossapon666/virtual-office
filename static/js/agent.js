'use strict';

/* ============================================================
   Agent profile + chat
   ============================================================ */

function chatMessagesHTML(aid) {
  const list = state.chat[aid] || [];
  return list.map((m) => `<div class="msg ${m.role === 'user' ? 'user' : 'agent'}">${esc(m.content)}</div>`
    + ((m.choices && m.choices.length)
      ? `<div class="msg-choices">${m.choices.map((c) => `<button data-action="chat-suggest" data-id="${aid}" data-text="${esc(c)}">${esc(c)}</button>`).join('')}</div>`
      : '')).join('')
    + (state.chatBusy[aid] ? '<div class="msg agent typing">กำลังพิมพ์…</div>' : '');
}

function chatChoices(res) {
  const act = (res.actions || []).find((a) => (a.candidates || []).length);
  const cands = res.candidates || (act ? act.candidates : []) || [];
  if (!cands.length) return [];
  let verb = res.verb || '';
  if (!verb && act) verb = act.tool === 'reschedule_task' ? 'เลื่อนงาน' : 'ปิดงาน';
  return cands.map((c) => `${verb ? verb + ' ' : ''}${c.title}`);
}

function isMutating(res) {
  return (res.actions || []).some((a) => a.ok
    && ['create_task', 'complete_task', 'reschedule_task'].includes(a.tool));
}

function renderChat(aid) {
  const box = document.getElementById('chatMessages');
  if (!box) return;
  box.innerHTML = chatMessagesHTML(aid);
  box.scrollTop = box.scrollHeight;
}

function openAgentModal(id) {
  const a = agentById(id);
  if (!a) return;
  const tasks = state.data.tasks.filter((t) => t.agent_id === a.id);
  const open = tasks.filter((t) => ['todo', 'doing'].includes(t.status));
  const overdue = open.filter((t) => t.due_date && t.due_date < todayYMD());

  if (!state.chat[a.id]) {
    state.chat[a.id] = [{
      role: 'assistant',
      content: `สวัสดีครับ/ค่ะ ฉันคือ ${a.name} ${a.role} ประจำ${a.dept_name || 'ออฟฟิศ'}\n`
        + `ตอนนี้มีงานค้าง ${open.length} งาน${overdue.length ? ` (เกินกำหนด ${overdue.length} งาน)` : ''} `
        + `และดูแลเอกสาร ${a.docs} รายการ\nต้องการให้ช่วยเรื่องอะไรดีคะ`,
    }];
  }

  openModal(`
    ${modalHead('โปรไฟล์ผู้ช่วย AI', 'ทุกคนทำงานให้คุณคนเดียว — สั่งงานหรือคุยได้ทันที')}
    <div class="modal-body">
      <div class="agent-hero" style="--c:${esc(a.color)}">
        <div class="agent-big">${a.emoji}</div>
        <div>
          <h3>${esc(a.name)}</h3>
          <div class="role">${esc(a.role)}</div>
          <div class="dept-line">${a.dept_icon || '🏢'} ${esc(a.dept_name || 'ไม่ระบุแผนก')}</div>
          <div class="badge-row">
            <span class="meta-chip"><span class="status-dot ${esc(a.status)}" style="position:static;display:inline-block;vertical-align:-1px;margin-right:4px"></span>${AGENT_STATUS[a.status] || a.status}</span>
            <span class="meta-chip">🗂️ งานค้าง ${open.length}</span>
            <span class="meta-chip">📄 เอกสาร ${a.docs}</span>
          </div>
        </div>
      </div>

      <div class="agent-layout">
        <div>
          <div class="agent-stat-row">
            <div class="agent-stat"><b>${open.length}</b><span>งานค้าง</span></div>
            <div class="agent-stat"><b style="color:var(--red)">${overdue.length}</b><span>เกินกำหนด</span></div>
            <div class="agent-stat"><b style="color:#047857">${a.done_tasks}</b><span>เสร็จแล้ว</span></div>
          </div>

          <div class="agent-section" style="margin-top:16px">
            <h4>หน้าที่ความรับผิดชอบ</h4>
            <div class="duties-text">${esc(a.duties).replace(/ • /g, '<br>• ')}</div>
          </div>

          <div class="agent-section">
            <h4>สถานะการทำงาน</h4>
            <div class="status-select">
              ${Object.entries(AGENT_STATUS).map(([k, v]) => `<button class="status-pill ${a.status === k ? 'active' : ''}"
                data-action="agent-status" data-id="${a.id}" data-status="${k}">${v}</button>`).join('')}
            </div>
          </div>

          <div class="agent-section" style="margin-bottom:10px">
            <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:7px">
              <h4 style="margin:0">งานในความดูแล (${open.length})</h4>
              <button class="btn btn-sm" data-action="add-task" data-agent="${a.id}" data-dept="${a.department_id}">${I.plus} มอบหมายงาน</button>
            </div>
            ${open.length ? `<div class="mini-list">${open.slice(0, 7).map((t) => `
              <div class="mini-task" data-action="edit-task" data-id="${t.id}" style="cursor:pointer">
                <span class="dot" style="background:${esc(t.dept_color || a.color)}"></span>
                <span class="t">${esc(t.title)}</span>
                <span class="d" style="${t.due_date && t.due_date < todayYMD() ? 'color:var(--red)' : ''}">${dueInfo(t).text}</span>
              </div>`).join('')}</div>`
              : '<div class="mini-empty">ยังไม่มีงานค้าง พร้อมรับงานใหม่</div>'}
          </div>
        </div>

        <div class="chat-panel">
          <div class="chat-head">
            💬 คุยกับ ${esc(a.name)}
            <span class="ai-tag ${state.data.ai.enabled ? '' : 'off'}">${state.data.ai.enabled ? 'AI จริง' : 'โหมดอัตโนมัติ'}</span>
          </div>
          <div class="chat-messages" id="chatMessages">${chatMessagesHTML(a.id)}</div>
          <div class="chat-suggest">
            <button data-action="chat-suggest" data-id="${a.id}" data-text="สรุปงานวันนี้ให้หน่อย">สรุปงานวันนี้</button>
            <button data-action="chat-suggest" data-id="${a.id}" data-text="งานไหนด่วนที่สุดตอนนี้">งานด่วน</button>
            <button data-action="chat-prefill" data-id="${a.id}" data-text="เพิ่มงาน ">➕ เพิ่มงาน</button>
            <button data-action="chat-prefill" data-id="${a.id}" data-text="ปิดงาน ">✅ ปิดงาน</button>
            <button data-action="chat-prefill" data-id="${a.id}" data-text="เลื่อนงาน ">📅 เลื่อนงาน</button>
          </div>
          <form class="chat-input" id="chatForm" data-agent="${a.id}">
            <input id="chatText" maxlength="1000" autocomplete="off" placeholder="พิมพ์ข้อความถึง ${esc(a.name)}…">
            <button type="submit" aria-label="ส่งข้อความ">${I.send}</button>
          </form>
        </div>
      </div>
    </div>
    <div class="modal-foot">
      <button class="btn" data-action="close-modal">ปิด</button>
      <button class="btn btn-primary" data-action="add-task" data-agent="${a.id}" data-dept="${a.department_id}">${I.plus} มอบหมายงานใหม่</button>
    </div>`, 'xwide');

  setTimeout(() => {
    const box = document.getElementById('chatMessages');
    if (box) box.scrollTop = box.scrollHeight;
  }, 30);
}

async function sendChat(aid, text) {
  const msg = String(text || '').trim();
  if (!msg || state.chatBusy[aid]) return;
  const a = agentById(aid);
  if (!state.chat[aid]) state.chat[aid] = [];
  const history = state.chat[aid].slice(-8);
  state.chat[aid].push({ role: 'user', content: msg });
  state.chatBusy[aid] = true;
  renderChat(aid);
  const input = document.getElementById('chatText');
  if (input) input.value = '';
  try {
    const res = await api(`/api/agents/${aid}/chat`, {
      method: 'POST',
      body: { message: msg, history },
    });
    state.chat[aid].push({
      role: 'assistant',
      content: res.reply,
      choices: chatChoices(res),
    });
    if (isMutating(res)) {
      toast(String(res.reply || 'ดำเนินการเรียบร้อย').split('\n')[0], 'ok', '✨');
      await load();
      renderChat(aid);
    }
  } catch (err) {
    state.chat[aid].push({
      role: 'assistant',
      content: `ขออภัยครับ/ค่ะ เกิดข้อผิดพลาด: ${err.message}`,
    });
  } finally {
    state.chatBusy[aid] = false;
    renderChat(aid);
  }
}

async function setAgentStatus(id, status) {
  const a = agentById(id);
  if (!a || a.status === status) return;
  try {
    await api(`/api/agents/${id}`, { method: 'PATCH', body: { status } });
    toast(`${a.name} เปลี่ยนสถานะเป็น “${AGENT_STATUS[status]}”`);
    await load();
    openAgentModal(id);
  } catch (err) {
    toast(err.message, 'error');
  }
}

/* ---------------- command bar (หน้าออฟฟิศ) ---------------- */
function renderCommandResult(res) {
  const who = res.agent && res.agent.name ? `<span class="cr-agent">🤖 ${esc(res.agent.name)}</span>` : '';
  const body = esc(res.reply || res.error || 'ดำเนินการเรียบร้อย').replace(/\n/g, '<br>');
  const cls = res.ok === false && res.error ? 'command-error' : 'command-ok';
  const cands = res.candidates || ((res.actions || []).find((a) => (a.candidates || []).length) || {}).candidates;
  let choices = '';
  if (cands && cands.length) {
    const verb = res.verb || (cands[0] && cands[0].verb) || '';
    choices = `<div class="command-choices">${cands.map((c) => {
      const text = `${verb ? verb + ' ' : ''}${c.title}`;
      return `<button type="button" data-action="command-run" data-text="${esc(text)}">${esc(c.title)}</button>`;
    }).join('')}</div>`;
  }
  return `${who}<div class="${cls}">${body}</div>${choices}`;
}

async function runCommand(text) {
  const msg = String(text || '').trim();
  if (!msg) return;
  const input = document.getElementById('commandText');
  const box = document.getElementById('commandResult');
  const btn = document.getElementById('commandSend');
  if (btn) btn.disabled = true;
  if (box) {
    box.hidden = false;
    box.innerHTML = '<span class="command-pending">กำลังดำเนินการ…</span>';
  }
  try {
    const res = await api('/api/commands', { method: 'POST', body: { message: msg } });
    const mutated = isMutating(res);
    if (mutated) {
      toast(String(res.reply || 'ดำเนินการเรียบร้อย').split('\n')[0], 'ok', '✨');
      await load();
    }
    const liveBox = document.getElementById('commandResult');
    if (liveBox) {
      liveBox.hidden = false;
      liveBox.innerHTML = renderCommandResult(res);
    }
    const fresh = document.getElementById('commandText');
    if (fresh) {
      fresh.value = '';
      if (mutated) fresh.focus();
    }
  } catch (err) {
    if (box) {
      box.hidden = false;
      box.innerHTML = `<div class="command-error">${esc(err.message)}</div>`;
    }
    toast(err.message, 'error');
  } finally {
    const b = document.getElementById('commandSend');
    if (b) b.disabled = false;
  }
}
