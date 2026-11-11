(() => {
  const STORE = 'imas-presen-v1';
  const sheet = document.getElementById('sheet');
  let DATA = null;
  let state = null;
  const openPickers = new Set();

  const uid = () => Math.random().toString(36).slice(2, 9);
  const newSong = () => ({ id: uid(), theme: '', title: '', text: '', jacket: '', members: [] });
  const defaultState = () => ({
    producer: '', from: '765', to: 'cg', customMembers: {}, songs: [newSong()]
  });
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const brand = id => DATA.brands.find(b => b.id === id);

  function save() {
    try { localStorage.setItem(STORE, JSON.stringify(state)); }
    catch (e) { /* 容量超過(大きい画像)などは無視 */ }
  }
  function load() {
    try {
      const raw = localStorage.getItem(STORE);
      if (raw) return Object.assign(defaultState(), JSON.parse(raw));
    } catch (e) {}
    return defaultState();
  }

  function brandOptions(sel) {
    return DATA.brands.map(b =>
      `<option value="${b.id}"${b.id === sel ? ' selected' : ''}>${esc(b.name)}</option>`).join('');
  }
  function candidates(brandId) {
    const b = brand(brandId);
    return [...b.members, ...(state.customMembers[brandId] || [])];
  }

  function songHTML(s) {
    const cands = candidates(state.to);
    const chips = s.members.map(m =>
      `<span class="chip">${esc(m)}<button class="no-export" data-a="rm" data-m="${esc(m)}" title="外す">×</button></span>`).join('');
    const picker = openPickers.has(s.id) ? `
      <div class="picker no-export">
        <div class="opts">${cands.map(m =>
          `<button class="opt${s.members.includes(m) ? ' on' : ''}" data-a="tog" data-m="${esc(m)}">${esc(m)}</button>`).join('')}</div>
        <div class="custom">
          <input type="text" class="custom-in" placeholder="一覧にない名前を追加">
          <button data-a="custom">追加</button>
        </div>
      </div>` : '';
    return `
    <section class="song" data-id="${s.id}">
      <div class="song-head">
        <input type="text" class="theme" data-f="theme" placeholder="○○な曲" value="${esc(s.theme)}">
        <button class="del no-export" data-a="del" title="この曲を削除">✕</button>
      </div>
      <div class="song-body">
        <label class="jacket">
          ${s.jacket ? `<img src="${s.jacket}" alt="jacket">` : 'ジャケット<br>クリックで画像を選択'}
          <input type="file" accept="image/*" data-a="jacket" hidden>
        </label>
        <div class="info">
          <input type="text" class="title" data-f="title" placeholder="曲名" value="${esc(s.title)}">
          <textarea class="text" data-f="text" placeholder="プレゼン内容（おすすめポイントなど）">${esc(s.text)}</textarea>
          <div class="members">
            <span class="label">歌唱予想</span>${chips}
            <button class="add-member no-export" data-a="pick">${openPickers.has(s.id) ? '閉じる' : '＋ メンバー'}</button>
          </div>
          ${picker}
        </div>
      </div>
    </section>`;
  }

  function render() {
    const b = brand(state.to);
    document.documentElement.style.setProperty('--accent', b.color);
    sheet.innerHTML = `
      <div class="sheet-head">
        <div class="producer">
          <input type="text" id="producer" placeholder="名無しP" value="${esc(state.producer)}"><span>P</span>
        </div>
        <div class="route">
          <select id="from">${brandOptions(state.from)}</select><span>から</span>
          <select id="to">${brandOptions(state.to)}</select><span>へのオススメ曲</span>
        </div>
      </div>
      ${state.songs.map(songHTML).join('')}
      <button class="add-song no-export" data-a="add">＋ 新しい曲を追加する</button>`;
  }

  // ---- 入力 ----
  sheet.addEventListener('input', e => {
    const t = e.target;
    if (t.id === 'producer') state.producer = t.value;
    else if (t.dataset.f) {
      const s = state.songs.find(x => x.id === t.closest('.song').dataset.id);
      s[t.dataset.f] = t.value;
    } else return;
    save();
  });

  sheet.addEventListener('change', e => {
    const t = e.target;
    if (t.id === 'from') { state.from = t.value; save(); }
    else if (t.id === 'to') { state.to = t.value; save(); render(); }
    else if (t.dataset.a === 'jacket' && t.files[0]) {
      const song = state.songs.find(x => x.id === t.closest('.song').dataset.id);
      const reader = new FileReader();
      reader.onload = () => {
        shrinkImage(reader.result, 600).then(url => { song.jacket = url; save(); render(); });
      };
      reader.readAsDataURL(t.files[0]);
    }
  });

  // 保存容量対策でジャケットを縮小
  function shrinkImage(src, max) {
    return new Promise(res => {
      const img = new Image();
      img.onload = () => {
        const r = Math.min(1, max / Math.max(img.width, img.height));
        const c = document.createElement('canvas');
        c.width = Math.round(img.width * r); c.height = Math.round(img.height * r);
        c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
        res(c.toDataURL('image/jpeg', 0.88));
      };
      img.onerror = () => res(src);
      img.src = src;
    });
  }

  sheet.addEventListener('click', e => {
    const btn = e.target.closest('[data-a]');
    if (!btn || btn.tagName === 'INPUT') return;
    const a = btn.dataset.a;
    if (a === 'add') { state.songs.push(newSong()); save(); render(); return; }
    const card = btn.closest('.song');
    if (!card) return;
    const s = state.songs.find(x => x.id === card.dataset.id);
    if (a === 'del') {
      if (state.songs.length > 1 && !confirm('この曲を削除しますか？')) return;
      state.songs = state.songs.filter(x => x !== s);
      if (!state.songs.length) state.songs.push(newSong());
    } else if (a === 'pick') {
      openPickers.has(s.id) ? openPickers.delete(s.id) : openPickers.add(s.id);
    } else if (a === 'tog') {
      const m = btn.dataset.m;
      s.members = s.members.includes(m) ? s.members.filter(x => x !== m) : [...s.members, m];
    } else if (a === 'rm') {
      s.members = s.members.filter(x => x !== btn.dataset.m);
    } else if (a === 'custom') {
      const name = card.querySelector('.custom-in').value.trim();
      if (!name) return;
      const list = state.customMembers[state.to] = state.customMembers[state.to] || [];
      if (!candidates(state.to).includes(name)) list.push(name);
      if (!s.members.includes(name)) s.members.push(name);
    } else return;
    save(); render();
  });

  // ---- 画像出力 ----
  document.getElementById('btn-save').addEventListener('click', async () => {
    if (typeof html2canvas === 'undefined') {
      alert('画像化ライブラリを読み込めませんでした。ネットワークを確認してください。');
      return;
    }
    const canvas = await html2canvas(sheet, {
      scale: 2, backgroundColor: '#ffffff', useCORS: true,
      onclone: doc => {
        const root = doc.getElementById('sheet');
        root.querySelectorAll('.no-export').forEach(el => el.remove());
        root.querySelectorAll('input[type=text], textarea, select').forEach(el => {
          const div = doc.createElement('div');
          let v = el.tagName === 'SELECT' ? el.options[el.selectedIndex].text : el.value;
          if (el.id === 'producer' && !v.trim()) v = '名無し';
          div.className = 'ex-text ' + (el.className || '') + ' ' + (el.id || '');
          div.textContent = v;
          if (el.tagName === 'SELECT') div.className += ' brand-from';
          el.replaceWith(div);
        });
        root.querySelectorAll('.ex-text').forEach(el => {
          el.style.border = 'none'; el.style.background = 'none'; el.style.padding = '0';
        });
        root.querySelectorAll('.song-head .ex-text').forEach(el => { el.style.color = '#fff'; });
        root.querySelectorAll('.ex-text.title').forEach(el => {
          el.style.borderBottom = '2px solid ' + getComputedStyle(doc.documentElement).getPropertyValue('--accent');
          el.style.paddingBottom = '2px';
        });
        // 空の曲名・内容・題名は枠だけ残さない
      }
    });
    const a = document.createElement('a');
    const name = (state.producer.trim() || '名無し') + 'P_布教シート.png';
    a.download = name;
    a.href = canvas.toDataURL('image/png');
    a.click();
  });

  document.getElementById('btn-reset').addEventListener('click', () => {
    if (!confirm('入力内容をすべて消して最初の状態に戻します。よろしいですか？')) return;
    state = defaultState(); openPickers.clear(); save(); render();
  });

  // ---- 起動 ----
  fetch('members.json')
    .then(r => r.json())
    .then(d => { DATA = d; state = load(); if (!brand(state.from)) state.from = d.brands[0].id;
      if (!brand(state.to)) state.to = d.brands[1].id; render(); })
    .catch(() => {
      sheet.innerHTML = '<p>members.json を読み込めませんでした。GitHub Pages上、またはローカルサーバー経由で開いてください。</p>';
    });
})();
