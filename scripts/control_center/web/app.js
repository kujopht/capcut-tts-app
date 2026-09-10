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

// V0.6.1 — TOA: viec CHA (vat chua) hien tren, N viec CON thut vao duoi no,
// kem dem chay/cho/xong/hong. Nghiem thu tay: "goi 8 agent" phai THAY 8 dong,
// khong phai mot viec to. Khong doi cot bang.
const toaCua = (t) => ((t.contract || {})._toa || {});
function toaDem(con) {
  const d = { chay: 0, cho: 0, xong: 0, hong: 0, chan: 0 };
  for (const c of con) {
    if (['RUNNING', 'REVIEW'].includes(c.state)) d.chay += 1;
    else if (['QUEUED', 'WAITING', 'PAUSED'].includes(c.state)) d.cho += 1;
    else if (c.state === 'DONE') d.xong += 1;
    else if (c.state === 'FAILED') d.hong += 1;
    else if (c.state === 'BLOCKED') d.chan += 1;
  }
  return d;
}
function veTasks() {
  const loc = $('#o-tim').value.trim().toLowerCase();
  const tb = $('#bang-tasks tbody');
  const theoCha = {};
  for (const t of S.tasks) if (t.parent_id) (theoCha[t.parent_id] ||= []).push(t);
  const coCha = new Set(S.tasks.map((t) => t.task_id));
  const laCon = (t) => t.parent_id && coCha.has(t.parent_id);
  const hangCua = (t, con) => {
    const wt = (t.worktree || '').split(/[\\/]/).pop();
    const cs = theoCha[t.task_id] || [];
    let ten = t.title || t.task_id;
    let phu = '';
    if (cs.length) {
      const d = toaDem(cs);
      phu = ` <span class="qs-phu">· ${cs.length} con: ${d.chay} chạy · ${d.cho} chờ · ${d.xong} xong`
        + `${d.hong ? ` · ${d.hong} hỏng` : ''}${d.chan ? ` · ${d.chan} chặn` : ''}</span>`;
    }
    if (con) {
      // Con cua mot lan toa: runtime dang chay + tai nguyen/che do (READ docs,
      // READ git:history…) — de mot con dung hinh vi khoa doc ra ngay tren bang.
      const s = S.sessions.find((y) => y.session_id === t.owner_session) || {};
      const tn = (t.resources || []).map((r) => {
        const p = String(r).split(':');
        if (p.length >= 3 && /^(READ|WRITE)$/i.test(p[0])) {
          return `${p[0].toUpperCase()} ${p[1] === 'FILESYSTEM' ? '' : p[1].toLowerCase() + ':'}${p.slice(2).join(':')}`;
        }
        return `WRITE ${p.slice(1).join(':')}`;
      });
      ten = `↳ ${ten}`;
      phu = ` <span class="qs-phu">${s.runtime_id ? `· ${esc(s.runtime_id)} ` : ''}${tn.length ? `· ${esc(tn.join(', '))}` : ''}</span>`;
    }
    const hang = [
      t.title || t.task_id, t.state, t.owner_session || '—',
      thoiLuong(t.started_at, t.ended_at), t.priority,
      (t.dependencies || []).length || '—', wt || '—', gio(t.updated_at)];
    if (loc && !hang.join(' ').toLowerCase().includes(loc)) return '';
    return `<tr data-tid="${esc(t.task_id)}" data-cha="${esc(t.parent_id || '')}"
      class="${t.task_id === viecDangChon ? 'dang-mo' : ''}${con ? ' viec-con' : ''}${cs.length ? ' viec-cha' : ''}">
      <td title="${esc(t.objective || '')}" style="${con ? 'padding-left:18px' : ''}">${esc(ten)}${phu}</td>
      <td>${hh(t.state)}</td><td>${esc(hang[2])}</td><td>${esc(hang[3])}</td>
      <td>${esc(hang[4])}</td>
      <td title="${esc((t.dependencies || []).join('\n'))}">${esc(hang[5])}</td>
      <td title="${esc(t.worktree || '')}">${esc(hang[6])}</td>
      <td>${esc(hang[7])}</td></tr>`;
  };
  const rows = [];
  for (const t of S.tasks) {
    if (laCon(t)) continue;                     // ve duoi cha cua no
    rows.push(hangCua(t, false));
    const cs = (theoCha[t.task_id] || []).slice().sort((a, b) =>
      ((toaCua(a).chi_so || 0) - (toaCua(b).chi_so || 0)) || (a.created_at - b.created_at));
    for (const c of cs) rows.push(hangCua(c, true));
  }
  tb.innerHTML = rows.join('');
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
      ...veToaChiTiet(t),
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

// Chi tiet mot lan TOA: cha -> tung con (trang thai, runtime/model, ung vien);
// con -> chi so i/N + cha. Doc tu `contract._toa` va `result.toa`.
function veToaChiTiet(t) {
  const toa = toaCua(t);
  if (!toa || (!toa.cha && !toa.cha_id)) return [];
  if (!toa.cha) {
    return ['', `TOẢ: việc con ${toa.chi_so}/${toa.so} của ${toa.cha_id}`,
      toa.phan_vung ? `phân vùng: ${toa.phan_vung}` : ''];
  }
  const con = S.tasks.filter((x) => x.parent_id === t.task_id)
    .sort((a, b) => (toaCua(a).chi_so || 0) - (toaCua(b).chi_so || 0));
  const d = toaDem(con);
  const sc = toa.suc_chua || {};
  const ra = ['', `TOẢ: ${toa.so} việc con — ${d.chay} chạy · ${d.cho} chờ · ${d.xong} xong`
    + `${d.hong ? ` · ${d.hong} hỏng` : ''}${d.chan ? ` · ${d.chan} chặn` : ''}`,
  `sức chứa lúc tách: ${sc.chay_ngay ?? '?'}/${sc.yeu_cau ?? '?'} chạy ngay, ${sc.cho ?? '?'} chờ`
    + ` (khe rảnh ${sc.khe_ranh ?? '?'}, tài khoản rảnh ${sc.tai_khoan_ranh ?? '?'},`
    + ` trần ${sc.tran_song_song ?? '?'}${(sc.leader_chiem || []).length ? `, Leader chiếm ${sc.leader_chiem.join(',')}` : ''})`];
  for (const c of con) {
    const s = S.sessions.find((y) => y.session_id === c.owner_session) || {};
    ra.push(`  [${toaCua(c).chi_so}] ${c.state.padEnd(7)} ${s.runtime_id || '—'}${s.model_id ? '/' + s.model_id : ''}  ${c.task_id}`);
  }
  const th = (t.result || {}).toa;
  if (th) {
    ra.push('', `TỔNG HỢP: ${th.xong}/${th.so_con} xong · ${(th.ung_vien || []).length} kết quả · khử ${th.trung_da_bo} trùng`
      + (th.song_song_toi_da ? ` · song song thực đo tối đa ${th.song_song_toi_da}/${th.so_con}` : ''));
    for (const m of (th.ung_vien || [])) {
      const ng = m.nguon || {};
      ra.push(`  • ${m.ung_vien}  ← [${ng.chi_so}] ${ng.runtime || '?'}/${ng.model || '?'} ${ng.task_id || ''}`);
    }
  }
  return ra;
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
    // Day SONG phai theo du an MOI — xem `noiWs`.
    if (wsDuAn !== S.selected) noiWs();
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

// ------------------------------------------------------------ ky uc (V0.6) ----
// KHONG nam trong `veHet()`: mot lan thong ke la vai `count(*)` tren mot so
// co the rat lon, va tim kiem la mot truy van FTS. Chi lam moi khi MO tab,
// khi doi bo loc, hoac khi nguoi dung bam.
let kyUcLoc = 'timeline';
let kyUcDangTai = false;
const MAU_KYUC = {
  episodic: 'xam', semantic: 'xanh', decision: 'tim', procedural: 'luc',
  incident: 'do', architecture: 'vang',
};

function coDocKyUc(b) { return coDoc(b); }

async function veKyUcThongKe() {
  if (!S.selected) { dat('#kyuc-thongke', trong('chưa chọn dự án')); return; }
  let tk;
  try {
    tk = await api(`/api/memory/stats?project=${encodeURIComponent(S.selected)}`);
  } catch (e) { dat('#kyuc-thongke', trong(`không đọc được: ${e.message}`)); return; }
  if (!tk.san_sang) {
    dat('#kyuc-thongke', `<div class="kyuc-o do">Ký ức KHÔNG SẴN — ${esc(tk.loi_cuoi || tk.ly_do || '')}
      <br><i>Router vẫn chạy bình thường; chỉ phần nhớ lâu bị tắt.</i></div>`);
    return;
  }
  const d = tk.dem || {}, b = tk.byte || {};
  const o = (nhan, gt, phu = '') => `<div class="kyuc-o"><div class="kyuc-so">${esc(gt)}</div>
    <div class="kyuc-nhan">${esc(nhan)}${phu ? `<span class="qs-phu"> ${esc(phu)}</span>` : ''}</div></div>`;
  dat('#kyuc-thongke', [
    o('Sự kiện (lịch sử thô)', d.su_kien ?? '—',
      `${coDocKyUc(b.lich_su_tho || 0)}${d.su_kien_backfill ? ` · ${d.su_kien_backfill} nhập lịch sử` : ''}`),
    o('Ký ức có cấu trúc', d.ky_uc ?? '—',
      `${coDocKyUc(b.co_cau_truc || 0)} · ${d.ky_uc_user_explicit ?? 0} người dùng tuyên bố`),
    o('Quyết định', d.quyet_dinh ?? '—',
      `${d.ky_uc_decision_hieu_luc ?? 0} hiệu lực · ${d.ky_uc_thay_the ?? 0} đã thay thế`),
    o('Sự cố', d.ky_uc_incident ?? '—'),
    o('Ràng buộc', d.ky_uc_constraint ?? '—', `${d.ky_uc_constraint_hieu_luc ?? 0} hiệu lực`),
    o('Yêu cầu', d.ky_uc_requirement ?? '—', `${d.ky_uc_requirement_hieu_luc ?? 0} hiệu lực`),
    o('Quy trình', d.ky_uc_procedural ?? '—'),
    o('Điểm dừng', d.diem_dung ?? '—'),
    o('Mắt xích bằng chứng', d.bang_chung ?? '—', `${tk.so_blob ?? 0} blob · ${coDocKyUc(b.bang_chung || 0)}`),
    o('Chỉ mục', coDocKyUc(b.chi_muc || 0), tk.che_do_tim || ''),
    o('Tổng trên đĩa', coDocKyUc(b.tong || 0), `db ${coDocKyUc(b.tep_db || 0)}`),
  ].join('') + `<div class="kyuc-o kyuc-rong"><div class="qs-phu">sổ: ${esc(tk.ns || '')}
    · lược đồ v${esc((tk.toan_ven || {}).phien_ban_luoc_do ?? '?')}
    · quick_check ${esc((tk.toan_ven || {}).quick_check || '?')}
    · trùng nội dung đã khử: ${esc(d.su_kien_trung_dau ?? 0)}</div></div>`);
}

function theKyUc(k, phu = '') {
  const loai = k.loai || 'episodic';
  return `<div class="kyuc-hang" data-ma="${esc(k.ma)}">
    <span class="hh ${MAU_KYUC[loai] || 'xam'}">${esc(loai)}</span>
    <span class="kyuc-td" title="${esc(k.ma)}">${esc(k.tieu_de || k.noi_dung.slice(0, 80))}</span>
    <span class="qs-phu">${esc(k.tuoi_chu || '')}${phu ? ` · ${esc(phu)}` : ''}${
      k.da_loc ? ` · đã lọc ${esc(k.da_loc)}` : ''}</span></div>`;
}

function theSuKien(s) {
  return `<div class="kyuc-hang" data-sk="${esc(s.id)}">
    <span class="hh xam">${esc(String(s.loai || '').replace('event:', ''))}</span>
    <span class="kyuc-td">${esc((s.tom_tat || '').slice(0, 120))}</span>
    <span class="qs-phu">#${esc(s.id)} · ${esc(s.tuoi_chu || '')}${
      s.blob_sha ? ' · có blob' : ''}${s.da_loc ? ` · đã lọc ${esc(s.da_loc)}` : ''}</span></div>`;
}

async function veKyUcDanhSach() {
  if (!S.selected || kyUcDangTai) return;
  kyUcDangTai = true;
  const pid = encodeURIComponent(S.selected);
  const q = ($('#kyuc-tim').value || '').trim();
  try {
    let html = '';
    if (q) {
      const r = await api(`/api/memory/search?project=${pid}&q=${encodeURIComponent(q)}`
        + (kyUcLoc !== 'timeline' && kyUcLoc !== 'context' && kyUcLoc !== 'checkpoint'
          ? `&loai=${encodeURIComponent(kyUcLoc)}` : ''));
      html += `<div class="nhan">KÝ ỨC KHỚP (${r.ket_qua.length}) · ${esc(r.che_do_tim || '')}</div>`;
      html += r.ket_qua.map((k) => theKyUc(k, `điểm ${Number(k.diem).toFixed(2)}`)).join('')
        || trong('không có ký ức khớp');
      if (r.su_kien && r.su_kien.length) {
        html += `<div class="nhan" style="margin-top:8px">LỊCH SỬ THÔ KHỚP (${r.su_kien.length})</div>`;
        html += r.su_kien.map(theSuKien).join('');
      }
    } else if (kyUcLoc === 'timeline') {
      const r = await api(`/api/memory/timeline?project=${pid}&limit=80`);
      html = r.su_kien.map(theSuKien).join('') || trong('chưa có lịch sử');
    } else if (kyUcLoc === 'context') {
      const r = await api(`/api/memory/context?project=${pid}&q=`);
      html = `<div class="nhan">GÓI NGỮ CẢNH — ${esc(r.token_uoc)}/${esc(r.token_tran)} token ·
        ${esc(r.chon ? r.chon.length : 0)} chọn · ${esc(r.bo_qua ?? 0)} bỏ qua ·
        ${esc(r.lich_su_so_su_kien ?? 0)} sự kiện trong sổ</div>
        <pre class="kyuc-goi">${esc(r.van || '(rỗng — chưa có gì để nhớ)')}</pre>`;
    } else if (kyUcLoc === 'backfill') {
      html = veBackfillPanel(await api(`/api/memory/backfill/sources?project=${pid}`), null);
    } else {
      const r = await api(`/api/memory/list?project=${pid}&loai=${encodeURIComponent(kyUcLoc)}`);
      if (kyUcLoc === 'decision') {
        html = r.ket_qua.map((q) => `<div class="kyuc-hang" data-ma="${esc(q.ma)}">
          <span class="hh ${q.hieu_luc ? 'tim' : 'xam'}">${esc(q.ma)}</span>
          <span class="kyuc-td">${esc(q.ky_uc ? (q.ky_uc.tieu_de || q.ky_uc.noi_dung.slice(0, 90)) : '')}</span>
          <span class="qs-phu">${q.hieu_luc ? 'HIỆU LỰC' : `THAY THẾ bởi ${esc(q.bi_thay_the)}`}${
            q.thay_the_cho.length ? ` · thay ${esc(q.thay_the_cho.join(','))}` : ''}</span></div>`).join('')
          || trong('chưa có quyết định — bấm “+ Quyết định” để ghi');
      } else if (kyUcLoc === 'checkpoint') {
        html = r.ket_qua.map((d) => `<div class="kyuc-hang" data-ma="${esc(d.ma)}">
          <span class="hh luc">${esc(d.ma.slice(0, 10))}</span>
          <span class="kyuc-td">${esc(d.muc_tieu || d.ly_do)}</span>
          <span class="qs-phu">${esc(tuoiChu((Date.now() / 1000) - d.ts))} · ${esc(d.ly_do)}</span></div>`).join('')
          || trong('chưa có điểm dừng');
      } else {
        html = r.ket_qua.map((k) => theKyUc(k)).join('') || trong(`chưa có bản ghi ${kyUcLoc}`);
      }
    }
    dat('#kyuc-ds', html);
  } catch (e) {
    dat('#kyuc-ds', trong(`không đọc được: ${e.message}`));
  } finally { kyUcDangTai = false; }
}

// Nguon lich su: quet / thu kho / nhap. Moi hanh dong la MOT nut bam ro rang;
// khong tu nhap gi khi mo tab.
function veBackfillPanel(ng, kq) {
  const hang = (ng.nguon || []).map((n) => {
    const lc = n.lan_cuoi;
    const tk = lc ? lc.thong_ke || {} : null;
    return `<div class="kyuc-hang" data-nguon="${esc(n.nguon)}">
      <span class="hh ${n.san ? 'luc' : 'xam'}">${n.san ? 'sẵn' : 'không sẵn'}</span>
      <span class="kyuc-td"><b>${esc(n.nhan)}</b>${n.ly_do ? ` — ${esc(n.ly_do)}` : ''}</span>
      <span class="qs-phu">đã nhập ${esc(n.da_nhap)}${tk ? ` · lần cuối: ${tk.thu_kho ? 'thử khô' : 'nhập'}
        ${esc(tk.kham_pha ?? 0)} khám phá / ${esc(tk.da_nhap ?? 0)} nhập / ${esc(tk.trung ?? 0)} trùng /
        ${esc(tk.de_bat ?? 0)} đề bạt · ${esc(tuoiChu((Date.now() / 1000) - lc.ts))}` : ''}</span></div>`;
  }).join('') || trong('không có nguồn nào');
  let kqHtml = '';
  if (kq) {
    const t = kq.tong || {};
    kqHtml = `<div class="nhan" style="margin-top:8px">${kq.thu_kho ? 'THỬ KHÔ' : 'ĐÃ NHẬP'} —
      ${esc(kq.giay)}s</div>
      <div class="kyuc-thongke" style="grid-template-columns:repeat(4,minmax(0,1fr))">
        ${[['khám phá', t.kham_pha], ['nhập', t.da_nhap], ['trùng (bỏ)', t.trung], ['bỏ qua', t.bo_qua],
           ['đã lọc bí mật', t.da_loc], ['đề bạt', t.de_bat], ['còn lại', t.con_lai], ['nguồn không sẵn', t.khong_san]]
          .map(([n, v]) => `<div class="kyuc-o"><div class="kyuc-so">${esc(v ?? 0)}</div><div class="kyuc-nhan">${esc(n)}</div></div>`).join('')}
      </div>
      ${(kq.nguon || []).map((s) => `<div class="qs-phu">· ${esc(s.nguon)}: khám phá ${esc(s.kham_pha)},
        nhập ${esc(s.da_nhap)}, trùng ${esc(s.trung)}, đề bạt ${esc(s.de_bat)}${s.khong_san ? `, không sẵn: ${esc(s.khong_san)}` : ''}
        ${(s.ghi_chu || []).length ? ` · ${esc(s.ghi_chu[0])}` : ''}</div>`).join('')}`;
  }
  return `<div class="nhan">NGUỒN LỊCH SỬ CỦA DỰ ÁN <span class="qs-phu">— chỉ đọc nguồn; ghi vào sổ ký ức;
      chỉ đề bạt lịch sử trước mốc ký ức ${ng.moc_ky_uc ? esc(new Date(ng.moc_ky_uc * 1000).toLocaleString()) : ''}</span></div>
    ${hang}
    <div class="hang-nut" style="margin-top:8px">
      <button id="bf-scan" class="nho">Quét lại</button>
      <button id="bf-dry" class="nho" title="Chỉ đếm, không ghi">Thử khô</button>
      <button id="bf-import" title="Ghi vào sổ ký ức (idempotent, resumable)">Nhập</button>
    </div>${kqHtml}`;
}

async function chayBackfill(thuKho) {
  const pid = encodeURIComponent(S.selected);
  dat('#kyuc-ds', trong(thuKho ? 'đang thử khô…' : 'đang nhập lịch sử… (có thể mất vài phút)'));
  try {
    const kq = await api('/api/memory/backfill', { method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project: S.selected, thu_kho: thuKho }) });
    const ng = await api(`/api/memory/backfill/sources?project=${pid}`);
    dat('#kyuc-ds', veBackfillPanel(ng, kq));
    if (!thuKho) veKyUcThongKe();
  } catch (e) { dat('#kyuc-ds', trong(`không chạy được: ${e.message}`)); }
}
$('#kyuc-ds').addEventListener('click', (e) => {
  if (e.target.id === 'bf-scan') veKyUcDanhSach();
  else if (e.target.id === 'bf-dry') chayBackfill(true);
  else if (e.target.id === 'bf-import') chayBackfill(false);
});

function veBangChung(bcs) {
  if (!bcs || !bcs.length) return '<p class="ghi-chu">không có mắt xích bằng chứng (bản ghi gốc)</p>';
  return bcs.map((b) => {
    const sk = b.su_kien;
    let s = `<div class="kyuc-bc">`;
    if (sk) {
      s += `<div><b>sự kiện #${esc(sk.id)}</b> · ${esc(sk.loai)} · ${esc(sk.nguon)} ·
        ${esc(new Date(sk.ts * 1000).toLocaleString())}</div>
        <pre class="kyuc-goi">${esc(sk.tom_tat)}</pre>`;
    }
    if (b.blob) {
      s += `<div><b>nội dung đầy đủ</b> · sha ${esc(b.blob.sha.slice(0, 12))} ·
        toàn vẹn ${b.blob.toan_ven ? 'OK' : 'HỎNG'}</div>
        <pre class="kyuc-goi">${esc(String(b.blob.noi_dung).slice(0, 4000))}</pre>`;
    }
    if (!b.co) s += `<div class="qs-phu">bằng chứng thiếu: ${esc(b.ly_do || '')}</div>`;
    return s + '</div>';
  }).join('');
}

async function moBanGhiKyUc(ma) {
  if (!S.selected) return;
  let r;
  try {
    r = await api(`/api/memory/record?project=${encodeURIComponent(S.selected)}&ma=${encodeURIComponent(ma)}`);
  } catch (e) { dat('#kyuc-chitiet', trong(e.message)); return; }
  if (!r.co) { dat('#kyuc-chitiet', trong(r.ly_do || 'không có')); return; }
  const k = r.ky_uc, q = r.quyet_dinh, d = r.diem_dung;
  let html = '';
  if (k) {
    html += `<div class="nhan">${esc(k.ma)} <span class="hh ${MAU_KYUC[k.loai] || 'xam'}">${esc(k.loai)}</span></div>
      <div class="kyuc-meta">
        <span class="hh ${k.hieu_luc ? 'luc' : (k.trang_thai === 'thay_the' ? 'xam' : 'vang')}">${
          k.hieu_luc ? 'HIỆU LỰC' : esc(String(k.trang_thai || '').toUpperCase())}</span>
        ghi ${esc(new Date(k.ts * 1000).toLocaleString())} ·
        chuyện xảy ra ${esc(new Date(k.ts_su_kien * 1000).toLocaleString())}
        ${k.ts_sua && Math.abs(k.ts_sua - k.ts) > 1 ? ` · sửa ${esc(new Date(k.ts_sua * 1000).toLocaleString())}` : ''} ·
        quan trọng ${esc(k.quan_trong)}/10 · thẩm quyền <b>${esc(k.tin_cay)}</b>
        ${k.nguon_loai ? ` · nguồn <b>${esc(k.nguon_loai)}</b>${k.nguon_id ? ` #${esc(k.nguon_id)}` : ''}` : ''}
        ${k.het_han ? ' · <span class="hh vang">QUÁ TTL</span>' : ''}
        ${k.da_loc ? ` · đã lọc ${esc(k.da_loc)}` : ''}</div>
      ${(k.thay_the_cho || []).length ? `<div class="qs-phu">thay thế cho: ${esc(k.thay_the_cho.join(', '))}</div>` : ''}
      ${k.bi_thay_the ? `<div class="qs-phu">bị thay thế bởi: <a href="#" data-ma="${esc(k.bi_thay_the)}" class="kyuc-link">${esc(k.bi_thay_the)}</a></div>` : ''}
      ${k.tieu_de ? `<h4>${esc(k.tieu_de)}</h4>` : ''}
      <pre class="kyuc-goi">${esc(k.noi_dung)}</pre>
      ${k.the.length ? `<div class="qs-phu">thẻ: ${esc(k.the.join(', '))}</div>` : ''}`;
  }
  if (q) {
    html += `<div class="nhan" style="margin-top:8px">QUYẾT ĐỊNH ${esc(q.ma)} —
      ${q.hieu_luc ? '<span class="hh tim">HIỆU LỰC</span>' : `<span class="hh xam">THAY THẾ</span> bởi ${esc(q.bi_thay_the)}`}</div>
      ${q.thay_the_cho.length ? `<div class="qs-phu">thay thế cho: ${esc(q.thay_the_cho.join(', '))}</div>` : ''}
      ${q.ly_do ? `<div><b>vì sao:</b> ${esc(q.ly_do)}</div>` : ''}`;
  }
  if (d) {
    html += `<div class="nhan">ĐIỂM DỪNG ${esc(d.ma)}</div>
      <pre class="kyuc-goi">${esc(JSON.stringify(d, null, 1))}</pre>`;
  }
  if (r.su_kien) {
    html += `<div class="nhan">SỰ KIỆN #${esc(r.su_kien.id)}</div>` + veBangChung([r]);
  } else if (r.bang_chung) {
    html += `<div class="nhan" style="margin-top:8px">VÌ SAO NHỚ — BẰNG CHỨNG GỐC</div>` + veBangChung(r.bang_chung);
  }
  dat('#kyuc-chitiet', html);
}

function veKyUc() { veKyUcThongKe(); veKyUcDanhSach(); }

$('#nut-kyuc-tim').onclick = veKyUcDanhSach;
$('#kyuc-tim').addEventListener('keydown', (e) => { if (e.key === 'Enter') veKyUcDanhSach(); });
$$('.kyuc-chip').forEach((b) => {
  b.onclick = () => {
    kyUcLoc = b.dataset.loc;
    $$('.kyuc-chip').forEach((x) => x.classList.toggle('dang-mo', x === b));
    veKyUcDanhSach();
  };
});
$('#kyuc-ds').addEventListener('click', (e) => {
  const h = e.target.closest('.kyuc-hang');
  if (!h) return;
  if (h.dataset.ma) moBanGhiKyUc(h.dataset.ma);
  else if (h.dataset.sk) moBanGhiKyUc(`sk#${h.dataset.sk}`);
});
$('#nut-kyuc-checkpoint').onclick = () => moHopThoai('Ghi điểm dừng (handoff)', `
  <p class="ghi-chu">Điểm dừng là thứ phiên SAU đọc để tiếp tục mà không cần dán handoff.
  Trạng thái việc được lấy từ sổ; ở đây bạn ghi phần máy không tự biết.</p>
  <label>Đang làm gì<textarea id="dd-muc-tieu" rows="2"></textarea></label>
  <label>Giả thuyết hiện tại<textarea id="dd-gia-thuyet" rows="2"></textarea></label>
  <label>Chưa xong (mỗi dòng một mục)<textarea id="dd-chua-xong" rows="3"></textarea></label>
  <div class="hang-nut"><button id="dd-luu">Ghi điểm dừng</button></div>`, () => {
  $('#dd-luu').onclick = async () => {
    try {
      const r = await api('/api/memory/checkpoint', { method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project: S.selected, ly_do: 'handoff từ giao diện',
          noi_dung: { muc_tieu: $('#dd-muc-tieu').value, gia_thuyet: $('#dd-gia-thuyet').value,
                      chua_xong: $('#dd-chua-xong').value } }) });
      dongHopThoai(); kyUcLoc = 'checkpoint';
      $$('.kyuc-chip').forEach((x) => x.classList.toggle('dang-mo', x.dataset.loc === 'checkpoint'));
      veKyUc(); if (r && r.ma) moBanGhiKyUc(r.ma);
    } catch (e) { alert(`không ghi được: ${e.message}`); }
  };
});
$('#nut-kyuc-quyetdinh').onclick = () => moHopThoai('Ghi quyết định', `
  <p class="ghi-chu">Quyết định là BẤT BIẾN: đổi ý thì ghi quyết định mới và nêu nó thay
  thế cái nào. Cái cũ chỉ đổi trạng thái, không bị sửa.</p>
  <label>Tiêu đề<input id="qd-tieu-de"></label>
  <label>Quyết định gì<textarea id="qd-noi-dung" rows="3"></textarea></label>
  <label>Vì sao<textarea id="qd-ly-do" rows="2"></textarea></label>
  <label>Thay thế cho (mã qd_…, cách nhau bởi dấu phẩy, để trống nếu không)
    <input id="qd-thay-the" placeholder="qd_0001"></label>
  <div class="hang-nut"><button id="qd-luu">Ghi quyết định</button></div>`, () => {
  $('#qd-luu').onclick = async () => {
    try {
      const r = await api('/api/memory/decision', { method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project: S.selected, tieu_de: $('#qd-tieu-de').value,
          noi_dung: $('#qd-noi-dung').value, ly_do: $('#qd-ly-do').value,
          thay_the_cho: $('#qd-thay-the').value.split(',').map((x) => x.trim()).filter(Boolean) }) });
      dongHopThoai(); kyUcLoc = 'decision';
      $$('.kyuc-chip').forEach((x) => x.classList.toggle('dang-mo', x.dataset.loc === 'decision'));
      veKyUc(); if (r && r.ma) moBanGhiKyUc(r.ma);
    } catch (e) { alert(`không ghi được: ${e.message}`); }
  };
});

// ------------------------------------------------------------------- tab ----
function doiKhung(ten) {
  $$('.tab').forEach((b) => b.classList.toggle('dang-mo', b.dataset.khung === ten));
  $$('.khung').forEach((k) => k.classList.toggle('dang-mo', k.id === `khung-${ten}`));
  if (ten === 'usage') veUsage();
  if (ten === 'kyuc') veKyUc();
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

// ==================== V0.6.1: PROVIDERS & ACCOUNTS ====================
//
// Mot hop thoai, ba phan: KHO BI MAT (kieu, san hay khong), BE TAI KHOAN
// ANTIGRAVITY (so dem tu so dang ky dang chay — khong gia dinh "8"), NHA
// CUNG CAP NGOAI (provider / tai khoan / model). Gia tri khoa di vao DUY
// NHAT o o `type=password` cua form "Them tai khoan", gui MOT LAN toi
// 127.0.0.1 kem token, va khong bao gio quay lai: moi phan hoi chi mang
// `credential_ref`. Khong nut nao o day dinh tuyen AUTO — "Hoi thu" la
// duong THU CONG, nguoi bam, mot luot.
let pvState = { d: null, u: null };

function pvBadgeTaiKhoan(t) {
  if (!t.bat) return hh('OFF');
  if (t.cooldown_den && t.cooldown_den * 1000 > Date.now()) return hh('COOLDOWN');
  if (t.lan_thu_ok === true) return hh('OK');
  if (t.lan_thu_ok === false) return hh('DOWN');
  return hh('UNKNOWN');
}

function veProvidersHtml(d, u) {
  const kho = d.kho_bi_mat || {};
  const pool = (u && u.pool) || {};
  const rts = ((u && u.runtimes) || []).filter((r) => r.provider === 'antigravity');
  const ag = pool.antigravity;
  const models = d.models || {};
  const tks = d.tai_khoan || [];
  const presets = d.presets || [];
  const cs = d.chinh_sach || {};

  const khoHtml = `<div class="nhan">KHO BÍ MẬT</div>
    <div class="qs-hang"><span class="qs-ten">${esc(kho.kieu || '?')}</span>
      <span class="qs-phu">${esc(kho.chi_tiet || '')}</span>
      ${hh(kho.san ? (kho.ben ? 'OK' : 'DEGRADED') : 'DOWN')}</div>
    <p class="ghi-chu">Giá trị khoá chỉ đi vào kho này (vùng tên <code>${esc(kho.vung_ten || '')}</code>).
      Sổ <code>providers.db</code> chỉ giữ <b>credential_ref</b>, alias, trạng thái; sổ Control
      Center và ký ức dự án chỉ giữ sự kiện đã lọc. Không có kho an toàn thì KHÔNG thêm được tài
      khoản — không rơi về tệp thường.</p>`;

  const agHtml = `<div class="nhan" style="margin-top:10px">BỂ TÀI KHOẢN ANTIGRAVITY
      <span class="qs-phu">— đếm từ sổ đăng ký đang chạy${u ? '' : ' (chọn một dự án để đọc)'}</span></div>
    ${ag ? `<div class="kyuc-thongke" style="grid-template-columns:repeat(4,minmax(0,1fr))">
      ${[['đăng ký', ag.dang_ky], ['cấp phát', ag.cap_phat], ['nhận dispatch', ag.nhan_dispatch],
         ['khoẻ', ag.khoe], ['cooldown', ag.cooldown], ['offline', ag.offline],
         ['chỗ đang dùng / tổng', `${ag.dang_dung}/${ag.tong_cho}`], ['hồ sơ riêng', ag.ho_so_rieng]]
        .map(([n, v]) => `<div class="kyuc-o"><div class="kyuc-so">${esc(v)}</div>
          <div class="kyuc-nhan">${esc(n)}</div></div>`).join('')}</div>
      <div class="qs-phu">Leader đang chiếm chỗ ở: ${(ag.leader_chiem || []).length
        ? esc(ag.leader_chiem.join(', ')) : 'không'} · Leader và worker dùng CÙNG bể (Leader ghim AG01);
        từ V0.6.1 chỗ Leader chiếm hiện ra với bộ lập lịch.</div>
      <details><summary>${rts.length} khe</summary>
        ${rts.map((r) => `<div class="qs-hang">
          <span class="qs-ten">${esc(r.runtime_id)} <span class="qs-phu">${esc(r.auth_profile || '')}</span></span>
          <span class="qs-phu">${esc(r.in_flight)}/${esc(r.concurrency)}${(r.running_tasks || []).length
            ? ' · ' + esc(r.running_tasks.join(', ')) : ''}${r.consecutive_failures
            ? ` · hỏng liên tiếp ${esc(r.consecutive_failures)}` : ''}${r.health_detail
            ? ` · ${esc(r.health_detail)}` : ''}${r.needs_provisioning ? ` · ${esc(r.needs_provisioning)}` : ''}</span>
          ${hh(r.status)}</div>`).join('')}</details>` : trong('chưa đọc được bể — chọn dự án rồi mở lại')}`;

  const pvs = (d.providers || []).map((p) => {
    const ms = models[p.provider_id] || [];
    const tk = tks.filter((t) => t.provider_id === p.provider_id);
    const be = (d.be || {})[p.provider_id] || {};
    return `<div class="pv-khoi" data-pid="${esc(p.provider_id)}" style="border:1px solid var(--vien);border-radius:6px;padding:8px;margin-top:8px">
      <div class="qs-hang"><span class="qs-ten"><b>${esc(p.provider_id)}</b> — ${esc(p.ten)}</span>
        <span class="qs-phu">${esc(p.preset)} · <code>${esc(p.base_url)}</code></span>
        ${hh(p.bat ? 'OK' : 'OFF')}
        <button class="nho" data-act="pv-xoa" data-pid="${esc(p.provider_id)}" title="Xoá provider + mọi tài khoản + credential của nó">Xoá</button></div>
      <div class="qs-phu">${esc(ms.filter((m) => m.nguon === 'probed').length)} model đo được ·
        ${esc(ms.filter((m) => m.nguon === 'preset').length)} gợi ý (chưa đo) ·
        bể: ${esc(be.bat ?? 0)} bật / ${esc(be.khoe ?? 0)} khoẻ / ${esc(be.cooldown ?? 0)} cooldown</div>
      ${tk.length ? tk.map((t) => `<div class="qs-hang" data-acc="${esc(t.account_id)}">
          <span class="qs-ten">${esc(t.alias)} <span class="qs-phu">ref ${esc(t.credential_ref)}</span></span>
          <span class="qs-phu">${t.lan_thu_ts ? `thử ${esc(tuoiChu(Date.now() / 1000 - t.lan_thu_ts))}: ` : ''}${esc(t.lan_thu_chi_tiet || 'chưa thử')}</span>
          ${pvBadgeTaiKhoan(t)}
          <button class="nho" data-act="tk-thu" data-acc="${esc(t.account_id)}" title="GET /models (miễn phí) hoặc chat max_tokens=1">Thử kết nối</button>
          <button class="nho" data-act="tk-bat" data-acc="${esc(t.account_id)}" data-bat="${t.bat ? '0' : '1'}">${t.bat ? 'Tắt' : 'Bật'}</button>
          <button class="nho" data-act="tk-hoi" data-acc="${esc(t.account_id)}" data-pid="${esc(p.provider_id)}" title="Định tuyến THỦ CÔNG một lượt">Hỏi thử</button>
          <button class="nho" data-act="tk-xoa" data-acc="${esc(t.account_id)}" title="Xoá tài khoản + credential khỏi kho">Xoá</button>
        </div>`).join('') : trong('chưa có tài khoản — thêm bên dưới (khoá không rời máy này)')}
      <div class="cd-hang" style="margin-top:6px">
        <input type="text" class="pv-alias" placeholder="alias (vd prod)" style="width:30%">
        <input type="password" class="pv-khoa" placeholder="API key — chỉ gửi MỘT lần tới 127.0.0.1" autocomplete="off" style="flex:1">
        <button class="nho" data-act="tk-them" data-pid="${esc(p.provider_id)}">Thêm tài khoản</button>
      </div>
      <div class="pv-ket-qua qs-phu"></div>
    </div>`;
  }).join('') || trong('chưa có nhà cung cấp ngoài nào');

  const themHtml = `<div class="nhan" style="margin-top:10px">THÊM NHÀ CUNG CẤP</div>
    <div class="cd-hang">
      <select id="pv-preset">${presets.map((p) => `<option value="${esc(p.ma)}" data-url="${esc(p.base_url_mac_dinh)}">${esc(p.ten)}</option>`).join('')}</select>
      <input id="pv-id" type="text" placeholder="mã (vd alibaba)" style="width:22%">
    </div>
    <div class="cd-hang">
      <input id="pv-url" type="text" placeholder="base_url (https://…/v1)" style="flex:1"
        value="${esc((presets[0] || {}).base_url_mac_dinh || '')}">
      <button id="pv-them" class="chinh nho">Thêm</button>
    </div>
    <p class="ghi-chu" id="pv-preset-ghi-chu">${esc((presets[0] || {}).ghi_chu || '')}</p>
    <p class="ghi-chu">Định tuyến AUTO cho provider ngoài: <b>${cs.auto_routing ? 'BẬT' : 'TẮT'}</b>. ${esc(cs.ly_do || '')}</p>`;

  return khoHtml + agHtml + `<div class="nhan" style="margin-top:10px">NHÀ CUNG CẤP NGOÀI</div>` + pvs + themHtml;
}

async function veProviders() {
  try { pvState.d = await api('/api/providers'); }
  catch (e) { dat('#pv-than', trong(`không đọc được providers: ${e.message}`)); return; }
  try { pvState.u = S.selected ? await api(`/api/usage?project=${encodeURIComponent(S.selected)}`) : null; }
  catch { pvState.u = null; }
  dat('#pv-than', veProvidersHtml(pvState.d, pvState.u));
  const sel = $('#pv-preset');
  if (sel) {
    sel.onchange = () => {
      const o = sel.options[sel.selectedIndex];
      $('#pv-url').value = o.dataset.url || '';
      const p = (pvState.d.presets || []).find((x) => x.ma === sel.value) || {};
      $('#pv-preset-ghi-chu').textContent = p.ghi_chu || '';
      if (!$('#pv-id').value) $('#pv-id').value = (sel.value.split('_')[0] || '').slice(0, 24);
    };
  }
}

async function pvGoi(duong, opt, ketQuaEl) {
  try {
    const r = await api(duong, opt);
    await veProviders();
    return r;
  } catch (e) {
    noi(`provider: ${e.message}`);
    if (ketQuaEl) ketQuaEl.textContent = e.message;
    return null;
  }
}

$('#nut-providers').onclick = async () => {
  moHopThoai('Providers & Accounts', `<div id="pv-than">${trong('đang tải…')}</div>`);
  await veProviders();
};

document.addEventListener('click', async (e) => {
  const b = e.target.closest('button');
  if (!b || !$('#pv-than')) return;
  const json = (body) => ({ method: 'POST', headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(body) });
  const pid = b.dataset.pid, acc = b.dataset.acc;
  const khoi = b.closest('.pv-khoi');
  const kq = khoi ? khoi.querySelector('.pv-ket-qua') : null;
  if (b.id === 'pv-them') {
    const r = await pvGoi('/api/providers', json({ provider_id: $('#pv-id').value.trim(),
      preset: $('#pv-preset').value, base_url: $('#pv-url').value.trim() }));
    if (r) noi(`đã thêm provider ${r.provider_id}`);
  } else if (b.dataset.act === 'pv-xoa') {
    if (!window.confirm(`Xoá provider ${pid} cùng MỌI tài khoản và credential của nó?`)) return;
    await pvGoi(`/api/providers/${encodeURIComponent(pid)}?xac_nhan=true`, { method: 'DELETE' });
  } else if (b.dataset.act === 'tk-them') {
    const alias = khoi.querySelector('.pv-alias').value.trim();
    const oKhoa = khoi.querySelector('.pv-khoa');
    const gia_tri = oKhoa.value;
    oKhoa.value = '';                                  // xoa khoi DOM ngay
    if (!alias || !gia_tri) { noi('cần alias và khoá'); return; }
    const r = await pvGoi(`/api/providers/${encodeURIComponent(pid)}/accounts`,
      json({ alias, gia_tri, project: S.selected || '' }), kq);
    if (r) noi(`đã lưu vào kho bí mật — ref ${r.credential_ref}`);
  } else if (b.dataset.act === 'tk-thu') {
    if (kq) kq.textContent = 'đang thử kết nối…';
    const r = await pvGoi(`/api/providers/accounts/${encodeURIComponent(acc)}/test`,
      json({ project: S.selected || '' }), kq);
    const el = $('#pv-than') && $('#pv-than').querySelector(`[data-acc="${acc}"]`);
    if (r && el) noi(`${r.ket_qua.ok ? 'OK' : 'HỎNG'} · ${r.ket_qua.chi_tiet}`);
  } else if (b.dataset.act === 'tk-bat') {
    await pvGoi(`/api/providers/accounts/${encodeURIComponent(acc)}/toggle`,
      json({ bat: b.dataset.bat === '1' }), kq);
  } else if (b.dataset.act === 'tk-xoa') {
    if (!window.confirm(`Xoá tài khoản ${acc} và credential của nó khỏi kho?`)) return;
    await pvGoi(`/api/providers/accounts/${encodeURIComponent(acc)}?xac_nhan=true`, { method: 'DELETE' });
  } else if (b.dataset.act === 'tk-hoi') {
    const ms = ((pvState.d || {}).models || {})[pid] || [];
    const model = window.prompt('Model (định tuyến THỦ CÔNG, một lượt):',
      (ms.find((m) => m.nguon === 'probed') || ms[0] || {}).model_id || '');
    if (!model) return;
    const cau = window.prompt('Câu hỏi:', 'Trả lời một từ: ping?');
    if (!cau) return;
    if (kq) kq.textContent = 'đang hỏi…';
    try {
      const r = await api(`/api/providers/accounts/${encodeURIComponent(acc)}/ask`,
        json({ model, cau, project: S.selected || '', max_tokens: 128 }));
      if (kq) kq.textContent = r.ok ? `[${model}] ${r.noi_dung}` : `HỎNG: ${r.chi_tiet}`;
    } catch (err) { if (kq) kq.textContent = err.message; }
  }
});

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

// WebSocket THEO DU AN DANG CHON. Loi that (nghiem thu toa V0.6.1): ket noi
// duoc mo MOT lan luc tai trang voi `project=` cua du an dau tien, va doi du
// an chi goi `lamMoi()` (mot lan fetch) — moi day SONG sau do van la cua du an
// cu, ma du an cu khong doi gi nen server KHONG day gi ca. Ket qua: bang
// Tasks/Agents cua du an dang xem dung hinh sau lan fetch, du API co 3 phien
// BUSY. Nen: doi du an -> dong ket noi cu (khong tu noi lai) -> mo ket noi
// moi; va bo qua goi cua du an khac neu con den tre.
let wsDangMo = null;
let wsDuAn = '';
function noiWs() {
  if (wsDangMo) {
    const cu = wsDangMo;
    wsDangMo = null;                       // `onclose` cua cu thay khac -> khong noi lai
    try { cu.close(); } catch { /* da dong */ }
  }
  wsDuAn = S.selected;
  const u = `ws://${location.host}/ws?t=${encodeURIComponent(TOKEN)}`
    + `&project=${encodeURIComponent(S.selected)}`;
  const ws = new WebSocket(u);
  wsDangMo = ws;
  ws.onopen = () => noi('đã kết nối · trạng thái sống');
  ws.onmessage = (ev) => {
    const goi = JSON.parse(ev.data);
    if (goi.kind !== 'state') return;
    if (goi.data.selected && S.selected && goi.data.selected !== S.selected) return;
    S = { ...S, ...goi.data };
    S.selected = goi.data.selected || S.selected;
    veHet();
  };
  ws.onclose = () => {
    if (wsDangMo !== ws) return;           // dong CO Y khi doi du an
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
