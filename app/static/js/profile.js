function renderProfileData(data, updateHistory) {
    document.querySelector(".user-name").textContent = `${data.user.name}님`;
    updateHeaderProfile(data.user);
    document.querySelector(".user-rank").textContent = data.user.rank;

    document.querySelector("#card-total-assets .summary-value").textContent =
        data.summary.total_assets;

    document.querySelector("#card-total-assets .summary-change").textContent =
        data.summary.daily_change;

    document.querySelector("#card-total-assets .summary-change-pct").textContent =
        data.summary.daily_rate;
    const profitClass = data.summary.daily_change.startsWith('-') ? 'negative' : 'positive';
    document.querySelector('#card-total-assets .summary-change').className = `summary-change ${profitClass} head1`;
    document.querySelector('#card-total-assets .summary-change-pct').className = `summary-change-pct ${profitClass} head3`;

    document.querySelector("#card-purchase > .summary-value").textContent =
        data.summary.purchase_amount;

    document.querySelector("#card-purchase .summary-sub .summary-value").textContent =
        data.summary.cash;

    const tbody = document.querySelector("#holdings-table tbody");
    const focusedLink = tbody.contains(document.activeElement)
        ? document.activeElement.getAttribute('href') : null;
    tbody.querySelectorAll('.mini-chart').forEach(StockolonCharts.disposeChart);
    tbody.innerHTML = "";

    if (data.holdings.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7" class="head2" style="text-align:center;">
                    아직 보유한 주식이 없습니다.
                </td>
            </tr>
        `;
    } else {
        for (const item of data.holdings) {
            const row = document.createElement('tr');
            row.className = 'holding-row';
            const values = [item.name, `${item.quantity.toLocaleString('ko-KR')}주`,
                `${item.price.toLocaleString('ko-KR')}원`, `${item.profit >= 0 ? '+' : ''}${item.profit.toLocaleString('ko-KR')}원`,
                `${item.rate >= 0 ? '+' : ''}${item.rate.toFixed(2)}%`];
            values.forEach((value, index) => {
                const cell = document.createElement('td');
                cell.className = 'head2';
                if (index === 3 || index === 4) cell.classList.add(item.profit < 0 ? 'negative' : 'positive');
                cell.textContent = value;
                row.appendChild(cell);
            });
            const chartCell = document.createElement('td');
            chartCell.className = 'chart-cell';
            const chart = document.createElement('div');
            chart.className = 'mini-chart';
            StockolonCharts.renderCandlestickChart(chart, {
                candles: item.candles,
                compact: true,
                ariaLabel: `${item.name} 최근 30분 5분봉 가격 차트`
            });
            chartCell.append(chart);
            row.appendChild(chartCell);
            const actionCell = document.createElement('td');
            actionCell.className = 'holding-actions-cell';
            const actions = document.createElement('div');
            actions.className = 'holding-actions';
            const buy = document.createElement('a');
            buy.className = 'holding-trade-button buy-action';
            buy.href = `/buy?club=${encodeURIComponent(item.club_num)}&side=buy`;
            buy.textContent = '추가 매수';
            buy.setAttribute('aria-label', `${item.name} 추가 매수`);
            const sell = document.createElement('a');
            sell.className = 'holding-trade-button sell-action';
            sell.href = `/buy?club=${encodeURIComponent(item.club_num)}&side=sell`;
            sell.textContent = '매도';
            sell.setAttribute('aria-label', `${item.name} 매도`);
            actions.append(buy, sell);
            actionCell.append(actions);
            row.appendChild(actionCell);
            tbody.appendChild(row);
        }
    }
    if (focusedLink) {
        const link = Array.from(tbody.querySelectorAll('a'))
            .find(item => item.getAttribute('href') === focusedLink);
        if (link) link.focus({ preventScroll: true });
    }
    if (!updateHistory) return;

    const history = document.querySelector('#trade-history-list');
    history.replaceChildren();
    if (!data.orders.length) {
        history.textContent = '아직 거래 내역이 없습니다.';
    } else {
        const more = document.createElement('details');
        more.className = 'trade-history-more';
        const toggle = document.createElement('summary');
        const remaining = data.orders.length - 3;
        const updateToggle = () => {
            toggle.textContent = more.open ? '거래 내역 접기' : `이전 거래 ${remaining}개 펼쳐보기`;
        };
        updateToggle();
        more.addEventListener('toggle', updateToggle);
        more.append(toggle);
        for (const [index, order] of data.orders.entries()) {
            const row = document.createElement('div');
            row.className = 'trade-history-row';
            const date = new Date(order.timestamp * 1000).toLocaleString('ko-KR', {timeZone: 'Asia/Seoul'});
            const title = document.createElement('strong');
            title.textContent = `${order.club_name} · ${order.side === 'buy' ? '매수' : '매도'} ${order.quantity.toLocaleString('ko-KR')}주`;
            const detail = document.createElement('span');
            detail.textContent = `${order.price.toLocaleString('ko-KR')}원 · 총 ${order.total.toLocaleString('ko-KR')}원 · ${date}`;
            row.append(title, detail);
            (index < 3 ? history : more).appendChild(row);
        }
        if (remaining > 0) history.append(more);
    }
}

let profileRefreshTimer;
let profileLoading = false;
let profileLoaded = false;
let profileSessionExpired = false;

async function loadProfileData() {
    clearTimeout(profileRefreshTimer);
    if (profileLoading || document.hidden || profileSessionExpired) return;
    profileLoading = true;
    const status = document.querySelector('#profile-update-status');
    try {
        const response = await fetch('/api/profile-data', {
            cache: 'no-store',
            signal: AbortSignal.timeout(15000)
        });
        if (response.status === 401) {
            profileSessionExpired = true;
            location.assign('/auth/login');
            return;
        }
        if (!response.ok) throw new Error('Profile unavailable');
        const data = await response.json();
        if (!data.success) throw new Error('Profile unavailable');
        renderProfileData(data, !profileLoaded);
        profileLoaded = true;
        status.hidden = true;
        status.textContent = '';
    } catch (error) {
        status.textContent = profileLoaded
            ? '연결이 원활하지 않아 마지막으로 받은 정보를 표시하고 있어요. 잠시 후 자동으로 다시 시도합니다.'
            : '프로필 정보를 불러오지 못했어요. 잠시 후 자동으로 다시 시도합니다.';
        status.hidden = false;
    } finally {
        profileLoading = false;
        if (!document.hidden && !profileSessionExpired) {
            profileRefreshTimer = setTimeout(loadProfileData, 10000);
        }
    }
}

document.addEventListener('visibilitychange', () => {
    clearTimeout(profileRefreshTimer);
    if (!document.hidden) loadProfileData();
});
window.addEventListener('pageshow', event => {
    if (event.persisted) loadProfileData();
});
loadProfileData();
