# 🐉 ASTRAL DRAGON 3D: SOLAR ODYSSEY (No Man's Sky Edition)

Phiên bản game Rắn Săn Mồi hóa thân thành **Rồng Thần Không Gian 3D (Astral Cosmic Dragon)** tự do bay lượn 6 bậc tự do (6DoF) trong hệ mặt trời siêu thực lấy cảm hứng từ kiệt tác không gian *No Man's Sky*.

---

## 🌟 Nâng Cấp Đồ Họa Đẳng Cấp No Man's Sky

1. **Xử Lý Hậu Kỳ Điện Ảnh (Offline HDR UnrealBloomPass)**:
   - Tích hợp module hậu kỳ HDR Bloom chạy 100% offline nội bộ.
   - Mọi nguồn năng lượng: Mặt Trời Solaris, sừng rồng hoàng kim, mắt rồng starlight, đạn plasma, lõi tinh vân và đĩa bồi tụ lỗ đen đều thực sự phát sáng và tỏa vầng hào quang rực rỡ (*light bleed*) vào ống kính.

2. **Khí Quyển Tán Xạ Chân Thực (GLSL Atmospheric Scattering Limb Shader)**:
   - Viết custom shader GLSL tính toán Fresnel góc nhìn với pháp tuyến mặt cầu (`pow(1.0 - dot(N, V), power)`).
   - Tạo vầng hào quang tán xạ Rayleigh xanh ngọc rực rỡ bao quanh **Terra Nova** và vầng sáng tím huyền bí bao quanh hành tinh khí **Aurelia**.

3. **Hệ Thống Mây 2 Tầng Độc Lập (Dynamic Rotating Cloud Deck)**:
   - Tầng mây trắng bồng bềnh bán trong suốt xoay độc lập phía trên đại dương và lục địa của Terra Nova, tạo cảm giác hành tinh đang sống và có đối lưu khí quyển.

4. **Bụi Không Gian 3D & Vệt Tốc Độ Bẻ Cong Không Gian (Space Dust & Pulse Drive Streaks)**:
   - 2,400 hạt bụi vũ trụ trôi dạt 3D xung quanh rồng theo thời gian thực.
   - Khi kích hoạt **Warp Speed (Pulse Drive)**: Toàn bộ hạt bụi ngay lập tức kéo dài thành những vệt sáng laser siêu tốc (*Hyperspace Streaks*) xé toạc không gian, kết hợp cùng hiệu ứng mở rộng góc nhìn FOV điện ảnh (Dolly Zoom từ 65° ra 88°).

5. **Dải Bụi Sao Đuôi Rồng & Đầu Cánh (Stardust Ribbon Particle Trail)**:
   - Đầu hai cánh và chóp đuôi rồng liên tục rải lại dải hạt bụi sao lấp lánh kéo dài trong không gian khi lướt và uốn lượn.
   - Thân rồng phủ lớp giáp óng ánh (*Iridescent Material*) phản quang đổi màu dưới ánh mặt trời.

6. **Giao Diện Hologram Khoa Học Viễn Tưởng (Sci-Fi Holographic HUD)**:
   - **Tọa độ la bàn 3D (Screen-Space Waypoints)**: Định vị thời gian thực tên và khoảng cách tới từng hành tinh (*AURELIA [340u]*, *TERRA NOVA [560u]*, v.v.).
   - **Pulse Drive Telemetry HUD**: Bảng đo tốc độ bẻ cong không gian (*4.6 AU/s*) và vạch xung năng lượng rực sáng khi warp.

---

## 🎮 Cách khởi chạy phiên bản Rồng Vũ Trụ 3D

### Cách 1: Chạy Desktop Native Window (Khuyên dùng)
- Nhấp đúp chuột vào:
  ```text
  play_dragon.bat (ở thư mục gốc)
  ```
  hoặc
  ```text
  cosmic_dragon_3d/play_dragon.bat
  ```
  Trò chơi sẽ mở trong một cửa sổ Native Desktop độ phân giải cao 1240x880.

### Cách 2: Chạy trực tiếp trên Trình duyệt Web
- Mở file `cosmic_dragon_3d/index.html` bằng bất kỳ trình duyệt nào.
- Hoạt động 100% Offline nhờ các thư viện Three.js và Postprocessing nội bộ (`three.min.js`, `postprocessing.min.js`).

---

## 🕹️ Bảng điều khiển Rồng Thần 3D

| Thao tác | Bàn phím & Chuột | Cảm ứng / Mobile |
| :--- | :--- | :--- |
| **Đổi hướng bay 3D** | Rê **Chuột** (Tâm ngắm theo chuột) | Kéo trượt màn hình |
| **Bứt tốc Warp Speed** | Giữ phím **SPACE** hoặc **Chuột trái** | Giữ nút **WARP** tròn màu tím |
| **Hơi thở Rồng Plasma**| Bấm phím **F** hoặc **Chuột phải** | Chạm nút **FIRE** tròn màu đỏ |
| **Đổi Camera (3 chế độ)**| Bấm phím **C** | Chạm thanh **Góc nhìn** hoặc nút **🎥** |
| **Tạm dừng / Tiếp tục** | Phím **P** hoặc **ESC** | Nút **⏸** trên thanh điều khiển HUD |
| **Bật/Tắt Âm thanh & Nhạc**| Nút **🔊** và **🎵** trên góc phải | Chạm trực tiếp vào icon tương ứng |
