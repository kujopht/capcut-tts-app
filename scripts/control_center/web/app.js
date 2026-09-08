// Router Control Center — frontend web (V0.2).
//
// KHONG CO LOGIC DIEU PHOI O DAY. Tep nay chi: goi API, ve DOM, va gui
// thao tac cua nguoi dung len server. Moi quyet dinh (phan ra viec, chon
// agent, khoa tai nguyen, cong GATED) van nam trong `engine.py`/Router V4 —
// dung nhu yeu cau "khong nhet backend vao frontend".
//
// TOKEN: launcher mo `/?t=<token>`. Trang lay token roi XOA khoi URL ngay
// (`history.replaceState`) de no khong nam lai trong lich su, trong thanh
// dia chi, hay trong `Referer` cua bat ky request nao. Sau do token o
// `sessionStorage` — mat khi dong tab, dung nhu mot token phien nen lam.

const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

// ---------------------------------------------------------------- token ----
function layToken() {
  const u = new URL(location.href);
  const t = u.searchParams.get('t');
  if (t) {
    sessionStorage.setItem('cc_token', t);
    u.searchParams.delete('t');
    history.replaceState(null, '', u.pathname + (u.search || '') + u.hash);
  }
  return sessionStorage.getItem('cc_token') || '';
}
const TOKEN = layToken();

async function api(duong, opt = {}) {
  const r = await fetch(duong, {
    ...opt,
    headers: { 'X-CC-Token': TOKEN, ...(opt.headers || {}) },
  });
  if (!r.ok) {
    let m = `HTTP ${r.status}`;
    try { m = (await r.json()).error || m; } catch { /* body khong phai JSON */ }
    throw new Error(m);
  }
  return r.status === 204 ? null : r.json();
}

// ------------------------------------------------------------ trang thai ----
let S = { projects: [], selected: '', tasks: [], sessions: [], chat: [],
          locks: [], attachments_by_message: {} };
let dinhKemChoGui = [];     // metadata cua tep DA nhan vao kho, chua gui
let viecDangChon = '';
let logDangXem = '';
let dauTin = '';            // van tay danh sach tin, de khong ve lai vo co

const HHMAU = {
  QUEUED: 'xam', WAITING: 'vang', RUNNING: 'xanh', BLOCKED: 'do',
  REVIEW: 'tim', DONE: 'luc', FAILED: 'do', PAUSED: 'xam',
  IDLE: 'xam', BUSY: 'xanh', DRAINING: 'vang', STOPPED: 'xam', DEAD: 'do',
  STARTING: 'xam', ACTUAL: 'luc', ESTIMATED: 'vang', UNAVAILABLE: 'xam',
};
const hh = (t) => `<span class="hh ${HHMAU[t] || 'xam'}">${esc(t || '?')}</span>`;

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function coDoc(n) {
  n = Number(n || 0);
  const d = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  while (n >= 1024 && i < 3) { n /= 1024; i++; }
  return i === 0 ? `${n} B` : `${n.toFixed(1)} ${d[i]}`;
}

function thoiLuong(batDau, ketThuc) {
  if (!batDau) return '—';
  const g = Math.max(0, Math.floor(((ketThuc || Date.now() / 1000) - batDau)));
  if (g < 60) return `${g}s`;
  const p = Math.floor(g / 60);
  if (p < 60) return `${p}m ${String(g % 60).padStart(2, '0')}s`;
  return `${Math.floor(p / 60)}h ${String(p % 60).padStart(2, '0')}m`;
}

const gio = (ts) => ts
  ? new Date(ts * 1000).toLocaleTimeString('vi-VN', { hour12: false })
  : '—';

function noi(msg) { $('#tt-noi').textContent = msg; }

// ------------------------------------------------------------- hop thoai ----
function moHopThoai(ten, htmlThan) {
  $('#ht-ten').textContent = ten;
  $('#ht-than').innerHTML = htmlThan;
  $('#hop-thoai').showModal();      // <dialog> dong bang Esc san
}
$('#ht-dong').onclick = () => $('#hop-thoai').close();

function xacNhan(ten, thongDiep) {
  // Thao tac khong hoan tac duoc phai xac nhan; `confirm()` cua trinh duyet
  // la hop thoai NATIVE, khong the bi CSS che mat, va dong duoc bang Esc.
  return window.confirm(`${ten}\n\n${thongDiep}`);
}

// ------------------------------------------------------------------- ve ----
function veProjects() {
  const ul = $('#ds-project');
  ul.innerHTML = S.projects.map((p) => `
    <li data-pid="${esc(p.project_id)}"
        class="${p.project_id === S.selected ? 'dang-mo' : ''}"
        title="${esc(p.repo_path || '')}">${esc(p.name || p.project_id)}</li>`
  ).join('');
  const p = S.projects.find((x) => x.project_id === S.selected);
  $('#ten-project').textContent = p ? (p.name || p.project_id) : '—';
}

function veThanhTren() {
  const chay = S.tasks.filter((t) => t.state === 'RUNNING').length;
  const chan = S.tasks.filter((t) => t.state === 'BLOCKED').length;
  $('#chip-chay').innerHTML = `<b>${chay}</b> đang chạy`;
  $('#chip-chan').innerHTML = `<b>${chan}</b> bị chặn`;
}

function keHoachTu(m) {
  const ke = (m.meta && m.meta.plan) || {};
  const ids = (m.meta && m.meta.task_ids) || [];
  const tenKe = {};
  for (const t of (ke.tasks || [])) tenKe[t.task_id] = t.title;
  return ids.map((tid, i) => {
    const t = S.tasks.find((x) => x.task_id === tid) || {};
    return {
      task_id: tid,
      title: t.title || tenKe[tid] || tenKe[tid.split('.').pop()] || tid,
      state: t.state || '?',
      agent: t.owner_session || '',
      blocked_reason: t.blocked_reason || '',
      cuoi: i === ids.length - 1,
    };
  });
}

function veChat() {
  const van = JSON.stringify([
    S.chat.map((m) => [m.message_id, m.role]),
    S.tasks.map((t) => [t.task_id, t.state, t.owner_session]),
  ]);
  if (van === dauTin) return;     // KHONG ve lai vo co: se giet vung dang boi den
  const oCuoi = (() => {
    const e = $('#ds-tin');
    return e.scrollHeight - e.scrollTop - e.clientHeight < 40;
  })();
  dauTin = van;

  $('#ds-tin').innerHTML = S.chat.map((m) => {
    const dk = (S.attachments_by_message || {})[String(m.message_id)] || [];
    const anhHtml = dk.map((a) => a.media_type === 'image'
      ? `<a href="/api/attachments/${esc(a.attachment_id)}/blob?t=${esc(TOKEN)}"
            target="_blank" rel="noopener"><img class="tin-anh"
            src="/api/attachments/${esc(a.attachment_id)}/blob?t=${esc(TOKEN)}"
            alt="${esc(a.filename)}" title="${esc(a.filename)} · ${coDoc(a.size_bytes)}"></a>`
      : `<a class="tin-tep" download
            href="/api/attachments/${esc(a.attachment_id)}/blob?t=${esc(TOKEN)}"
            >${esc(a.filename)} <i>${coDoc(a.size_bytes)}</i></a>`).join('');

    if (m.role === 'router') {
      const hang = keHoachTu(m);
      const cay = hang.length ? `
        <div class="tom">Đã nhận mục tiêu — phân rã thành ${hang.length} việc:</div>
        ${hang.map((h) => `
          <div class="hang-viec ${h.state === 'BLOCKED' ? 'chan' : ''}">
            <span class="nhanh">${h.cuoi ? '└─' : '├─'}</span>
            <button class="ten-viec" data-mo="${esc(h.task_id)}">${esc(h.title)}</button>
            ${hh(h.state)}
            ${h.agent ? `<span class="agent">${esc(h.agent)}</span>` : ''}
            ${h.state === 'BLOCKED'
              ? `<button class="duyet" data-duyet="${esc(h.task_id)}"
                   title="${esc(h.blocked_reason)}">Duyệt…</button>` : ''}
          </div>`).join('')}` : `<div class="tho">${esc(m.text)}</div>`;
      return `<article class="tin router"><header>ROUTER</header>${cay}
        <details><summary>Chi tiết quyết định</summary>
          <pre class="ma">${esc(m.text)}</pre></details>${anhHtml}</article>`;
    }
    const nhan = m.role === 'user' ? 'BẠN' : String(m.role || 'hệ thống').toUpperCase();
    return `<article class="tin ${m.role === 'user' ? 'user' : 'khac'}">
      <header>${esc(nhan)}</header><div class="tho">${esc(m.text)}</div>
      ${anhHtml}</article>`;
  }).join('');

  if (oCuoi) $('#ds-tin').scrollTop = $('#ds-tin').scrollHeight;
}

function veTasks() {
  const loc = $('#o-tim').value.trim().toLowerCase();
  const tb = $('#bang-tasks tbody');
  tb.innerHTML = S.tasks.map((t) => {
    const wt = (t.worktree || '').split(/[\\/]/).pop();
    const hang = [
      t.title || t.task_id, t.state, t.owner_session || '—',
      thoiLuong(t.started_at, t.ended_at), t.priority,
      (t.dependencies || []).length || '—', wt || '—', gio(t.updated_at)];
    if (loc && !hang.join(' ').toLowerCase().includes(loc)) return '';
    return `<tr data-tid="${esc(t.task_id)}"
      class="${t.task_id === viecDangChon ? 'dang-mo' : ''}">
      <td title="${esc(t.objective || '')}">${esc(hang[0])}</td>
      <td>${hh(t.state)}</td><td>${esc(hang[2])}</td><td>${esc(hang[3])}</td>
      <td>${esc(hang[4])}</td>
      <td title="${esc((t.dependencies || []).join('\n'))}">${esc(hang[5])}</td>
      <td title="${esc(t.worktree || '')}">${esc(hang[6])}</td>
      <td>${esc(hang[7])}</td></tr>`;
  }).join('');
  veChiTiet();
}

function veChiTiet() {
  const t = S.tasks.find((x) => x.task_id === viecDangChon);
  const e = $('#chi-tiet-viec');
  if (!t) { e.innerHTML = '<p class="mo">Chọn một việc để xem chi tiết</p>'; return; }
  e.innerHTML = `
    <h3>${esc(t.title || t.task_id)}</h3>${hh(t.state)}
    <pre tabindex="0">${esc([
      `mã việc   : ${t.task_id}`, `trạng thái: ${t.state}`,
      `quyền     : ${t.permission || '—'}`, `ưu tiên   : ${t.priority}`,
      `phiên     : ${t.owner_session || '—'}`,
      `worktree  : ${t.worktree || '—'}`, `nhánh     : ${t.branch || '—'}`,
      `lượt thử  : ${t.attempts}`,
      `phụ thuộc : ${(t.dependencies || []).join(', ') || '—'}`, '',
      'MỤC TIÊU', t.objective || '—',
      ...(t.gate_reason ? ['', 'CỔNG', t.gate_reason] : []),
      ...(t.blocked_reason ? ['', 'ĐANG CHỜ BẠN', t.blocked_reason] : []),
    ].join('\n'))}</pre>
    <div class="hang-nut">
      <button data-viec="pause">Tạm dừng</button>
      <button data-viec="resume">Tiếp tục</button>
      <button data-viec="stop">Dừng</button>
      <button data-viec="log">Nhật ký</button>
    </div>
    ${t.state === 'BLOCKED'
      ? '<button class="duyet rong" data-viec="approve">Duyệt cổng GATED…</button>'
      : ''}`;
}

function veAgents() {
  const loc = $('#o-tim').value.trim().toLowerCase();
  $('#bang-agents tbody').innerHTML = S.sessions.map((s) => {
    const wt = (s.worktree || '').split(/[\\/]/).pop();
    const hang = [`${s.provider || '—'}${s.runtime_id ? ' · ' + s.runtime_id : ''}`,
      s.session_id || '—', s.state, s.current_task || '—',
      thoiLuong(s.created_at), gio(s.last_activity), wt || '—', 'UNAVAILABLE'];
    if (loc && !hang.join(' ').toLowerCase().includes(loc)) return '';
    return `<tr>${hang.map((c, i) => i === 2 || i === 7
      ? `<td>${hh(c)}</td>` : `<td>${esc(c)}</td>`).join('')}</tr>`;
  }).join('');
}

function veInspector() {
  const d = [];
  for (const t of S.tasks.filter((x) => ['RUNNING', 'REVIEW', 'WAITING'].includes(x.state))) {
    const s = S.sessions.find((y) => y.session_id === t.owner_session) || {};
    d.push(`● ${t.title || t.task_id}`,
      `   ${t.state}  ·  ${thoiLuong(t.started_at)}`,
      `   agent: ${s.provider || '—'}${s.runtime_id ? '/' + s.runtime_id : ''}`,
      `   phiên: ${t.owner_session || '—'}`,
      `   cây  : ${(t.worktree || '—').split(/[\\/]/).pop()}`, '');
  }
  if (S.locks.length) {
    d.push('KHOÁ ĐANG GIỮ');
    for (const k of S.locks) d.push(`   ${k.kind}  ${k.resource}`);
  }
  const moi = d.join('\n') || '(chưa có việc nào chạy)';
  const e = $('#inspector');
  if (e.textContent !== moi) {
    // Chi ghi khi THAT SU doi: ghi lai vo co se giet vung dang boi den, va
    // do la mot loi CLIPBOARD (bai hoc tu review doi khang cua V0.1.1).
    const chon = window.getSelection().toString();
    if (!chon) e.textContent = moi;
  }
}

function veHet() {
  veProjects(); veThanhTren(); veChat(); veTasks(); veAgents(); veInspector();
}

// -------------------------------------------------------------- dinh kem ----
function veDaiDinhKem() {
  const dai = $('#dai-dinh-kem');
  dai.hidden = dinhKemChoGui.length === 0;
  const tong = dinhKemChoGui.reduce((a, x) => a + Number(x.size_bytes || 0), 0);
  $('#dai-nhan').textContent = dinhKemChoGui.length
    ? `${dinhKemChoGui.length} tệp đính kèm · ${coDoc(tong)}` : '';
  $('#dai-the').innerHTML = dinhKemChoGui.map((a) => `
    <div class="the-dk" title="${esc(a.filename)}
${esc(a.media_type)} · ${coDoc(a.size_bytes)}
sha256 ${esc(a.sha256)}">
      ${a.media_type === 'image'
        ? `<img src="/api/attachments/${esc(a.attachment_id)}/blob?t=${esc(TOKEN)}"
               alt="${esc(a.filename)}" data-xem="${esc(a.attachment_id)}">`
        : `<span class="loai">${esc((a.media_type || 'tệp').toUpperCase())}</span>`}
      <div class="dk-chu"><b>${esc(a.filename)}</b>
        <i>${coDoc(a.size_bytes)} · ${esc(a.sha256.slice(0, 8))}</i></div>
      <button class="dk-xem" data-xem="${esc(a.attachment_id)}">Xem</button>
      <button class="dk-bo" data-bo="${esc(a.attachment_id)}"
              title="Bỏ tệp này ra khỏi tin nhắn">&times;</button>
    </div>`).join('');
  $('#nut-gui').textContent = dinhKemChoGui.length
    ? `Gửi (${dinhKemChoGui.length} tệp)` : 'Gửi';
}

async function taiLenMotTep(tep, tenGoiY) {
  const fd = new FormData();
  fd.append('project_id', S.selected);
  // `tenGoiY`: anh dan tu clipboard la mot Blob KHONG co ten. Dat ten o day
  // de server co duoi tep ma kiem allowlist va chu ky byte.
  fd.append('file', tep, tenGoiY || tep.name || 'dan.png');
  return api('/api/attachments', { method: 'POST', body: fd });
}

async function nhanTep(dsTep, tenGoiY) {
  for (const [i, tep] of [...dsTep].entries()) {
    try {
      const dk = await taiLenMotTep(tep, i === 0 ? tenGoiY : null);
      if (!dinhKemChoGui.some((x) => x.attachment_id === dk.attachment_id)) {
        dinhKemChoGui.push(dk);
      }
      noi(`đã đính kèm ${dk.filename} (${coDoc(dk.size_bytes)})`);
    } catch (e) {
      // Mot tep bi tu choi KHONG duoc lam mat cac tep kia, va phai noi RO
      // cai nao bi tu choi.
      noi(`không đính kèm được ${tep.name || 'tệp'} — ${e.message}`);
    }
  }
  veDaiDinhKem();
}

async function boDinhKem(aid) {
  try { await api(`/api/attachments/${aid}`, { method: 'DELETE' }); }
  catch (e) { noi(`không bỏ được — ${e.message}`); }
  dinhKemChoGui = dinhKemChoGui.filter((x) => x.attachment_id !== aid);
  veDaiDinhKem();
}

// ------------------------------------------------------- dan va keo-tha ----
const o = $('#o-soan');

// DAN: xu ly tren `paste` cua textarea.
//
// KHONG `preventDefault()` tru khi that su co tep. Do la ranh gioi giu cho
// Ctrl+V van la Ctrl+V: dan van ban thuan phai di duong mac dinh cua trinh
// duyet, y nhu truoc. Va clipboard co the mang CA anh CA van ban mot luc,
// nen van ban duoc de nguyen cho trinh duyet chen, con tep thi ta lay rieng.
o.addEventListener('paste', (e) => {
  const dt = e.clipboardData;
  if (!dt) return;
  const tep = [...(dt.files || [])];
  if (tep.length) {
    // Anh chup tu Win+Shift+S toi day duoi dang mot File khong ten hoac
    // ten chung; dat ten co duoi .png de server kiem duoc.
    const co = tep.length === 1 && (tep[0].type || '').startsWith('image/')
      && (!tep[0].name || tep[0].name === 'image.png');
    nhanTep(tep, co ? `dan-${Date.now()}.png` : null);
    if (!dt.getData('text')) e.preventDefault();
  }
});

['dragenter', 'dragover'].forEach((k) => o.addEventListener(k, (e) => {
  if ([...(e.dataTransfer?.types || [])].includes('Files')) {
    e.preventDefault();
    o.classList.add('dang-tha');
  }
}));
['dragleave', 'drop'].forEach((k) => o.addEventListener(k, () => {
  o.classList.remove('dang-tha');
}));
o.addEventListener('drop', (e) => {
  const tep = [...(e.dataTransfer?.files || [])];
  if (tep.length) { e.preventDefault(); nhanTep(tep); }
});

$('#nut-dinh-kem').onclick = () => $('#chon-tep').click();
$('#chon-tep').onchange = (e) => {
  nhanTep(e.target.files);
  e.target.value = '';            // de chon lai dung tep do van bat su kien
};
$('#nut-bo-het').onclick = async () => {
  for (const a of [...dinhKemChoGui]) await boDinhKem(a.attachment_id);
};

// --------------------------------------------------------------- gui tin ----
async function gui() {
  const text = o.value.trim();
  const ma = dinhKemChoGui.map((x) => x.attachment_id);
  if (!text && !ma.length) return;
  $('#nut-gui').disabled = true;
  $('#trang-thai-gui').textContent = 'Router đang phân rã…';
  try {
    await api('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: S.selected, text,
                             attachment_ids: ma }),
    });
    o.value = '';
    dinhKemChoGui = [];
    veDaiDinhKem();
    await lamMoi();
  } catch (e) {
    noi(`gửi hỏng — ${e.message}`);
  } finally {
    $('#nut-gui').disabled = false;
    $('#trang-thai-gui').textContent = '';
  }
}
$('#nut-gui').onclick = gui;

// Enter xuong dong; Ctrl+Enter gui. Nut Gui la duong chinh — loi tat chi la
// tuy chon, khong bao gio la kien thuc bat buoc.
o.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); gui(); }
});

// ------------------------------------------------------------ thao tac ----
document.addEventListener('click', async (e) => {
  const t = e.target.closest('[data-pid],[data-tid],[data-mo],[data-duyet],'
    + '[data-viec],[data-bo],[data-xem],[data-copy]');
  if (!t) return;

  if (t.dataset.pid) { S.selected = t.dataset.pid; dauTin = ''; await lamMoi(); return; }
  if (t.dataset.copy) {
    const e2 = document.getElementById(t.dataset.copy);
    await navigator.clipboard.writeText(e2.innerText || e2.textContent || '');
    noi('đã copy vào clipboard'); return;
  }
  if (t.dataset.bo) { await boDinhKem(t.dataset.bo); return; }
  if (t.dataset.xem) {
    const a = dinhKemChoGui.find((x) => x.attachment_id === t.dataset.xem);
    if (!a) return;
    const u = `/api/attachments/${a.attachment_id}/blob?t=${TOKEN}`;
    if (a.media_type === 'image') {
      moHopThoai(a.filename, `<img class="xem-to" src="${u}" alt="">
        <p class="ghi-chu">${esc(a.filename)} · ${coDoc(a.size_bytes)} ·
        sha256 ${esc(a.sha256)}</p>`);
    } else { window.open(u, '_blank', 'noopener'); }
    return;
  }
  if (t.dataset.mo || t.dataset.tid) {
    viecDangChon = t.dataset.mo || t.dataset.tid;
    if (t.dataset.mo) doiKhung('tasks');
    veTasks(); return;
  }
  if (t.dataset.duyet) { await duyet(t.dataset.duyet); return; }

  if (t.dataset.viec) {
    const tid = viecDangChon;
    if (!tid) return;
    const v = t.dataset.viec;
    if (v === 'log') { await moLog(tid); return; }
    if (v === 'approve') { await duyet(tid); return; }
    if (v === 'stop' && !xacNhan(`Dừng hẳn việc ${tid}?`,
        'Việc sẽ chuyển sang FAILED và không tự chạy lại. Worktree trên đĩa '
        + 'KHÔNG bị xoá — công việc chưa commit vẫn còn đó.')) return;
    try { await api(`/api/task/${tid}/${v}`, { method: 'POST' }); noi(`${v} ${tid}`); }
    catch (err) { noi(`${v} hỏng — ${err.message}`); }
    await lamMoi();
  }
});

async function duyet(tid) {
  const t = S.tasks.find((x) => x.task_id === tid) || {};
  if (!xacNhan(`Cho phép ${tid} chạy?`,
      `${t.blocked_reason || t.gate_reason || 'Việc này chạm lớp GATED.'}\n\n`
      + 'Duyệt là hành động của BẠN và được ghi vào sổ kiểm toán.')) return;
  try { await api(`/api/task/${tid}/approve`, { method: 'POST' }); }
  catch (e) { noi(`duyệt hỏng — ${e.message}`); }
  await lamMoi();
}

// ------------------------------------------------------------------ logs ----
let logTho = '';
async function moLog(tid) {
  logDangXem = tid;
  doiKhung('logs');
  $('#log-nhan').textContent = `Nhật ký · ${tid}`;
  try { logTho = (await api(`/api/task/${tid}/log`)).text || ''; }
  catch (e) { logTho = `không đọc được nhật ký: ${e.message}`; }
  veLog();
}
function veLog() {
  const loc = $('#log-loc').value.trim().toLowerCase();
  const dong = logTho.split('\n').filter((d) => !loc || d.toLowerCase().includes(loc));
  const e = $('#log-o');
  const theo = $('#log-theo').classList.contains('bat');
  const moi = dong.join('\n');
  if (e.textContent === moi) return;
  if (window.getSelection().toString()) return;   // dang boi den: khong ghi
  const cho = e.scrollTop;
  e.textContent = moi;
  e.scrollTop = theo ? e.scrollHeight : Math.min(cho, e.scrollHeight);
}
$('#log-loc').oninput = veLog;
$('#log-theo').onclick = (e) => {
  const b = e.target.classList.toggle('bat');
  e.target.textContent = `Theo dõi: ${b ? 'BẬT' : 'TẮT'}`;
  veLog();
};
$('#log-copy-all').onclick = async () => {
  await navigator.clipboard.writeText(logTho);
  noi('đã copy toàn bộ nhật ký');
};

// ----------------------------------------------------------------- usage ----
async function veUsage() {
  let bc;
  try { bc = await api(`/api/usage?project=${encodeURIComponent(S.selected)}`); }
  catch (e) { $('#usage-tom').textContent = `không đọc được usage: ${e.message}`; return; }
  const ms = bc.metrics || [];
  const dem = { ACTUAL: 0, ESTIMATED: 0, UNAVAILABLE: 0 };
  $('#bang-usage tbody').innerHTML = ms.map((m) => {
    const tin = String(m.confidence || 'UNAVAILABLE').toUpperCase();
    dem[tin] = (dem[tin] || 0) + 1;
    return `<tr><td>${esc(m.label || '—')}</td>
      <td>${m.value === null || m.value === undefined ? '—' : esc(m.value)}</td>
      <td>${esc(m.unit || '')}</td><td>${hh(tin)}</td>
      <td>${esc(m.note || '')}</td></tr>`;
  }).join('');
  $('#usage-tom').textContent = `${ms.length} hạng mục — ${dem.ACTUAL || 0} `
    + `ACTUAL, ${dem.ESTIMATED || 0} ESTIMATED, ${dem.UNAVAILABLE || 0} UNAVAILABLE.`;
}

// ------------------------------------------------------------------- tab ----
function doiKhung(ten) {
  $$('.tab').forEach((b) => b.classList.toggle('dang-mo', b.dataset.khung === ten));
  $$('.khung').forEach((k) => k.classList.toggle('dang-mo', k.id === `khung-${ten}`));
  if (ten === 'usage') veUsage();
}
$$('.tab').forEach((b) => { b.onclick = () => doiKhung(b.dataset.khung); });
$('#o-tim').oninput = () => { veTasks(); veAgents(); };

$('#nut-tro-giup').onclick = () => moHopThoai('Hướng dẫn dùng', `<pre class="ma">
Router Control Center — dùng bằng CHUỘT

Bạn không cần nhớ phím nào. Mọi việc đều có nút.

  Chat     Gõ mục tiêu vào ô dưới, bấm Gửi. Router tự phân rã thành việc,
           chọn agent, dựng worktree, chạy, báo cáo.
           Đính kèm: bấm "Đính kèm tệp…", hoặc dán Ctrl+V (ảnh chụp
           Win+Shift+S cũng được), hoặc kéo-thả tệp vào ô soạn.
  Tasks    Bảng mọi việc. Bấm một hàng để xem chi tiết bên phải, kèm nút
           Tạm dừng / Tiếp tục / Dừng / Nhật ký.
  Agents   Phiên agent thật đang chạy, provider, việc, thời lượng.
  Logs     Nhật ký đầy đủ. Bôi đen bằng chuột rồi Ctrl+C, hoặc bấm Copy.
  Usage    Số usage kèm mức tin cậy ACTUAL / ESTIMATED / UNAVAILABLE.

Việc chạm lớp GATED (deploy production, đổi quyền, chạm bí mật) KHÔNG tự
chạy. Nó dừng ở BLOCKED và chờ bạn bấm Duyệt — đúng như vậy là cố ý.

Clipboard là clipboard của TRÌNH DUYỆT: bôi đen bằng chuột, Ctrl+C copy,
Ctrl+V dán, chuột phải có Copy/Paste. Trang này không chiếm tổ hợp nào.

Lối tắt (tuỳ chọn, không bắt buộc):
  Ctrl+Enter   gửi tin trong ô soạn
  Esc          đóng hộp thoại đang mở
</pre>`);

$('#nut-cai-dat').onclick = () => moHopThoai('Cài đặt', `<pre class="ma">
V0.2 chưa có mục cài đặt nào đổi được từ giao diện — và nói thẳng như vậy
thì tốt hơn là dựng một khung trống trông như làm được gì đó.

API      http://127.0.0.1 (chỉ localhost; mọi request đòi token phiên)
Đính kèm nằm cục bộ dưới .router/attachments/ — không tệp nào được tải lên
         đâu cả.
Quyền của agent nằm ở tệp cấu hình của agy và CỐ Ý không sửa được từ đây —
         xem docs/CONTROL_CENTER.md §4b.
</pre>`);

$('#nut-project-moi').onclick = () => moHopThoai('Dự án mới', `
  <p class="ghi-chu">Nhập đường dẫn tuyệt đối tới một kho git trên máy này.</p>
  <input id="np-duong" type="text" placeholder="C:\\duong\\dan\\den\\kho" style="width:100%">
  <div class="hang-nut"><span class="day"></span>
    <button id="np-luu" class="chinh">Thêm dự án</button></div>`);
document.addEventListener('click', async (e) => {
  if (e.target.id !== 'np-luu') return;
  const duong = $('#np-duong').value.trim();
  if (!duong) return;
  const ten = duong.split(/[\\/]/).filter(Boolean).pop() || 'du-an';
  const pid = ten.toLowerCase().replace(/[^a-z0-9_-]/g, '').slice(0, 24);
  try {
    await api('/api/project', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: pid, name: ten, repo_path: duong }),
    });
    $('#hop-thoai').close();
    await lamMoi();
  } catch (err) { noi(`không thêm được dự án — ${err.message}`); }
});

// ---------------------------------------------------------- noi va lam moi --
async function lamMoi() {
  try {
    const d = await api(`/api/state?project=${encodeURIComponent(S.selected)}`);
    S = { ...S, ...d };
    S.selected = d.selected || S.selected;
    veHet();
  } catch (e) { noi(`không đọc được trạng thái — ${e.message}`); }
}

function noiWs() {
  const u = `ws://${location.host}/ws?t=${encodeURIComponent(TOKEN)}`
    + `&project=${encodeURIComponent(S.selected)}`;
  const ws = new WebSocket(u);
  ws.onopen = () => noi('đã kết nối · trạng thái sống');
  ws.onmessage = (ev) => {
    const goi = JSON.parse(ev.data);
    if (goi.kind === 'state') {
      S = { ...S, ...goi.data };
      S.selected = goi.data.selected || S.selected;
      veHet();
    }
  };
  ws.onclose = () => {
    noi('mất kết nối — thử lại sau 2s');
    setTimeout(noiWs, 2000);
  };
  ws.onerror = () => { try { ws.close(); } catch { /* da dong */ } };
}

(async function batDau() {
  if (!TOKEN) {
    document.body.innerHTML = '<main style="padding:40px"><h2>Thiếu token '
      + 'phiên</h2><p>Mở lại bằng <code>router-cc-web.cmd</code>. Trang này '
      + 'chỉ nhận token do launcher cấp — mở trực tiếp bằng URL sẽ không '
      + 'chạy, và đó là cố ý.</p></main>';
    return;
  }
  await lamMoi();
  noiWs();
  veDaiDinhKem();
})();
