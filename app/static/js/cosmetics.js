(() => {
    const ids = new Set(['prologue','prime','apex','sovereign','earlybird','tracker','oracle','anchor','slayer']);
    const el = (tag, cls, text) => {
        const node = document.createElement(tag);
        if (cls) node.className = cls;
        if (text !== undefined) node.textContent = text;
        return node;
    };
    function badge(value) {
        const node = el('span', 'signature-badge', value?.name || '');
        node.hidden = !ids.has(value?.signature);
        if (!node.hidden) node.dataset.style = value.signature;
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
