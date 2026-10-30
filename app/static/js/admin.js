const updated = document.querySelector('#market-updated');
const newsClub = document.querySelector('#news-club');
const newsPreset = document.querySelector('#news-preset');
const newsPresetOptions = document.querySelector('#news-preset-options');

function refreshNewsPresets() {
    if (!newsClub || !newsPreset || !newsPresetOptions) return;
    const club = newsClub.value;
    newsPreset.replaceChildren(new Option(club ? '뉴스 문구를 선택하세요' : '동아리를 먼저 선택하세요', ''));
    if (club) {
        const options = [...newsPresetOptions.content.querySelectorAll(`[data-club="${club}"]`)];
        for (const option of options) newsPreset.append(option.cloneNode(true));
    }
    newsPreset.disabled = !club;
}

if (newsClub) newsClub.addEventListener('change', refreshNewsPresets);

async function refreshMarket() {
    if (document.hidden) return;
    try {
        const response = await fetch('/admin/api/market', {cache: 'no-store', signal: AbortSignal.timeout(15000)});
        if (response.status === 401 || response.status === 403) { location.assign('/admin/login'); return; }
        if (!response.ok) throw new Error('market unavailable');
        const data = await response.json();
        for (const stock of data.stocks) {
            const row = document.querySelector(`[data-club="${stock.club_num}"]`);
            if (!row) continue;
            const won = value => `${Math.round(value).toLocaleString('ko-KR')}원`;
            row.querySelector('[data-price]').textContent = won(stock.price);
            row.querySelector('[data-high]').textContent = won(stock.high);
            row.querySelector('[data-low]').textContent = won(stock.low);
            const rate = row.querySelector('[data-rate]');
            rate.textContent = `${stock.changeRate > 0 ? '+' : ''}${stock.changeRate.toFixed(2)}%`;
            rate.className = stock.changeRate >= 0 ? 'up' : 'down';
        }
        updated.textContent = `${new Date(data.timestamp * 1000).toLocaleString('ko-KR', {timeZone: 'Asia/Seoul'})} 갱신${data.catchingUp ? ' · 이력 복구 중' : ''}`;
    } catch {
        updated.textContent = '연결이 끊겨 마지막 데이터를 표시 중입니다. 다시 연결합니다.';
    }
}
setInterval(refreshMarket, 10000);
