# OpenRGB Temp Sync (Unified Desktop App)

**OpenRGB Temp Sync** là ứng dụng hoàn chỉnh và thống nhất chạy dưới khay hệ thống (System Tray) trên Windows, tự động đồng bộ hóa màu sắc đèn LED máy tính theo nhiệt độ thời gian thực của CPU hoặc GPU.

Phiên bản Unified One-App tích hợp trọn gói:
1. **Một bộ cài đặt duy nhất (One Installer)**: Cài đặt và cấu hình hoàn chỉnh trong một lần, không cần cài đặt hoặc khởi chạy thủ công OpenRGB hay Core Temp.
2. **Quản lý máy chủ OpenRGB độc lập**: Tự động khởi chạy máy chủ OpenRGB nội bộ ở chế độ ẩn, an toàn tuyệt đối trên giao diện loopback cục bộ (`127.0.0.1:6742`).
3. **Bộ đọc cảm biến nội bộ (Internal Sensor Bridge)**: Tích hợp công nghệ `LibreHardwareMonitorLib` để đọc nhiệt độ CPU (AMD/Intel) và GPU (NVIDIA) trực tiếp với quyền Administrator.
4. **Khởi động cùng Windows qua Scheduled Task**: Sử dụng tác vụ đăng nhập đặc quyền cao (Elevated Logon Scheduled Task) để khởi động tự động mượt mà, không bật thông báo UAC phiền toái.

---

## 🌟 Tính Năng Chính

- **Đồng bộ hóa mượt mà (Smoothed Transitions):**
  Thuật toán lọc Exponential Moving Average (EMA) kết hợp nội suy màu sắc 20 Hz (Linear Interpolation) mang lại chuyển động đổi màu êm ái, loại bỏ hiện tượng nhấp nháy khi nhiệt độ biến thiên nhanh.
- **Tùy biến chi tiết từng bóng LED (Per-LED Customization):**
  - Điều chỉnh độ sáng độc lập (0% - 100%) cho từng bóng LED.
  - Chọn nguồn nhiệt độ độc lập (CPU hoặc GPU) cho từng bóng LED.
  - Hỗ trợ đổi hàng loạt ("Set all") cực nhanh trong giao diện cài đặt.
- **Điều khiển dải LED địa chỉ (Addressable Zones):**
  - Chọn riêng số bóng cho các zone có thể cấu hình như `JRAINBOW1/JRAINBOW2`; giới hạn min/max lấy trực tiếp từ OpenRGB và được lưu lại cho lần chạy sau.
  - Nút **Reset to Original** trả từng thiết bị về mode, màu và số bóng trước khi app bắt đầu đồng bộ; **Resume Sync** bật lại điều khiển nhiệt độ.
  - **Restore Manufacturer Defaults** là thao tác riêng. Với MSI B550, hai ENE DRAM và Gigabyte RTX 3060 hiện chưa có đường lệnh OEM exact-device được chứng minh nên nút này hiển thị `Unverified` và bị khóa; app không giả mạo snapshot restore/OpenRGB Reset Zone thành reset nhà sản xuất. Vendor baseline snapshots được lưu theo canonical stable key độc lập để ghi nhận trạng thái mong muốn của phần cứng mà không giả lập OEM factory reset.
- **Bảo mật và an toàn kết nối:**
  - Kiểm tra nghiêm ngặt cổng 6742; từ chối và chặn kết nối nếu phát hiện listener mở rộng ra toàn mạng (`0.0.0.0` wildcard) để bảo vệ mạng nội bộ.
  - Tự động nhận diện và kết nối an toàn với máy chủ OpenRGB bên ngoài nếu đang mở sẵn.
  - Cơ chế Windows Job Object đảm bảo các tiến trình con (OpenRGB engine và Sensor bridge) luôn được đóng sạch sẽ khi ứng dụng tắt, không để lại tiến trình mồ côi.
- **Tích hợp khay hệ thống thông minh:**
  - Biểu tượng khay đổi màu động theo nhiệt độ thực tế.
  - Menu khay tiện lợi: Start/Stop Sync, Bật/Tắt đèn (Turn Lights Off), Settings, Khởi động cùng Windows, Retry Engine, và Export Diagnostics.
  - Tự động tắt đèn tiết kiệm điện khi màn hình chờ (Screensaver) kích hoạt.

---

## ⚙️ Cài Đặt & Sử Dụng

1. Bản phát hành một file mới nhất là `release/OpenRGBTempSync-Final.exe`; chạy file bằng quyền Administrator. File tự bung OpenRGB và SensorBridge vào thư mục tạm khi chạy, còn cấu hình/log vẫn nằm trong `%LOCALAPPDATA%\OpenRGBTempSync`.
2. Ứng dụng sẽ tự khởi động và xuất hiện tại khay hệ thống (System Tray).
3. Nhấp đúp hoặc nhấp chuột phải vào biểu tượng khay -> chọn **Settings** để cấu hình ngưỡng nhiệt độ, bảng màu và độ sáng đèn.
4. Tùy chọn **Start with Windows** được cấu hình tự động thông qua Windows Task Scheduler.

### Trạng thái xác minh phần cứng

Tự động kiểm thử mã nguồn đạt 171/171. Smoke test trên OpenRGB SDK của máy này đã xác nhận nhận đủ 4 controller và sau khi khởi động lại đều khôi phục mode `Direct`. Baseline hiện tại do người dùng xác nhận là mặc định đã được lưu dưới tên `vendor_default` trong `%LOCALAPPDATA%\OpenRGBTempSync\config.json`, tách riêng hai thanh RAM bằng stable key. Hướng effect dạng chữ được chuyển đúng sang enum số mà SDK yêu cầu; `SetCustomMode` chỉ dùng cho motherboard MSI đã xác định, còn RAM/GPU dùng mode packet thông thường để tránh làm rơi socket SDK. Khi socket rơi, engine chuyển sang `Degraded`, UI hiển thị lỗi kết nối và yêu cầu retry thay vì vẫn hiển thị Running. Nút **Reset to Original** có fallback sang baseline đã lưu khi snapshot runtime mất sau reconnect. **Restore Manufacturer Defaults** vẫn khóa `Unverified` cho MSI B550, ENE DRAM và Gigabyte RTX 3060 cho đến khi có bằng chứng OEM độc lập và cold-boot.

---

## 🛠️ Hướng Dẫn Phát Triển & Kiểm Thử

Chi tiết quy trình build và kiểm thử:
- [Hướng dẫn Build & Đóng gói](docs/BUILD.md)
- [Cẩm nang Xử lý Sự cố (Troubleshooting)](docs/TROUBLESHOOTING.md)
- [Thông tin Bản quyền bên thứ ba (Third-Party Notices)](docs/THIRD_PARTY.md)

Chạy bộ kiểm thử tự động:
```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

---

Kho mã chỉ chứa OpenRGB Temp Sync và SensorBridge; các artefact build/cache được loại khỏi source và không nằm trong gói phát hành.
