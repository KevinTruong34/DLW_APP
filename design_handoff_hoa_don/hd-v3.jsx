// V3 — Day Timeline (group theo giờ)
// Layout: stats strip + filter row, then a vertical timeline.
// Invoices grouped by hour bucket. Each bucket header shows hour stats.
// Items list shown inline inside each invoice card as compact pill row.
// Strengths: tells the "story of the day", less clicking, friendly rhythm,
// great for end-of-shift review.

const { useState: useStateV3 } = React;

function VariationV3({ tweaks }) {
  const stats = TODAY_STATS;
  const [statusTab, setStatusTab] = useStateV3('all');
  const [expanded, setExpanded] = useStateV3({ 'AHD000162': true });

  // group invoices by hour
  const byHour = {};
  MOCK_INVOICES.forEach(inv => {
    const h = shortTime(inv.tg).slice(0,2);
    if (!byHour[h]) byHour[h] = { hour: h, list: [], revenue: 0 };
    byHour[h].list.push(inv);
    if (inv.status === 'Hoàn thành')
      byHour[h].revenue += (inv.loai === 'Đổi/Trả' ? (inv.chenh||0) : (inv.tra||0));
  });
  const hours = Object.values(byHour).sort((a,b) => b.hour.localeCompare(a.hour));
  const maxRev = Math.max(...hours.map(h => h.revenue), 1);

  return (
    <div className="stl-app">
      <BranchBar active={stats.branch} />

      <div className="between" style={{marginBottom:10}}>
        <h1 className="stl-h1" style={{margin:0}}>Hoá đơn · {stats.weekday} {stats.date}</h1>
        <span className="muted small">{stats.count} chứng từ · {fmtMoney(stats.total_revenue)}</span>
      </div>

      {tweaks.showStats && <StatsStrip stats={stats} />}

      {/* Top NV strip — only in V3 to differentiate */}
      <div className="st-container" style={{padding:'10px 12px', marginBottom:10}}>
        <div className="row" style={{gap:14}}>
          <div className="row" style={{gap:6}}>
            <span style={{fontSize:11, fontWeight:600, color:'var(--hd-ink-3)', letterSpacing:'.4px', textTransform:'uppercase'}}>
              Top nhân viên
            </span>
          </div>
          {stats.top_nv.map((nv, i) => (
            <div key={nv.ten} className="row" style={{gap:6}}>
              <span style={{
                width:18, height:18, borderRadius:'50%',
                background: i===0?'#fef3c7':i===1?'#e7e7ea':'#f5e7dc',
                color: i===0?'#b45309':i===1?'#3f3f46':'#a8530b',
                display:'inline-grid', placeItems:'center',
                fontSize:10, fontWeight:700
              }}>{i+1}</span>
              <NvPill ten={nv.ten} />
              <span className="muted small stl-mono">{nv.count} HĐ · {fmtMoneyShort(nv.rev)}</span>
            </div>
          ))}
          <span className="grow"></span>
          <span className="st-btn ghost" style={{height:28, fontSize:12}}>Xem tất cả →</span>
        </div>
      </div>

      <FilterRow
        statusTab={statusTab} onStatusTab={setStatusTab}
        counts={{all:11, ok:9, cancel:1, pdt:1, apsc:1}}
      />

      {/* Timeline */}
      <div className="stack" style={{gap:14}}>
        {hours.map(bucket => (
          <div key={bucket.hour}>
            {/* Hour header */}
            <div className="row" style={{
              gap:10, marginBottom:8, alignItems:'baseline',
              borderBottom:'1px solid var(--hd-border)', paddingBottom:6,
            }}>
              <span className="stl-mono" style={{
                fontSize:18, fontWeight:600, color:'var(--hd-ink)',
                letterSpacing:'-.2px',
              }}>{bucket.hour}:00</span>
              <span className="muted small">·</span>
              <span className="small" style={{color:'var(--hd-ink-2)'}}>
                <b>{bucket.list.length}</b> hoá đơn
              </span>
              <span className="muted small">·</span>
              <span className="small stl-mono" style={{color:'var(--hd-ink)', fontWeight:600}}>
                {fmtMoney(bucket.revenue)}
              </span>
              {/* mini bar */}
              <div style={{
                flex:1, height:6, borderRadius:3,
                background:'var(--hd-surface-3)', marginLeft:14,
                overflow:'hidden', maxWidth:260,
              }}>
                <div style={{
                  width: (bucket.revenue/maxRev*100) + '%',
                  height:'100%', background:'var(--hd-accent)',
                  borderRadius:3,
                }}></div>
              </div>
              <span className="grow"></span>
            </div>

            {/* Invoices in bucket */}
            <div className="stack" style={{gap:6}}>
              {bucket.list.map(inv => (
                <TimelineCard key={inv.ma} inv={inv}
                  open={!!expanded[inv.ma]}
                  onToggle={() => setExpanded(s => ({...s, [inv.ma]: !s[inv.ma]}))} />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function TimelineCard({ inv, open, onToggle }) {
  const total = inv.loai === 'Đổi/Trả' ? inv.chenh : inv.tra;
  const itemsCount = inv.loai === 'Đổi/Trả'
    ? ((inv.items_tra||[]).length + (inv.items_moi||[]).length)
    : ((inv.items||[]).length);
  const items = inv.items || [...(inv.items_tra||[]), ...(inv.items_moi||[])];

  return (
    <div style={{
      background: inv.status==='Đã hủy' ? 'var(--hd-surface-2)' : 'var(--hd-surface)',
      border:'1px solid var(--hd-border)',
      borderRadius:'var(--hd-radius)',
      padding:'10px 12px',
      boxShadow:'var(--hd-shadow-sm)',
      opacity: inv.status==='Đã hủy' ? 0.85 : 1,
    }}>
      {/* Row 1 */}
      <div className="between" style={{gap:10}}>
        <div className="row" style={{gap:10, flex:1, minWidth:0}}>
          <button onClick={onToggle} style={{
            width:22, height:22, border:0, background:'transparent',
            cursor:'pointer', color:'var(--hd-ink-3)', fontSize:12,
            transform: open ? 'rotate(90deg)' : 'rotate(0)',
            transition:'transform .15s',
          }}>▶</button>
          <span className="stl-mono" style={{fontWeight:600, fontSize:13}}>{inv.ma}</span>
          <span className="muted small stl-mono">{shortTime(inv.tg)}</span>
          <TypeBadge kenh={inv.kenh} loai={inv.loai} />
          <span style={{minWidth:0, flex:1, overflow:'hidden'}}>
            <KhachCell khach={inv.khach} sdt={inv.sdt} repeat={inv.repeat} />
          </span>
        </div>
        <div className="row" style={{gap:10}}>
          <NvPill ten={inv.nv} />
          <PayIcons pttt={inv.pttt} />
          <span className="stl-mono" style={{fontWeight:600, fontSize:14, minWidth:'10ch', textAlign:'right'}}>
            {inv.loai === 'Đổi/Trả'
              ? (inv.chenh > 0
                  ? <span style={{color:'var(--hd-good)'}}>+{fmtMoney(inv.chenh)}</span>
                  : <span style={{color:'var(--hd-warn)'}}>{fmtMoney(inv.chenh)}</span>)
              : (inv.status === 'Đã hủy'
                  ? <span className="muted" style={{textDecoration:'line-through'}}>{fmtMoney(inv.tong)}</span>
                  : fmtMoney(total))
            }
          </span>
          <StatusBadge status={inv.status} />
        </div>
      </div>

      {/* Inline item pills (always-visible peek) */}
      {!open && items.length > 0 && (
        <div className="row wrap" style={{gap:6, marginTop:8, marginLeft:32, fontSize:12}}>
          <span className="muted small" style={{fontSize:11}}>{itemsCount} SP:</span>
          {items.slice(0,3).map((it, i) => (
            <span key={i} style={{
              background:'var(--hd-surface-2)', border:'1px solid var(--hd-border)',
              padding:'2px 8px', borderRadius:999, fontSize:11.5,
              color:'var(--hd-ink-2)',
            }}>
              {it.ten} {it.sl > 1 && <span className="stl-mono muted">×{it.sl}</span>}
            </span>
          ))}
          {items.length > 3 && (
            <span className="muted small">+{items.length-3} khác</span>
          )}
        </div>
      )}

      {/* Expanded */}
      {open && (
        <div style={{marginTop:10, marginLeft:32}}>
          {inv.loai === 'Đổi/Trả' ? (
            <div className="stack" style={{gap:8}}>
              {inv.items_tra?.length>0 && (
                <div className="st-container--flat" style={{padding:0, overflow:'hidden'}}>
                  <div style={{padding:'6px 10px', background:'#fef0f0', fontSize:11.5, fontWeight:600, color:'var(--hd-warn)'}}>
                    ← KHÁCH TRẢ LẠI
                  </div>
                  <ItemsTable items={inv.items_tra} />
                </div>
              )}
              {inv.items_moi?.length>0 && (
                <div className="st-container--flat" style={{padding:0, overflow:'hidden'}}>
                  <div style={{padding:'6px 10px', background:'#e9f6ee', fontSize:11.5, fontWeight:600, color:'var(--hd-good)'}}>
                    → KHÁCH MUA MỚI
                  </div>
                  <ItemsTable items={inv.items_moi} />
                </div>
              )}
            </div>
          ) : (
            <div className="st-container--flat" style={{padding:0, overflow:'hidden'}}>
              <ItemsTable items={inv.items} />
            </div>
          )}
          <div className="row" style={{gap:8, marginTop:10}}>
            <button className="st-btn">🖨 In lại</button>
            <button className="st-btn">⎘ Sao chép</button>
            <button className="st-btn ghost">⤴ Mở phiếu kho</button>
          </div>
        </div>
      )}
    </div>
  );
}

window.VariationV3 = VariationV3;
