/* Hàng hóa — UI redesign main app */
const { useState, useMemo, useEffect, useRef } = React;
const { BRANCHES, GROUPS, PRODUCTS } = window.HH_DATA;

const SORTS = [
{ id: 'name-asc', label: 'Tên A → Z', fn: (a, b) => a.ten_hang.localeCompare(b.ten_hang) },
{ id: 'price-desc', label: 'Giá cao → thấp', fn: (a, b) => b.gia_ban - a.gia_ban },
{ id: 'price-asc', label: 'Giá thấp → cao', fn: (a, b) => a.gia_ban - b.gia_ban },
{ id: 'code-asc', label: 'Mã hàng A → Z', fn: (a, b) => a.ma_hang.localeCompare(b.ma_hang) }];


const fmtVND = (n) => n.toLocaleString('vi-VN');

function useOutsideClick(ref, onClose, enabled) {
  useEffect(() => {
    if (!enabled) return;
    const handler = (e) => {if (ref.current && !ref.current.contains(e.target)) onClose();};
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [enabled]);
}

// ───────────────────────────────────────────────────────── Header
function Header({ totalSku, branchId, setBranchId, onAdd }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useOutsideClick(ref, () => setOpen(false), open);
  const cur = BRANCHES.find((b) => b.id === branchId);
  return (
    <div className="hdr">
      <div className="title">Hàng hóa</div>
      <div className="sub">{PRODUCTS.length.toLocaleString('vi-VN')} SKU · 3 chi nhánh</div>
      <div className="spacer"></div>
      <div className="actions">
        <div className="popover-anchor" ref={ref}>
          <button className="btn" onClick={() => setOpen((v) => !v)}>
            <span className="dot"></span> {cur.name} <span className="caret">⌄</span>
          </button>
          {open &&
          <div className="menu" style={{ top: 36, right: 0 }}>
              {BRANCHES.map((b) =>
            <div key={b.id}
            className={'item ' + (b.id === branchId ? 'active' : '')}
            onClick={() => {setBranchId(b.id);setOpen(false);}}>
                  <span className="check">✓</span>
                  <span className="dot" style={{ background: b.id === branchId ? 'var(--good)' : 'var(--muted-2)' }}></span>
                  {b.name}
                </div>
            )}
              <div className="sep"></div>
              <div className="item" style={{ color: 'var(--muted)' }}>
                <span className="check"></span>Xem tất cả chi nhánh
              </div>
            </div>
          }
        </div>
        <button className="btn btn-icon" title="Tải lại">↻</button>
        <button className="btn btn-primary" onClick={onAdd}>+ Thêm hàng hóa</button>
      </div>
    </div>);

}

// ───────────────────────────────────────────────────────── Search / Filter
function SearchAndFilter({
  keyword, setKeyword,
  group, setGroup,
  sort, setSort
}) {
  const [sortOpen, setSortOpen] = useState(false);
  const sortRef = useRef(null);
  useOutsideClick(sortRef, () => setSortOpen(false), sortOpen);
  const sortItem = SORTS.find((s) => s.id === sort);
  return (
    <>
      <div className="search-row">
        <div className="search-input">
          <span className="icon">🔍</span>
          <input
            placeholder="Tìm theo tên, mã hàng hoặc mã vạch…"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)} />
          
          {keyword &&
          <span className="icon" style={{ cursor: 'pointer' }} onClick={() => setKeyword('')}>✕</span>
          }
        </div>
        <div className="divider"></div>
        <button className="btn btn-icon" title="Quét mã vạch">⌷</button>
        <div className="divider"></div>
        <div className="popover-anchor" ref={sortRef}>
          <div className="sort" onClick={() => setSortOpen((v) => !v)}>
            <span className="key">Sắp xếp:</span> {sortItem.label} <span className="caret">⌄</span>
          </div>
          {sortOpen &&
          <div className="menu" style={{ top: 38, right: 0 }}>
              {SORTS.map((s) =>
            <div key={s.id}
            className={'item ' + (s.id === sort ? 'active' : '')}
            onClick={() => {setSort(s.id);setSortOpen(false);}}>
                  <span className="check">✓</span>{s.label}
                </div>
            )}
            </div>
          }
        </div>
      </div>

      <div className="pills">
        <div className={'pill ' + (group === null ? 'active' : '')} onClick={() => setGroup(null)}>
          Tất cả <span className="count">{PRODUCTS.length}</span>
        </div>
        {GROUPS.map((g) =>
        <div key={g.name}
        className={'pill ' + (group === g.name ? 'active' : '')}
        onClick={() => setGroup(group === g.name ? null : g.name)}>
            {g.name} <span className="count">{g.count}</span>
          </div>
        )}
        <div className="spacer"></div>
        <div className="pill ghost">⊞ Bộ lọc nâng cao</div>
      </div>
    </>);

}

// ───────────────────────────────────────────────────────── Branch inventory cards
function BranchCards({ tons, activeBranchId }) {
  const total = BRANCHES.reduce((s, b) => s + (tons[b.id] || 0), 0);
  const max = Math.max(1, ...BRANCHES.map((b) => tons[b.id] || 0));
  return (
    <div className="branch-grid">
      {BRANCHES.map((b) => {
        const n = tons[b.id] || 0;
        const pct = n / max * 100;
        const share = total ? Math.round(n / total * 100) : 0;
        const isActive = b.id === activeBranchId;
        return (
          <div key={b.id} className={'branch-card ' + (isActive ? 'active' : '')}>
            <div className="b-label">
              {isActive && <span className="b-pin"></span>}
              {b.name}
            </div>
            <div className="b-val">{n.toLocaleString('vi-VN')}</div>
            <div className="b-share">{share}% tổng tồn</div>
            <div className="b-bar"><div className="b-fill" style={{ width: pct + '%' }}></div></div>
          </div>);

      })}
    </div>);

}

// ───────────────────────────────────────────────────────── Single-product detail
function ProductDetail({ product, branchId, onClose }) {
  return (
    <div className="detail">
      <button className="close-btn" onClick={onClose} title="Bỏ chọn">✕</button>
      <div className="top">
        <div className="info">
          <div className="product-name">
            {product.ten_hang}
            <span className="code">{product.ma_hang}</span>
            {product.ma_vach && product.ma_vach !== product.ma_hang &&
            <span className="code dashed">{product.ma_vach}</span>
            }
          </div>
          <div className="meta">
            <span>{product.nhom}</span>
            {product.thuong_hieu && product.thuong_hieu !== '—' &&
            <><span className="sep">›</span><span>{product.thuong_hieu}</span></>
            }
            <span className="sep">·</span>
            <span>Giá bán <b>{fmtVND(product.gia_ban)} đ</b></span>
          </div>
        </div>
        <div className="actions">
          <button className="btn btn-icon" title="Sửa thông tin" style={{ borderWidth: "0.8px 0.8px 0.8px 0px" }}>✎</button>
          <button className="btn btn-icon" title="Chỉnh tồn kho">▣</button>
          <button className="btn btn-icon" title="Lịch sử">↺</button>
          <button className="btn btn-icon" title="Ẩn hàng hóa">⊘</button>
        </div>
      </div>
      <BranchCards tons={product.ton} activeBranchId={branchId} />
    </div>);

}

// ───────────────────────────────────────────────────────── Group detail (aggregate)
function GroupDetail({ group, products, branchId, onClear }) {
  const tons = useMemo(() => {
    const t = { lqd: 0, cvt: 0, gbr: 0 };
    products.forEach((p) => {t.lqd += p.ton.lqd;t.cvt += p.ton.cvt;t.gbr += p.ton.gbr;});
    return t;
  }, [products]);
  return (
    <div className="detail">
      <button className="close-btn" onClick={onClear} title="Bỏ lọc nhóm">✕</button>
      <div className="top">
        <div className="info">
          <div className="product-name">
            {group}
            <span className="code">{products.length} SKU</span>
          </div>
          <div className="meta">
            <span>Tồn kho theo chi nhánh</span>
            <span className="sep">·</span>
            <span>Cộng dồn toàn bộ SKU trong nhóm</span>
          </div>
        </div>
      </div>
      <BranchCards tons={tons} activeBranchId={branchId} />
    </div>);

}

// ───────────────────────────────────────────────────────── Table
function ProductTable({
  products, selectedMa, setSelectedMa,
  checked, toggleCheck, toggleAll, allChecked, someChecked,
  keyword, group, onClearKeyword, onClearGroup
}) {
  return (
    <div className="table-wrap">
      <div className="table-meta">
        <span><b>{products.length.toLocaleString('vi-VN')}</b> sản phẩm</span>
        {group &&
        <span className="filter-tag">
            Nhóm: {group}
            <span className="clear" onClick={onClearGroup}>✕</span>
          </span>
        }
        {keyword &&
        <span className="filter-tag">
            Từ khóa: "{keyword}"
            <span className="clear" onClick={onClearKeyword}>✕</span>
          </span>
        }
      </div>

      {products.length === 0 ?
      <div className="empty">Không tìm thấy hàng hóa phù hợp.</div> :

      <table className="products">
          <thead>
            <tr>
              <th className="cb-cell">
                <div
                className={'cb ' + (allChecked ? 'checked' : someChecked ? 'indeterminate' : '')}
                onClick={toggleAll}>
              </div>
              </th>
              <th>Sản phẩm</th>
              <th>Nhóm</th>
              <th>Mã hàng</th>
              <th>Mã vạch</th>
              <th className="num">Giá bán</th>
            </tr>
          </thead>
          <tbody>
            {products.map((p) => {
            const isSel = selectedMa === p.ma_hang;
            const isChk = checked.has(p.ma_hang);
            return (
              <tr key={p.ma_hang}
              className={(isSel ? 'selected ' : '') + (isChk ? 'checked' : '')}
              onClick={() => setSelectedMa(isSel ? null : p.ma_hang)}>
                  <td className="cb-cell" onClick={(e) => e.stopPropagation()}>
                    <div className={'cb ' + (isChk ? 'checked' : '')}
                  onClick={() => toggleCheck(p.ma_hang)}></div>
                  </td>
                  <td className="product-cell">
                    <span className="pname">{p.ten_hang}</span>
                    {p.thuong_hieu && p.thuong_hieu !== '—' &&
                  <span className="brand">{p.thuong_hieu}</span>
                  }
                  </td>
                  <td className="group-cell">{p.nhom}</td>
                  <td className="mono">{p.ma_hang}</td>
                  <td className="mono">{p.ma_vach}</td>
                  <td className="num price-cell">{fmtVND(p.gia_ban)}<span className="unit"> ₫</span></td>
                </tr>);

          })}
          </tbody>
        </table>
      }
    </div>);

}

// ───────────────────────────────────────────────────────── Print Barcode Modal
function PrintBarcodeModal({ items, onClose }) {
  const [qtys, setQtys] = useState(() => Object.fromEntries(items.map((i) => [i.ma_hang, 1])));
  const [symb, setSymb] = useState('code128');
  const total = items.reduce((s, i) => s + (qtys[i.ma_hang] || 0), 0);
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3>🏷️ In tem mã vạch</h3>
          <div className="x" onClick={onClose}>✕</div>
        </div>
        <div className="modal-body">
          <div style={{ display: 'flex', gap: 14, marginBottom: 14 }}>
            <div className="field" style={{ flex: 1, marginBottom: 0 }}>
              <label>Loại mã vạch</label>
              <select value={symb} onChange={(e) => setSymb(e.target.value)}>
                <option value="code128">Code 128 (mặc định)</option>
                <option value="code39">Code 39</option>
                <option value="ean13">EAN-13</option>
                <option value="qr">QR Code</option>
              </select>
            </div>
            <div className="field" style={{ flex: 1, marginBottom: 0 }}>
              <label>Khổ tem</label>
              <select>
                <option>40 × 25 mm (mặc định)</option>
                <option>50 × 30 mm</option>
                <option>60 × 40 mm</option>
              </select>
            </div>
          </div>
          <table className="print-list">
            <thead>
              <tr>
                <th>Mã hàng</th>
                <th>Tên</th>
                <th style={{ textAlign: 'right' }}>Giá</th>
                <th>Mã vạch</th>
                <th style={{ textAlign: 'right' }}>SL tem</th>
              </tr>
            </thead>
            <tbody>
              {items.map((it) =>
              <tr key={it.ma_hang}>
                  <td style={{ fontFamily: 'var(--mono)', fontSize: 12 }}>{it.ma_hang}</td>
                  <td>{it.ten_hang}</td>
                  <td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                    {fmtVND(it.gia_ban)}
                  </td>
                  <td style={{ fontFamily: 'var(--mono)', fontSize: 12 }}>{it.ma_vach}</td>
                  <td style={{ textAlign: 'right' }}>
                    <input
                    className="qty-input" type="number" min="0" max="999"
                    value={qtys[it.ma_hang]}
                    onChange={(e) => setQtys({ ...qtys, [it.ma_hang]: parseInt(e.target.value || 0) })} />
                  
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="modal-foot">
          <div className="total">
            Tổng số tem sẽ in: <b>{total}</b>
            {total > 500 && <span style={{ color: 'var(--accent)', marginLeft: 8 }}>⚠ số tem lớn, có thể chậm</span>}
          </div>
          <button className="btn" onClick={onClose}>Hủy</button>
          <button className="btn btn-accent" disabled={total === 0}>📂 Mở trang in</button>
        </div>
      </div>
    </div>);

}

// ───────────────────────────────────────────────────────── App
function App() {
  const [branchId, setBranchId] = useState('lqd');
  const [keyword, setKeyword] = useState('');
  const [group, setGroup] = useState(null);
  const [sort, setSort] = useState('name-asc');
  const [selectedMa, setSelectedMa] = useState(null);
  const [checked, setChecked] = useState(new Set());
  const [showPrint, setShowPrint] = useState(false);

  const filtered = useMemo(() => {
    const kw = keyword.trim().toLowerCase();
    let arr = PRODUCTS.filter((p) => {
      if (group && p.nhom !== group) return false;
      if (kw) {
        const hay = (p.ten_hang + ' ' + p.ma_hang + ' ' + p.ma_vach + ' ' + p.thuong_hieu).toLowerCase();
        if (!hay.includes(kw)) return false;
      }
      return true;
    });
    const sortFn = SORTS.find((s) => s.id === sort).fn;
    return [...arr].sort(sortFn);
  }, [keyword, group, sort]);

  // If selected product is filtered out, clear selection
  useEffect(() => {
    if (selectedMa && !filtered.some((p) => p.ma_hang === selectedMa)) {
      setSelectedMa(null);
    }
  }, [filtered, selectedMa]);

  const selectedProduct = selectedMa ? PRODUCTS.find((p) => p.ma_hang === selectedMa) : null;

  const toggleCheck = (ma) => {
    const next = new Set(checked);
    next.has(ma) ? next.delete(ma) : next.add(ma);
    setChecked(next);
  };
  const allInView = filtered.map((p) => p.ma_hang);
  const allChecked = allInView.length > 0 && allInView.every((m) => checked.has(m));
  const someChecked = !allChecked && allInView.some((m) => checked.has(m));
  const toggleAll = () => {
    if (allChecked) {
      const next = new Set(checked);
      allInView.forEach((m) => next.delete(m));
      setChecked(next);
    } else {
      setChecked(new Set([...checked, ...allInView]));
    }
  };

  const printItems = [...checked].map((ma) => PRODUCTS.find((p) => p.ma_hang === ma)).filter(Boolean);

  return (
    <div className="app">
      <Header totalSku={PRODUCTS.length} branchId={branchId} setBranchId={setBranchId}
      onAdd={() => alert('Mở popover thêm hàng hóa (giữ logic gốc)')} />

      <SearchAndFilter
        keyword={keyword} setKeyword={setKeyword}
        group={group} setGroup={setGroup}
        sort={sort} setSort={setSort} />
      

      {/* Detail panel — only when single product selected OR specific group filter active */}
      {selectedProduct &&
      <ProductDetail
        product={selectedProduct}
        branchId={branchId}
        onClose={() => setSelectedMa(null)} />

      }
      {!selectedProduct && group &&
      <GroupDetail
        group={group}
        products={filtered}
        branchId={branchId}
        onClear={() => setGroup(null)} />

      }

      <ProductTable
        products={filtered}
        selectedMa={selectedMa}
        setSelectedMa={setSelectedMa}
        checked={checked}
        toggleCheck={toggleCheck}
        toggleAll={toggleAll}
        allChecked={allChecked}
        someChecked={someChecked}
        keyword={keyword}
        group={group}
        onClearKeyword={() => setKeyword('')}
        onClearGroup={() => setGroup(null)} />
      

      <div className="table-foot" style={{ borderRadius: '0 0 10px 10px', marginTop: -1, border: '1px solid var(--border)', borderTop: 0 }}>
        <span className="hint">
          {checked.size === 0 ?
          'Tick các dòng cần in tem, hoặc click 1 dòng để xem chi tiết.' :
          <>Đã chọn <span className="selected-count">{checked.size} sản phẩm</span> để in tem.</>}
        </span>
        <button
          className="btn btn-accent"
          disabled={checked.size === 0}
          onClick={() => setShowPrint(true)}>
          🏷️ In tem mã vạch {checked.size > 0 && <span className="count-badge">{checked.size}</span>}
        </button>
      </div>

      {showPrint &&
      <PrintBarcodeModal items={printItems} onClose={() => setShowPrint(false)} />
      }
    </div>);

}

window.App = App;