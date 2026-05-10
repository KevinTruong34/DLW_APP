"""
Streamlit custom component cho module Chuyển hàng — Master-Detail UX.

Wrapper:
- chuyen_hang_component(props, key) → trả về event dict hoặc None.
- Event shape: {action, id?, payload?, nonce}.
- Caller dùng nonce để dedup (mỗi action click ra 1 nonce mới).
"""

from pathlib import Path
import streamlit.components.v1 as components

_DIR = Path(__file__).parent
_FRONTEND_DIR = _DIR / "frontend"

# Declare local component (no dev server — đọc trực tiếp index.html)
_component_func = components.declare_component(
    "chuyen_hang_mvc",
    path=str(_FRONTEND_DIR),
)


def chuyen_hang_component(
    *,
    tickets: list,
    branches: list,
    accessible_branches: list,
    active_branch: str,
    is_admin: bool,
    current_user: str,
    hang_hoa: list,
    the_kho_by_branch: dict,
    first_month_iso: str,
    first_last_iso: str,
    key: str = "chuyen_hang_mvc",
    height: int = 900,
):
    """Render module Chuyển hàng dưới dạng master-detail single-page.

    Args:
        tickets: list các phiếu, mỗi phiếu là dict đầy đủ kèm items[].
        branches: ALL_BRANCHES.
        accessible_branches: chi nhánh user có quyền xem.
        active_branch: chi nhánh đang active.
        is_admin: True nếu role=admin.
        current_user: tên hiển thị mặc định cho nguoi_tao/nguoi_nhan.
        hang_hoa: master list sản phẩm [{ma, name, gia}].
        the_kho_by_branch: {branch: {ma: ton}} — tồn theo chi nhánh.
        first_month_iso: ISO date đầu tháng hiện tại (YYYY-MM-DD).
        first_last_iso: ISO date đầu tháng trước (YYYY-MM-DD).
        key: streamlit component key.
        height: chiều cao iframe (px).

    Returns:
        Event dict hoặc None nếu chưa có action.
    """
    return _component_func(
        tickets=tickets,
        branches=branches,
        accessible_branches=accessible_branches,
        active_branch=active_branch,
        is_admin=is_admin,
        current_user=current_user,
        hang_hoa=hang_hoa,
        the_kho_by_branch=the_kho_by_branch,
        first_month_iso=first_month_iso,
        first_last_iso=first_last_iso,
        key=key,
        default=None,
        height=height,
    )
