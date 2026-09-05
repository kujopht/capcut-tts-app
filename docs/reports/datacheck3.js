// Doi soat du lieu muc UNG DUNG tren ban Appwrite DA KHOI PHUC. Chi DOC.
//
// HAI LAN TRUOC DEU SAI ID, va ca hai lan deu ra "0 document tren moi
// collection" — mot ket qua trong sach trong khi du lieu that van nam nguyen.
// Do dung la ve "khoi phuc rong" ma dot dien tap nay sinh ra de bac bo, nen
// ghi lai cho ro:
//
//   r.$id   -> khong ton tai trong adapter Mongo cua Appwrite
//   r._uid  -> ID NGUOI DOC duoc ("novels"), khong dung de dat ten collection
//   r._id   -> UUID noi bo, DAY moi la thu ghep vao ten collection vat ly
//
// Ten vat ly = _<projectId>_database_<dbInternalId>_collection_<_id>
const dbA = db.getSiblingDB('appwrite');
const names = dbA.getCollectionNames();
const metas = names.filter(n => /_database_[0-9a-f-]+$/.test(n));

const tong = {};

metas.forEach(function (m) {
  const proj = m.replace(/^_/, '').split('_database_')[0];
  const dbid = m.split('_database_')[1];
  const rows = dbA.getCollection(m).find({}).toArray();
  if (!rows.length) { return; }
  const dbName = rows[0].databaseId || '(?)';
  print('\n=== DATABASE ' + dbName + '  (project ' + proj.slice(0, 8) + '...) ===');

  rows.sort(function (a, b) { return (a.name || '').localeCompare(b.name || ''); });
  let doc = 0, colCoData = 0;
  rows.forEach(function (r) {
    const phys = '_' + proj + '_database_' + dbid + '_collection_' + r._id;
    let n = -1;
    try { n = dbA.getCollection(phys).countDocuments({}); } catch (e) { n = -1; }
    if (n > 0) { doc += n; colCoData += 1; }
    if (n > 0) { print('  ' + (r.name || r._uid).padEnd(34) + ' docs=' + n); }
  });
  print('  -- collection khai bao: ' + rows.length +
        ', co du lieu: ' + colCoData + ', tong document: ' + doc);
  tong[dbName] = { collection: rows.length, coDuLieu: colCoData, document: doc };
});

print('\n=== TONG KET ===');
Object.keys(tong).forEach(function (k) {
  print(k + ': collection=' + tong[k].collection +
        ' co_du_lieu=' + tong[k].coDuLieu +
        ' document=' + tong[k].document);
});
