"""
Reusable live barcode scanner component dùng html5-qrcode + st.components.v2.

Usage:
    from utils.scanner_component import live_scanner

    scan = live_scanner(key="my_unique_key")
    if scan and scan.get("code"):
        # process scan["code"], scan["type"], scan["ts"]

Adaptation: isolate_styles=False để html5-qrcode tìm được #reader qua
document.getElementById() (default True đẩy HTML vào ShadowRoot → fail).
"""
import streamlit as st


# HTML template — render scanner viewfinder + status text
_HTML = """
<div id="scanner-wrapper">
  <div id="reader" style="width:100%; max-width:480px; min-height:320px; margin:0 auto;"></div>
  <div id="status" style="text-align:center; padding:8px; font-family:sans-serif; font-size:14px; color:#666;">
    Khởi động camera...
  </div>
</div>
"""

# JS — Streamlit v2 component pattern (setTriggerValue → Python rerun)
_JS = """
export default function(component) {
  const { setTriggerValue, parentElement } = component;

  // Load html5-qrcode từ unpkg — hard-code version 2.3.8 (KHÔNG dùng @latest)
  const script = document.createElement('script');
  script.src = 'https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js';

  let scanner = null;
  let lastCode = null;
  let lastTime = 0;
  const COOLDOWN_MS = 1500;

  const statusEl = parentElement.querySelector('#status');

  script.onload = () => {
    try {
      scanner = new Html5Qrcode("reader", { verbose: false });

      const config = {
        fps: 10,
        qrbox: { width: 280, height: 100 },
        formatsToSupport: [
          Html5QrcodeSupportedFormats.CODE_128,
          Html5QrcodeSupportedFormats.CODE_39,
          Html5QrcodeSupportedFormats.EAN_13,
          Html5QrcodeSupportedFormats.EAN_8,
          Html5QrcodeSupportedFormats.QR_CODE,
        ],
        // useBarCodeDetectorIfSupported defaults true → BarcodeDetector API trên iOS Safari 17+
      };

      scanner.start(
        { facingMode: "environment" },
        config,
        (decodedText, decodedResult) => {
          // Cooldown — tránh duplicate scan cùng tem
          const now = Date.now();
          if (decodedText === lastCode && (now - lastTime) < COOLDOWN_MS) {
            return;
          }
          lastCode = decodedText;
          lastTime = now;

          // Hiển thị nhanh trên UI
          if (statusEl) {
            statusEl.textContent = `✅ ${decodedText}`;
            statusEl.style.color = '#16a34a';
          }

          // Trigger Python rerun
          setTriggerValue('scan', {
            code: decodedText,
            type: decodedResult?.result?.format?.formatName || 'UNKNOWN',
            ts: now,
          });
        },
        (errorMessage) => {
          // Decode error per-frame (ignore, sẽ tự retry)
        }
      ).then(() => {
        if (statusEl) statusEl.textContent = 'Đang quét... chĩa camera vào tem mã vạch';
      }).catch((err) => {
        if (statusEl) {
          statusEl.textContent = `❌ Lỗi camera: ${err.message || err}`;
          statusEl.style.color = '#dc2626';
        }
      });
    } catch (e) {
      if (statusEl) {
        statusEl.textContent = `❌ Lỗi khởi tạo: ${e.message}`;
        statusEl.style.color = '#dc2626';
      }
    }
  };

  script.onerror = () => {
    if (statusEl) {
      statusEl.textContent = '❌ Không load được thư viện html5-qrcode (check internet)';
      statusEl.style.color = '#dc2626';
    }
  };

  document.head.appendChild(script);

  // Cleanup khi component unmount
  return () => {
    if (scanner) {
      scanner.stop().catch(() => {});
    }
  };
}
"""

_CSS = """
#reader {
  min-height: 320px;
}
#reader video {
  width: 100% !important;
  height: auto !important;
  display: block !important;
  border-radius: 8px;
}
#reader img {
  display: none !important;  /* ẩn placeholder camera icon khi đang quét */
}
#reader__dashboard {
  background: #f3f4f6;
  padding: 8px;
  border-radius: 8px;
}
#reader__dashboard_section_csr button {
  background: #2563eb !important;
  color: white !important;
  border: none !important;
  padding: 6px 12px !important;
  border-radius: 6px !important;
}
"""


# Component factory — declare 1 lần, reusable qua mounting calls.
# isolate_styles=False: HTML mount vào main DOM (KHÔNG ShadowRoot) để
# html5-qrcode tìm được #reader qua document.getElementById().
_scanner_component = st.components.v2.component(
    "barcode_live_scanner_v2",
    html=_HTML,
    css=_CSS,
    js=_JS,
    isolate_styles=False,
)


def live_scanner(key: str):
    """
    Render live barcode scanner. Returns dict {code, type, ts} when scan
    succeeds, else None.

    Args:
        key: unique key per mount location (Phase 3 ban_hang vs Phase 4 doi_tra
             phải dùng key khác nhau để tránh component conflict).

    Returns:
        dict {"code": str, "type": str, "ts": int (ms)} hoặc None.
    """
    if not key:
        raise ValueError("key is required to avoid component conflict")

    result = _scanner_component(
        key=key,
        on_scan_change=lambda: None,
    )
    return getattr(result, "scan", None) if result else None
