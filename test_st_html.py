"""
test_st_html.py — Diagnostic for HANDOFF_FIX_hang_hoa_v3 section 3.1.

Hypothesis: st.html() has CSS isolation behavior — CSS from global <style>
in <head> does NOT reach content rendered via st.html().

Run:
    streamlit run test_st_html.py

Open in browser. Each test renders one block. Report whether the TEXT inside
each block is RED (the .test-from-head class would make it RED if global CSS
reaches it):

  - Test 1 (st.markdown + class): expected RED — st.markdown lets global CSS apply
  - Test 2 (st.html + class): expected NOT RED — confirms isolation hypothesis
  - Test 3 (st.html + inline style): always RED — inline styles bypass isolation

If Test 2 is RED → hypothesis WRONG, do NOT apply v3 inline-style refactor.
If Test 2 NOT RED and Test 3 RED → hypothesis correct, proceed with v3.
"""

import streamlit as st

st.set_page_config(layout="wide")

# ── Inject global CSS into <head> via st.html (same path as inject_hang_hoa_css)
st.html("""
<style>
.test-from-head {
  color: #e63946;
  font-size: 24px;
  font-weight: 700;
  padding: 12px;
  border: 2px solid #e63946;
  border-radius: 8px;
  margin: 8px 0;
}
</style>
""")

st.title("Diagnostic: st.html() CSS isolation")

st.write("---")
st.subheader("Test 1: st.markdown + class")
st.caption("Expected: text is RED with red border (global CSS reaches st.markdown)")
st.markdown(
    '<div class="test-from-head">MARKDOWN-RENDERED TEXT — should be RED</div>',
    unsafe_allow_html=True,
)

st.write("---")
st.subheader("Test 2: st.html + class (THE KEY TEST)")
st.caption("If NOT RED → confirms st.html isolation hypothesis (v3 is correct)")
st.caption("If RED → hypothesis WRONG, st.html does reach global CSS, STOP v3")
st.html('<div class="test-from-head">HTML-RENDERED TEXT — RED only if no isolation</div>')

st.write("---")
st.subheader("Test 3: st.html + INLINE style")
st.caption("Expected: always RED (inline styles bypass isolation)")
st.html(
    '<div style="color:#e63946;font-size:24px;font-weight:700;padding:12px;'
    'border:2px solid #e63946;border-radius:8px;margin:8px 0">'
    'INLINE-STYLED TEXT — always RED</div>'
)

st.write("---")
st.subheader("Diagnostic summary to report")
st.code("""
Streamlit version:  (run: python -c "import streamlit; print(streamlit.__version__)")
Test 1 (markdown + class):       RED / NOT RED
Test 2 (html + class):           RED / NOT RED   <-- key result
Test 3 (html + inline style):    RED / NOT RED
""", language="text")
