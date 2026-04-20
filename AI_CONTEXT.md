AI_CONTEXT.md — Watch Store Management App
1. Tổng quan & Stack Công nghệ
Mục tiêu dự án: App nội bộ quản lý cửa hàng đồng hồ (3 chi nhánh) — dần thay thế KiotViet. Quy mô nhỏ: vài nhân viên, 1 developer (owner + AI assist).

Stack:

Frontend/Backend: Streamlit (Python).

Database: Supabase (PostgreSQL).

Auth: bcrypt hash password, session token UUID lưu URL query params.

Dependencies: streamlit, pandas, plotly, supabase, bcrypt, openpyxl.

3 Chi nhánh: 100 Lê Quý Đôn, Coop Vũng Tàu, GO BÀ RỊA.
3 Role: admin (toàn quyền), ke_toan, nhan_vien.

2. Cấu trúc Thư mục
app.py: Single-file code base chứa toàn bộ logic.

requirements.txt: Các thư viện phụ thuộc.

CLAUDE.md: Quy tắc hành vi (Think-before-code, Simplicity, Surgical changes).

3. Trạng thái Hiện tại
Bảng Supabase chính:

nhan_vien, sessions, hang_hoa, the_kho, hoa_don.

phieu_chuyen_kho: Chứa cả phiếu KiotViet và phiếu App.

phieu_kiem_ke & phieu_kiem_ke_chi_tiet: (Đang phát triển) Lưu thông tin đợt kiểm kê và chi tiết từng mã hàng.

Logic delta tồn kho (CỰC KỲ QUAN TRỌNG):

Phiếu App (loai_phieu = "Chuyển hàng (App)") sinh delta động lên snapshot the_kho.

Tuyệt đối không thay đổi logic này để tránh làm sai lệch tồn kho khi tính toán realtime.

4. Quy ước Code (CLAUDE.md)
Think-before-code: Luôn phân tích logic trước khi viết.

Simplicity: Giữ code đơn giản, dễ bảo trì.

Surgical changes: Chỉ sửa đúng chỗ cần thiết, không refactor lan man.

Natural Familiarity: Không dùng các cụm từ như "Dựa trên...", "Vì bạn đã đề cập...".

5. Vấn đề Đang kẹt & Tech Debt (Cập nhật 02/04/2026)
TRỌNG TÂM: Hoàn thiện Module Kiểm kê

Hiện tại module Kiểm kê đang gặp các lỗi logic và yêu cầu tinh chỉnh UX sau:

1. Lỗi Runtime & Logic:

NameError: Lỗi _kk_complete is not defined khi bấm nút "Hoàn thành kiểm kê" khiến phiếu bị kẹt không thể chốt.

Lỗi Lọc Nhóm Con: Bộ lọc Nhóm con đang bị lỗi trả về kết quả trống (không tìm thấy hàng tồn) ngay cả khi có hàng.

2. Yêu cầu UX/UI mới:

Lọc đa nhóm: Hỗ trợ chọn nhiều nhóm hàng cùng lúc (nhóm cha, nhóm con lẫn lộn) để kiểm kê nhiều khu vực cùng lúc.

Sắp xếp bảng quét: Mặt hàng vừa quét thành công phải được đẩy lên đầu danh sách để nhân viên dễ theo dõi kết quả vừa tít.

Thay đổi Metrics: Đổi 3 chỉ số dưới bảng từ "Số SKU, tổng quét, tổng lệch tuyệt đối" thành:

Tổng tồn (số lượng lý thuyết).

Tổng quét (số lượng thực tế).

Tổng chênh lệch (số lượng chênh lệch thực tế).

3. Quyền hạn:

Nút "Hủy phiếu" biến mất hoặc không hoạt động ổn định khi cần xóa các phiếu tạo lỗi/phiếu rác.
