// Mock data mirroring real schema from hang_hoa.py
const BRANCHES = [
  { id: 'lqd', name: 'Lê Quý Đôn', short: 'Lê Quý Đôn' },
  { id: 'cvt', name: 'Coop Vũng Tàu', short: 'Coop VT' },
  { id: 'gbr', name: 'GO Bà Rịa', short: 'GO Bà Rịa' },
];

const GROUPS = [
  { name: 'Đồng hồ đeo tay', count: 3245 },
  { name: 'Thời trang & Trang sức', count: 515 },
  { name: 'Đồng hồ treo tường', count: 217 },
  { name: 'Đồng hồ để bàn', count: 50 },
  { name: 'Pin', count: 38 },
  { name: 'Phụ tùng & Phụ kiện', count: 57 },
];

// Inventory by branch (simulated per row — driven by seeded RNG so it's stable)
function seedRand(seed) {
  let s = seed % 2147483647;
  return () => { s = (s * 16807) % 2147483647; return (s - 1) / 2147483646; };
}

const PRODUCTS = (() => {
  const list = [
    // ma_hang, ten_hang, nhom, thuong_hieu, gia, ma_vach
    ['PDH200','Pin 200','Pin','—',200000,'PDH200'],
    ['PDHKBH150','Pin 150 (không bảo hành)','Pin','—',150000,'PDHKBH150'],
    ['PDH50','Pin 50','Pin','—',50000,'PDH50'],
    ['MD100','Đồng hồ Model','Đồng hồ để bàn','—',100000,'MD100'],
    ['PDH150','Pin 150','Pin','—',150000,'PDH150'],
    ['MDHTTGA','Máy Trôi GASTAT','Phụ tùng & Phụ kiện','GASTAT',150000,'MDHTTGA'],
    ['PDH100','Pin 100','Pin','—',100000,'PDH100'],
    ['PDH10','Pin 10','Pin','—',10000,'PDH10'],
    ['DD20540','Dây da 20mm','Thời trang & Trang sức','—',540000,'DD20540'],
    ['DD18289','Dây da 18mm','Thời trang & Trang sức','—',289000,'DD18289'],
    ['DD20376','Dây da 20mm','Thời trang & Trang sức','—',376000,'DD20376'],
    ['DD12275','Dây da 12mm','Thời trang & Trang sức','—',275000,'DD12275'],
    ['DD22546','Dây da 22mm','Thời trang & Trang sức','—',546000,'DD22546'],
    ['DD16528','Dây da 16mm','Thời trang & Trang sức','—',528000,'DD16528'],
    ['DD18376','Dây da 18mm','Thời trang & Trang sức','—',376000,'DD18376'],
    ['OP2486LSK','Đồng hồ OP 2486 LSK','Đồng hồ đeo tay','Olym Pianus',2326000,'2486LSK'],
    ['OP990SK','Đồng hồ OP 990 SK','Đồng hồ đeo tay','Olym Pianus',4150000,'990SK'],
    ['CASIOEDIFICE','Casio Edifice EFR-526','Đồng hồ đeo tay','Casio',3890000,'EFR526'],
    ['CASIOGS','Casio G-Shock GA-2100','Đồng hồ đeo tay','Casio',2950000,'GA2100'],
    ['SEIKO5SRPD','Seiko 5 Sports SRPD','Đồng hồ đeo tay','Seiko',7250000,'SRPD55K1'],
    ['CITIZENNH','Citizen NH8350','Đồng hồ đeo tay','Citizen',4490000,'NH8350'],
    ['ORIENT3STAR','Orient 3 Star','Đồng hồ đeo tay','Orient',3650000,'RA-AB0024'],
    ['TISSOTPRX','Tissot PRX 40','Đồng hồ đeo tay','Tissot',16800000,'T1374071105100'],
    ['DHTT45','Đồng hồ treo 45cm','Đồng hồ treo tường','—',420000,'DHTT45'],
    ['DHTT60','Đồng hồ treo 60cm','Đồng hồ treo tường','—',680000,'DHTT60'],
    ['DHTT30','Đồng hồ treo 30cm','Đồng hồ treo tường','—',280000,'DHTT30'],
    ['DHDB22','Đồng hồ để bàn DB22','Đồng hồ để bàn','—',520000,'DHDB22'],
    ['DAYTHEP18','Dây thép 18mm','Thời trang & Trang sức','—',180000,'DAYTHEP18'],
    ['VONGTAYBAC','Vòng tay bạc','Thời trang & Trang sức','—',1250000,'VTB001'],
  ];
  const rng = seedRand(7);
  return list.map(([ma_hang, ten, nhom, th, gia, vach], i) => ({
    ma_hang, ten_hang: ten, nhom, thuong_hieu: th, gia_ban: gia, ma_vach: vach,
    ton: {
      lqd: Math.floor(rng() * 320),
      cvt: Math.floor(rng() * 180),
      gbr: Math.floor(rng() * 1100),
    },
  }));
})();

window.HH_DATA = { BRANCHES, GROUPS, PRODUCTS };
