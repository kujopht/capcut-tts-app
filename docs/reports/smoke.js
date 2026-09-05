// Doc/ghi that tren ban DA KHOI PHUC. Ghi vao mot collection NHAP rieng,
// khong dong vao bat ky collection du lieu nao, va don sach sau khi xong.
const dbA = db.getSiblingDB('appwrite');
const c = dbA.getCollection('_rehearsal_smoke');
c.drop();

const r1 = c.insertOne({ probe: 'rehearsal-20260905', n: 1, at: new Date() });
print('INSERT       ack=' + r1.acknowledged);

const back = c.findOne({ probe: 'rehearsal-20260905' });
print('READBACK     n=' + back.n + ' probe=' + back.probe);

const r2 = c.updateOne({ probe: 'rehearsal-20260905' }, { $set: { n: 42 } });
print('UPDATE       matched=' + r2.matchedCount + ' modified=' + r2.modifiedCount);
print('READBACK     n=' + c.findOne({}).n);

// Appwrite 1.9 dung TRANSACTION, va transaction CHI chay duoc tren replica
// set. Neu buoc nay hong thi Appwrite se hong du moi phep doc deu xanh.
let txnOk = false;
try {
  const s = dbA.getMongo().startSession();
  s.startTransaction();
  s.getDatabase('appwrite').getCollection('_rehearsal_smoke')
    .insertOne({ probe: 'txn', n: 7 });
  s.commitTransaction();
  s.endSession();
  txnOk = true;
} catch (e) {
  print('TRANSACTION  LOI: ' + e.message);
}
print('TRANSACTION  commit=' + txnOk + ' tong_doc=' + c.countDocuments({}));

const r3 = c.deleteMany({});
print('CLEANUP      deleted=' + r3.deletedCount);
c.drop();
print('DA_XOA_COLLECTION_NHAP=' +
      (dbA.getCollectionNames().indexOf('_rehearsal_smoke') === -1));

// Xac nhan du lieu that KHONG bi dong toi.
const P = '01a021df-8fa6-7271-89cc-d69481be1bc9';
const D = '01a021e9-f671-70c6-bae9-629f4b58ff94';
const meta = dbA.getCollection('_' + P + '_database_' + D);
const rn = meta.findOne({ _uid: 'novels' });
const nov = dbA.getCollection('_' + P + '_database_' + D + '_collection_' + rn._id);
print('NOVELS_VAN_CON=' + nov.countDocuments({}));
