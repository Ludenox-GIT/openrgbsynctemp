# OpenRGB Temp Sync

**OpenRGB Temp Sync** là một ứng dụng chạy ẩn dưới khay hệ thống (System Tray) dành cho Windows, giúp tự động đồng bộ hóa màu sắc đèn LED của máy tính dựa theo nhiệt độ của CPU hoặc GPU trong thời gian thực.

Ứng dụng kết nối trực tiếp đến máy chủ **OpenRGB SDK** và điều khiển độc lập từng bóng LED trên các thiết bị tương thích (Mainboard, RAM, VGA, Quạt ARGB, Dây LED...).

---

## 🌟 Tính Năng Nổi Bật

- **Đồng bộ hóa mượt mà (Smoothed Transitions):** Sử dụng thuật toán lọc nhiễu số (EMA) và nội suy màu sắc ở tần số cao (20Hz) giúp màu đèn chuyển đổi cực kỳ mượt mà, không bị giật cục khi nhiệt độ nhảy đột ngột.
- **Tùy biến chi tiết từng bóng LED (Per-LED Customization):**
  - Đặt độ sáng độc lập (0% - 100%) cho từng đèn.
  - Chọn nguồn nhiệt độ độc lập (CPU hoặc GPU) cho từng đèn.
- **Hỗ trợ Đa nguồn nhiệt độ (CPU/GPU Temp):**
  - Đọc nhiệt độ CPU qua bộ nhớ chia sẻ của **Core Temp** (vượt qua các rào cản bảo mật driver của Windows Core Isolation/Memory Integrity).
  - Đọc nhiệt độ GPU của các dòng card đồ họa **NVIDIA** thông qua thư viện gốc `nvml.dll`.
- **Tích hợp hệ thống thông minh:**
  - Tự động tắt đèn LED để tiết kiệm điện năng khi màn hình chờ (Screensaver) được kích hoạt.
  - Menu chuột phải tiện lợi: Bật/tắt nhanh đồng bộ, bật/tắt nhanh đèn LED, mở Cài đặt, và tùy chọn khởi động cùng Windows.
  - Chạy ẩn 100% không hiện cửa sổ dòng lệnh đen (Console window).

---

## 🛠️ Yêu Cầu Hệ Thống & Chuẩn Bị

Để phần mềm hoạt động chính xác, máy tính của bạn cần chạy sẵn hai phần mềm nền sau:

1. **[Core Temp](https://www.alcpu.com/CoreTemp/):** Khởi chạy Core Temp để ứng dụng có thể đọc nhiệt độ CPU. (Có thể thu nhỏ vào khay hệ thống).
2. **[OpenRGB](https://openrgb.org/):**
   - Khởi chạy OpenRGB.
   - Đi tới tab **SDK Server** và nhấn **Start Server** (mặc định chạy trên cổng `6742`).
   - *Lưu ý:* Cần thiết lập OpenRGB khởi động cùng Windows và tự động bật SDK Server.
3. **NVIDIA Driver (Tùy chọn):** Chỉ cần thiết nếu bạn muốn đồng bộ màu đèn theo nhiệt độ GPU NVIDIA.

---

## 🚀 Hướng Dẫn Cài Đặt & Sử Dụng

### Cách 1: Sử dụng File Chạy Ngay (.exe) - Khuyên Dùng
Bạn không cần cài đặt Python, chỉ cần tải thư mục dự án về máy:
1. Chạy **`start.bat`** để khởi chạy ứng dụng ẩn vào khay hệ thống. Lúc này bạn sẽ thấy biểu tượng hình nguyên tử neon sáng lên ở góc phải màn hình.
2. Để cấu hình màu sắc, nhấp chuột phải vào biểu tượng khay hệ thống và chọn **`Settings`**.
3. Để tắt ứng dụng hoàn toàn, nhấp chuột phải vào biểu tượng và chọn **`Exit`** hoặc chạy file **`stop.bat`**.

### Cách 2: Chạy từ Mã nguồn Python
Nếu bạn muốn chỉnh sửa hoặc chạy trực tiếp bằng Python:
1. Cài đặt Python 3.10 trở lên và các thư viện cần thiết:
   ```bash
   pip install pillow pystray openrgb-python
   ```
2. Khởi chạy ứng dụng:
   ```bash
   pythonw src/openrgb_tray_app.py
   ```

---

## ⚙️ Hướng Dẫn Cấu Hình (Settings)

Nhấp chuột phải vào biểu tượng khay hệ thống và chọn **Settings** để mở bảng điều khiển:

### 1. Tab Color Settings (Cài đặt Màu sắc & Hệ thống)
- **Temperature Thresholds & Colors:** Cài đặt 3 mốc nhiệt độ (Low / Mid / High) và màu sắc tương ứng (mặc định: Xanh lá ở 30°C, Xanh dương ở 60°C, Đỏ ở 75°C). Bạn có thể nhấp vào ô màu để tự do chọn màu tùy ý qua bảng màu Windows.
- **Color Transition Speed:** Tốc độ phản hồi và chuyển màu của đèn LED (Từ 1 - 10, số càng lớn chuyển màu càng nhanh).
- **System Integration:**
  - `Turn off LEDs when screensaver starts`: Tự động tắt LED khi màn hình chờ Screensaver bắt đầu.
- **Start with Windows:** Tích chọn trên Menu chuột phải để ứng dụng tự động chạy khi bạn mở máy.

### 2. Tab Advanced Per-LED Brightness (Cài đặt Nâng cao từng đèn)
- **Select Device:** Chọn thiết bị phần cứng đang kết nối với OpenRGB để cấu hình.
- **Danh sách bóng LED:** Mỗi dòng tương ứng với một bóng đèn trên thiết bị:
  - Chọn **CPU** hoặc **GPU** làm nguồn nhiệt độ điều khiển bóng đèn đó.
  - Kéo thanh trượt để chỉnh độ sáng độc lập cho bóng đèn đó từ `0%` đến `100%`.
- **Set all (Áp dụng nhanh):** Chọn độ sáng và nguồn nhiệt độ ở bảng điều khiển nhanh đầu tab, sau đó nhấn **`Apply All`** để áp dụng đồng loạt cho toàn bộ bóng đèn của thiết bị đó.
- Nhấn **`Save Settings`** để lưu lại cấu hình. Mọi thiết lập được lưu trữ di động trong file `config.json` nằm cùng thư mục phần mềm.

---

## 📄 Giấy Phép & Bản Quyền

Dự án này được phát triển phục vụ mục đích đồng bộ hóa cá nhân và hoàn toàn miễn phí.
