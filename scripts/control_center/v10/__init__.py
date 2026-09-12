# -*- coding: utf-8 -*-
"""V1.0 — NỀN MÓNG PROJECT LEADER TỰ CHỦ.

Gói này KHÔNG thay Router V4 và KHÔNG thay vòng kín V0.9. Nó thêm đúng thứ
hai tầng đó cố ý không có:

    vai_tro.py    VAI TRÒ ổn định, MODEL thay được — và chính sách review
                  chéo họ model (B4, B5)
    phien_leader.py  Leader có DANH TÍNH theo dự án + phiên nối lại được,
                  trên một trừu tượng runtime (B2, B3)
    su_kien.py    BUS SỰ KIỆN có kiểu cho Team Activity (B7)
    su_co.py      VÒNG SỰ CỐ: phân loại -> sửa -> kiểm lại -> leo thang,
                  CÓ TRẦN (B6)
    han_muc.py    MÔ HÌNH TÀI NGUYÊN: bể quota đo được, UNKNOWN là hợp lệ (B8)

RANH GIỚI KHÔNG ĐƯỢC XOÁ (B9): Leader quyết ĐIỀU GÌ NÊN LÀM. Router quyết
ĐIỀU GÌ ĐƯỢC PHÉP XẢY RA. Không có đường nào từ gói này tới một shell không
giới hạn; mọi tác động ra ngoài vẫn đi qua phong bì quyền, cổng GATED và
worktree cô lập của V0.9.x.
"""
