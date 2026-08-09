/**
 * Duong dang nhap bang nha cung cap nao dang duoc chao ban.
 *
 * MAY CHU MOI LA NOI CUONG CHE. Co o day chi quyet dinh giao dien co VE cai
 * nut hay khong; `/api/auth/oauth/facebook` tu no da tra 404 khi
 * `FAS_FACEBOOK_LOGIN` chua bat. Sua file nay khong mo lai duoc duong dang
 * nhap that.
 *
 * Phai khop voi `Settings.facebook_login_enabled` trong `server/config.py`.
 * Co mot test Python doc chinh file nay va so hai gia tri — lech la do, nen
 * khong am tham troi duoc: `server/tests/test_oauth.py`.
 *
 * Cung khuon voi `lib/limits.ts`, va vi cung mot ly do: hai gia tri o hai
 * ngon ngu khac nhau se troi khoi nhau neu khong ai giu.
 *
 * VI SAO TAT: quyet dinh san pham, khong phai loi ky thuat. Toan bo phan hien
 * thuc Facebook — nut, route, adapter, cau hinh Appwrite, credential o Meta —
 * deu duoc GIU NGUYEN. Bat lai la doi mot bien moi truong.
 */
export const FACEBOOK_LOGIN_ENABLED: boolean = false;

/** Google luon bat. Khai bao ra de hai duong doc giong nhau o cho goi. */
export const GOOGLE_LOGIN_ENABLED: boolean = true;
