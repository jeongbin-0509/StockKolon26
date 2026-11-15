(() => {
    const ids = new Set(['prologue','prime','apex','sovereign','earlybird','tracker','oracle','anchor','slayer']);
    // Inline vector emblems stay crisp at header size and never depend on fonts.
    const emblems = {
        prologue: 'M4 5h6l2 2 2-2h6v14h-6l-2 2-2-2H4ZM12 7v14',
        prime: 'M12 2 21 7v10l-9 5-9-5V7ZM7 15l5-7 5 7M9 13h6',
        apex: 'M2 20 12 3l10 17H2ZM8 20l4-7 4 7M12 3v5',
        sovereign: 'M3 7l5 4 4-7 4 7 5-4-3 12H6ZM6 22h12M12 1v1',
        earlybird: 'M4 17a8 8 0 0 1 16 0M2 20h20M12 2v3M3 6l2 2M21 6l-2 2M1 13h3M20 13h3',
        tracker: 'M8 3H3v5M16 3h5v5M3 16v5h5M21 16v5h-5M7 17l10-10M10 7h7v7',
        oracle: 'M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12ZM12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8ZM12 1v2M12 21v2',
        anchor: 'M12 8v13M8 11h8M4 14v3c0 3 8 5 8 5s8-2 8-5v-3M2 16l2-2 2 2M18 16l2-2 2 2M12 2a3 3 0 1 0 0 6 3 3 0 0 0 0-6',
        slayer: 'M4 2l8 8-3 3L2 4ZM20 2l-8 8 3 3 7-9ZM5 14l5 5M14 5l5 5M3 21l6-6M15 9l6-6M14 14l7 7M14 19l5-5',
    };
    const corners = {
        prologue: ['M5 30V5h30'],
        prime: ['M2 40V12L12 2h42l-9 6H15l-7 7v18Z', 'M14 34V16h26M19 21h8'],
        apex: ['M5 48 0 20 10 28 5 0 27 16 25 4 57 15 35 21 46 31 22 25Z', 'M5 0 22 25 0 20M27 16 22 25 35 21M5 48 22 25'],
        sovereign: ['M8 52C-3 35 0 13 9 4L16 20C23 8 39 1 63 3L47 12 58 13 39 21 48 24 29 29C19 29 12 39 8 52Z', 'M8 52Q7 23 46 9M16 31 9 15M23 23l-3-10M23 23l18 1M34 15l14-1'],
        earlybird: ['M5 36A31 31 0 0 1 36 5M12 36A24 24 0 0 1 36 12M4 15l7 3M15 4l3 7'],
        tracker: ['M2 38V8l6-6h30M10 30V10h20M18 22l9-9M22 13h5v5'],
        oracle: ['M4 36V13l9-9h23M10 27l17-17M5 6l5-5 5 5-5 5ZM21 26l5-5 5 5-5 5Z'],
        anchor: ['M5 40V17A12 12 0 0 1 17 5h23M11 40V17a6 6 0 0 1 6-6h23M2 22h12M22 2v12'],
        slayer: ['M0 55 6 6 18 0 12 25ZM15 45 23 12 48 0 32 19ZM31 35 45 13 72 8 52 24Z', 'M6 6l6 19M23 12l9 7M45 13l7 11'],
    };
    const crests = {
        apex: ['M9 29 37 23 32 10 48 19 60 0 72 19 88 10 83 23 111 29 75 32 60 23 45 32Z', 'M60 0v23M48 19l12 4 12-4M32 10l13 22M88 10 75 32'],
        sovereign: ['M25 8 43 17 60 1 77 17 95 8 87 31H33ZM8 30l15-9 4 10ZM112 30l-15-9-4 10Z', 'M33 26h54M60 11l5 7-5 7-5-7ZM39 20l3 6M81 20l-3 6'],
        slayer: ['M9 0 48 17 60 13 72 17 111 0 86 27 76 24 60 35 44 24 34 27ZM43 6l17 7 17-7-7 14H50Z', 'M9 0l35 24M111 0 76 24M60 19v10M53 19l3 2M67 19l-3 2'],
    };
    function vector(paths, viewBox, cls, plated = false) {
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('viewBox', viewBox); svg.setAttribute('class', cls);
        svg.setAttribute('aria-hidden', 'true'); svg.setAttribute('focusable', 'false');
        paths.forEach((d, i) => {
            const path = document.createElementNS(svg.namespaceURI, 'path');
            path.setAttribute('d', d);
            path.setAttribute('class', plated && i === 0 ? 'frame-plate' : 'frame-engraving');
            svg.append(path);
        });
        return svg;
    }
    const el = (tag, cls, text) => {
        const node = document.createElement(tag);
        if (cls) node.className = cls;
        if (text !== undefined) node.textContent = text;
        return node;
    };
    function badge(value) {
        const node = el('span', 'signature-badge', value?.name || '');
        node.hidden = !ids.has(value?.signature);
        if (!node.hidden) {
            node.dataset.style = value.signature;
            node.prepend(vector([emblems[value.signature]], '0 0 24 24', 'signature-emblem'));
        }
        return node;
    }
    function frame(box, id) {
        if (!box) return;
        box.querySelector(':scope > .frame-ornament')?.remove();
        box.classList.toggle('cosmetic-frame', ids.has(id));
        if (ids.has(id)) {
            box.dataset.style = id;
            const ornament = el('span', 'frame-ornament');
            ornament.setAttribute('aria-hidden', 'true');
            for (const position of ['tl','tr','bl','br']) {
                ornament.append(vector(corners[id], '0 0 72 60', `frame-corner corner-${position}`, ['prime','apex','sovereign','slayer'].includes(id)));
            }
            if (crests[id]) ornament.append(vector(crests[id], '0 0 120 36', 'frame-crest', true));
            else if (['earlybird','oracle','anchor'].includes(id)) ornament.append(vector([emblems[id]], '0 0 24 24', 'frame-sigil'));
            ornament.append(el('span', 'frame-energy energy-left'), el('span', 'frame-energy energy-right'));
            box.append(ornament);
        } else delete box.dataset.style;
        return box;
    }
    function label(name, value) {
        if (!name) return;
        let stack = name.parentElement;
        if (!stack.classList.contains('cosmetic-name')) {
            stack = el('span', 'cosmetic-name');
            name.replaceWith(stack);
            stack.append(name);
        }
        stack.querySelector('.signature-badge')?.remove();
        stack.append(badge(value));
    }
    window.StockCosmetics = {badge, frame, label};

    const token = () => document.querySelector('meta[name="cosmetics-csrf"]')?.content;
    async function post(path, body) {
        const response = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':token()},
            body:JSON.stringify(body), signal:AbortSignal.timeout(15000)});
        const data = await response.json();
        if (!response.ok || !data.success) throw new Error(data.message || '저장하지 못했습니다. 다시 시도해주세요.');
        return data;
    }
    document.addEventListener('DOMContentLoaded', () => {
        let visiting = false;
        async function visit() {
            if (document.hidden || visiting || !token()) return;
            visiting = true;
            try { await post('/api/cosmetics/visit', {}); } catch (_) {} finally { visiting = false; }
        }
        visit();
        setInterval(visit, 60000);
        document.addEventListener('visibilitychange', () => { if (!document.hidden) visit(); });
        const memberData = document.getElementById('member-portfolio-data');
        if (memberData) {
            try {
                const user = JSON.parse(memberData.textContent).user;
                label(document.querySelector('.member-hero h1'), user.cosmetics);
            } catch (_) {}
        }
        const root = document.getElementById('cosmetic-collection');
        if (!root) return;
        const status = document.getElementById('cosmetic-status');
        const count = document.getElementById('cosmetic-count');
        const grid = document.getElementById('cosmetic-grid');
        const preview = document.getElementById('cosmetic-preview');
        let collection, photo = '/static/images/default_stock_logo.png', userName = '나의 프로필', saving = false;
        function progressText(item) {
            if (item.unlocked) return item.id === 'prologue' ? '기본 지급' : '획득 완료';
            if (['prime','apex','sovereign','anchor'].includes(item.id)) {
                const mins = Math.floor(item.progress / 60);
                return `${Math.floor(mins/60)}시간 ${mins%60}분 / ${item.goal/3600}시간`;
            }
            if (item.id === 'tracker') return `${item.progress} / 200계단`;
            if (item.id === 'oracle') return `${item.progress} / 5회 연속`;
            return '조건 달성 시 획득';
        }
        function render() {
            count.textContent = `${collection.items.filter(item => item.unlocked).length} / ${collection.items.length} UNLOCKED`;
            const img = el('img'); img.src = photo; img.alt = '프로필 사진';
            const identity = el('div', 'collection-identity');
            identity.append(el('small', '', 'EQUIPPED'), el('strong', '', userName), badge(collection.equipped));
            preview.replaceChildren(img, identity);
            frame(preview, collection.equipped.frame);
            grid.replaceChildren(...collection.items.map((item, index) => {
                const card = el('article', 'cosmetic-card'); card.dataset.style = item.id;
                card.dataset.locked = String(!item.unlocked);
                const top = el('div', 'cosmetic-card-top');
                top.append(el('span', '', item.tier), el('span', '', String(index+1).padStart(2,'0')));
                const artwork = el('div', 'cosmetic-artwork');
                const avatar = el('img'); avatar.src = photo; avatar.alt = '프로필 사진';
                artwork.setAttribute('aria-label', `${item.frame} 리더보드 카드 프레임 미리보기`);
                artwork.append(avatar, badge({signature:item.id, name:item.name}));
                frame(artwork, item.id);
                const frameName = el('p', 'cosmetic-frame-name', item.frame + ' FRAME');
                const condition = el('p', 'cosmetic-condition', item.condition);
                const progress = el('progress'); progress.max = item.goal; progress.value = item.unlocked ? item.goal : item.progress;
                progress.setAttribute('aria-label', item.name + ' 획득 진행');
                const note = el('span', 'cosmetic-progress', progressText(item));
                const actions = el('div', 'cosmetic-actions');
                for (const [kind, title] of [['signature','시그니처'],['frame','프레임']]) {
                    const selected = collection.equipped[kind] === item.id;
                    const button = el('button', '', item.unlocked ? `${title} ${selected ? '해제' : '장착'}` : `${title} 잠김`);
                    button.type = 'button'; button.disabled = !item.unlocked || saving;
                    button.setAttribute('aria-pressed', String(selected));
                    button.setAttribute('aria-label', `${item.name} ${button.textContent}`);
                    button.addEventListener('click', () => equip(kind, selected ? null : item.id));
                    actions.append(button);
                }
                card.append(top, artwork, frameName, condition, progress, note, actions);
                return card;
            }));
        }
        async function equip(kind, id) {
            if (saving) return;
            saving = true; render(); status.textContent = '장착 정보를 저장하고 있습니다.';
            try {
                const data = await post('/api/cosmetics/equip', {signature:collection.equipped.signature, frame:collection.equipped.frame, [kind]:id});
                collection.equipped = data.equipped;
                if (window.updateHeaderProfile) updateHeaderProfile({name:userName, profileImg:photo, cosmetics:data.equipped});
                status.textContent = '프로필에 적용했습니다.';
            } catch (error) { status.textContent = error.message; }
            finally { saving = false; render(); }
        }
        document.addEventListener('profile-image-changed', event => {
            if (event.detail?.profileImg) { photo = event.detail.profileImg; if (collection) render(); }
        });
        async function load() {
            status.textContent = '컬렉션을 불러오는 중입니다.';
            try {
                const [response, profile] = await Promise.all([fetch('/api/cosmetics', {cache:'no-store', signal:AbortSignal.timeout(20000)}),
                    fetch('/api/header-profile').then(r=>r.ok?r.json():null).catch(()=>null)]);
                const data = await response.json();
                if (!response.ok || !data.success) throw new Error(data.message || '컬렉션을 불러오지 못했습니다.');
                collection = data;
                if (profile?.user) { photo = profile.user.profileImg || photo; userName = profile.user.name || userName; }
                render(); status.textContent = data.catching_up ? '시장 기록을 복구 중입니다. 잠시 후 새로고침해주세요.' : '획득한 시그니처와 프레임을 자유롭게 조합하세요.';
            } catch (error) { status.textContent = error.message; }
        }
        document.getElementById('cosmetic-refresh').addEventListener('click', load);
        load();
    });
})();
