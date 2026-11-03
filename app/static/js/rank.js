(() => {
    const status = document.getElementById('status');
    const content = document.getElementById('ranking-content');
    const filters = [...document.querySelectorAll('[data-scope]')];
    const labels = {school: '전교 랭킹', class: '내 학급 랭킹', club: '내 동아리 랭킹'};
    let scope = 'school', requestNumber = 0;
    const element = (tag, cls, value) => {
        const node = document.createElement(tag);
        if (cls) node.className = cls;
        if (value !== undefined) node.textContent = value;
        return node;
    };
    function card(member, podium = false) {
        const article = element('article', `${podium ? 'podium-card' : 'rank-card'}${member.is_me ? ' is-me' : ''}`);
        article.append(element('span', 'rank-number', `${member.rank}위`));
        const img = element('img', 'rank-avatar');
        img.src = member.profileImg;
        img.alt = '';
        article.append(img);
        const identity = element('div', 'rank-identity');
        identity.append(element('div', 'rank-name', `${member.name || '이름 없음'}${member.is_me ? ' (나)' : ''}`));
        identity.append(element('span', 'rank-sub', member.club_name || '동아리 미선택'));
        article.append(identity);
        const values = element('div', 'rank-values');
        const assets = element('div');
        assets.append(element('span', 'rank-label', '총자산'), element('strong', '', `${member.assets.toLocaleString('ko-KR')}원`));
        const rate = element('div');
        rate.append(element('span', 'rank-label', '보유 주식 수익률'));
        const rateText = member.rate === null ? '—' : `${member.rate > 0 ? '+' : ''}${member.rate.toFixed(2)}%`;
        rate.append(element('strong', member.rate > 0 ? 'rate-up' : member.rate < 0 ? 'rate-down' : '', rateText));
        values.append(assets, rate);
        article.append(values);
        return article;
    }
    async function load(showLoading = true) {
        const current = ++requestNumber;
        if (showLoading) { status.hidden = false; status.textContent = '랭킹을 불러오는 중입니다.'; content.hidden = true; }
        try {
            const response = await fetch(`/api/rankings?scope=${encodeURIComponent(scope)}`, {cache: 'no-store'});
            const data = await response.json();
            if (current !== requestNumber) return;
            if (!response.ok || !data.success) throw new Error(data.message || '랭킹을 불러오지 못했습니다.');
            if (!data.available) { content.hidden = true; status.hidden = false; status.textContent = data.message; return; }
            document.getElementById('my-rank').replaceChildren(card(data.me));
            document.getElementById('list-title').textContent = labels[scope];
            document.getElementById('member-count').textContent = `${data.count.toLocaleString('ko-KR')}명 참여`;
            document.getElementById('podium').replaceChildren(...data.members.slice(0, 3).map(item => card(item, true)));
            document.getElementById('rank-list').replaceChildren(...data.members.slice(3).map(item => card(item)));
            content.hidden = false;
            status.hidden = !data.catching_up;
            if (data.catching_up) status.textContent = '시장 가격을 갱신하는 중입니다. 잠시 후 다시 확인해주세요.';
        } catch (error) {
            if (current !== requestNumber) return;
            status.hidden = false;
            status.textContent = `${error.message || '랭킹을 불러오지 못했습니다.'} 새로고침을 눌러 다시 시도해주세요.`;
            content.hidden = true;
        }
    }
    filters.forEach(button => button.addEventListener('click', () => {
        scope = button.dataset.scope;
        filters.forEach(item => { const active = item === button; item.classList.toggle('active', active); item.setAttribute('aria-pressed', String(active)); });
        load();
    }));
    document.getElementById('refresh').addEventListener('click', () => load());
    setInterval(() => { if (!document.hidden) load(false); }, 30000);
    load();
})();
