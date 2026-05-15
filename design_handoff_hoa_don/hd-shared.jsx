// Shared visual primitives for all 3 variations.
// Each component uses inline styles when it represents pure-HTML output
// (st.html), and stylesheet classes when it represents native Streamlit
// widgets (st.text_input, st.button, etc.) so the mock honors
// STREAMLIT_DESIGN_RULES.md constraint #1 (no global CSS into st.html).
//
// Schema note: inv.psc is a single object (or null) — quan hệ 1:1
// qua hoa_don."Mã YCSC" → phieu_sua_chua.ma_phieu.

const { useState } = React;

// ───────────────────────────────────────────────────────────────
// Status / type badges — pure HTML in production, inline styles.
// ───────────────────────────────────────────────────────────────
function StatusBadge({ status }) {
  if (status === 'Hoàn thành')
    return <span className="badge badge--ok">● Hoàn thành</span>;
  if (status === 'Đã hủy')
    return <span className="badge badge--cancel">✕ Đã hủy</span>;
  if (status === 'Nợ')
    return <span className="badge badge--debt">⏱ Nợ</span>;
  return <span className="badge">—</span>;
}

function TypeBadge({ kenh, loai }) {
  if (loai === 'Đổi/Trả') return <span className="badge badge--return">↔ Đổi/Trả</span>;
  if (loai === 'Sửa chữa') return <span className="badge badge--repair">🔧 Sửa chữa</span>;
  if (kenh === 'POS')      return <span className="badge badge--pos">🛒 POS</span>;
  return <span className="badge" style={{background:'#f3f3f5',color:'#71717a'}}>KiotViet</span>;
}

// Payment icon row — only show methods > 0
function PayIcons({ pttt }) {
  if (!pttt) return null;
  const out = [];
  if (pttt.tm  > 0) out.push(<span key="tm"  className="pay pay--cash" title="Tiền mặt">đ</span>);
  if (pttt.ck  > 0) out.push(<span key="ck"  className="pay pay--ck"   title="Chuyển khoản">CK</span>);
  if (pttt.the > 0) out.push(<span key="the" className="pay pay--card" title="Thẻ">T</span>);
  if (pttt.vi  > 0) out.push(<span key="vi"  className="pay pay--vi"   title="Ví">V</span>);
  if (out.length === 0) return <span className="dim small">—</span>;
  return <span className="row" style={{gap:4}}>{out}</span>;
}

// NV bán "avatar pill"
function NvPill({ ten }) {
  const initials = (ten||'').split(' ').slice(-2).map(s => s[0]||'').join('').toUpperCase().slice(0,2);
  const hash = (ten||'').split('').reduce((a,c)=>a + c.charCodeAt(0), 0);
  const cls = `av av--${(hash % 5) + 1}`;
  return (
    <span className="nv">
      <span className={cls}>{initials || '?'}</span>
      <span>{ten || '—'}</span>
    </span>
  );
}

// Small KH cell — name + phone (or "Khách lẻ" muted)
function KhachCell({ khach, sdt, repeat }) {
  const isWalk = (!khach || khach === 'Khách lẻ') && !sdt;
  return (
    <div className="twoline">
      <span className="name" style={{display:'flex',alignItems:'center',gap:6}}>
        {isWalk ? <span style={{color:'#a1a1aa'}}>Khách lẻ</span> : khach}
        {repeat && (
          <span title="Khách quay lại"
            style={{fontSize:10, padding:'1px 6px', borderRadius:999,
                    background:'#fff4d6', color:'#8a6d00', fontWeight:600, letterSpacing:'.2px'}}>
            ↻
          </span>
        )}
      </span>
      {sdt && <span className="secondary stl-mono">{sdt}</span>}
    </div>
  );
}

// ───────────────────────────────────────────────────────────────
// Branch chip strip — mocks st.selectbox at top
// ───────────────────────────────────────────────────────────────
function BranchBar({ active, branches = ['100 Lê Quý Đôn', 'Cửa hàng số 2', 'Kho trung tâm'] }) {
  return (
    <div className="row" style={{marginBottom:10}}>
      <span className="muted small" style={{marginRight:4}}>📍</span>
      <div className="row" style={{gap:6}}>
        {branches.map(b => (
          <span key={b} className={`chip brand ${b===active?'active':''}`}>{b}</span>
        ))}
        <span className="chip">Tất cả</span>
      </div>
    </div>
  );
}

// ───────────────────────────────────────────────────────────────
// Stats strip — pure HTML cards via st.html()
// Compact and full variants
// ───────────────────────────────────────────────────────────────
function StatsStrip({ stats, compact = false }) {
  const cashPct = Math.round(stats.pay_split.tm * 100);
  const ckPct   = Math.round(stats.pay_split.ck * 100);
  const thePct  = Math.round(stats.pay_split.the * 100);
  const viPct   = Math.round(stats.pay_split.vi * 100);

  return (
    <div style={{
      display:'grid',
      gridTemplateColumns:'1.4fr 1fr 1fr 1.6fr',
      gap:10, marginBottom:12,
    }}>
      <div className="metric">
        <div className="lbl">Doanh thu hôm nay</div>
        <div className="val">{fmtMoney(stats.total_revenue)}</div>
        <div className="sub">
          <span className={stats.vs_yesterday_pct >= 0 ? 'delta--up' : 'delta--down'}>
            {stats.vs_yesterday_pct >= 0 ? '▲' : '▼'} {Math.abs(stats.vs_yesterday_pct)}%
          </span>
          <span>so hôm qua · {fmtMoney(stats.vs_yesterday_amount)}</span>
        </div>
      </div>

      <div className="metric">
        <div className="lbl">Số hoá đơn</div>
        <div className="val">{stats.count}</div>
        <div className="sub">
          <span style={{color:'var(--hd-good)'}}>● {stats.count_ok}</span>
          <span style={{color:'var(--hd-warn)'}}>✕ {stats.count_cancel}</span>
          <span style={{color:'var(--hd-purple)'}}>↔ {stats.count_pdt}</span>
          <span style={{color:'var(--hd-amber)'}}>🔧 {stats.count_apsc}</span>
        </div>
      </div>

      <div className="metric">
        <div className="lbl">TB/HĐ</div>
        <div className="val">{fmtMoneyShort(stats.avg_per)}</div>
        <div className="sub muted">Mỗi hoá đơn</div>
      </div>

      <div className="metric">
        <div className="lbl">PT thanh toán</div>
        {/* stacked bar */}
        <div style={{display:'flex', height:10, borderRadius:5, overflow:'hidden', marginTop:6, background:'#eee'}}>
          <span style={{width:cashPct+'%', background:'#1a7f37'}}></span>
          <span style={{width:ckPct+'%',   background:'#2563eb'}}></span>
          <span style={{width:thePct+'%',  background:'#b45309'}}></span>
          <span style={{width:viPct+'%',   background:'#7c3aed'}}></span>
        </div>
        <div className="sub" style={{gap:10, fontSize:11.5}}>
          <span><span className="dot" style={{background:'#1a7f37',marginRight:4}}></span>Tiền mặt {cashPct}%</span>
          <span><span className="dot" style={{background:'#2563eb',marginRight:4}}></span>CK {ckPct}%</span>
          {thePct>0 && <span><span className="dot" style={{background:'#b45309',marginRight:4}}></span>Thẻ {thePct}%</span>}
          {viPct>0  && <span><span className="dot" style={{background:'#7c3aed',marginRight:4}}></span>Ví {viPct}%</span>}
        </div>
      </div>
    </div>
  );
}

// ───────────────────────────────────────────────────────────────
// Filter row — search + date pill + chips + status segment
// In real Streamlit this is: st.container(border=True) wrapping
//  st.columns([3,1,1,1,1]) with text_input, popover, popover, popover, segmented
// ───────────────────────────────────────────────────────────────
function FilterRow({
  search='', onSearchChange=()=>{},
  date='Hôm nay · 15/05',
  nv='Tất cả NV', pttt='Tất cả PTTT', loai='Tất cả loại',
  statusTab='all', onStatusTab=()=>{},
  counts={all:11, ok:10, cancel:1, pdt:1, apsc:1, no:0},
}) {
  return (
    <div className="st-container" style={{padding:'10px 12px', marginBottom:12}}>
      {/* Row 1: smart search + date + 3 filter pickers */}
      <div className="row" style={{gap:8, marginBottom:8}}>
        <div className="st-input" style={{flex:1, minWidth:280}}>
          <span style={{color:'var(--hd-ink-3)'}}>🔍</span>
          <input value={search} onChange={e=>onSearchChange(e.target.value)}
                 placeholder="Tìm mã HĐ, số điện thoại, tên khách… (số→SĐT, chữ→tên)" />
          <span className="kbd">/</span>
        </div>
        <span className="st-select"><span className="lbl">📅</span>{date}<span className="caret">▾</span></span>
        <span className="st-select"><span className="lbl">NV:</span>{nv}<span className="caret">▾</span></span>
        <span className="st-select"><span className="lbl">PTTT:</span>{pttt}<span className="caret">▾</span></span>
        <span className="st-select"><span className="lbl">Loại:</span>{loai}<span className="caret">▾</span></span>
      </div>

      {/* Row 2: status segmented (replaces the 3 redundant sub-tabs) */}
      <div className="row between">
        <div className="seg">
          <button className={statusTab==='all'?'on':''}    onClick={()=>onStatusTab('all')}>
            Tất cả <span className="count">{counts.all}</span>
          </button>
          <button className={statusTab==='ok'?'on':''}     onClick={()=>onStatusTab('ok')}>
            <span className="dot" style={{background:'var(--hd-good)'}}></span> Hoàn thành <span className="count">{counts.ok}</span>
          </button>
          <button className={statusTab==='cancel'?'on':''} onClick={()=>onStatusTab('cancel')}>
            <span className="dot" style={{background:'var(--hd-warn)'}}></span> Đã hủy <span className="count">{counts.cancel}</span>
          </button>
          <button className={statusTab==='pdt'?'on':''}    onClick={()=>onStatusTab('pdt')}>
            <span className="dot" style={{background:'var(--hd-purple)'}}></span> Đổi/Trả <span className="count">{counts.pdt}</span>
          </button>
          <button className={statusTab==='apsc'?'on':''}   onClick={()=>onStatusTab('apsc')}>
            <span className="dot" style={{background:'var(--hd-amber)'}}></span> Sửa chữa <span className="count">{counts.apsc}</span>
          </button>
        </div>
        <div className="row" style={{gap:6}}>
          <span className="muted small">Sắp xếp:</span>
          <span className="chip active" style={{height:24, fontSize:12}}>Mới nhất ↓</span>
          <span className="st-btn ghost" style={{height:32}}>⬇ Xuất Excel</span>
        </div>
      </div>
    </div>
  );
}

// ───────────────────────────────────────────────────────────────
// Detail card body — full HD breakdown (used by drawer / rail)
// ───────────────────────────────────────────────────────────────
function InvoiceDetail({ inv, onClose }) {
  if (!inv) return null;
  const isPdt = inv.loai === 'Đổi/Trả';

  // PSC status badge color coding (1:1 — single object check)
  const pscStatusStyle = (tinhTrang) => {
    const tt = String(tinhTrang || '').toLowerCase();
    if (tt.includes('đã giao') || tt.includes('hoàn thành')) {
      return { background:'var(--hd-good-soft)', color:'var(--hd-good)', border:'1px solid #cce8d3' };
    }
    if (tt.includes('đang sửa') || tt.includes('chờ')) {
      return { background:'#ffffff', color:'var(--hd-amber)', border:'1px solid #f3d99c' };
    }
    if (tt.includes('hủy')) {
      return { background:'var(--hd-warn-soft)', color:'var(--hd-warn)', border:'1px solid #fbcfca' };
    }
    return { background:'var(--hd-surface-3)', color:'var(--hd-ink-3)', border:'1px solid var(--hd-border)' };
  };

  return (
    <div className="stack" style={{gap:14}}>
      {/* Header */}
      <div className="between" style={{alignItems:'flex-start'}}>
        <div>
          <div className="row" style={{gap:8, marginBottom:6}}>
            <TypeBadge kenh={inv.kenh} loai={inv.loai} />
            <StatusBadge status={inv.status} />
            {inv.repeat && <span className="badge" style={{background:'#fff4d6', color:'#8a6d00'}}>↻ Khách quay lại</span>}
          </div>
          <div style={{fontSize:18, fontWeight:600, letterSpacing:'-.2px', fontFamily:'var(--hd-mono)'}}>{inv.ma}</div>
          <div className="muted small" style={{marginTop:2}}>{inv.tg}</div>
        </div>
        {onClose && (
          <button className="st-btn icon ghost" onClick={onClose} title="Đóng">✕</button>
        )}
      </div>

      {/* Customer block */}
      <div className="st-container--flat" style={{padding:'10px 12px'}}>
        <div className="between">
          <div className="twoline">
            <span style={{fontWeight:600}}>{inv.khach || 'Khách lẻ'}</span>
            <span className="secondary stl-mono">{inv.sdt || '—'}</span>
          </div>
          <div className="row" style={{gap:6}}>
            <NvPill ten={inv.nv} />
          </div>
        </div>
      </div>

      {/* Totals */}
      {isPdt ? (
        <div style={{display:'grid', gridTemplateColumns:'1fr 1fr', gap:8}}>
          <div className="metric">
            <div className="lbl">{inv.chenh >= 0 ? 'Khách bù thêm' : 'Cửa hàng hoàn'}</div>
            <div className="val">{fmtMoney(Math.abs(inv.chenh))}</div>
          </div>
          <div className="metric">
            <div className="lbl">Phương thức</div>
            <div className="row" style={{gap:6, marginTop:6}}><PayIcons pttt={inv.pttt} /></div>
          </div>
        </div>
      ) : (
        <div style={{display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:8}}>
          <div className="metric">
            <div className="lbl">Tổng hàng</div>
            <div className="val" style={{fontSize:17}}>{fmtMoney(inv.tong)}</div>
          </div>
          <div className="metric">
            <div className="lbl">Giảm giá</div>
            <div className="val" style={{fontSize:17, color: inv.giam>0?'var(--hd-warn)':'inherit'}}>
              {fmtMoney(inv.giam||0)}
            </div>
          </div>
          <div className="metric">
            <div className="lbl">Khách đã trả</div>
            <div className="val" style={{fontSize:17, color:'var(--hd-accent)'}}>{fmtMoney(inv.tra)}</div>
          </div>
        </div>
      )}

      {/* Payment methods inline */}
      {!isPdt && (
        <div className="st-container--flat" style={{padding:'8px 12px'}}>
          <div className="row" style={{gap:8}}>
            <span className="muted small" style={{minWidth:90}}>Phương thức:</span>
            <PayIcons pttt={inv.pttt} />
            <span className="small stl-mono" style={{marginLeft:'auto'}}>
              {Object.entries(inv.pttt||{}).map(([k,v]) =>
                <span key={k} style={{marginLeft:8}}>{ {tm:'TM',ck:'CK',the:'Thẻ',vi:'Ví'}[k] }: {fmtMoneyShort(v)}</span>
              )}
            </span>
          </div>
        </div>
      )}

      {/* Linked phiếu sửa chữa (APSC ↔ PSC) — quan hệ 1:1, render single object */}
      {inv.loai === 'Sửa chữa' && inv.psc && (
        <div>
          <div className="row between" style={{marginBottom:6}}>
            <span style={{fontSize:12, fontWeight:600, color:'var(--hd-ink-3)', letterSpacing:'.4px', textTransform:'uppercase'}}>
              Phiếu sửa chữa liên đới
            </span>
          </div>
          <div style={{
            background:'var(--hd-amber-soft)',
            border:'1px solid #f3d99c',
            borderRadius:'var(--hd-radius-sm)',
            padding:'10px 12px',
          }}>
            <div className="between" style={{marginBottom:6, gap:8, flexWrap:'wrap'}}>
              <div className="row" style={{gap:8}}>
                <span style={{
                  fontFamily:'var(--hd-mono)', fontSize:13, fontWeight:600,
                  color:'var(--hd-amber)', letterSpacing:'-.1px',
                }}>🔧 {inv.psc.ma}</span>
                <span className="badge" style={pscStatusStyle(inv.psc.tinh_trang)}>
                  {inv.psc.tinh_trang}
                </span>
              </div>
              <button className="st-btn ghost" style={{height:24, fontSize:11.5, padding:'0 8px'}}
                title="Mở phiếu sửa chữa">Mở ↗</button>
            </div>
            <div style={{fontSize:12.5, color:'var(--hd-ink-2)', marginBottom:6}}>
              {inv.psc.san_pham}
            </div>
            <div className="row" style={{gap:14, fontSize:11.5, color:'var(--hd-ink-3)', flexWrap:'wrap'}}>
              <span>Nhận: <span className="stl-mono" style={{color:'var(--hd-ink-2)'}}>{inv.psc.ngay_nhan}</span></span>
              <span>Hẹn trả: <span className="stl-mono" style={{color:'var(--hd-ink-2)'}}>{inv.psc.ngay_tra}</span></span>
              <span>KTV: <span style={{color:'var(--hd-ink-2)'}}>{inv.psc.kt_vien}</span></span>
            </div>
          </div>
        </div>
      )}

      {/* Items table */}
      <div>
        <div className="row between" style={{marginBottom:6}}>
          <span style={{fontSize:12, fontWeight:600, color:'var(--hd-ink-3)', letterSpacing:'.4px', textTransform:'uppercase'}}>
            {isPdt ? 'Chi tiết đổi/trả' : inv.loai==='Sửa chữa' ? 'Dịch vụ sửa chữa' : 'Chi tiết hàng hoá'}
          </span>
          {!isPdt && <span className="muted small">{(inv.items||[]).length} {inv.loai==='Sửa chữa'?'dịch vụ':'mặt hàng'}</span>}
        </div>

        {isPdt ? (
          <div className="stack" style={{gap:8}}>
            <div className="st-container--flat" style={{padding:0, overflow:'hidden'}}>
              <div style={{padding:'6px 10px', background:'#fef0f0', fontSize:11.5, fontWeight:600, color:'var(--hd-warn)'}}>
                ← KHÁCH TRẢ LẠI
              </div>
              <ItemsTable items={inv.items_tra} />
            </div>
            <div className="st-container--flat" style={{padding:0, overflow:'hidden'}}>
              <div style={{padding:'6px 10px', background:'#e9f6ee', fontSize:11.5, fontWeight:600, color:'var(--hd-good)'}}>
                → KHÁCH MUA MỚI
              </div>
              <ItemsTable items={inv.items_moi} />
            </div>
          </div>
        ) : (
          <div className="st-container--flat" style={{padding:0, overflow:'hidden'}}>
            <ItemsTable items={inv.items} />
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="row" style={{gap:8}}>
        <button className="st-btn primary" style={{flex:1}}>🖨 In lại</button>
        <button className="st-btn" style={{flex:1}}>⎘ Sao chép</button>
        <button className="st-btn" title="Mở phiếu xuất kho gốc">⤴ Phiếu kho</button>
        <button className="st-btn icon" title="Thêm">⋯</button>
      </div>
    </div>
  );
}

function ItemsTable({ items = [] }) {
  if (!items.length) return <div className="muted small" style={{padding:10}}>—</div>;
  return (
    <table className="invlist" style={{fontSize:12.5}}>
      <thead>
        <tr>
          <th style={{width:'9ch'}}>Mã</th>
          <th>Tên hàng</th>
          <th style={{textAlign:'right', width:'5ch'}}>SL</th>
          <th style={{textAlign:'right', width:'10ch'}}>Đơn giá</th>
          <th style={{textAlign:'right', width:'10ch'}}>Thành tiền</th>
        </tr>
      </thead>
      <tbody>
        {items.map((it, i) => (
          <tr key={i}>
            <td className="code">{it.ma}</td>
            <td>{it.ten}</td>
            <td className="num">{it.sl}</td>
            <td className="num">{fmtMoneyShort(it.dg)}</td>
            <td className="num" style={{fontWeight:600}}>{fmtMoney(it.tt)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

Object.assign(window, {
  StatusBadge, TypeBadge, PayIcons, NvPill, KhachCell,
  BranchBar, StatsStrip, FilterRow,
  InvoiceDetail, ItemsTable,
});
