// V2 — Master-Detail Rail (visual rhyme with hang_hoa.py redesign)
// Layout: branch + stats + filter row, then 60/40 columns.
// Left: compact list (rendered as st.html cards with row-button behaviour).
// Right: sticky detail rail.
// Strengths: consistent across modules, view chi tiết without losing the list,
// great for browsing many invoices in a session.
//
// Schema note: inv.psc is a single object (or null) — quan hệ 1:1
// qua hoa_don."Mã YCSC" → phieu_sua_chua.ma_phieu.

const { useState: useStateV2 } = React;

function VariationV2({ tweaks }) {
  const stats = TODAY_STATS;
  const [selMa, setSelMa] = useStateV2('APSC000041');
  const [statusTab, setStatusTab] = useStateV2('all');

  const filtered = MOCK_INVOICES.filter(i => {
    if (statusTab === 'ok')     return i.status === 'Hoàn thành' && !i.loai;
    if (statusTab === 'cancel') return i.status === 'Đã hủy';
    if (statusTab === 'pdt')    return i.loai === 'Đổi/Trả';
    if (statusTab === 'apsc')   return i.loai === 'Sửa chữa';
    return true;
  });
  const sel = MOCK_INVOICES.find(i => i.ma === selMa);

  return (
    <div className="stl-app">
      <BranchBar active={stats.branch} />

      <div className="between" style={{marginBottom:10}}>
        <h1 className="stl-h1" style={{margin:0}}>Hoá đơn · {stats.weekday} {stats.date}</h1>
        <span className="muted small">{filtered.length} chứng từ</span>
      </div>

      {tweaks.showStats && <StatsStrip stats={stats} />}

      <FilterRow
        statusTab={statusTab} onStatusTab={setStatusTab}
        counts={{all:13, ok:9, cancel:1, pdt:1, apsc:2}}
      />

      {/* Master-detail grid */}
      <div style={{display:'grid', gridTemplateColumns:'minmax(0,1.4fr) minmax(0,1fr)', gap:14, alignItems:'flex-start'}}>
        {/* Left: list */}
        <div className="stack" style={{gap:6}}>
          {filtered.map(inv => {
            const isSel = inv.ma === selMa;
            const total = inv.loai === 'Đổi/Trả' ? inv.chenh : inv.tra;
            const itemsCount = inv.loai === 'Đổi/Trả'
              ? ((inv.items_tra||[]).length + (inv.items_moi||[]).length)
              : ((inv.items||[]).length);
            return (
              <div key={inv.ma} onClick={()=>setSelMa(inv.ma)} style={{
                background: isSel ? 'var(--hd-accent-soft)' : 'var(--hd-surface)',
                border: '1px solid ' + (isSel ? '#f6c3c7' : 'var(--hd-border)'),
                borderRadius: 'var(--hd-radius)',
                padding: '10px 12px',
                cursor: 'pointer',
                boxShadow: isSel ? 'inset 3px 0 0 var(--hd-accent)' : 'var(--hd-shadow-sm)',
                transition: 'background .1s, border-color .1s',
              }}>
                {/* Row 1: code · time · status */}
                <div className="between" style={{marginBottom:6}}>
                  <div className="row" style={{gap:8}}>
                    <span className="stl-mono" style={{fontWeight:600, fontSize:13}}>{inv.ma}</span>
                    <span className="muted small stl-mono">{shortTime(inv.tg)}</span>
                    <TypeBadge kenh={inv.kenh} loai={inv.loai} />
                    {/* PSC badge — 1:1 relationship, no count needed */}
                    {inv.loai === 'Sửa chữa' && inv.psc && (
                      <span className="badge" style={{
                        background:'#fff', border:'1px solid #f3d99c',
                        color:'var(--hd-amber)', fontWeight:500,
                      }}>🔗 PSC</span>
                    )}
                  </div>
                  <StatusBadge status={inv.status} />
                </div>
                {/* Row 2: customer + nv + total */}
                <div className="between" style={{gap:10}}>
                  <div className="row" style={{gap:10, minWidth:0, flex:1}}>
                    <KhachCell khach={inv.khach} sdt={inv.sdt} repeat={inv.repeat} />
                  </div>
                  <div className="row" style={{gap:10}}>
                    <NvPill ten={inv.nv} />
                    <span className="muted small stl-mono">{itemsCount} SP</span>
                    <PayIcons pttt={inv.pttt} />
                    <span className="stl-mono" style={{fontWeight:600, fontSize:13.5, minWidth:'10ch', textAlign:'right'}}>
                      {inv.loai === 'Đổi/Trả'
                        ? (inv.chenh > 0
                            ? <span style={{color:'var(--hd-good)'}}>+{fmtMoneyShort(inv.chenh)}</span>
                            : <span style={{color:'var(--hd-warn)'}}>{fmtMoneyShort(inv.chenh)}</span>)
                        : (inv.status === 'Đã hủy'
                            ? <span className="muted" style={{textDecoration:'line-through'}}>{fmtMoney(inv.tong)}</span>
                            : fmtMoney(total))
                      }
                    </span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Right: detail rail (sticky in real Streamlit via CSS on column) */}
        <div className="st-container" style={{padding:14, position:'sticky', top:0}}>
          {sel
            ? <InvoiceDetail inv={sel} onClose={()=>setSelMa(null)} />
            : <EmptyRail />}
        </div>
      </div>
    </div>
  );
}

function EmptyRail() {
  return (
    <div style={{padding:'40px 10px', textAlign:'center'}}>
      <div style={{
        width:54, height:54, borderRadius:14,
        background:'var(--hd-surface-2)', border:'1px dashed var(--hd-border-2)',
        display:'inline-grid', placeItems:'center', marginBottom:12,
        fontSize:20, color:'var(--hd-ink-4)'
      }}>📄</div>
      <div style={{fontWeight:600, marginBottom:4}}>Chưa chọn hoá đơn</div>
      <div className="muted small" style={{lineHeight:1.5}}>
        Click 1 dòng bên trái để xem<br/>chi tiết hàng hoá, PTTT, thao tác.
      </div>
    </div>
  );
}

window.VariationV2 = VariationV2;
