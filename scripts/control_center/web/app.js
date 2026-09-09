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

    const loai = (m.meta && m.meta.loai) || '';
    // `router` la vai CU (truoc V0.3). Giu lai de nhung hoi thoai da luu
    // van doc duoc — mot ban nang cap khong duoc lam mat lich su chat.
    const uyThac = loai === 'delegation' || m.role === 'router';

    if (uyThac) {
      const hang = keHoachTu(m);
      // Loi cua LEADER dan dau; the viec la PHU. Nguoi dung doc mot cau,
      // khong doc mot bang. Id phien/worktree nam duoi "Chi tiet".
      const loiDan = m.role === 'router'
        ? '' : `<div class="tho">${esc(m.text.split('\n\n')[0])}</div>`;
      const the = hang.length ? `
        <div class="the-viec">
          ${hang.map((h) => `
          <div class="hang-viec ${h.state === 'BLOCKED' ? 'chan' : ''}">
            <button class="ten-viec" data-mo="${esc(h.task_id)}">${esc(h.title)}</button>
            ${hh(h.state)}
            ${h.agent ? `<span class="agent">${esc(h.agent)}</span>` : ''}
            ${['RUNNING', 'QUEUED', 'WAITING'].includes(h.state)
              ? `<button class="nho" data-dung="${esc(h.task_id)}">Dừng</button>` : ''}
            ${h.state === 'BLOCKED'
              ? `<button class="duyet" data-duyet="${esc(h.task_id)}"
                   title="${esc(h.blocked_reason)}">Duyệt…</button>` : ''}
          </div>`).join('')}
        </div>` : '';
      return `<article class="tin khac"><header>LEADER</header>
        ${loiDan}${the}
        <details><summary>Chi tiết</summary>
          <pre class="ma">${esc(m.text)}</pre></details>${anhHtml}</article>`;
    }

    if (loai === 'ket_qua') {
      const md = m.meta || {};
      const cho = [md.worker, md.model].filter(Boolean).join('/');
      return `<article class="tin khac ket-qua"><header>LEADER</header>
        <div class="tho">${esc(m.text)}</div>
        ${md.task_id ? `<div class="hang-viec">
            <button class="ten-viec" data-mo="${esc(md.task_id)}">Chi tiết việc</button>
            ${hh(md.state || '')}
            ${cho ? `<span class="agent">${esc(cho)}</span>` : ''}
          </div>` : ''}${anhHtml}</article>`;
    }

    const nhan = m.role === 'user' ? 'BẠN'
      : (m.role === 'assistant' ? 'LEADER'
        : String(m.role || 'hệ thống').toUpperCase());
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

// ------------------------------------------------------------- inspector ----
// Cot phai: nam ngay canh o chat, khong sau mot tab. Yeu cau V0.4 la "mot
// man hinh la biet he thong dang lam gi".
//
// `dat()` chi ghi khi noi dung THAT SU doi VA khong co vung nao dang boi
// den — ghi lai vo co giet mat vung chon, va do la mot loi CLIPBOARD, du
// no trong nhu loi hieu nang (bai hoc tu review doi khang cua V0.1.1).
function dat(sel, html) {
  const e = $(sel);
  if (e.innerHTML === html) return;
  if (window.getSelection().toString() && e.contains(
      window.getSelection().anchorNode)) return;
  e.innerHTML = html;
}

const trong = (t) => `<div class="qs-trong">${esc(t)}</div>`;

function veInspDangChay() {
  const ds = S.tasks.filter(
    (x) => ['RUNNING', 'REVIEW', 'WAITING'].includes(x.state));
  const bay = new Set(S.in_flight || []);
  let h = ds.map((t) => {
    const s = S.sessions.find((y) => y.session_id === t.owner_session) || {};
    const cho = [s.provider, s.runtime_id].filter(Boolean).join('/');
    return `<div class="qs-hang ${bay.has(t.task_id) ? 'song' : ''}">
      <button class="qs-ten" data-mo="${esc(t.task_id)}"
        title="${esc(t.objective || '')}">${esc(t.title || t.task_id)}</button>
      ${hh(t.state)}
      <span class="qs-phu">${esc(thoiLuong(t.started_at))}</span></div>
      ${cho ? `<div class="qs-phu" style="padding-left:9px">${esc(cho)}
        · ${esc((t.worktree || '—').split(/[\\/]/).pop())}</div>` : ''}`;
  }).join('');
  if (!ds.length) h = trong('chưa có việc nào chạy');
  if ((S.locks || []).length) {
    h += `<div class="nhan" style="margin-top:7px">KHOÁ ĐANG GIỮ</div>`
      + S.locks.map((k) => `<div class="qs-phu">${esc(k.kind)} ·
         ${esc(k.resource)}</div>`).join('');
  }
  dat('#insp-dangchay', h);
}

function veInspTasks() {
  // Sap theo "vua doi gan day nhat" — cot nay tra loi "vua co gi xay ra",
  // khong phai "liet ke het". Bang day du van o tab Tasks.
  const ds = [...S.tasks].sort(
    (a, b) => (b.updated_at || 0) - (a.updated_at || 0)).slice(0, 8);
  dat('#insp-tasks', ds.length ? ds.map((t) => `
    <div class="qs-hang">
      <button class="qs-ten" data-mo="${esc(t.task_id)}"
        >${esc(t.title || t.task_id)}</button>
      ${hh(t.state)}
      <span class="qs-phu">${esc(gio(t.updated_at))}</span></div>`).join('')
    : trong('dự án này chưa có việc nào'));
}

function veInspAgents() {
  const ds = S.sessions.filter((s) => s.state !== 'STOPPED');
  dat('#insp-agents', ds.length ? ds.map((s) => `
    <div class="qs-hang">
      <span class="qs-ten" title="${esc(s.session_id || '')}"
        >${esc([s.provider, s.runtime_id].filter(Boolean).join('/') || '—')}
        <span class="qs-phu">${esc(s.model_id || '')}</span></span>
      ${hh(s.state)}</div>
    ${s.current_task ? `<div class="qs-phu" style="padding-left:9px"
       >việc ${esc(s.current_task)}</div>` : ''}`).join('')
    : trong('không có phiên agent nào đang sống'));
}

// Usage: KHONG BIA SO. Khong do duoc thi ghi UNAVAILABLE va de trong gia
// tri — cung luat voi `usage.py` va voi anh chup cua Leader.
//
// `/api/usage` tra ve `{local, pools, runtimes, accounts, providers}`, KHONG
// phai `{metrics}`. Ban truoc doc `bc.metrics` — mot khoa khong ton tai —
// nen bang Usage LUON rong va dong tom tat luon la "0 hang muc". Mot loi
// im lang: khong ngoai le, khong dong log, chi mot bang trang trong nhu
// "chua co du lieu". Do la ly do o quan sat nay phai gom theo NGUON.
let usageCache = null;

function usageNhom(bc) {
  // [{nguon, note, metrics}] — `local` la so cua chinh so Control Center
  // (luon ACTUAL vi ta tu dem), `pools` la be quota theo provider/tai
  // khoan, `providers` chi co khi nguoi dung BAM lam moi (goi CLI thật).
  const ra = [];
  if (!bc) return ra;
  if ((bc.local || []).length) {
    ra.push({ nguon: 'sổ Control Center', note: 'đếm trong sổ, luôn ACTUAL',
              metrics: bc.local });
  }
  for (const p of (bc.pools || [])) {
    ra.push({ nguon: [p.provider, p.account_id].filter(Boolean).join(' · '),
              note: p.note || '', metrics: p.metrics || [] });
  }
  for (const p of (bc.providers || [])) {
    ra.push({ nguon: `${p.provider || '?'} (đo bằng CLI)`,
              note: p.note || '', metrics: p.metrics || [] });
  }
  return ra;
}

async function veInspUsage() {
  if (!S.selected) return;
  try {
    usageCache = await api(
      `/api/usage?project=${encodeURIComponent(S.selected)}`);
  } catch (e) {
    dat('#insp-usage', trong(`không đọc được usage: ${e.message}`));
    return;
  }
  veInspUsageTuCache();
  veUsageTuCache();
}
function usageHang(m) {
  return `<div class="qs-hang">
    <span class="qs-ten" title="${esc(m.note || '')}">${esc(m.label)}</span>
    <span class="qs-phu">${m.value === null || m.value === undefined
      ? '—' : esc(m.value)}${esc(m.unit || '')}</span>
    ${hh(String(m.confidence || 'UNAVAILABLE').toUpperCase())}</div>`;
}

function veInspUsageTuCache() {
  const nhom = usageNhom(usageCache);
  if (!nhom.length) {
    dat('#insp-usage', trong('chưa có hạng mục usage nào'));
    return;
  }
  // Nhom DAU (sổ Control Center) mo san — do la so cua DU AN nay. Cac be
  // quota gap vao `<details>`: chung la 2 hang gan nhu giong nhau cho MOI
  // tai khoan, va o day co sau tai khoan. De mo het thi o quan sat dai
  // hon man hinh va day "ảnh chụp dự án" xuong duoi mep — tuc la pha dung
  // yeu cau "mot man hinh la biet he thong dang lam gi".
  const [dau, ...be] = nhom;
  const soBe = be.reduce((a, g) => a + g.metrics.length, 0);
  dat('#insp-usage',
    dau.metrics.map(usageHang).join('')
    + (be.length ? `<details><summary>${be.length} bể quota ·
        ${soBe} hạng mục</summary>`
      + be.map((g) => `<div class="nhan" style="margin-top:5px"
          >${esc(g.nguon)}</div>`
        + (g.metrics.length ? g.metrics.map(usageHang).join('')
          : trong('không đo được'))).join('')
      + '</details>' : ''));
}

// ==================== V0.5: TRANG THAI SONG CUA DU AN ====================
//
// TACH HAN khoi cac o Router o duoi. Router dem viec do CHINH Control
// Center dieu phoi; o nay do nhung he thong BEN NGOAI (systemd tren may
// khac, luu tru, ung dung) chay doc lap. Gop hai thu do lai chinh la loi
// V0.5 ton tai de sua — xem `observability/model.py`.
//
// SAU trang thai, ba cai cuoi la ba cach "khong biet" KHAC NHAU, va
// khong cai nao duoc ve nhu DOWN:
//   ACTIVE / DEGRADED / DOWN  -> do duoc
//   UNKNOWN     -> co probe, lan do nay that bai
//   UNAVAILABLE -> khong co probe nao cho thu nay
//   STALE       -> co so, nhung cu hon nguong tin duoc
const MAU_SONG = {
  ACTIVE: 'luc', DEGRADED: 'vang', DOWN: 'do',
  UNKNOWN: 'xam', UNAVAILABLE: 'xam', STALE: 'vang',
};

let songCache = null;
let songDangDo = false;

function tuoiChu(giay) {
  const g = Math.max(0, Math.round(Number(giay) || 0));
  if (g < 60) return `${g}s trước`;
  if (g < 3600) return `${Math.floor(g / 60)}m trước`;
  return `${Math.floor(g / 3600)}h trước`;
}

async function veSong(buocMoi = false) {
  if (!S.selected || songDangDo) return;
  songDangDo = true;
  if (buocMoi) dat('#insp-song', trong('đang đo…'));
  try {
    songCache = await api(`/api/live?project=${encodeURIComponent(S.selected)}`
      + (buocMoi ? '&refresh=1' : ''));
  } catch (e) {
    dat('#insp-song', trong(`không đo được: ${e.message}`));
    $('#song-tuoi').textContent = '';
    return;
  } finally { songDangDo = false; }
  veSongTuCache();
}

function veSongTuCache() {
  const a = songCache;
  if (!a) { dat('#insp-song', trong('chưa đo')); return; }
  const hang = [];
  // Phan NGOAI truoc, va no la phan tra loi cau "con chay khong".
  for (const nhom of ['dich_vu', 'ung_dung', 'luu_tru', 'kho']) {
    for (const k of Object.values(a[nhom] || {})) {
      hang.push(`<div class="qs-hang">
        <span class="qs-ten" title="${esc(k.ly_do || '')}"
          >${esc(k.nhan || k.khoa)}</span>
        <span class="hh ${MAU_SONG[k.trang_thai] || 'xam'}"
          >${esc(k.trang_thai)}</span></div>`);
      for (const q of (k.quan_sat || [])) {
        const doDuoc = ['ACTIVE', 'DEGRADED', 'DOWN'].includes(q.trang_thai);
        // KHONG bao gio ve mot gia tri cho o UNKNOWN/UNAVAILABLE: mot so
        // 0 o do la mot khang dinh ve production ma khong ai do.
        const phai = doDuoc && q.gia_tri !== null && q.gia_tri !== undefined
          ? esc(q.gia_tri)
          : `<i>${esc(q.trang_thai)}</i>`;
        hang.push(`<div class="qs-hang" style="padding-left:9px">
          <span class="qs-ten qs-phu" title="${esc(q.ly_do || q.nguon || '')}"
            >${esc(q.nhan || q.khoa)}</span>
          <span class="qs-phu">${phai}</span></div>`);
      }
    }
  }
  if (!hang.length) hang.push(trong('dự án này chưa khai probe ngoài nào'));
  // Router dat CUOI va co nhan ro, de khong ai doc no thanh trang thai
  // cua he thong ngoai.
  const r = (a.router || {}).router;
  if (r) {
    const g = (khoa) => {
      const q = (r.quan_sat || []).find((x) => x.khoa === khoa);
      return q && q.gia_tri !== null ? q.gia_tri : '—';
    };
    hang.push(`<div class="nhan" style="margin-top:6px">ROUTER (nội bộ —
      không nói gì về dịch vụ ngoài)</div>`);
    hang.push(`<div class="qs-hang"><span class="qs-ten">Router tasks</span>
      <span class="qs-phu">${esc(g('running_tasks'))}</span></div>`);
    hang.push(`<div class="qs-hang"><span class="qs-ten">Agents</span>
      <span class="qs-phu">${esc(g('live_agents'))}</span></div>`);
  }
  dat('#insp-song', hang.join(''));
  const cu = Number(a.tuoi || 0) > 60;
  $('#song-tuoi').textContent = `${a.trang_thai_chung} · ${tuoiChu(a.tuoi)}`;
  $('#song-tuoi').classList.toggle('cu', cu);
}

// Anh chup du an: nhanh/HEAD/sach-ban. NHIP CHAM RIENG, khong theo
// WebSocket — no chay ~6 lenh `git`, va o bap `--noconsole` moi lenh la
// mot tien trinh con. Gan vao nhip song la ~6 tien trinh moi giay.
let anhChup = null;
let chupDangChay = false;
async function veInspSnapshot(batBuoc = false) {
  if (!S.selected) { dat('#insp-snapshot', trong('chưa chọn dự án')); return; }
  if (chupDangChay) return;
  if (!batBuoc && anhChup && anhChup.project_id === S.selected
      && Date.now() - (anhChup._layLuc || 0) < 30000) {
    veInspSnapshotTuCache(); return;
  }
  chupDangChay = true;
  try {
    anhChup = await api(
      `/api/snapshot?project=${encodeURIComponent(S.selected)}`);
    anhChup._layLuc = Date.now();
  } catch (e) {
    dat('#insp-snapshot', trong(`không chụp được: ${e.message}`));
    return;
  } finally { chupDangChay = false; }
  veInspSnapshotTuCache();
}
function veInspSnapshotTuCache() {
  const a = anhChup;
  if (!a) return;
  const d = [];
  if (!a.la_kho_git) {
    d.push('(!) đường dẫn này KHÔNG phải kho git');
  } else {
    d.push(`nhánh : ${a.branch || '(không rõ)'}`,
      `HEAD  : ${a.head_ngan || '(chưa có commit)'}`,
      `cây   : ${a.sach ? 'sạch' : `CÓ THAY ĐỔI (${a.tep_doi.length} tệp)`}`);
    if ((a.commit_gan_day || []).length) {
      d.push('', 'commit gần đây:');
      d.push(...a.commit_gan_day.slice(0, 4).map((c) => `  ${c}`));
    }
  }
  d.push('', `định tuyến : ${a.che_do || '—'}`,
    `backend    : ${bkDangChay(a)}`,
    `chụp lúc   : ${gio(a.ts)}`);
  dat('#insp-snapshot', `<pre>${esc(d.join('\n'))}</pre>`);
  $('#chip-che-do').innerHTML = `<b>${esc(a.che_do || '—')}</b>`;
}
function bkDangChay(a) {
  // "backend dang hoat dong" = provider/model cua nhung phien CON SONG,
  // suy tu SO chu khong hoi nha cung cap. Khong co phien nao thi noi
  // thang la khong co — khong doan mot cai ten cho dep man hinh.
  const t = [...new Set((a.phien || []).map(
    (s) => [s.provider, s.model_id].filter(Boolean).join('/')))].filter(Boolean);
  return t.length ? t.join(', ') : '(không phiên nào đang sống)';
}

// ------------------------------------------------------------ dang lam gi ----
// Nhan den tu SERVER (`snapshot().buoc`), khong phai tu trang thai cua tab
// nay — nen hai tab dang mo cung thay, va tab moi mo giua mot luot Leader
// dai cung thay ngay la he thong dang lam gi.
let dhDangLam = null;
function veDangLam() {
  const b = S.buoc;
  const e = $('#dang-lam');
  if (!b) {
    e.hidden = true;
    if (dhDangLam) { clearInterval(dhDangLam); dhDangLam = null; }
    return;
  }
  e.hidden = false;
  $('#dang-lam-nhan').textContent = b.nhan;
  const nhip = () => {
    $('#dang-lam-gio').textContent = thoiLuong(b.tu_luc);
  };
  nhip();
  if (!dhDangLam) dhDangLam = setInterval(nhip, 1000);
}

//: Van tay cua thu USAGE dem: so viec, tong luot thu, so phien, trang
//: thai phien. Doi mot trong nhung thu do la usage DA doi.
let dauUsage = '';

function veHet() {
  veProjects(); veThanhTren(); veChat(); veTasks(); veAgents();
  veInspDangChay(); veInspTasks(); veInspAgents(); veInspUsageTuCache();
  veSongTuCache();
  veDangLam();

  // LAY LAI USAGE KHI TRANG THAI DOI — day la duong lam moi CHINH, khong
  // phai dong ho. `cuc_bo()` dem dung nhung thu duoi day tu sổ SQLite,
  // nen van tay nay doi CHINH XAC khi con so usage doi. Cach nay cung
  // dung mot nguon su that voi the Tasks/Agents, nen khong con canh "the
  // nay song, the kia dong bang".
  const van = JSON.stringify([
    (S.tasks || []).length,
    (S.tasks || []).reduce((a, t) => a + (t.attempts || 0), 0),
    (S.sessions || []).map((s) => [s.session_id, s.state]),
  ]);
  if (van !== dauUsage) {
    dauUsage = van;
    veInspUsage();
  }
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
// Mot lan gui dang chay. Chan gui hai lan cung mot cau khi nguoi dung bam
// Enter lien tuc trong luc Leader dang nghi (co the ca phut o lan lanh).
let dangGui = false;

//: Ban nhap DA GUI nhung server CHUA nhan. Chi khac rong khi mot lan gui
//: that bai va khong tra lai duoc vao o soan (vi nguoi dung da go cau moi).
let nhapChuaGui = null;

async function gui() {
  if (dangGui) return;
  const text = o.value.trim();
  const ma = dinhKemChoGui.map((x) => x.attachment_id);
  if (!text && !ma.length) return;
  if (!S.selected) { baoGui('chưa chọn dự án nào', true); return; }

  // ============ XOA NGAY, TRONG CUNG MOT LUOT TUONG TAC ============
  //
  // TRUOC MOI `await`. Day la ca ban sua, va day la vi sao:
  //
  // `POST /api/chat` chay TRON MOT LUOT `chat()` dong bo o server —
  // Leader quyet dinh, phan ra muc tieu, giao viec cho Router V4. Do
  // duoc 6.12s khi Leader da am, va 67.87s o lan mo lanh. Nhung server
  // ghi dong chat CUA NGUOI DUNG ngay dong dau cua `_chat()`, nen
  // WebSocket day tin nhan len dong thoi gian trong ~1s.
  //
  // Ban truoc dat `o.value = ''` SAU `await api(...)`, nen nguoi dung
  // thay: tin nhan da hien trong chat, ma cau vua go VAN CON trong o
  // soan — roi vai giay (hoac ca phut) sau moi bien mat. Dung hinh dang
  // "app dang treo".
  //
  // Xoa dong bo thi mat cau nguoi dung vua go NEU gui hong; nen ban nhap
  // duoc GIU LAI o `nhapChuaGui` va tra ve o duoi.
  const nhap = { text, ma, dinh_kem: dinhKemChoGui };
  o.value = '';
  dinhKemChoGui = [];
  veDaiDinhKem();
  // Giu focus NGAY — khong doi `finally`, de nguoi dung go tiep duoc
  // trong luc Leader con dang nghi.
  o.focus();

  dangGui = true;
  $('#nut-gui').disabled = true;
  baoGui('đang gửi…', false);
  try {
    await api('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: S.selected, text,
                             attachment_ids: ma }),
    });
    baoGui('', false);
    await lamMoi();
  } catch (e) {
    tra_lai_nhap(nhap, e.message);
    noi(`gửi hỏng — ${e.message}`);
  } finally {
    dangGui = false;
    $('#nut-gui').disabled = false;
    o.focus();
  }
}

function tra_lai_nhap(nhap, ly_do) {
  // KHONG DE LEN VAN BAN MOI. Mot lan gui hong co the mat ca phut moi
  // biet, va trong khoang do nguoi dung da go cau tiep theo — ghi de len
  // no la mat du lieu lan thu hai, o dung cho vua hua se khong mat.
  if (o.value.trim() === '') {
    o.value = nhap.text;
    dinhKemChoGui = nhap.dinh_kem;
    veDaiDinhKem();
    nhapChuaGui = null;
    baoGui(`không gửi được — ${ly_do} · bản nháp đã trả lại ô soạn`, true);
    o.focus();
    return;
  }
  nhapChuaGui = nhap;
  baoGui(`không gửi được — ${ly_do} · giữ bản nháp cũ`, true, true);
}

function baoGui(msg, hong, co_lay_lai) {
  const e = $('#trang-thai-gui');
  e.textContent = msg;
  e.classList.toggle('hong', !!hong);
  if (co_lay_lai && nhapChuaGui) {
    const b = document.createElement('button');
    b.className = 'nho';
    b.id = 'nut-lay-lai';
    b.textContent = 'Lấy lại bản nháp';
    b.title = nhapChuaGui.text.slice(0, 200);
    b.onclick = () => {
      if (!nhapChuaGui) return;
      // Chen vao TRUOC van ban dang co, khong xoa gi ca.
      o.value = nhapChuaGui.text
        + (o.value ? String.fromCharCode(10) + o.value : '');
      dinhKemChoGui = nhapChuaGui.dinh_kem.concat(dinhKemChoGui);
      nhapChuaGui = null;
      veDaiDinhKem();
      baoGui('', false);
      o.focus();
    };
    e.append(' ', b);
  }
}
$('#nut-gui').onclick = gui;

// Enter GUI; Shift+Enter xuong dong.
//
// Doi chieu voi V0.3 (Enter xuong dong, Ctrl+Enter gui): o nay la mot o
// CHAT, va quy uoc chat o moi noi khac deu la Enter-gui. Nguoi dung go
// "ê bro" roi bam Enter va cho — khong co gi xay ra ca. `isComposing`
// duoc ton trong: bo go tieng Viet (Telex/VNI) dung Enter de chot chu,
// va gui giua luc do la cat mat chu dang go.
o.addEventListener('keydown', (e) => {
  if (e.key !== 'Enter') return;
  if (e.isComposing || e.keyCode === 229) return;
  if (e.shiftKey) return;                       // xuong dong: de mac dinh
  e.preventDefault();
  // `repeat`: giu Enter lam ban phim ban ra mot chuoi keydown. `gui()` da
  // co cua `dangGui`, nhung chan ngay o day thi mot lan giu phim khong
  // con sinh ra hang chuc lan goi vo ich.
  if (e.repeat) return;
  gui();
});

// ------------------------------------------------------------ thao tac ----
document.addEventListener('click', async (e) => {
  const t = e.target.closest('[data-pid],[data-tid],[data-mo],[data-duyet],'
    + '[data-viec],[data-bo],[data-xem],[data-copy],[data-dung]');
  if (!t) return;

  // Dung NGAY tu the viec trong chat — khong bat nguoi dung di sang tab
  // Tasks roi tim lai dung dong. Van hoi xac nhan: dung han la mot hanh
  // dong mat viec dang lam.
  if (t.dataset.dung) {
    const tid = t.dataset.dung;
    if (!xacNhan(`Dừng hẳn việc ${tid}?`,
        'Việc sẽ chuyển sang FAILED và không tự chạy lại. Worktree trên đĩa '
        + 'KHÔNG bị xoá — công việc chưa commit vẫn còn đó.')) return;
    try { await api(`/api/task/${tid}/stop`, { method: 'POST' }); }
    catch (err) { noi(`dừng hỏng — ${err.message}`); }
    await lamMoi(); return;
  }

  if (t.dataset.pid) {
    S.selected = t.dataset.pid;
    dauTin = '';
    anhChup = null; usageCache = null;    // cache cua DU AN CU, phai bo
    songCache = null;
    await lamMoi();
    veInspUsage(); veInspSnapshot(true); veSong();
    return;
  }
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
  try {
    usageCache = await api(
      `/api/usage?project=${encodeURIComponent(S.selected)}`);
  } catch (e) {
    $('#usage-tom').textContent = `không đọc được usage: ${e.message}`;
    return;
  }
  veUsageTuCache();
  veInspUsageTuCache();
}
function veUsageTuCache() {
  const nhom = usageNhom(usageCache);
  const dem = { ACTUAL: 0, ESTIMATED: 0, UNAVAILABLE: 0 };
  let n = 0;
  $('#bang-usage tbody').innerHTML = nhom.map((g) => g.metrics.map((m) => {
    const tin = String(m.confidence || 'UNAVAILABLE').toUpperCase();
    dem[tin] = (dem[tin] || 0) + 1;
    n++;
    return `<tr><td>${esc(g.nguon)}</td><td>${esc(m.label || '—')}</td>
      <td>${m.value === null || m.value === undefined ? '—' : esc(m.value)}</td>
      <td>${esc(m.unit || '')}</td><td>${hh(tin)}</td>
      <td>${esc(m.note || '')}</td></tr>`;
  }).join('')).join('');
  $('#usage-tom').textContent = `${n} hạng mục — ${dem.ACTUAL || 0} `
    + `ACTUAL, ${dem.ESTIMATED || 0} ESTIMATED, ${dem.UNAVAILABLE || 0} `
    + `UNAVAILABLE.`
    + (usageCache && usageCache.provider_probe_ran === false
      ? ' Số của nhà cung cấp CHỈ có khi bấm làm mới — gọi CLI là thao'
        + ' tác chậm và tốn một lượt, nên nó không chạy trong vòng vẽ.'
      : '');
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

  Chat     Gõ mục tiêu vào ô dưới, bấm Gửi (hoặc Enter). Router tự phân
           rã thành việc, chọn agent, dựng worktree, chạy, báo cáo.
           Đính kèm: bấm "Đính kèm tệp…", hoặc dán Ctrl+V (ảnh chụp
           Win+Shift+S cũng được), hoặc kéo-thả tệp vào ô soạn.
  Tasks    Bảng mọi việc. Bấm một hàng để xem chi tiết bên phải, kèm nút
           Tạm dừng / Tiếp tục / Dừng / Nhật ký.
  Agents   Phiên agent thật đang chạy, provider, việc, thời lượng.
  Logs     Nhật ký đầy đủ. Bôi đen bằng chuột rồi Ctrl+C, hoặc bấm Copy.
  Usage    Số usage kèm mức tin cậy ACTUAL / ESTIMATED / UNAVAILABLE.

CỘT PHẢI luôn hiện, không cần đổi tab: việc đang chạy, việc vừa đổi,
agent đang sống, usage, và ảnh chụp dự án (nhánh / HEAD / sạch-bẩn).
Ảnh chụp làm mới CHẬM có chủ ý — nó chạy git thật; nút ↻ để chụp ngay.

Việc chạm lớp GATED (deploy production, đổi quyền, chạm bí mật) KHÔNG tự
chạy. Nó dừng ở BLOCKED và chờ bạn bấm Duyệt — đúng như vậy là cố ý.

Clipboard là clipboard của TRÌNH DUYỆT: bôi đen bằng chuột, Ctrl+C copy,
Ctrl+V dán, chuột phải có Copy/Paste. Trang này không chiếm tổ hợp nào.

Bàn phím trong ô soạn:
  Enter         gửi
  Shift+Enter   xuống dòng
  Esc           đóng hộp thoại đang mở
Ô soạn chỉ được xoá SAU khi server đã nhận. Gửi hỏng thì câu bạn vừa gõ
vẫn còn nguyên trong ô, kèm lý do hỏng hiện ngay cạnh nút Gửi.

Ảnh nền: Cài đặt -> Ảnh nền. Ảnh được sao vào kho đính kèm cục bộ, có
thanh trượt làm tối và làm nhoè, và bền qua khởi động lại.
</pre>`);

// ------------------------------------------------------------- anh nen ----
// `wallpaper` giu mot MA DINH KEM, khong phai duong dan tep tren dia.
//
// Do la quyet dinh an toan quan trong nhat cua tinh nang nay. Nhan duong
// dan thi de VE duoc anh phai mo mot endpoint doc tep tuy y — dung lai
// dung lo ma `attachments.py` ton tai de bit. Di qua duong dinh kem thi
// duoc thua ca bon bat bien san co: kiem chu ky byte, duong luu do bam
// noi dung sinh, doc lai chi qua `attachment_id`, va kiem containment
// sau `resolve()`.
let caiDatUI = {};

function apDungNen() {
  const g = document.documentElement.style;
  const aid = caiDatUI.wallpaper || '';
  if (aid) {
    g.setProperty('--nen-anh',
      `url("/api/attachments/${encodeURIComponent(aid)}/blob`
      + `?t=${encodeURIComponent(TOKEN)}")`);
    // `dim` la do TOI muon them. `--nen-mo` la do THAY anh, nen no la
    // phan bu. Mac dinh 0.45 chu khong phai 0: chu tren mot anh chua bi
    // lam toi thuong khong doc noi, va mot mac dinh khong doc duoc thi
    // khong phai mot mac dinh.
    const toi = caiDatUI.dim === undefined ? 0.45 : Number(caiDatUI.dim);
    g.setProperty('--nen-mo', String(Math.max(0, Math.min(1, 1 - toi))));
    g.setProperty('--nen-nhoe', `${Math.max(0, Number(caiDatUI.blur) || 0)}px`);
    g.setProperty('--nen-fit', ['cover', 'contain', '100% 100%']
      .includes(caiDatUI.fit) ? caiDatUI.fit : 'cover');
  } else {
    g.setProperty('--nen-anh', 'none');
    g.setProperty('--nen-mo', '0');       // man phu DAC -> nen mot mau
    g.setProperty('--nen-nhoe', '0px');
  }
}

async function napCaiDatUI() {
  try { caiDatUI = await api('/api/ui') || {}; }
  catch { caiDatUI = {}; }                // thieu cai dat khong duoc chan app
  apDungNen();
}

async function luuCaiDatUI(d) {
  try {
    caiDatUI = await api('/api/ui', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(d),
    }) || caiDatUI;
    apDungNen();
    noi('đã lưu cài đặt giao diện');
  } catch (e) { noi(`không lưu được — ${e.message}`); }
}

function veXemTruocNen() {
  const aid = caiDatUI.wallpaper || '';
  const e = $('#cd-xem');
  if (!e) return;
  e.style.backgroundImage = aid
    ? `url("/api/attachments/${encodeURIComponent(aid)}/blob`
      + `?t=${encodeURIComponent(TOKEN)}")`
    : 'none';
  e.style.backgroundSize = caiDatUI.fit || 'cover';
  e.textContent = aid ? '' : 'chưa chọn ảnh';
  e.style.color = 'var(--mo)';
  e.style.display = 'flex';
  e.style.alignItems = 'center';
  e.style.justifyContent = 'center';
}

$('#nut-cai-dat').onclick = () => {
  const dim = caiDatUI.dim === undefined ? 0.45 : Number(caiDatUI.dim);
  const blur = Number(caiDatUI.blur) || 0;
  moHopThoai('Cài đặt', `
    <div class="nhan">ẢNH NỀN</div>
    <div id="cd-xem"></div>
    <div class="cd-hang">
      <label for="cd-tep">Ảnh trên máy</label>
      <input id="cd-tep" type="file" accept="image/*">
      <button id="cd-bo">Bỏ ảnh</button>
    </div>
    <div class="cd-hang">
      <label for="cd-dim">Làm tối</label>
      <input id="cd-dim" type="range" min="0" max="1" step="0.05"
             value="${dim}">
      <span class="cd-so" id="cd-dim-so">${Math.round(dim * 100)}%</span>
    </div>
    <div class="cd-hang">
      <label for="cd-blur">Làm nhoè</label>
      <input id="cd-blur" type="range" min="0" max="24" step="1"
             value="${blur}">
      <span class="cd-so" id="cd-blur-so">${blur}px</span>
    </div>
    <div class="cd-hang">
      <label for="cd-fit">Cách co giãn</label>
      <select id="cd-fit">
        <option value="cover">Phủ kín (cắt bớt)</option>
        <option value="contain">Vừa khung (chừa viền)</option>
        <option value="100% 100%">Kéo cho khớp (méo)</option>
      </select>
    </div>
    <p class="ghi-chu">Ảnh được sao vào kho đính kèm cục bộ
      (<code>.router/attachments/</code>) và đọc lại qua mã đính kèm — giao
      diện KHÔNG có đường đọc một tệp tuỳ ý trên đĩa, và đó là cố ý.
      Cài đặt này bền qua khởi động lại.</p>
    <hr style="border:none;border-top:1px solid var(--vien);margin:12px 0">
    <pre class="ma">API      http://127.0.0.1 (chỉ localhost; mọi request đòi token phiên)
Đính kèm nằm cục bộ dưới .router/attachments/ — không tệp nào được tải
         lên đâu cả.
Quyền của agent nằm ở tệp cấu hình của agy và CỐ Ý không sửa được từ
         đây — xem docs/CONTROL_CENTER.md §4b.
Chế độ định tuyến ECO/AUTO/STRONG/MAX hiện đổi được ở tầng backend, chưa
         có ô chọn ở đây — xem docs/HANDOFF.md.</pre>`);
  $('#cd-fit').value = caiDatUI.fit || 'cover';
  veXemTruocNen();

  $('#cd-tep').onchange = async (e) => {
    const f = e.target.files && e.target.files[0];
    e.target.value = '';
    if (!f) return;
    if (!S.selected) { noi('chọn một dự án trước đã'); return; }
    try {
      const dk = await taiLenMotTep(f, f.name);
      await luuCaiDatUI({ wallpaper: dk.attachment_id });
      veXemTruocNen();
    } catch (err) { noi(`không đặt được ảnh nền — ${err.message}`); }
  };
  $('#cd-bo').onclick = async () => {
    await luuCaiDatUI({ wallpaper: '' });
    veXemTruocNen();
  };
  // Keo thanh truot: xem NGAY tren ca giao dien, luu khi tha. Luu moi
  // buoc keo la mot request moi 50ms.
  const truot = (id, khoa, ve) => {
    const el = $(id);
    el.oninput = () => {
      caiDatUI[khoa] = Number(el.value);
      $(`${id}-so`).textContent = ve(el.value);
      apDungNen();
    };
    el.onchange = () => luuCaiDatUI({ [khoa]: Number(el.value) });
  };
  truot('#cd-dim', 'dim', (v) => `${Math.round(Number(v) * 100)}%`);
  truot('#cd-blur', 'blur', (v) => `${v}px`);
  $('#cd-fit').onchange = (e) => luuCaiDatUI({ fit: e.target.value });
};

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

$('#nut-chup-lai').onclick = () => veInspSnapshot(true);
$('#nut-song-lai').onclick = () => veSong(true);

(async function batDau() {
  if (!TOKEN) {
    document.body.innerHTML = '<main style="padding:40px"><h2>Thiếu token '
      + 'phiên</h2><p>Mở lại bằng <code>router-cc-web.cmd</code>. Trang này '
      + 'chỉ nhận token do launcher cấp — mở trực tiếp bằng URL sẽ không '
      + 'chạy, và đó là cố ý.</p></main>';
    return;
  }
  await napCaiDatUI();
  await lamMoi();
  noiWs();
  veDaiDinhKem();
  veInspUsage();
  veInspSnapshot(true);
  veSong();
  // USAGE lam moi khi TRANG THAI DOI, khong theo dong ho co dieu kien.
  //
  // Ban truoc: `setInterval(() => { if (!document.hidden) veInspUsage(); },
  // 60000)`. Hai sai lam trong mot dong:
  //
  // 1. `document.hidden` KHONG DANG TIN trong cua so WebView2 dong goi.
  //    Do duoc: 1/10 lan lay mau tren ban EXE cho `visibilityState ===
  //    "hidden"` trong khi cua so dang mo va nguoi dung dang nhin. Cua
  //    so app khong phai mot tab trinh duyet; no "an" ngay khi khong con
  //    la cua so truoc. Nen phep lam moi KHONG BAO GIO chay, va the
  //    Usage giu nguyen anh chup luc khoi dong — tuc la TOAN SO 0 — trong
  //    khi the Tasks/Agents van song vi chung di theo WebSocket. Dung cai
  //    nguoi dung bao: viec DONE, AG01 BUSY roi IDLE, ma Usage van 0.
  //
  // 2. 60s la qua cham cho mot phep do RE. `/api/usage` chi doc SQLite +
  //    fabric trong bo nho (`provider_probe_ran=false`, so nha cung cap
  //    CHI lay khi bam lam moi), nen no khong dat. Bop nhip xuong 60s la
  //    de phong mot chi phi khong co that.
  //
  // Gio: lam moi khi van tay viec/phien DOI (nguon su that giong het cai
  // Tasks/Agents dung), cong mot dong ho AN TOAN khong dieu kien, cong
  // mot lan khi cua so hien lai.
  setInterval(veInspUsage, 20000);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) { veInspUsage(); veInspSnapshot(); veSong(); }
  });
  // TRANG THAI SONG: nhip CHAM NHAT trong ca giao dien. Moi lan la
  // mot phien SSH that ra may production, nen 90s + bo dem o server
  // (`TUOI_TUOI`/`TUOI_CON_DUNG`) la du. Nut ↻ de do ngay.
  setInterval(() => { if (!document.hidden) veSong(); }, 90000);
  // ANH CHUP DU AN thi VAN cham va VAN co dieu kien — no chay ~6 lenh
  // `git`, tuc la ~6 tien trinh con moi lan. Do la chi phi that, khac
  // han usage. Nut ↻ de chup ngay.
  setInterval(() => { if (!document.hidden) veInspSnapshot(); }, 45000);
  // Con tro nam san trong o soan khi mo app: dung duoc ngay, khong phai
  // bam mot lan vao o truoc khi go.
  o.focus();
})();
