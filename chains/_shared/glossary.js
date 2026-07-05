/* glossary.js —— 产业链研究各页共享：术语浮窗（点带虚线的词看大白话）。
   页面在 body 末尾 <script src=".../glossary.js"></script> 即可，自动注入样式 + 给全文加虚线 + 浮窗。 */
(function () {
  const GLOSSARY = {
    "斯特林发动机": "一种 1816 年发明的外燃机：靠外部加热让封闭气体（氦/氢）一冷一热地胀缩来做功。安静、能烧各种燃料，但功率密度低、密封难、成本高——所以两百年来当发电机反复商业失败，原理本身是公有领域、零专利壁垒。",
    "斯特林循环": "斯特林发动机背后的热力学循环：等温压缩→等容吸热→等温膨胀→等容放热。1816 年就公开了、谁都能用——价值不在这个循环本身，在把它做可靠的精密制造。",
    "斯特林制冷机": "把斯特林循环反过来跑：用电驱动、把冷指降到 40-150K 的机械式低温制冷机。是制冷型红外探测器降温的主流冷源之一——这是斯特林两百年真正赚到钱、有护城河的一面。",
    "制冷型红外": "把红外焦平面封进真空杜瓦、用制冷机降到约 77K 来压住热噪声的高灵敏红外探测器，主用于军用导引头/远距侦察。相对的『非制冷』便宜但灵敏度低，用于车载/安防。",
    "cryocooler": "低温制冷机的统称，把东西降到极低温。常见类型有斯特林、脉管、GM、JT——斯特林约占其中 32%（Mordor 2025）。",
    "脉管": "脉管制冷机——一种没有低温运动部件的制冷机，零振动、寿命更长，正在长寿命场景（空间载荷/MRI）蚕食斯特林制冷机的份额。",
    "MTTF": "平均无故障时间——设备平均能可靠运行多少小时才坏一次。制冷机的 MTTF 从早期约 4,000 小时做到军用 20,000-30,000 小时，是几十年攒出来的硬壁垒。",
    "自由活塞斯特林": "英文 FPSE——一种没有曲柄连杆、靠气体弹簧让活塞自由往复的斯特林机，结构简单、寿命长。空间核电转换器和高端制冷机都用它。",
    "AIP": "不依赖空气推进——让常规潜艇不上浮、不用通气管也能在水下航行数周的系统。斯特林发动机是其中一种成熟路线，但正被锂电池和燃料电池替代。",
    "布雷顿循环": "燃气轮机用的那种热力学循环（气体压缩→加热→膨胀做功）。空间核电的大功率堆 2025 年选了它、而不是斯特林——是斯特林在空间核电的主要竞争对手。",
    "RTG": "放射性同位素温差发电机——靠钚-238 衰变热用温差直接发电（无运动部件），是深空探测器的主力电源。效率只有约 6-7%，斯特林转换器理论上能到约 26%、但可靠性不如它。",
    "capex": "资本开支——公司为扩产花的大钱，比如买地、建厂、买设备。云厂的 capex 主要是买 AI 芯片和建数据中心。",
    "compute": "算力，也就是计算能力——衡量能跑多少 AI 运算。",
    "被定价": "好消息已经反映进股价了。一个好生意如果人人都知道好、股价已经涨上去，再买就赚不到便宜。",
    "认知差": "你对一家公司的判断和市场主流看法不一样、而且很可能是你对。价值投资真正赚大钱靠的就是这个差。",
    "variant perception": "认知差——你的判断和市场主流不一样、而且可能是你对。",
    "β 风险": "贝塔风险——不是某一家公司自己的问题，而是整条链、整个板块一起涨跌的大环境风险。万一 AI 投资退潮，相关股票会一起跌。",
    "护城河": "一家公司或一个环节长期挡住竞争对手、保住高利润的本事，比如独家工艺、专利、客户离不开它。护城河越深，好日子越能持续。",
    "结构护城河": "靠工艺/IP/良率/关系筑起、产能想扩也扩不出来的持久壁垒——能穿越周期，是真护城河。",
    "周期租金": "只是因为眼下短缺、产能暂时不够才赚到的暴利。产能一补上就回吐，不持久。和结构护城河相对。",
    "利润池": "整条链赚到的钱不是平均分的。利润池就是看这笔总利润堆在哪几个环节、各分到多少——堆得最多的地方最值得研究。",
    "卡脖子": "整条链里供不应求、谁也绕不开的那个环节。卡脖子的环节最有定价权——但要分清是结构护城河还是周期租金。",
    "资本周期": "一个行业景气时大家拼命扩产，导致产能过剩、价格崩、利润垮，再减产、又紧缺的循环。看供给（谁在扩产）往往比看需求更能提前判断利润拐点。",
    "供给受限": "想扩产也扩不出来（技术太难、建设周期太长、或寡头不愿扩）。供给受限的环节超额利润能维持更久。",
    "扩张顶部": "全行业都在疯狂砸钱扩产的时刻——往往利润最好、但也最危险，因为新产能一投产就会把价格打下来。",
    "价值占有": "一个环节实际能从整条链里拿走多少利润。和价值创造（对整条链有多重要）常常是两回事。",
    "价值创造": "一个环节给整条链帮了多大忙、有多重要。重要不等于能赚到钱（要看价值占有）。",
    "ROIC": "投入资本回报率——每投 1 块钱能赚回多少。长期高于借钱成本，才是真正在创造价值的好生意。",
    "WACC": "加权平均资本成本——公司融到这笔钱的平均代价。赚的（ROIC）要比这个高，才算创造了价值。",
    "反向 DCF": "正常估值是用假设算公司值多少钱；反向 DCF 反过来——从现在的股价倒推出市场假设了它未来要增长多快，再判断这个假设是不是已经太乐观。",
    "中周期归一化": "不要用景气最高峰那年的暴利去估值（那不可持续），而是用一个跨越好年和坏年的平均水平来算，避免在山顶上按最贵的价买。",
    "毛利率": "卖一件东西、扣掉直接成本后还剩多少比例的钱。毛利率高通常意味着有定价权、有技术含量。",
    "毛利": "卖一件东西、扣掉直接成本后赚的那部分。占售价的比例（毛利率）高，通常意味着有定价权。",
    "渗透率": "新技术替代老技术的进度。比如液冷渗透率＝多少比例的数据中心已经从风冷换成了液冷。",
    "国产替代": "原来靠进口的零件或材料，改用国产的。既是国产厂商的机会，也常因为一拥而上变成价格内卷。",
    "寡头": "整个市场只被极少数几家公司把持的格局，通常有很强的定价权。",
    "议价权": "谈价格时谁更有底气。是供应商求着客户买（议价权弱），还是客户排队求供应（议价权强）。",
    "backlog": "在手订单——已签约、还没交货的订单量。backlog 越厚、锁得越远，未来几年收入越有保障。",
    "book-to-bill": "新接订单 ÷ 当期出货。大于 1 表示订单比出货还多、需求在加速。",
    "BOM": "物料清单——一个产品由哪些零件、各花多少钱拼成的成本明细表。成本拆解就是拆这张表。",
    "成本栈": "把一件大工程的总花费，按各个部分拆开、看每部分占多少钱的结构表。",
    "Bear": "熊市情景——分析时假设的最差那种情况（需求转冷、价格下跌），用来检验万一不顺时会亏多少。",
    "attach 率": "配套比例。比如每张 GPU 平均要配几个光模块，这个比例越高、需求越大。",
    "折旧": "贵重设备会逐年损耗、分摊成本。AI 芯片折旧按几年摊，直接影响账面利润——摊得慢、利润就显得高。",
    "循环融资": "我投资你、你再回头买我的东西，形成的资金闭环。比如英伟达投资客户、客户再用这笔钱买英伟达芯片——好看但脆弱。",
    "安全边际": "用保守估值减去现在的价格留出的缓冲。安全边际厚，意味着就算看错了也不容易亏本金。",
    "GPU": "图形处理器——英伟达做的那种 AI 算力芯片，是训练大模型的主力。",
    "ASIC": "为某一种活儿定制的专用芯片。云厂自研 ASIC（谷歌 TPU、亚马逊 Trainium）就是想绕开英伟达、降成本。",
    "CUDA": "英伟达的软件生态（开发工具加代码库）。全世界 AI 程序员都习惯用它，换别家芯片要重写代码——这是英伟达真正的护城河。",
    "HBM": "高带宽内存——紧贴 AI 芯片、负责高速喂数据的特种内存。被 SK 海力士等三家垄断，是当前最紧缺、最赚钱的环节之一。",
    "CoWoS": "台积电的一种先进封装工艺，把 AI 芯片和 HBM 内存拼装在一起。产能卡死、供不应求，是过去两年的头号瓶颈。",
    "先进封装": "把多块芯片高密度拼装在一起的工艺（CoWoS 就是其中一种），决定了 AI 芯片能不能做出来。",
    "晶圆代工": "替别人制造芯片的工厂，台积电是绝对龙头。几乎所有 AI 芯片都在它那里生产。",
    "EML": "光模块里负责发光的激光芯片。全球只有几家能做、英伟达砸钱锁产能，是卡脖子中的卡脖子。",
    "光模块": "数据中心里把电信号转成光、让成千上万张 GPU 互相高速通信的器件。中国厂商（中际旭创等）全球领先。",
    "DSP": "光模块里做信号处理的芯片，被博通和 Marvell 两家垄断，国产几乎是空白。",
    "CPO": "共封装光学——下一代把光直接封进交换芯片的技术，2028 年后可能颠覆现在用的可插拔光模块。",
    "硅光": "用硅基工艺做光器件的技术路线，被看作光通信的未来方向之一。",
    "NVLink": "英伟达自家的高速互联技术，让一个机柜里的多张 GPU 像一块大芯片一样协同。",
    "燃气轮机": "烧天然气发电的大型设备。数据中心要能马上供上的电，燃气轮机是当前唯一能大规模快速供电的来源。",
    "单晶叶片": "燃气轮机里承受上千度高温的涡轮叶片，用单晶镍基高温合金整体铸造，全球极少数厂能做，是燃气轮机最贵、最难仿、最卡脖子的零件。",
    "高温合金": "能在上千度高温下不变形的特种金属，用来做燃气轮机叶片、航空发动机，工艺极难、供应极集中。",
    "LTSA": "长期服务协议——卖出燃气轮机后签的几十年维护保养合同。利润比卖设备本身还高（约两倍）、年年收、抗周期，是燃气轮机真正的利润池。",
    "服务年金": "设备卖出后，靠几十年维保合同年年收的稳定现金流。像年金一样可预测、抗周期。",
    "GOES": "取向硅钢——做变压器铁芯的特种钢材，全球极少数厂能产（美国只有一家），是变压器的卡脖子原料之一。",
    "取向硅钢": "做变压器铁芯的特种钢材（英文 GOES），冶炼工艺极难、产地极少，是变压器的卡脖子原料。",
    "变压器": "把电网的高压电升压/降压、再送进数据中心的关键设备。现在全球短缺、交期长达数年。",
    "变电站": "把高压电网的电降压、再分配给数据中心的设施。新建一座要 5–10 年审批建设，是落地最大瓶颈之一。",
    "并网": "新建的电厂或数据中心接入电网。美国现在并网排队要等 4–7 年，是 AI 数据中心落地的最大物理瓶颈。",
    "开关柜": "把电分配、保护、通断的成套电气设备，数据中心中压配电的关键一环，现在交期很长。",
    "UPS": "不间断电源——市电断了也能瞬间顶上、保证数据中心不停机的设备，里面大量用功率半导体和电池。",
    "IGBT": "一种功率半导体开关器件，是 UPS、变频、电源里控制大电流的核心芯片。市场成熟、分散，国产已价格战。",
    "SiC": "碳化硅——新一代功率半导体材料，比传统 IGBT 更高效省电，正在高端 UPS 和电源里替代 IGBT。",
    "功率半导体": "专门控制大电流大电压的芯片（IGBT、SiC 等），是电源、UPS、变频的心脏。",
    "BESS": "电池储能系统——用一堆电池给数据中心储电、削峰、备电，正在抢传统 UPS 和柴油机的活。",
    "PCS": "储能变流器——储能系统里把电池的直流电和电网的交流电互相转换的设备。",
    "EMS": "能量管理系统——储能 / 配电系统里负责调度、控制的软件与设备。",
    "LFP": "磷酸铁锂——目前储能电池的主流路线，便宜、安全、循环寿命长，被宁德时代等中国厂主导。",
    "柴油发电机": "市电断了时启动供电的备用柴油发电机组。占数据中心电气投资比例不小，但技术门槛相对低。",
    "母线": "工厂预制的大电流导体排（铜或铝），把电从变压器送到机柜。成本几乎全是金属（铜/铝）。",
    "能源孤岛": "数据中心不等漫长的电网排队，自己在旁边建电厂直接供电。贵，但能早几年通电——在 AI 竞赛里这几年值几十亿。",
    "固态变压器": "用功率电子（SiC 等）替代传统铜+硅钢铁芯的新型变压器，英文 SST，2028 年后放量，是对传统变压器的远端威胁。",
    "联合循环": "燃气发电的一种高效方式，先用燃气轮机发电、再用余热烧锅炉带蒸汽轮机再发一次电。",
    "速度到电": "从立项到真正通上电要多久。AI 竞赛里谁先通电谁先赚钱，所以宁可多花钱也要快。",
    "覆铜板": "做电路板（PCB）的基础材料，英文缩写 CCL。高端 AI 服务器板用的高速覆铜板是卡脖子材料。",
    "ODM": "代工厂——按客户要求把零件组装成整机（如服务器）。活儿重要但毛利薄，是典型的搬砖环节。",
    "IDC": "数据中心（机房）运营商，提供机柜、电力、网络给云厂和企业租用，是重资产生意。",
    "液冷": "用液体而不是风给高功率 AI 芯片散热。新一代 AI 机柜太热、风冷散不掉，只能上液冷。"
  };

  const css = ".term{border-bottom:1px dashed #1f6f8b;cursor:help}.term:hover{color:#1f6f8b}"
    + ".term-pop{display:none;position:absolute;z-index:80;max-width:340px;background:#0f2e3d;color:#eaf2f5;"
    + "font-size:12.5px;line-height:1.64;padding:12px 15px;border-radius:11px;"
    + "box-shadow:0 24px 50px rgba(16,34,48,.28);border:1px solid rgba(255,255,255,.08)}"
    + ".term-pop::before{content:'\\1F4A1 \\5927\\767D\\8BDD';display:block;font-size:10.5px;font-weight:700;color:#ffd98a;letter-spacing:.5px;margin-bottom:5px}"
    + ".term-demo{border-bottom:1px dashed #1f6f8b;color:#1f6f8b}";
  const st = document.createElement("style"); st.textContent = css; document.head.appendChild(st);

  const pop = document.createElement("div"); pop.className = "term-pop"; document.body.appendChild(pop);
  let pinned = false;
  function place(el) {
    pop.style.display = "block";
    const r = el.getBoundingClientRect(), pw = pop.offsetWidth, ph = pop.offsetHeight;
    let left = Math.min(r.left + window.scrollX, window.scrollX + document.documentElement.clientWidth - pw - 16);
    left = Math.max(left, window.scrollX + 10);
    let top = r.bottom + window.scrollY + 8;
    if (r.bottom + 8 + ph > window.innerHeight && r.top - 8 - ph > 0) top = r.top + window.scrollY - ph - 8;
    pop.style.left = left + "px"; pop.style.top = top + "px";
  }
  function show(el) { pop.textContent = el.getAttribute("data-def") || ""; place(el); }
  document.addEventListener("mouseover", e => { const t = e.target.closest(".term"); if (t && !pinned) show(t); });
  document.addEventListener("mouseout", e => { const t = e.target.closest(".term"); if (t && !pinned) pop.style.display = "none"; });
  document.addEventListener("click", e => {
    const t = e.target.closest(".term");
    if (t) { pinned = true; show(t); e.stopPropagation(); } else { pinned = false; pop.style.display = "none"; }
  });

  try {
    const esc = s => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const keys = Object.keys(GLOSSARY).sort((a, b) => b.length - a.length);
    const parts = keys.map(k => /^[\x00-\x7f]+$/.test(k) ? "(?<![A-Za-z0-9])" + esc(k) + "(?![A-Za-z0-9])" : esc(k));
    const RE = new RegExp(parts.join("|"), "g");
    const SKIP = "script,style,summary,h1,.sec-title,.term,.term-pop,.term-demo,.lkt,.pill,.tier-pill,.drill-status,.gate-pill,.howto-title,.dname,.flag";
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
      acceptNode(n) {
        const p = n.parentElement;
        if (!p || p.closest(SKIP)) return NodeFilter.FILTER_REJECT;
        if (!n.nodeValue || !n.nodeValue.trim()) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    const nodes = []; let wn; while (wn = walker.nextNode()) nodes.push(wn);
    nodes.forEach(tn => {
      const txt = tn.nodeValue; RE.lastIndex = 0;
      if (!RE.test(txt)) return; RE.lastIndex = 0;
      const frag = document.createDocumentFragment(); let last = 0, m;
      while (m = RE.exec(txt)) {
        const term = m[0], i = m.index;
        if (i > last) frag.appendChild(document.createTextNode(txt.slice(last, i)));
        const span = document.createElement("span");
        span.className = "term"; span.tabIndex = 0;
        span.setAttribute("data-def", GLOSSARY[term] || "");
        span.textContent = term;
        frag.appendChild(span); last = i + term.length;
        if (m.index === RE.lastIndex) RE.lastIndex++;
      }
      if (last < txt.length) frag.appendChild(document.createTextNode(txt.slice(last)));
      tn.parentNode.replaceChild(frag, tn);
    });
  } catch (err) { /* 老浏览器不支持 lookbehind 时静默跳过 */ }
})();
