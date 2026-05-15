// Main app — design canvas + tweaks panel, hosts the 3 variations
// in their respective artboards (1180 x 1500 each).

const { useState: useStateApp } = React;

function App() {
  const [t, setTweak] = useTweaks({
    showStats: false,          // user explicitly opted out — keep as opt-in tweak
    accent: '#e63946',         // brand accent override
  });

  // apply accent live
  React.useEffect(() => {
    document.documentElement.style.setProperty('--hd-accent', t.accent);
  }, [t.accent]);

  return (
    <>
      <DesignCanvas>
        <DCSection id="redesign"
          title="hoa_don.py — Master-Detail Rail (chốt)"
          subtitle="Bỏ Stats strip · thêm khối Phiếu sửa chữa liên đới cho APSC. Click 1 dòng để xem chi tiết rail phải.">
          <DCArtboard id="v2" label="V2 · Master-Detail Rail" width={1180} height={1600}>
            <VariationV2 tweaks={t} />
          </DCArtboard>
          <DCArtboard id="v1-ref" label="V1 · Dense Cockpit (tham khảo)" width={1180} height={1500}>
            <VariationV1 tweaks={t} />
          </DCArtboard>
          <DCArtboard id="v3-ref" label="V3 · Day Timeline (tham khảo)" width={1180} height={1700}>
            <VariationV3 tweaks={t} />
          </DCArtboard>
        </DCSection>
      </DesignCanvas>

      <TweaksPanel title="Tweaks">
        <TweakSection label="Hiển thị">
          <TweakToggle label="Stats strip (KPI hôm nay)"
            value={t.showStats} onChange={v => setTweak('showStats', v)} />
        </TweakSection>

        <TweakSection label="Màu accent">
          <TweakColor label="Brand" value={t.accent}
            options={['#e63946','#2563eb','#1a7f37','#7c3aed']}
            onChange={v => setTweak('accent', v)} />
        </TweakSection>
      </TweaksPanel>
    </>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
