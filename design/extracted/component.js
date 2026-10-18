class Component extends DCLogic {
  componentDidMount() { this.run(); }

  componentWillUnmount() {
    clearTimeout(this.delay);
    clearInterval(this.timer);
    clearTimeout(this.burstTimer);
    clearTimeout(this.copyTimer);
  }

  reduced() {
    try { return window.matchMedia("(prefers-reduced-motion: reduce)").matches; } catch (e) { return false; }
  }

  run() {
    clearTimeout(this.delay);
    clearInterval(this.timer);
    this.setState({ tick: 0 });
    this.delay = setTimeout(() => {
      let t = 0;
      this.timer = setInterval(() => {
        t += 1;
        this.setState({ tick: t });
        if (t >= 76) clearInterval(this.timer);
      }, 60);
    }, 500);
  }

  refs() {
    if (!this._refs) {
      this._refs = {
        hero: (el) => { this.heroEl = el; },
        screen: (el) => { this.heroScreenEl = el; },
        radar: (el) => { this.radarEl = el; },
        badge: (el) => { this.badgeEl = el; }
      };
    }
    return this._refs;
  }

  componentDidUpdate(prevProps, prevState) {
    const ps = prevState || {};
    const s = this.state || {};
    if (!s.open || s.open === ps.open) return;
    const from = this.flipFrom;
    const dir = this.flipDir;
    this.flipFrom = null;
    this.flipDir = 0;
    try { if (this.heroEl) this.heroEl.focus({ preventScroll: true }); } catch (e) {}
    if (this.reduced()) return;
    try {
      if (from && this.heroScreenEl) {
        const to = this.heroScreenEl.getBoundingClientRect();
        const sc = from.width / to.width;
        const dx = (from.left + from.width / 2) - (to.left + to.width / 2);
        const dy = (from.top + from.height / 2) - (to.top + to.height / 2);
        this.heroScreenEl.animate([
          { transform: "translate(" + dx + "px," + dy + "px) scale(" + sc + ")" },
          { transform: "none" }
        ], { duration: 560, easing: "cubic-bezier(.2,.9,.25,1.08)" });
      } else if (dir && this.heroEl) {
        this.heroEl.animate([
          { opacity: 0, transform: "translateX(" + (dir * 56) + "px)" },
          { opacity: 1, transform: "none" }
        ], { duration: 380, easing: "cubic-bezier(.2,.9,.3,1.15)" });
        if (this.radarEl) {
          this.radarEl.animate([
            { transform: "scale(0)", opacity: 0 },
            { transform: "scale(1)", opacity: 1 }
          ], { duration: 700, easing: "cubic-bezier(.34,1.56,.64,1)" });
        }
      }
    } catch (e) {}
  }

  markSeen(id) {
    const seen = Object.assign({}, (this.state || {}).seen);
    seen[id] = true;
    return seen;
  }

  open(id, e) {
    let rect = null;
    try {
      const art = e && e.currentTarget && e.currentTarget.closest ? e.currentTarget.closest("article") : null;
      const scr = art ? art.querySelector(".card-screen") : null;
      if (scr) rect = scr.getBoundingClientRect();
    } catch (err) {}
    try { this.savedY = window.scrollY || 0; } catch (err) {}
    this.flipFrom = rect;
    this.flipDir = 0;
    this.setState({ open: id, seen: this.markSeen(id), showDraft: false, copied: false });
    try { window.scrollTo(0, 0); } catch (err) {}
  }

  flipTo(id, dir) {
    this.flipFrom = null;
    this.flipDir = dir;
    this.setState({ open: id, seen: this.markSeen(id), showDraft: false, copied: false });
  }

  close() {
    const y = this.savedY || 0;
    this.setState({ open: null, showDraft: false });
    setTimeout(() => { try { window.scrollTo(0, y); } catch (e) {} }, 0);
  }

  shade(hex, f) {
    const n = parseInt(String(hex).replace("#", ""), 16);
    if (isNaN(n)) return "#B8261C";
    const c = (v) => Math.max(0, Math.round(v * (1 - f))).toString(16).padStart(2, "0");
    return "#" + c((n >> 16) & 255) + c((n >> 8) & 255) + c(n & 255);
  }

  types() {
    return {
      ml: { label: "ML / AI", bg: "#EEE8FF", fg: "#5B3FD6", icon: "M3 6a2 2 0 1 0 4 0a2 2 0 1 0-4 0M3 18a2 2 0 1 0 4 0a2 2 0 1 0-4 0M17 12a2 2 0 1 0 4 0a2 2 0 1 0-4 0M10 12a2 2 0 1 0 4 0a2 2 0 1 0-4 0M6.5 7.5l4 3M6.5 16.5l4-3M14 12h3" },
      backend: { label: "Backend", bg: "#DDF5EA", fg: "#1A6B4A", icon: "M4 5h16v5H4zM4 14h16v5H4zM7.5 7.5h.01M7.5 16.5h.01" },
      frontend: { label: "Frontend", bg: "#FFE9DC", fg: "#B4441A", icon: "M3 5h18v14H3zM3 9h18M6 7h.01M8.5 7h.01" },
      design: { label: "Design", bg: "#FFE3EE", fg: "#AD2A5F", icon: "M12 3l6 8-6 10-6-10zM12 10v4" },
      mobile: { label: "Mobile", bg: "#DDEFFF", fg: "#1D65B8", icon: "M7 3h10v18H7zM11 18h2" },
      hardware: { label: "Hardware", bg: "#FFF3C4", fg: "#7A5D00", icon: "M7 7h10v10H7zM10 10h4v4h-4zM9 3v4M15 3v4M9 17v4M15 17v4M3 9h4M3 15h4M17 9h4M17 15h4" }
    };
  }

  candidates() {
    return [
      { id: "maya", name: "Maya Chen", dex: "0042", types: ["ml", "backend"], school: "UofT", schoolFull: "University of Toronto", year: "Year 3", city: "Toronto", score: 96, hacks: 7, wins: 3, repos: 41,
        why: "Won Best Use of ML twice. 3rd year, based in Toronto.",
        sum: "Turns messy real-world data into ML demos that work on the first try.",
        program: "Computer Science", grad: "April 2028", active: "2 days ago",
        ev: { ml: 252, backend: 168, frontend: 64, design: 26, mobile: 0, hardware: 0 },
        src: { ml: "Sightline, Pantry Pal, Transit Pulse", backend: "Sightline, Pantry Pal", frontend: "Pantry Pal, Transit Pulse", design: "Pantry Pal" },
        iv: [31, 30, 27, 22, 19, 11], n: { demo: 7, own: 5, mates: 9, kept: 2, docs: 3 },
        mlc: ["met", "6 of 7 projects use PyTorch or TensorFlow"], yrc: ["met", "Lists 3rd-year Computer Science"], locc: ["met", "Studies at UofT, St. George campus"],
        projects: [
          { name: "Sightline", abbr: "Si", type: "ml", event: "Hack the North 2025", desc: "Real-time sign-language captions in the browser.", prize: "Best Use of ML", kept: true, share: 58 },
          { name: "Pantry Pal", abbr: "Pp", type: "backend", event: "UofTHacks 12", desc: "Snap your fridge, get a week of recipes that cut food waste.", prize: "Best ML Hack", kept: false, share: 44 },
          { name: "Transit Pulse", abbr: "Tp", type: "mobile", event: "Hack the 6ix 2024", desc: "Predicts TTC delays from live transit feeds.", prize: "2nd overall", kept: true, share: 71 }
        ] },
      { id: "arjun", name: "Arjun Patel", dex: "0117", types: ["ml", "mobile"], school: "Waterloo", schoolFull: "University of Waterloo", year: "Year 3", city: "Waterloo", score: 91, hacks: 9, wins: 2, repos: 56,
        why: "Shipped 4 ML projects. About an hour from Toronto.",
        sum: "Ships polished ML features inside mobile apps, and ships them fast.",
        program: "Software Engineering (co-op)", grad: "April 2028", active: "today",
        ev: { ml: 220, backend: 80, frontend: 30, design: 0, mobile: 180, hardware: 0 },
        src: { ml: "Crop Doctor, Gesture Keys, 3 more", mobile: "Crop Doctor, Gesture Keys", backend: "Crop Doctor", frontend: "Gesture Keys" },
        iv: [28, 26, 20, 30, 24, 21], n: { demo: 8, own: 4, mates: 14, kept: 3, docs: 6 },
        mlc: ["met", "5 of 9 projects ship an ML model"], yrc: ["met", "Lists 3rd-year Software Engineering"], locc: ["close", "Waterloo, about an hour from Toronto"],
        projects: [
          { name: "Crop Doctor", abbr: "Cd", type: "ml", event: "Hack the North 2025", desc: "Snap a leaf to diagnose crop disease, fully offline.", prize: "Best Mobile Hack", kept: true, share: 63 },
          { name: "Gesture Keys", abbr: "Gk", type: "mobile", event: "DeltaHacks 11", desc: "Type with hand gestures using any phone camera.", prize: "", kept: false, share: 52 }
        ] },
      { id: "sofia", name: "Sofia Reyes", dex: "0208", types: ["frontend", "design"], school: "TMU", schoolFull: "Toronto Metropolitan University", year: "Year 3", city: "Toronto", score: 88, hacks: 5, wins: 2, repos: 23,
        why: "Built the ML demo UI on two winning teams.",
        sum: "Makes ML demos feel like real products. The UI is why judges remember them.",
        program: "Computer Science", grad: "April 2028", active: "5 days ago",
        ev: { ml: 40, backend: 60, frontend: 240, design: 170, mobile: 0, hardware: 0 },
        src: { frontend: "Lumen, Mood Garden, 3 more", design: "Mood Garden, Lumen", backend: "Mood Garden", ml: "Lumen" },
        iv: [29, 27, 15, 26, 12, 28], n: { demo: 5, own: 2, mates: 8, kept: 1, docs: 5 },
        mlc: ["close", "Built the UI for 2 ML projects"], yrc: ["met", "Lists 3rd-year Computer Science"], locc: ["met", "Studies at TMU, downtown Toronto"],
        projects: [
          { name: "Lumen", abbr: "Lu", type: "frontend", event: "UofTHacks 12", desc: "An accessible reading mode powered by an ML summarizer.", prize: "Best UI", kept: false, share: 66 },
          { name: "Mood Garden", abbr: "Mg", type: "design", event: "Hack the 6ix 2025", desc: "A journaling app that grows a garden as you write.", prize: "Best Design", kept: true, share: 72 }
        ] },
      { id: "daniel", name: "Daniel Okafor", dex: "0073", types: ["backend", "ml"], school: "UofT", schoolFull: "University of Toronto", year: "Year 4", city: "Toronto", score: 85, hacks: 11, wins: 1, repos: 64,
        why: "Wrote the inference API for a winning ML hack.",
        sum: "The person who makes the model actually serve real traffic.",
        program: "Computer Engineering", grad: "April 2027", active: "yesterday",
        ev: { ml: 160, backend: 252, frontend: 50, design: 0, mobile: 0, hardware: 48 },
        src: { backend: "Queue Less, Model Mart, 6 more", ml: "Model Mart, Queue Less", frontend: "Queue Less", hardware: "2 earlier projects" },
        iv: [25, 16, 29, 24, 30, 30], n: { demo: 9, own: 8, mates: 12, kept: 5, docs: 9 },
        mlc: ["met", "7 of 11 projects deploy an ML model"], yrc: ["close", "Lists 4th year, one year ahead"], locc: ["met", "Studies at UofT, St. George campus"],
        projects: [
          { name: "Queue Less", abbr: "Ql", type: "backend", event: "Hack the 6ix 2025", desc: "Real-time ER wait estimates from public data feeds.", prize: "Best Civic Hack", kept: true, share: 81 },
          { name: "Model Mart", abbr: "Mm", type: "ml", event: "UofTHacks 11", desc: "One-click hosting for student ML models.", prize: "", kept: true, share: 77 }
        ] },
      { id: "lina", name: "Lina Haddad", dex: "0311", types: ["hardware", "ml"], school: "McMaster", schoolFull: "McMaster University", year: "Year 3", city: "Hamilton", score: 82, hacks: 6, wins: 2, repos: 18,
        why: "On-device ML for a prize-winning wearable.",
        sum: "Puts small ML models on tiny devices that actually last on a battery.",
        program: "Mechatronics Engineering", grad: "April 2028", active: "3 days ago",
        ev: { ml: 170, backend: 40, frontend: 30, design: 0, mobile: 30, hardware: 240 },
        src: { hardware: "Fall Guard, Bee Count, 2 more", ml: "Bee Count, Fall Guard", backend: "Fall Guard", frontend: "Bee Count", mobile: "Fall Guard" },
        iv: [27, 28, 24, 20, 15, 22], n: { demo: 6, own: 4, mates: 7, kept: 1, docs: 4 },
        mlc: ["met", "4 of 6 projects run ML on-device"], yrc: ["met", "Lists 3rd-year Mechatronics"], locc: ["close", "Hamilton, about an hour from Toronto"],
        projects: [
          { name: "Fall Guard", abbr: "Fg", type: "hardware", event: "DeltaHacks 11", desc: "A wearable that detects falls for older adults.", prize: "Best Hardware Hack", kept: false, share: 69 },
          { name: "Bee Count", abbr: "Bc", type: "ml", event: "Hack the North 2025", desc: "Counts pollinators with an on-device vision model.", prize: "Best Use of Edge AI", kept: false, share: 61 }
        ] },
      { id: "priya", name: "Priya Nair", dex: "0099", types: ["ml"], school: "Western", schoolFull: "Western University", year: "Year 3", city: "London, ON", score: 79, hacks: 4, wins: 1, repos: 29,
        why: "Computer vision focus. Two hours from Toronto.",
        sum: "Careful computer vision work with unusually thorough write-ups.",
        program: "Computer Science", grad: "April 2028", active: "1 week ago",
        ev: { ml: 230, backend: 90, frontend: 40, design: 20, mobile: 0, hardware: 0 },
        src: { ml: "Skin Check, Shelf Scan, 2 more", backend: "Skin Check", frontend: "Shelf Scan", design: "Skin Check" },
        iv: [22, 18, 23, 14, 26, 31], n: { demo: 3, own: 3, mates: 5, kept: 2, docs: 4 },
        mlc: ["met", "All 4 projects are computer vision"], yrc: ["met", "Lists 3rd-year Computer Science"], locc: ["close", "London, ON, about two hours away"],
        projects: [
          { name: "Skin Check", abbr: "Sc", type: "ml", event: "Hack Western 11", desc: "Flags skin spots worth a doctor's look.", prize: "Best Health Hack", kept: true, share: 74 },
          { name: "Shelf Scan", abbr: "Ss", type: "ml", event: "Hack the North 2024", desc: "Counts store inventory from a single photo.", prize: "", kept: false, share: 48 }
        ] },
      { id: "ethan", name: "Ethan Park", dex: "0154", types: ["mobile", "ml"], school: "York", schoolFull: "York University", year: "Year 2", city: "Toronto", score: 76, hacks: 8, wins: 1, repos: 33,
        why: "Strong ML mobile apps, but in 2nd year, not 3rd.",
        sum: "A fast mobile builder who has started adding ML to everything he ships.",
        program: "Computer Science", grad: "April 2029", active: "today",
        ev: { ml: 120, backend: 70, frontend: 90, design: 0, mobile: 230, hardware: 0 },
        src: { mobile: "Study Buddy, Pocket Sommelier, 4 more", ml: "Study Buddy, Pocket Sommelier", frontend: "Pocket Sommelier", backend: "Study Buddy" },
        iv: [26, 14, 25, 27, 17, 9], n: { demo: 7, own: 5, mates: 11, kept: 2, docs: 2 },
        mlc: ["met", "3 of 8 projects use on-device ML"], yrc: ["miss", "Lists 2nd year"], locc: ["met", "Studies at York, Keele campus"],
        projects: [
          { name: "Study Buddy", abbr: "Sb", type: "mobile", event: "Hack the 6ix 2025", desc: "Turns lecture audio into flashcards on your phone.", prize: "Best Use of Speech AI", kept: false, share: 70 },
          { name: "Pocket Sommelier", abbr: "Ps", type: "mobile", event: "UofTHacks 12", desc: "Point your camera at a menu to get food pairings.", prize: "", kept: false, share: 64 }
        ] },
      { id: "noah", name: "Noah Tremblay", dex: "0260", types: ["design", "frontend"], school: "OCAD U", schoolFull: "OCAD University", year: "Year 3", city: "Toronto", score: 73, hacks: 5, wins: 1, repos: 12,
        why: "Designer on three ML-powered hacks.",
        sum: "A designer who makes ML features feel friendly and obvious.",
        program: "Digital Futures", grad: "April 2028", active: "4 days ago",
        ev: { ml: 30, backend: 0, frontend: 170, design: 252, mobile: 30, hardware: 0 },
        src: { design: "Calm Commute, Echo Notes, 3 more", frontend: "Echo Notes, Calm Commute", ml: "Echo Notes", mobile: "Calm Commute" },
        iv: [21, 15, 10, 29, 13, 25], n: { demo: 4, own: 1, mates: 13, kept: 1, docs: 4 },
        mlc: ["close", "Designer on 3 ML projects"], yrc: ["met", "Lists 3rd-year Digital Futures"], locc: ["met", "Studies at OCAD U, downtown Toronto"],
        projects: [
          { name: "Calm Commute", abbr: "Cc", type: "design", event: "Hack the 6ix 2025", desc: "Routes you around the most crowded transit cars.", prize: "Best UX", kept: false, share: 38 },
          { name: "Echo Notes", abbr: "En", type: "frontend", event: "UofTHacks 12", desc: "Voice notes that sort themselves by topic.", prize: "", kept: false, share: 30 }
        ] },
      { id: "grace", name: "Grace Liu", dex: "0185", types: ["backend"], school: "UofT", schoolFull: "University of Toronto", year: "New grad", city: "Toronto", score: 70, hacks: 10, wins: 0, repos: 47,
        why: "Deep backend work on ML pipelines. No wins yet.",
        sum: "A steady backend engineer behind a lot of other teams' ML pipelines.",
        program: "Computer Science (graduated)", grad: "June 2026", active: "today",
        ev: { ml: 140, backend: 252, frontend: 60, design: 0, mobile: 0, hardware: 58 },
        src: { backend: "Data Dock, Rain Check, 6 more", ml: "Data Dock, Rain Check", frontend: "Rain Check", hardware: "Rain Check" },
        iv: [24, 0, 26, 21, 28, 27], n: { demo: 8, own: 6, mates: 10, kept: 4, docs: 8 },
        mlc: ["close", "Built the data pipelines for 4 ML projects"], yrc: ["miss", "Graduated in 2026"], locc: ["met", "Based in Toronto"],
        projects: [
          { name: "Data Dock", abbr: "Dd", type: "backend", event: "Hack the North 2025", desc: "Self-serve data pipelines for student hackathon teams.", prize: "", kept: true, share: 79 },
          { name: "Rain Check", abbr: "Rc", type: "backend", event: "Hack the 6ix 2024", desc: "Flood-risk alerts from city sensor data.", prize: "", kept: true, share: 68 }
        ] }
    ];
  }

  avatar(id) {
    let h = 7;
    for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
    const r = () => { h = (Math.imul(h, 1664525) + 1013904223) >>> 0; return h / 4294967296; };
    const rs = Math.round(44 + r() * 22);
    const rx = Math.round(6 + r() * 40);
    const ry = Math.round(6 + r() * 40);
    const rot = Math.round(r() * 90);
    const cx = Math.round(30 + r() * 45);
    const cy = Math.round(35 + r() * 45);
    const cr = Math.round(16 + r() * 12);
    const x1 = Math.round(10 + r() * 30);
    const y1 = Math.round(55 + r() * 30);
    const a = r() * Math.PI;
    return {
      rx: rx, ry: ry, rs: rs,
      rt: "rotate(" + rot + " " + (rx + rs / 2) + " " + (ry + rs / 2) + ")",
      cx: cx, cy: cy, cr: cr, cf: r() > 0.45 ? "#FFCB3D" : "#FFFFFF",
      x1: x1, y1: y1, x2: Math.round(x1 + Math.cos(a) * 42), y2: Math.round(y1 - Math.sin(a) * 42)
    };
  }

  judge(v, accent) {
    if (v >= 31) return ["Best", "background:" + accent + ";color:#FFFFFF"];
    if (v >= 30) return ["Fantastic", "background:#FFE1DC;color:#9E2219"];
    if (v >= 26) return ["Very good", "background:#DDF5EA;color:#1A6B4A"];
    if (v >= 16) return ["Pretty good", "background:#DDEFFF;color:#1D65B8"];
    if (v >= 1) return ["Decent", "background:#F3E6DA;color:#4A3632"];
    return ["Not yet", "background:#F3E6DA;color:#6E5A55"];
  }

  getStarred() {
    const s = this.state || {};
    return s.starred || { arjun: true, sofia: true };
  }

  toggle(id) {
    const cur = Object.assign({}, this.getStarred());
    cur[id] = !cur[id];
    const patch = { starred: cur };
    if (cur[id]) {
      patch.burst = id;
      clearTimeout(this.burstTimer);
      this.burstTimer = setTimeout(() => this.setState({ burst: null }), 700);
      if (this.badgeEl && !this.reduced()) {
        try {
          this.badgeEl.animate([{ transform: "scale(1)" }, { transform: "scale(1.5)" }, { transform: "scale(1)" }], { duration: 420, easing: "cubic-bezier(.34,1.56,.64,1)" });
        } catch (e) {}
      }
    }
    this.setState(patch);
  }

  profile(c, order, ctx) {
    const T = ctx.T;
    const accent = ctx.accent;
    const t = T[c.types[0]];
    const first = c.name.split(" ")[0];
    const axes = ["ml", "backend", "frontend", "design", "mobile", "hardware"];
    const dirs = [[0, -1], [0.866, -0.5], [0.866, 0.5], [0, 1], [-0.866, 0.5], [-0.866, -0.5]];
    const radar = { v: {}, f: {} };
    const pts = [];
    axes.forEach((k, i) => {
      const v = c.ev[k] || 0;
      const f = Math.min(1, v / 252);
      const x = 170 + dirs[i][0] * 105 * f;
      const y = 150 + dirs[i][1] * 105 * f;
      pts.push(x.toFixed(1) + "," + y.toFixed(1));
      radar["d" + i] = { x: x.toFixed(1), y: y.toFixed(1), r: v > 0 ? 5.5 : 0, fill: T[k].fg };
      radar.v[k] = v;
      radar.f[k] = v > 0 ? T[k].fg : "#6E5A55";
    });
    radar.points = pts.join(" ");
    const total = axes.reduce((a, k) => a + (c.ev[k] || 0), 0);
    const nonzero = axes.filter((k) => c.ev[k] > 0).sort((a, b) => c.ev[b] - c.ev[a]);
    const zeros = axes.filter((k) => !c.ev[k]).map((k) => T[k].label);
    const evRows = nonzero.map((k) => ({ label: T[k].label, value: c.ev[k], fg: T[k].fg, bg: T[k].bg, icon: T[k].icon, src: c.src[k] || "earlier projects" }));

    const traitLabels = ["Ships demos", "Wins", "Ownership", "Teamwork", "Persistence", "Documentation"];
    const natures = ["Builder", "Competitor", "Leader", "Teammate", "Finisher", "Explainer"];
    const ev = [
      c.n.demo + " of " + c.hacks + " projects have a working demo",
      c.wins ? c.wins + " prize" + (c.wins > 1 ? "s" : "") + " in " + c.hacks + " hackathons" : "No prizes yet in " + c.hacks + " hackathons",
      "Owns the repo on " + c.n.own + " of " + c.hacks + " projects",
      "Built with " + c.n.mates + " different teammates",
      "Kept building " + c.n.kept + " of " + c.hacks + " after the event",
      "READMEs on " + c.n.docs + " of " + c.hacks + " projects"
    ];
    const ivTiles = c.iv.map((v, i) => {
      const j = this.judge(v, accent);
      return { label: traitLabels[i], value: v, judge: j[0], judgeStyle: j[1], evidence: ev[i] };
    });
    let hi = 0;
    let lo = 0;
    c.iv.forEach((v, i) => { if (v > c.iv[hi]) hi = i; if (v < c.iv[lo]) lo = i; });

    const statusMap = {
      met: { bg: "#DDF5EA", fg: "#1A6B4A", icon: "M5 12.5l4.5 4.5L19 7.5", status: "Matches" },
      close: { bg: "#FFF3C4", fg: "#7A5D00", icon: "M5 13c2-3 4-3 7 0s5 3 7 0", status: "Close" },
      miss: { bg: "#F3E6DA", fg: "#6E5A55", icon: "M7 7l10 10M17 7L7 17", status: "Does not match" }
    };
    const winc = c.wins ? ["met", c.wins + " prize" + (c.wins > 1 ? "s" : "") + " in " + c.hacks + " hackathons"] : ["miss", "No prizes yet"];
    const raw = [
      ["ML / AI", c.mlc, "GitHub"],
      ["Year 3", c.yrc, "Devpost"],
      ["Toronto", c.locc, "Devpost"],
      ["Hackathon winner", winc, "Devpost"]
    ];
    const crits = raw.map((r) => Object.assign({ label: r[0], note: r[1][1], src: r[2] }, statusMap[r[1][0]]));
    const met = raw.filter((r) => r[1][0] === "met").length;

    const top = c.projects[0];
    const topType = T[nonzero[0]].label;
    const idx = order.findIndex((x) => x.id === c.id);
    const prev = idx > 0 ? order[idx - 1] : null;
    const next = idx >= 0 && idx < order.length - 1 ? order[idx + 1] : null;
    const on = !!ctx.starred[c.id];
    const C = 2 * Math.PI * 29;

    return {
      id: c.id, name: c.name, first: first, dex: "#" + c.dex, dexNum: c.dex,
      fg: t.fg, bg: t.bg, av: this.avatar(c.id),
      meta: c.schoolFull + " · " + c.year + " · " + c.city,
      chips: c.types.map((k) => ({ label: T[k].label, icon: T[k].icon, style: "background:" + T[k].bg + ";color:" + T[k].fg })),
      sum: c.sum, score: c.score,
      scoreLabel: "Match score " + c.score + " percent",
      dash: (c.score / 100 * C).toFixed(1) + " " + C.toFixed(1),
      starred: on,
      shortLabel: on ? "Shortlisted!" : "Shortlist",
      shortStyle: on ? "background:#FFCB3D;box-shadow:0 5px 0 #C98F0E" : "background:#FFF6EE;box-shadow:0 5px 0 rgba(42,23,21,.14)",
      starFill: on ? "#FFFFFF" : "none",
      toggle: () => this.toggle(c.id),
      bursting: ctx.burst === c.id,
      crits: crits,
      metLabel: met + " of 4 match",
      metStyle: met === 4 ? "background:#DDF5EA;color:#1A6B4A" : "background:#FFF3C4;color:#7A5D00",
      radar: radar,
      radarLabel: "EV hexagon for " + c.name + ": " + nonzero.map((k) => T[k].label + " " + c.ev[k]).join(", ") + ".",
      evRows: evRows,
      hasZeros: zeros.length > 0,
      zeros: "No points yet in " + zeros.join(" or ") + ".",
      evTotal: total,
      trainedLabel: total >= 510 ? "Fully trained" : "Still training",
      trainedStyle: total >= 510 ? "background:" + accent + ";color:#FFFFFF" : "background:#FFF3C4;color:#7A5D00",
      ivTiles: ivTiles,
      natureName: natures[hi],
      natureLine: "Strongest at " + traitLabels[hi].toLowerCase() + ", lightest on " + traitLabels[lo].toLowerCase() + ".",
      schoolFull: c.schoolFull, program: c.program, grad: c.grad, active: c.active,
      verify: "GitHub and LinkedIn are linked from " + first + "'s own Devpost profile, so this is the right person.",
      projCount: c.projects.length + " of " + c.hacks,
      projects: c.projects.map((pr) => ({
        name: pr.name, abbr: pr.abbr, event: pr.event, desc: pr.desc, prize: pr.prize, hasPrize: !!pr.prize, kept: pr.kept,
        bg: T[pr.type].bg, fg: T[pr.type].fg, share: first + " wrote " + pr.share + "%"
      })),
      draftSubject: "Your " + top.name + " build at " + top.event,
      draftBody: "Hi " + first + ",\n\nI came across " + top.name + " on Devpost. " + top.desc + " That's an impressive build for one weekend.\n\nI'm hiring for [ROLE] at [COMPANY], working on [TEAM OR PRODUCT]. Your " + topType + " work stood out, and I think you'd be a great fit.\n\nWould you be open to a 20-minute chat next week?\n\n[YOUR NAME]",
      backLabel: "All " + order.length + " builders",
      pos: idx >= 0 ? (idx + 1) + " of " + order.length : "",
      prevLabel: prev ? "#" + prev.dex + " " + prev.name.split(" ")[0] : "Start",
      nextLabel: next ? "#" + next.dex + " " + next.name.split(" ")[0] : "End",
      prevAria: prev ? "Previous: " + prev.name : "No previous builder",
      nextAria: next ? "Next: " + next.name : "No next builder",
      noPrev: !prev, noNext: !next,
      goPrev: () => { if (prev) this.flipTo(prev.id, -1); },
      goNext: () => { if (next) this.flipTo(next.id, 1); },
      prevId: prev ? prev.id : null, nextId: next ? next.id : null
    };
  }

  renderVals() {
    const s = this.state || {};
    const accent = this.props.accent ?? "#E8382B";
    const accentDark = this.shade(accent, 0.24);
    const T = this.types();
    const all = this.candidates();
    const tick = s.tick || 0;
    const scanned = Math.min(214, tick * 3);
    const appear = (i) => 7 * (i + 1);
    const pos = {};
    all.forEach((c, i) => { pos[c.id] = i; });
    const shownList = all.filter((c, i) => tick >= appear(i));
    const isRevealed = (c) => tick >= appear(pos[c.id]) + 6;
    const done = tick >= 76;
    const filter = s.filter || "all";
    const sort = s.sort || "match";
    const starred = this.getStarred();
    const seen = s.seen || {};
    const removed = s.removed || {};

    const counts = {};
    shownList.forEach((c) => c.types.forEach((k) => { counts[k] = (counts[k] || 0) + 1; }));
    const tabKeys = ["all"].concat(Object.keys(T).filter((k) => counts[k]));
    const allIcon = "M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z";
    const tabs = tabKeys.map((k) => {
      const on = k === filter;
      return {
        label: k === "all" ? "All" : T[k].label,
        icon: k === "all" ? allIcon : T[k].icon,
        count: k === "all" ? shownList.length : counts[k],
        dot: on ? "#FFFFFF" : (k === "all" ? accent : T[k].fg),
        pressed: on,
        style: on ? "background:" + accent + ";color:#FFFFFF;box-shadow:0 4px 0 " + accentDark : "background:#FFFFFF;color:#2A1715;box-shadow:0 4px 0 rgba(42,23,21,.1)",
        pick: () => this.setState({ filter: k })
      };
    });

    let visible = filter === "all" ? shownList.slice() : shownList.filter((c) => c.types.indexOf(filter) !== -1);
    if (sort === "wins") visible.sort((a, b) => (b.wins - a.wins) || (b.score - a.score));
    if (sort === "hacks") visible.sort((a, b) => (b.hacks - a.hacks) || (b.score - a.score));

    const C = 2 * Math.PI * 17;
    const cards = visible.map((c) => {
      const t = T[c.types[0]];
      const on = !!starred[c.id];
      const rev = isRevealed(c);
      const wasSeen = !!seen[c.id];
      return {
        name: c.name, dex: "#" + c.dex, dexNum: c.dex, score: c.score, hacks: c.hacks, wins: c.wins, repos: c.repos, why: c.why,
        type: c.types[0], bg: t.bg, fg: t.fg,
        meta: c.school + " · " + c.year + " · " + c.city,
        dash: (c.score / 100 * C).toFixed(1) + " " + C.toFixed(1),
        scoreLabel: "Match score " + c.score + " percent",
        chips: c.types.map((k) => ({ label: T[k].label, icon: T[k].icon, style: "background:" + T[k].bg + ";color:" + T[k].fg })),
        av: this.avatar(c.id),
        revealed: rev, hidden: !rev, avClass: rev ? "" : "silhouette",
        seen: wasSeen,
        dexStyle: wasSeen ? "background:" + t.fg + ";color:#FFFFFF" : "background:#FFFFFF;color:" + t.fg,
        starred: on,
        starLabel: on ? "Remove " + c.name + " from shortlist" : "Add " + c.name + " to shortlist",
        starFill: on ? "#FFCB3D" : "none",
        starStroke: on ? "#C98F0E" : "#6E5A55",
        toggle: () => this.toggle(c.id),
        bursting: s.burst === c.id,
        open: (e) => this.open(c.id, e)
      };
    });

    const remaining = all.length - shownList.length;
    const skeletons = done || filter !== "all" ? [] : Array.from({ length: Math.min(3, remaining) }, (_, i) => ({ i: i }));

    const icons = {
      year: "M2 9l10-5 10 5-10 5-10-5zM6 11v5c0 1.4 2.7 3 6 3s6-1.6 6-3v-5",
      loc: "M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 1 1 13 0c0 5.4-6.5 11-6.5 11zM12 12.2a2.2 2.2 0 1 0 0-4.4 2.2 2.2 0 0 0 0 4.4z",
      win: "M8 4h8v5a4 4 0 0 1-8 0V4zM8 6H5a3 3 0 0 0 3.3 4M16 6h3a3 3 0 0 1-3.3 4M12 13v4M8.5 20h7M10 17h4"
    };
    const plain = "background:#FFFFFF;color:#2A1715";
    const baseFilters = [
      { id: "ml", label: "ML / AI", icon: T.ml.icon, style: "background:#EEE8FF;color:#5B3FD6" },
      { id: "year", label: "Year 3", icon: icons.year, style: plain },
      { id: "loc", label: "Toronto", icon: icons.loc, style: plain },
      { id: "win", label: "Hackathon winner", icon: icons.win, style: plain }
    ];
    const filters = baseFilters.filter((f) => !removed[f.id]).map((f) => Object.assign({}, f, {
      removeLabel: "Remove filter " + f.label,
      remove: () => { const r = Object.assign({}, this.state && this.state.removed); r[f.id] = true; this.setState({ removed: r }); }
    }));

    const order = visible.filter(isRevealed);
    let p = null;
    if (s.open) {
      const c = all.find((x) => x.id === s.open);
      if (c) p = this.profile(c, order, { T: T, accent: accent, starred: starred, burst: s.burst });
    }
    const profileMode = !!p;
    const tab = s.tab || "ev";
    const tabOn = "background:" + accent + ";color:#FFFFFF;box-shadow:0 3px 0 " + accentDark;
    const tabOff = "background:transparent;color:#2A1715";

    let phase = "Reading Devpost projects";
    if (scanned >= 72) phase = "Checking GitHub commits";
    if (scanned >= 144) phase = "Comparing builders to your search";

    return {
      accent: accent,
      accentDark: accentDark,
      refs: this.refs(),
      gridMode: !profileMode,
      profileMode: profileMode,
      p: p || {},
      headline: done ? all.length + " builders found!" : "Scouting for you…",
      filters: filters,
      anyRemoved: Object.keys(removed).length > 0,
      restore: () => this.setState({ removed: {} }),
      sort: sort,
      onSort: (e) => this.setState({ sort: e.target.value }),
      rerun: () => this.run(),
      scanning: !done,
      done: done,
      phase: phase,
      scanned: scanned,
      progress: (done ? 100 : Math.round(scanned / 214 * 100)) + "%",
      tabs: tabs,
      cards: cards,
      skeletons: skeletons,
      noneVisible: cards.length === 0 && skeletons.length === 0 && shownList.length > 0,
      starCount: Object.keys(starred).filter((k) => starred[k]).length,
      seenCount: Object.keys(seen).length,
      close: () => this.close(),
      onKey: (e) => {
        if (!p) return;
        if (e.key === "ArrowLeft" && p.prevId) { e.preventDefault(); this.flipTo(p.prevId, -1); }
        else if (e.key === "ArrowRight" && p.nextId) { e.preventDefault(); this.flipTo(p.nextId, 1); }
        else if (e.key === "Escape") { e.preventDefault(); this.close(); }
      },
      showDraft: !!s.showDraft,
      draftLabel: s.showDraft ? "Hide draft" : "Say hi",
      toggleDraft: () => this.setState({ showDraft: !s.showDraft, copied: false }),
      copyLabel: s.copied ? "Copied!" : "Copy email",
      copyIcon: s.copied ? "M5 12.5l4.5 4.5L19 7.5" : "M9 9h11v11H9zM5 15H4V4h11v1",
      copy: () => {
        try { if (p && navigator.clipboard) navigator.clipboard.writeText("Subject: " + p.draftSubject + "\n\n" + p.draftBody); } catch (e) {}
        this.setState({ copied: true });
        clearTimeout(this.copyTimer);
        this.copyTimer = setTimeout(() => this.setState({ copied: false }), 1600);
      },
      evOn: tab === "ev",
      ivOn: tab === "iv",
      evTabStyle: tab === "ev" ? tabOn : tabOff,
      ivTabStyle: tab === "iv" ? tabOn : tabOff,
      showEv: () => this.setState({ tab: "ev" }),
      showIv: () => this.setState({ tab: "iv" })
    };
  }
}
