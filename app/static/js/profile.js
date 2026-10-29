async function loadProfileData() {
    const response = await fetch("/api/profile-data");
    const data = await response.json();

    if (!data.success) {
        alert(data.message);
        location.href = "/auth/login";
        return;
    }

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

    const topRows = document.querySelectorAll("#card-top .top-row");

    topRows[0].querySelector(".top-stock-name").textContent = data.top.up_name;
    topRows[0].querySelector(".top-stock-info").textContent = data.top.up_info;
    topRows[0].querySelector(".top-stock-pct").textContent = data.top.up_rate;

    topRows[1].querySelector(".top-stock-name").textContent = data.top.down_name;
    topRows[1].querySelector(".top-stock-info").textContent = data.top.down_info;
    topRows[1].querySelector(".top-stock-pct").textContent = data.top.down_rate;

    const tbody = document.querySelector("#holdings-table tbody");
    tbody.innerHTML = "";

    if (data.holdings.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6" class="head2" style="text-align:center;">
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
                `${item.rate >= 0 ? '+' : ''}${item.rate.toFixed(2)}%`, '—'];
            values.forEach((value, index) => {
                const cell = document.createElement('td');
                cell.className = 'head2';
                if (index === 3 || index === 4) cell.classList.add(item.profit < 0 ? 'negative' : 'positive');
                cell.textContent = value;
                row.appendChild(cell);
            });
            tbody.appendChild(row);
        }
    }
    const history = document.querySelector('#trade-history-list');
    history.replaceChildren();
    if (!data.orders.length) {
        history.textContent = '아직 거래 내역이 없습니다.';
    } else {
        for (const order of data.orders) {
            const row = document.createElement('div');
            row.className = 'trade-history-row';
            const date = new Date(order.timestamp * 1000).toLocaleString('ko-KR', {timeZone: 'Asia/Seoul'});
            const title = document.createElement('strong');
            title.textContent = `${order.club_name} · ${order.side === 'buy' ? '매수' : '매도'} ${order.quantity.toLocaleString('ko-KR')}주`;
            const detail = document.createElement('span');
            detail.textContent = `${order.price.toLocaleString('ko-KR')}원 · 총 ${order.total.toLocaleString('ko-KR')}원 · ${date}`;
            row.append(title, detail);
            history.appendChild(row);
        }
    }
}

loadProfileData();
