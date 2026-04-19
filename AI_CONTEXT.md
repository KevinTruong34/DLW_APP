# AI_CONTEXT.md — Watch Store Management App

## 1. Tổng quan & Stack Công nghệ

**Mục tiêu dự án:** App nội bộ quản lý cửa hàng đồng hồ (3 chi nhánh) — dần thay thế KiotViet. Quy mô nhỏ: vài nhân viên, 1 developer (owner + AI assist).

**Stack:**
- **Frontend/Backend:** Streamlit (Python), deploy trên Streamlit Community Cloud
- **Database:** Supabase (PostgreSQL) qua supabase-py REST client
- **Auth:** bcrypt hash password, session token UUID lưu URL query params (`?token=xxx&branch=yyy`), expire 3 ngày
- **Dependencies:** `streamlit, pandas, plotly, supabase, bcrypt, openpyxl`

**3 Chi nhánh:** `100 Lê Quý Đôn`, `Coop Vũng Tàu`, `GO BÀ RỊA` (hardcode trong `ALL_BRANCHES`, có `CN_SHORT` map tên ngắn).

**3 Role:** `admin` (toàn quyền), `ke_toan` (xem nhiều CN), `nhan_vien` (chỉ CN của mình).

## 2. Cấu trúc Thư mục
