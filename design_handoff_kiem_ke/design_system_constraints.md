TARGET PLATFORM: Streamlit ≥1.33, deploy qua Streamlit Cloud.

CONSTRAINTS BẮT BUỘC (không phải HTML thường — học từ 3 vòng debug trước):

1. CSS isolation: st.html() KHÔNG cho global <style> vươn vào content. 
   → Mọi style cho element trong st.html() PHẢI là inline style="..." 
   trên chính element đó, không dùng class.

2. DOM wrapping: Không thể dùng pattern hh_html('<div class="X">') + 
   st.columns() + hh_html('</div>') để bao widget — Streamlit tạo DOM 
   block độc lập cho mỗi call. 
   → Frame/border quanh widget phải dùng st.container(border=True), 
   không phải CSS custom.

3. CSS file (static/*.css) chỉ apply được cho:
   - Streamlit native widgets qua selector [data-testid="..."]
   - Font imports (@import url)
   - Streamlit dataframe styling
   KHÔNG apply được cho HTML do st.html() render.

4. Sanitizer (st.markdown unsafe_allow_html) strip class attribute. 
   → Dùng st.html() thay st.markdown cho custom HTML, NHƯNG xem 
   constraint #1.

DELIVERABLE FORMAT: 
- Reference HTML prototype dùng inline styles cho component cần custom, 
  KHÔNG dùng class custom (chỉ class trên Streamlit data-testid override)
- Code Python helper render visual: build HTML với inline styles trên 
  từng element, gọi st.html() 1 lần
- CSS file chỉ chứa: design tokens (làm reference), Streamlit overrides, 
  font imports
- KHÔNG đưa pattern "wrap widget bằng div" trong implementation guide

WORKFLOW: Tôi không có local repo. Diagnostic test cần "streamlit run" 
KHÔNG feasible. Mọi verification phải qua: GitHub PR review hoặc 
Streamlit Cloud preview branch.
