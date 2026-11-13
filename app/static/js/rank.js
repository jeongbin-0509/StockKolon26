(() => {
    function podiumSlots(members) {
        return [1, 0, 2].map(index => {
            const member = members[index] || null;
            return {position: index + 1, member, tier: member ? Math.min(3, Math.max(1, member.rank)) : index + 1};
        });
    }
    if (typeof module !== 'undefined' && module.exports) module.exports = {podiumSlots};
    if (typeof document === 'undefined') return;

    const status = document.getElementById('status');
    const content = document.getElementById('ranking-content');
    const refresh = document.getElementById('refresh');
    const filters = [...document.querySelectorAll('[data-scope]')];
    const labels = {school: '전교 랭킹', class: '내 학급 랭킹', club: '내 동아리 랭킹'};
    let scope = 'school', requestNumber = 0, trophyNumber = 0;
    let rankCounts = new Map();
    const element = (tag, cls, value) => {
        const node = document.createElement(tag);
        if (cls) node.className = cls;
        if (value !== undefined) node.textContent = value;
        return node;
    };
    const rankLabel = member => `${(rankCounts.get(member.rank) || 0) > 1 ? '공동 ' : ''}${member.rank}위`;
    function avatar(member) {
        const image = element('img', 'rank-avatar');
        image.src = member.profileImg || '/static/images/default_stock_logo.png';
        image.alt = '';
        image.addEventListener('error', () => { image.src = '/static/images/default_stock_logo.png'; }, {once: true});
        return image;
    }
    function money(value, cls) {
        const node = element('strong', cls);
        node.append(document.createTextNode(value.toLocaleString('ko-KR')), element('small', '', '원'));
        return node;
    }
    function rate(member) {
        const value = Number.isFinite(member.rate) ? member.rate : null;
        return element('strong', value > 0 ? 'rate-up' : value < 0 ? 'rate-down' : '',
            value === null ? '—' : `${value > 0 ? '+' : ''}${value.toFixed(2)}%`);
    }
    function trophy(tier) {
        const colors = {
            1: ['#fff2be', '#efbb53', '#9f681e', '#fff6cf'],
            2: ['#f0f5ff', '#a8bfdc', '#5a7094', '#fff'],
            3: ['#ffdfc6', '#c58b62', '#805033', '#ffe6d0']
        }[tier];
        const id = 'rank-trophy-' + ++trophyNumber;
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('viewBox', '0 0 160 160');
        svg.setAttribute('class', 'trophy-svg');
        svg.setAttribute('aria-hidden', 'true');
        // Only fixed SVG geometry and our palette enter this markup. Member text uses textContent.
        svg.innerHTML = `
          <defs>
            <linearGradient id="${id}" x1="0" y1="0" x2="1" y2=".4">
              <stop offset="0" stop-color="${colors[2]}"/><stop offset=".2" stop-color="${colors[1]}"/>
              <stop offset=".43" stop-color="${colors[0]}"/><stop offset=".7" stop-color="${colors[1]}"/>
              <stop offset="1" stop-color="${colors[2]}"/>
            </linearGradient>
            <linearGradient id="${id}-stem" x1="0" y1="0" x2="0" y2="1">
              <stop stop-color="${colors[0]}"/><stop offset="1" stop-color="${colors[2]}"/>
            </linearGradient>
          </defs>
          <path d="M46 43H25v20c0 19 15 30 34 30M114 43h21v20c0 19-15 30-34 30"
                fill="none" stroke="url(#${id})" stroke-width="8" stroke-linejoin="round"/>
          <path d="M40 32h80l-7 42c-4 23-18 35-33 35S51 97 47 74Z"
                fill="url(#${id})" stroke="${colors[0]}" stroke-opacity=".35"/>
          <rect x="39" y="29" width="82" height="8" rx="3" fill="${colors[0]}"/>
          <path d="m52 43 5 27c2 13 7 22 14 27" fill="none" stroke="${colors[3]}" stroke-width="3" stroke-opacity=".45" stroke-linecap="round"/>
          <path d="m80 51 5.3 10.7 11.8 1.7-8.6 8.3 2 11.8L80 78l-10.5 5.5 2-11.8-8.6-8.3 11.8-1.7Z"
                fill="${colors[2]}" fill-opacity=".6" stroke="${colors[0]}" stroke-opacity=".45"/>
          <path d="M73 107h14v19H73Z" fill="url(#${id})"/>
          <path d="M63 125h34l7 10H56Z" fill="url(#${id}-stem)"/>
          <rect x="48" y="134" width="64" height="12" rx="3" fill="url(#${id})"/>
          <path d="M53 138h54" stroke="${colors[0]}" stroke-opacity=".7"/>
        `;
        return svg;
    }
    function podiumCard({position, member, tier}) {
        const card = element('article', `podium-card tier-${tier}${member?.is_me ? ' is-me' : ''}${!member ? ' is-empty' : ''}`);
        card.dataset.position = position;
        card.setAttribute('aria-label', member ? `${rankLabel(member)} ${member.name || '이름 없음'}, 총자산 ${member.assets.toLocaleString('ko-KR')}원` : `${position}번째 시상대, 아직 순위 없음`);
        const wrap = element('div', 'trophy-wrap');
        if (member && tier === 1) wrap.append(element('span', 'podium-crown-label', 'CHAMPION'));
        wrap.append(trophy(tier));
        const identity = element('div', 'podium-identity');
        if (member) {
            const person = element('a', 'podium-person member-link');
            person.href = '/members/' + encodeURIComponent(member.profile_key);
            person.append(avatar(member), element('span', 'rank-name', member.name || '이름 없음'));
            identity.append(person, element('span', 'rank-sub', member.club_name || '동아리 미선택'));
            if (window.StockCosmetics) identity.append(StockCosmetics.badge(member.cosmetics));
        } else identity.append(element('span', 'podium-empty-label', '아직 순위 없음'));
        const step = element('div', 'podium-step');
        if (member) {
            step.append(element('span', 'rank-label', '총자산'), money(member.assets, 'podium-assets'));
            const place = element('div', 'podium-rank');
            if ((rankCounts.get(member.rank) || 0) > 1) place.append(element('small', '', '공동 '));
            place.append(document.createTextNode(member.rank), element('small', '', '위'));
            step.append(place);
        } else step.append(element('div', 'podium-rank', '—'));
        if (member && window.StockCosmetics) StockCosmetics.frame(step, member.cosmetics?.frame);
        card.append(wrap, identity, step);
        return card;
    }
    function card(member, mine = false) {
        const article = element('article', `rank-card${mine ? ' my-position' : ''}${member.is_me ? ' is-me' : ''}`);
        if (!mine) article.setAttribute('role', 'listitem');
        article.setAttribute('aria-label', `${rankLabel(member)} ${member.name || '이름 없음'}${member.is_me ? ', 나의 순위' : ''}`);
        const rank = element('span', 'rank-number');
        rank.append(document.createTextNode(member.rank), element('small', '', '위'));
        if ((rankCounts.get(member.rank) || 0) > 1) rank.title = rankLabel(member);
        const person = element('a', 'rank-person member-link');
        person.href = '/members/' + encodeURIComponent(member.profile_key);
        const identity = element('div', 'rank-identity');
        const name = element('div', 'rank-name', member.name || '이름 없음');
        if (member.is_me) name.append(element('span', 'me-badge', 'ME'));
        identity.append(name, element('span', 'rank-sub', member.club_name || '동아리 미선택'));
        if (window.StockCosmetics) identity.append(StockCosmetics.badge(member.cosmetics));
        person.append(avatar(member), identity);
        const assets = element('div', 'rank-assets');
        assets.append(element('span', 'rank-label', '총자산'), money(member.assets, ''));
        const returns = element('div', 'rank-rate');
        returns.append(element('span', 'rank-label', '보유 주식 수익률'), rate(member));
        article.append(rank, person, assets, returns);
        if (window.StockCosmetics) StockCosmetics.frame(article, member.cosmetics?.frame);
        return article;
    }
    async function load(showLoading = true) {
        const current = ++requestNumber;
        refresh.disabled = true;
        content.setAttribute('aria-busy', 'true');
        if (showLoading) {
            status.hidden = false;
            status.textContent = '랭킹을 불러오는 중입니다.';
            content.hidden = true;
        }
        try {
            const response = await fetch(`/api/rankings?scope=${encodeURIComponent(scope)}`, {cache: 'no-store', signal: AbortSignal.timeout(15000)});
            const data = await response.json();
            if (current !== requestNumber) return;
            if (!response.ok || !data.success) throw new Error(data.message || '랭킹을 불러오지 못했습니다.');
            if (!data.available) {
                content.hidden = true;
                status.hidden = false;
                status.textContent = data.message;
                return;
            }
            rankCounts = new Map();
            data.members.forEach(member => rankCounts.set(member.rank, (rankCounts.get(member.rank) || 0) + 1));
            document.getElementById('my-rank').replaceChildren(card(data.me, true));
            document.getElementById('list-title').textContent = labels[scope];
            document.getElementById('member-count').textContent = `${data.count.toLocaleString('ko-KR')}명 참여 중`;
            document.getElementById('podium').replaceChildren(...podiumSlots(data.members).map(podiumCard));
            const list = document.getElementById('rank-list');
            list.replaceChildren(...data.members.slice(3).map(item => card(item)));
            if (data.members.length <= 3) {
                list.append(element('p', 'rank-list-empty', '현재 참가자 모두 시상대에 올랐어요.'));
            }
            document.querySelector('.rank-table-labels').hidden = data.members.length <= 3;
            content.hidden = false;
            status.hidden = !data.catching_up;
            if (data.catching_up) status.textContent = '시장 가격을 갱신하는 중입니다. 잠시 후 다시 확인해주세요.';
        } catch (error) {
            if (current !== requestNumber) return;
            status.hidden = false;
            status.textContent = `${error.name === 'TimeoutError' ? '서버 응답이 지연되고 있습니다.' : error.message || '랭킹을 불러오지 못했습니다.'} 새로고침을 눌러 다시 시도해주세요.`;
            content.hidden = true;
        } finally {
            if (current === requestNumber) {
                refresh.disabled = false;
                content.setAttribute('aria-busy', 'false');
            }
        }
    }
    filters.forEach(button => button.addEventListener('click', () => {
        scope = button.dataset.scope;
        filters.forEach(item => {
            const active = item === button;
            item.classList.toggle('active', active);
            item.setAttribute('aria-pressed', String(active));
        });
        load();
    }));
    refresh.addEventListener('click', () => load());
    setInterval(() => { if (!document.hidden) load(false); }, 30000);
    load();
})();
