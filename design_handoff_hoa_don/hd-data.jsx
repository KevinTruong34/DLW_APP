// Mock data for hoa_don.py redesign
// Shape mirrors load_hoa_don_unified() columns from source_code.py
//
// Schema note: HĐ APSC link to phieu_sua_chua via "Mã YCSC" — 1:1 relationship.
// Each invoice.psc is a SINGLE OBJECT or null (NOT an array).

const MOCK_INVOICES = [
  {
    ma: 'AHD000165', kenh: 'POS', loai: '', tg: '15/05/2026 14:22:08',
    khach: 'Chị Mai', sdt: '0912334455', nv: 'Bích Phượng',
    status: 'Hoàn thành',
    tong: 480000, giam: 0, tra: 480000,
    pttt: { ck: 480000 },
    items: [
      { ma:'HH012', ten:'Túi quà tặng size L', sl:2, dg:120000, tt:240000 },
      { ma:'HH033', ten:'Hộp gỗ trầm hương', sl:1, dg:240000, tt:240000 },
    ],
  },
  {
    ma: 'AHD000164', kenh: 'POS', loai: '', tg: '15/05/2026 13:48:31',
    khach: 'Khách lẻ', sdt:'', nv: 'Ngọc Nguyên',
    status: 'Hoàn thành',
    tong: 95000, giam: 0, tra: 95000,
    pttt: { tm: 95000 },
    items: [
      { ma:'HH008', ten:'Nhang trầm khoanh nhỏ', sl:1, dg:95000, tt:95000 },
    ],
  },
  {
    ma: 'APSC000042', kenh: 'APSC', loai: 'Sửa chữa', tg: '15/05/2026 13:15:00',
    khach: 'Anh Tuấn', sdt:'0911223344', nv: 'Minh Tâm',
    status: 'Hoàn thành',
    tong: 350000, giam: 0, tra: 350000,
    pttt: { tm: 350000 },
    // Phiếu sửa chữa liên đới — quan hệ 1:1 qua "Mã YCSC".
    // inv.psc là 1 object duy nhất (không phải array).
    psc: {
      ma: 'PSC000128', ngay_nhan: '12/05/2026', ngay_tra: '15/05/2026',
      san_pham: 'Vòng trầm hương 14 ly', tinh_trang: 'Đã giao khách',
      kt_vien: 'Thụ An',
    },
    items: [
      { ma:'SC003', ten:'Đánh bóng vòng trầm', sl:1, dg:350000, tt:350000 },
    ],
  },
  {
    ma: 'AHDD000008', kenh: 'PDT', loai: 'Đổi/Trả', tg: '15/05/2026 12:55:12',
    khach: 'Chị Hồng', sdt:'0908123456', nv: 'Bích Phượng',
    status: 'Hoàn thành',
    chenh: 80000,
    pttt: { ck: 80000 },
    items_tra: [{ ma:'HH021', ten:'Vòng trầm 14 ly', sl:1, dg:520000, tt:520000 }],
    items_moi: [{ ma:'HH022', ten:'Vòng trầm 16 ly', sl:1, dg:600000, tt:600000 }],
  },
  {
    ma: 'AHD000163', kenh: 'POS', loai: '', tg: '15/05/2026 11:42:01',
    khach: 'Khách lẻ', sdt:'', nv: 'Ngọc Nguyên',
    status: 'Hoàn thành',
    tong: 20000, giam: 0, tra: 20000,
    pttt: { tm: 20000 },
    items: [{ ma:'HH001', ten:'Túi giấy nhỏ', sl:1, dg:20000, tt:20000 }],
  },
  {
    ma: 'AHD000162', kenh: 'POS', loai: '', tg: '15/05/2026 11:10:44',
    khach: 'Cô Ly', sdt:'0399262535', nv: 'Bích Phượng',
    status: 'Hoàn thành',
    tong: 1250000, giam: 50000, tra: 1200000,
    pttt: { ck: 1200000 },
    items: [
      { ma:'HH041', ten:'Vòng đá phong thuỷ size M', sl:1, dg:850000, tt:850000 },
      { ma:'HH028', ten:'Mặt dây chuyền bạc', sl:1, dg:400000, tt:400000 },
    ],
    repeat: true,
  },
  {
    ma: 'AHD000161', kenh: 'POS', loai: '', tg: '15/05/2026 10:35:18',
    khach: 'Anh Khoa', sdt:'0903456789', nv: 'Ngọc Nguyên',
    status: 'Hoàn thành',
    tong: 450000, giam: 0, tra: 450000,
    pttt: { the: 450000 },
    items: [
      { ma:'HH015', ten:'Hộp đựng nhang', sl:1, dg:280000, tt:280000 },
      { ma:'HH009', ten:'Nhang trầm khoanh lớn', sl:1, dg:170000, tt:170000 },
    ],
  },
  {
    ma: 'AHD000160', kenh: 'POS', loai: '', tg: '15/05/2026 10:02:55',
    khach: 'Khách lẻ', sdt:'', nv: 'Minh Tâm',
    status: 'Đã hủy',
    tong: 80000, giam: 0, tra: 0,
    pttt: {},
    items: [{ ma:'HH002', ten:'Túi quà nhỡ', sl:1, dg:80000, tt:80000 }],
  },
  {
    ma: 'AHD000159', kenh: 'POS', loai: '', tg: '15/05/2026 09:48:30',
    khach: 'Chị Hà', sdt:'0987654321', nv: 'Bích Phượng',
    status: 'Hoàn thành',
    tong: 2100000, giam: 100000, tra: 2000000,
    pttt: { ck: 2000000 },
    items: [
      { ma:'HH055', ten:'Set quà tặng cao cấp', sl:1, dg:1800000, tt:1800000 },
      { ma:'HH033', ten:'Hộp gỗ trầm hương', sl:1, dg:300000, tt:300000 },
    ],
    repeat: true,
  },
  {
    ma: 'AHD000158', kenh: 'POS', loai: '', tg: '15/05/2026 09:22:12',
    khach: 'Khách lẻ', sdt:'', nv: 'Ngọc Nguyên',
    status: 'Hoàn thành',
    tong: 30000, giam: 0, tra: 30000,
    pttt: { tm: 30000 },
    items: [{ ma:'HH001', ten:'Túi giấy nhỏ', sl:1, dg:20000, tt:20000 },
            { ma:'HH004', ten:'Dây cột túi đỏ', sl:1, dg:10000, tt:10000 }],
  },
  {
    ma: 'AHD000157', kenh: 'POS', loai: '', tg: '15/05/2026 08:55:00',
    khach: 'Anh Phong', sdt:'0945123678', nv: 'Bích Phượng',
    status: 'Hoàn thành',
    tong: 180000, giam: 0, tra: 180000,
    pttt: { vi: 180000 },
    items: [{ ma:'HH011', ten:'Trầm xông phòng', sl:2, dg:90000, tt:180000 }],
  },
  {
    ma: 'AHD000156', kenh: 'POS', loai: '', tg: '15/05/2026 08:32:48',
    khach: 'Khách lẻ', sdt:'', nv: 'Minh Tâm',
    status: 'Hoàn thành',
    tong: 65000, giam: 0, tra: 65000,
    pttt: { tm: 65000 },
    items: [{ ma:'HH018', ten:'Vòng tay trầm mini', sl:1, dg:65000, tt:65000 }],
  },
  {
    ma: 'APSC000041', kenh: 'APSC', loai: 'Sửa chữa', tg: '14/05/2026 17:40:00',
    khach: 'Chị Vân', sdt:'0908667711', nv: 'Minh Tâm',
    status: 'Hoàn thành',
    tong: 280000, giam: 0, tra: 280000,
    pttt: { ck: 280000 },
    // 1:1 — chỉ 1 PSC duy nhất (đã chốt theo schema thực tế)
    psc: {
      ma: 'PSC000125', ngay_nhan: '08/05/2026', ngay_tra: '14/05/2026',
      san_pham: 'Nhẫn bạc đá gắn', tinh_trang: 'Đã giao khách',
      kt_vien: 'Thụ An',
    },
    items: [
      { ma:'SC005', ten:'Siết mấu + đánh bóng nhẫn', sl:1, dg:280000, tt:280000 },
    ],
  },
];

// Stats for today (mocked)
const TODAY_STATS = {
  date: '15/05/2026',
  weekday: 'Thứ Sáu',
  branch: '100 Lê Quý Đôn',
  total_revenue: 4960000,
  count: 11,
  count_ok: 10,
  count_cancel: 1,
  count_pdt: 1,
  count_apsc: 2,
  avg_per: 496000,
  pay_split: { tm: 0.30, ck: 0.55, the: 0.10, vi: 0.05 },
  vs_yesterday_pct: 12.4,        // +12.4%
  vs_yesterday_amount: 580000,
  vs_lastweek_pct: -3.2,
  // hourly distribution 8..18
  hourly: [
    {h: '08', count:2, rev: 245000},
    {h: '09', count:1, rev: 2000000},
    {h: '10', count:2, rev: 450000},
    {h: '11', count:2, rev: 1220000},
    {h: '12', count:1, rev: 80000},
    {h: '13', count:2, rev: 445000},
    {h: '14', count:1, rev: 480000},
    {h: '15', count:0, rev: 0},
    {h: '16', count:0, rev: 0},
    {h: '17', count:0, rev: 0},
    {h: '18', count:0, rev: 0},
  ],
  top_nv: [
    {ten:'Bích Phượng', count:5, rev:3760000},
    {ten:'Ngọc Nguyên', count:4, rev:565000},
    {ten:'Minh Tâm',     count:2, rev:480000},
  ],
};

// Friendly money formatter
function fmtMoney(n){
  if (n == null) return '—';
  const s = Math.abs(Math.round(n)).toLocaleString('vi-VN');
  return (n < 0 ? '-' : '') + s + 'đ';
}
function fmtMoneyShort(n){
  if (n == null) return '—';
  if (Math.abs(n) >= 1000000) return (n/1000000).toFixed(n%1000000===0?0:1).replace('.0','') + 'tr';
  if (Math.abs(n) >= 1000)    return Math.round(n/1000) + 'k';
  return Math.round(n).toString();
}
function fmtMoneyVi(n){ return fmtMoney(n); }
function shortTime(tg){ // "15/05/2026 11:42:01" → "11:42"
  const m = String(tg||'').match(/\d{2}:\d{2}/);
  return m ? m[0] : '';
}
function dateOf(tg){ // "15/05/2026 11:42:01" → "15/05"
  const m = String(tg||'').match(/(\d{2})\/(\d{2})/);
  return m ? `${m[1]}/${m[2]}` : '';
}

Object.assign(window, { MOCK_INVOICES, TODAY_STATS, fmtMoney, fmtMoneyShort, fmtMoneyVi, shortTime, dateOf });
