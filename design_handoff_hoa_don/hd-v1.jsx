// V1 — Dense Cockpit + Drawer
// Layout: Branch chip → Stats strip → Filter row → Dense table list
// Click row → opens drawer overlay on right (mocks st.dialog)
// Strengths: Maximum info per row, traditional table feel, native to Streamlit
// (st.dataframe still possible, or st.html() with one-row-per-line layout).

const { useState: useStateV1 } = React;

function VariationV1({ tweaks }) {
  const stats = TODAY_STATS;
  const [selMa, setSelMa] = useStateV1('AHD000162'); // mock pre-selected for screenshot
  const [statusTab, setStatusTab] = useStateV1('all');
  const [search, setSearch] = useStateV1('');

  const filtered = MOCK_INVOICES.filter(i => {
    if (statusTab === 'ok')     return i.status === 'Hoàn thành' && !i.loai;
    if (statusTab === 'cancel') return i.status === 'Đã hủy';
    if (statusTab === 'pdt')    return i.loai === 'Đổi/Trả';
    if (statusTab === 'apsc')   return i.loai === 'Sửa chữa';
    return true;
  });

  const sel = MOCK_INVOICES.find(i => i.ma === selMa);
  const density = tweaks.density || 'normal';
  const rowH = density === 'compact' ? 36 : density === 'dense' ? 44 : 50;

  return (
    <div className="stl-app" style={{position:'relative'}}>
      <BranchBar active={stats.branch} />

      <div className="between" style={{marginBottom:10}}>
        <h1 className="stl-h1" style={{margin:0}}>Hoá đơn · {stats.weekday} {stats.date}</h1>
        <div className="row" style={{gap:6}}>
          <span className="muted small">Cập nhật 14:25</span>
          <button className="st-btn ghost icon" title="Làm mới">↻</button>
        </div>
      </div>

      {tweaks.showStats && <StatsStrip stats={stats} />}

      <FilterRow
        search={search} onSearchChange={setSearch}
        statusTab={statusTab} onStatusTab={setStatusTab}
        counts={{all:11, ok:9, cancel:1, pdt:1, apsc:1}}
      />

      {/* Dense table */}
      <div className="st-container" style={{padding:0, overflow:'hidden'}}>
        <table className="invlist">
          <thead>
            <tr>
              <th style={{width:'12ch'}}>Mã / Loại</th>
              <th style={{width:'6ch'}}>Giờ</th>
              <th>Khách hàng</th>
              <th style={{width:'14ch'}}>Nhân viên</th>
              <th style={{width:'4ch', textAlign:'center'}}>SP</th>
              <th style={{width:'12ch'}}>PTTT</th>
              <th style={{width:'12ch', textAlign:'right'}}>Khách trả</th>
              <th style={{width:'14ch'}}>Trạng thái</th>
              <th style={{width:'5ch'}}></th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((inv, idx) => {
              const isSel = inv.ma === selMa;
              const itemsCount = inv.loai === 'Đổi/Trả'
                ? ((inv.items_tra||[]).length + (inv.items_moi||[]).length)
                : ((inv.items||[]).length);
              const total = inv.loai === 'Đổi/Trả' ? inv.chenh : inv.tra;
              return (
                <tr key={inv.ma} className={isSel?'sel':''} onClick={()=>setSelMa(inv.ma)}
                    style={{height:rowH}}>
                  <td>
                    <div className="twoline">
                      <span className="stl-mono" style={{fontWeight:600, color:'var(--hd-ink)', fontSize:12.5}}>{inv.ma}</span>
                      <span style={{display:'flex'}}>
                        <TypeBadge kenh={inv.kenh} loai={inv.loai} />
                      </span>
                    </div>
                  </td>
                  <td className="stl-mono muted">{shortTime(inv.tg)}</td>
                  <td><KhachCell khach={inv.khach} sdt={inv.sdt} repeat={inv.repeat} /></td>
                  <td><NvPill ten={inv.nv} /></td>
                  <td style={{textAlign:'center', fontFamily:'var(--hd-mono)', color:'var(--hd-ink-2)'}}>{itemsCount}</td>
                  <td><PayIcons pttt={inv.pttt} /></td>
                  <td className="num" style={{fontWeight:600, fontSize:13.5}}>
                    {inv.loai === 'Đổi/Trả' && (inv.chenh > 0
                      ? <span style={{color:'var(--hd-good)'}}>+{fmtMoney(inv.chenh)}</span>
                      : <span style={{color:'var(--hd-warn)'}}>{fmtMoney(inv.chenh)}</span>)}
                    {inv.loai !== 'Đổi/Trả' && (inv.status === 'Đã hủy'
                      ? <span className="muted" style={{textDecoration:'line-through'}}>{fmtMoney(inv.tong)}</span>
                      : fmtMoney(total))}
                  </td>
                  <td><StatusBadge status={inv.status} /></td>
                  <td style={{textAlign:'right', color:'var(--hd-ink-4)'}}>›</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="row" style={{marginTop:10, gap:10}}>
        <span className="muted small">↑ Click 1 dòng để xem chi tiết · Phím J/K để duyệt nhanh</span>
        <span className="grow"></span>
        <span className="muted small stl-mono">Tổng: 11 chứng từ · 5.300.000đ</span>
      </div>

      {/* Drawer */}
      {sel && (
        <div className="drawer scroll-y">
          <InvoiceDetail inv={sel} onClose={() => setSelMa(null)} />
        </div>
      )}
    </div>
  );
}

window.VariationV1 = VariationV1;
