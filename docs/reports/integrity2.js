// Bat bien muc UNG DUNG — ban sua sau khi ban dau kiem HO.
//
// Lan truoc dung `novelId` (camelCase). Kho nay dung `novel_id` (snake_case),
// nen ca 290 chapter deu "thieu novelId" va phep kiem tro thanh RONG: no in
// "DAT — khong co tham chieu mo coi" trong khi that ra khong so sanh gi ca.
// Mot phep kiem rong nguy hiem hon khong kiem, vi no phat ra bang chung gia.
// Nen ban nay TU CHOI ket luan DAT khi so ban ghi so sanh duoc bang 0.
const dbA = db.getSiblingDB('appwrite');
const P = '01a021df-8fa6-7271-89cc-d69481be1bc9';
const D = '01a021e9-f671-70c6-bae9-629f4b58ff94';
const meta = dbA.getCollection('_' + P + '_database_' + D);

function col(uid) {
  const r = meta.findOne({ _uid: uid });
  return r ? dbA.getCollection('_' + P + '_database_' + D + '_collection_' + r._id) : null;
}

const novels = col('novels');
const chapters = col('chapters');
const audio = col('audio_tracks');

print('KEYS novels : ' + Object.keys(novels.findOne({})).join(', '));
print('KEYS audio  : ' + Object.keys(audio.findOne({})).join(', '));

// --- 1. tap ID novel that ---
const idNovel = {};
let nNovel = 0;
novels.find({}, { novel_id: 1 }).toArray().forEach(function (n) {
  if (n.novel_id) { idNovel[n.novel_id] = 1; nNovel += 1; }
});
print('\nnovel co novel_id: ' + nNovel);

// --- 2. chapter -> novel ---
let tong = 0, thieu = 0, mo = 0;
chapters.find({}, { novel_id: 1 }).toArray().forEach(function (c) {
  tong += 1;
  if (!c.novel_id) { thieu += 1; return; }
  if (!idNovel[c.novel_id]) { mo += 1; }
});
const soSanhDuoc = tong - thieu;
print('\n=== CHAPTER -> NOVEL ===');
print('  tong chapter         : ' + tong);
print('  thieu novel_id       : ' + thieu);
print('  so sanh duoc         : ' + soSanhDuoc);
print('  tro toi novel KHONG co: ' + mo);
if (soSanhDuoc === 0) {
  print('  KET QUA: KHONG KET LUAN DUOC — khong co ban ghi nao de so sanh');
} else {
  print('  KET QUA: ' + (mo === 0 ? 'DAT' : 'HONG (' + mo + ' mo coi)'));
}

// --- 3. audio -> chapter ---
const idChap = {};
let nChap = 0;
chapters.find({}, { chapter_id: 1 }).toArray().forEach(function (c) {
  if (c.chapter_id) { idChap[c.chapter_id] = 1; nChap += 1; }
});
let at = 0, athieu = 0, amo = 0;
audio.find({}, { chapter_id: 1 }).toArray().forEach(function (a) {
  at += 1;
  if (!a.chapter_id) { athieu += 1; return; }
  if (!idChap[a.chapter_id]) { amo += 1; }
});
const aSoSanh = at - athieu;
print('\n=== AUDIO -> CHAPTER ===');
print('  chapter co chapter_id: ' + nChap);
print('  tong audio           : ' + at);
print('  thieu chapter_id     : ' + athieu);
print('  so sanh duoc         : ' + aSoSanh);
print('  tro toi chapter KHONG co: ' + amo);
if (aSoSanh === 0) {
  print('  KET QUA: KHONG KET LUAN DUOC');
} else {
  print('  KET QUA: ' + (amo === 0 ? 'DAT' : 'HONG (' + amo + ' mo coi)'));
}

// --- 4. noi dung that ---
print('\n=== NOI DUNG ===');
let tongKyTu = 0, rong = 0;
chapters.find({}, { content: 1 }).toArray().forEach(function (c) {
  const l = (c.content || '').length;
  tongKyTu += l;
  if (l === 0) { rong += 1; }
});
print('  tong ky tu trong 290 chapter: ' + tongKyTu);
print('  chapter rong                : ' + rong);
