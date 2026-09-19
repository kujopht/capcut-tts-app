# 🌐 CYBER SERPENT 3D - Titan Edition

Phiên bản 3D WebGL thế hệ mới đỉnh cao của game Rắn Săn Mồi, xây dựng trên nền tảng **Three.js** kết hợp bộ tổng hợp âm thanh **Web Audio API** nguyên bản.

---

## 🌟 Tính năng & Trải nghiệm 3D Độc Bản

1. **Vật lý Serpentine 3D uốn lượn tự nhiên (Inverse Kinematics)**:
   - Thân rắn 3D chuyển động mượt mà 60–120 FPS.
   - **Cơ chế Nghiêng Thân (Dynamic Banking & Roll)**: Khi rẽ ngoặt, các đốt thân sẽ nghiêng lượn theo góc cua như chiến đấu cơ phản lực!
   - Đầu chiến giáp gắn đèn chiếu sáng **Head PointLight** rọi xuống sàn kim loại phản chiếu bóng đổ thời gian thực.
   - Đuôi phản lực xả luồng hạt Plasma khi kích hoạt bứt tốc Turbo.

2. **3 Chế độ Camera Động (Bấm phím `C` hoặc nút 🎥)**:
   - **🎥 CHASE CAM (Góc nhìn thứ 3 theo đuôi)**: Camera đuổi theo sau lưng, tự động phóng tầm mắt FOV khi tăng tốc Turbo và rung chấn khi va chạm.
   - **🚀 COCKPIT (Góc nhìn thứ nhất từ kính lái)**: Trực diện từ buồng lái đầu rắn, lướt sát mặt sàn neon với cảm giác tốc độ chóng mặt!
   - **📐 TACTICAL (Góc nhìn từ trên xuống)**: Toàn cảnh đấu trường không gian 3D chiến thuật cổ điển với chiều sâu không gian ấn tượng.

3. **Kẻ thù Hardcore & Siêu Trùm 3D**:
   - 🐉 **3D APEX LEVIATHAN (BOSS)**:
     - Siêu trùm khổng lồ (kích thước gấp đôi), trang bị vảy gai đỏ đen và sừng năng lượng rực sáng.
     - Thanh máu Boss hiển thị trên HUD (`5/5 HP`).
     - **Trạng thái Cuồng Nộ (Hyper Enrage)**: Hú còi báo động, xả lửa đỏ và lao thẳng với tốc độ 30 units/s để nghiền nát người chơi!
     - Khi bị tiêu diệt, Boss nổ tung thành 35 viên Pha lê Năng lượng Vàng (+1500+ điểm)!
   - 🤖 **3D HUNTER-STALKERS**:
     - Bot AI 3D tính toán đường đi để đón lõng và tạt đầu ép người chơi va chạm.
   - 💣 **THỦY LÔI EMP 3D (Floating Mines)**:
     - Thủy lôi kim loại gai nhọn lơ lửng với vòng tròn cảm biến xoay quanh, nổ tung với phản ứng dây chuyền khi va chạm!
   - ⚡ **CỔNG LASER CAO ÁP 3D**:
     - Các cột trụ năng lượng phóng tia laser plasma đỏ rực thiêu rụi mọi thứ đi qua.

4. **Vật phẩm & Kỹ năng Chiến đấu**:
   - 💎 **Pha lê Năng lượng 3D**: Khối đa diện 3D Icosahedron xoay tròn lơ lửng với vòng xuyến Torus bao quanh.
   - 🧲 **Magnet Matrix**: Hút pha lê bay theo đường cong 3D về phía miệng rắn.
   - 🛡️ **Khiên Lượng Tử 3D (Energy Shield)**: Tạo lồng cầu trường lực lục giác 3D bao bọc bảo vệ đầu rắn khỏi 1 đòn chí mạng.
   - 💣 **Sóng Xung Kích EMP (Phím `E` / Chuột Phải / Nút `EMP`)**: Xung kích 360 độ kích nổ toàn bộ mìn và làm choáng (Stun) toàn bộ kẻ thù trong bán kính 35 units!

---

## 🎮 Cách khởi chạy phiên bản 3D

### Cách 1: Chạy Desktop Native Window (Khuyên dùng)
- Nhấp đúp chuột vào:
  ```text
  play_snake_3d.bat (ở thư mục gốc)
  ```
  hoặc
  ```text
  cyber_snake_3d/play_3d.bat
  ```
  Trò chơi sẽ mở trong một cửa sổ Desktop Native hiệu năng cao 1180x880.

### Cách 2: Chạy trực tiếp trên Trình duyệt Web
- Mở file `cyber_snake_3d/index.html` bằng bất kỳ trình duyệt nào.
- Chạy 100% Offline nhờ file thư viện Three.js nội bộ (`three.min.js`).

---

## 🕹️ Bảng điều khiển 3D

| Thao tác | Bàn phím & Chuột | Cảm ứng / Mobile |
| :--- | :--- | :--- |
| **Đổi hướng** | Rê **Chuột** hoặc phím **W A S D / Mũi tên** | Kéo **Cần gạt ảo (Joystick)** ở góc trái |
| **Đổi góc quay Camera** | Bấm phím **C** | Chạm thanh **Góc nhìn** hoặc nút **🎥** |
| **Bứt tốc Turbo** | Giữ phím **SPACE** hoặc **Chuột trái** | Giữ nút **BOOST** tròn màu đỏ |
| **Sóng Xung Kích EMP** | Bấm phím **E** hoặc **Chuột phải** | Chạm nút **EMP** màu xanh dương |
| **Tạm dừng / Tiếp tục** | Phím **P** hoặc **ESC** | Nút **⏸** trên thanh điều khiển HUD |
| **Bật/Tắt Âm thanh & Nhạc**| Nút **🔊** và **🎵** trên góc phải | Chạm trực tiếp vào icon tương ứng |
