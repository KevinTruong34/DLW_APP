"""
Hide Streamlit Cloud branding badge ("Hosted with Streamlit") + profile container
ở góc dưới phải màn hình.

Đã verify (12/05/2026) trên Chrome desktop:
- Top window cùng origin với iframe app (dl-watch-pos.streamlit.app)
- window.top.document accessible từ components.html iframe
- Selector a[href*="streamlit.io/cloud"] match đúng badge

LƯU Ý KỸ THUẬT — Tại sao dùng window.top, KHÔNG dùng window.parent:
- `components.html()` của Streamlit tạo iframe NESTED bên trong iframe app
- Từ trong iframe components, `window.parent` = iframe app POS (KHÔNG có badge)
- `window.top` = top window (chứa badge)
- → Phải dùng window.top để reach badge

Workaround tạm thời. Có thể break khi Streamlit Cloud thay đổi:
- Structure DOM (vd đổi class name, đổi href badge)
- Iframe sandbox policy (vd thêm sandbox flag block top access)
- Cross-origin (vd tách iframe sang subdomain khác)

Nếu badge xuất hiện lại sau update Streamlit → cần inspect lại + cập nhật selector.
"""
import streamlit as st
import streamlit.components.v1 as components


_JS_HIDE_BADGE = """
<script>
(function() {
    // Selectors target từ DOM inspection (12/05/2026):
    //   <a href="https://streamlit.io/cloud" class="_container_gzau3_1 _viewerBadge_nim44_23">
    //   <div class="_profileContainer_gzau3_53">
    // Class names có hash suffix → match qua attribute selector để robust với
    // case Streamlit rebuild + đổi hash.
    const SELECTORS = [
        'a[href*="streamlit.io/cloud"]',     // Badge "Hosted with Streamlit"
        '[class*="_profileContainer"]',       // Profile avatar góc phải
        '[class*="viewerBadge"]',             // Fallback nếu class đổi
        '[class*="_viewerBadge"]',
        '[data-testid="stStatusWidget"]',     // Status widget (Manage button)
        'button[title="Manage app"]',
        'button[aria-label="Manage app"]'
    ];
    
    function hideAll() {
        // CRITICAL: dùng window.top (KHÔNG dùng window.parent).
        // components.html() tạo iframe nested bên trong iframe app POS, nên
        // parent = iframe app POS (KHÔNG có badge), top = top window (có badge).
        try {
            const doc = window.top.document;
            if (!doc) return 0;
            
            let hidden = 0;
            SELECTORS.forEach(sel => {
                doc.querySelectorAll(sel).forEach(el => {
                    if (el.style.display !== 'none') {
                        el.style.display = 'none';
                        hidden++;
                    }
                });
            });
            return hidden;
        } catch (e) {
            // Cross-origin block (không xảy ra hiện tại, nhưng safe fallback)
            return -1;
        }
    }
    
    // Run ngay khi script load
    hideAll();
    
    // Retry vài lần vì Streamlit có thể render badge async sau load
    setTimeout(hideAll, 100);
    setTimeout(hideAll, 500);
    setTimeout(hideAll, 1500);
    
    // MutationObserver — watch top DOM, re-hide nếu Streamlit re-render badge
    // (vd sau khi user navigate giữa các page, hoặc sau st.rerun massive)
    try {
        const doc = window.top.document;
        if (doc && doc.body) {
            const observer = new MutationObserver(() => {
                hideAll();
            });
            observer.observe(doc.body, {
                childList: true,
                subtree: true
            });
        }
    } catch (e) {
        // Same-Origin block — bỏ qua observer, vẫn còn setTimeout retry
    }
})();
</script>
"""


def hide_streamlit_branding():
    """
    Ẩn badge "Hosted with Streamlit" + profile container ở top frame.
    
    Gọi 1 lần ngay sau st.set_page_config() trong app.py.
    
    Workaround tạm thời, có thể break khi Streamlit Cloud update.
    """
    # height=0, width=0 để component không chiếm chỗ visible
    components.html(_JS_HIDE_BADGE, height=0, width=0)
