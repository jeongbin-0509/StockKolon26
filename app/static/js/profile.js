async function loadProfileData() {
    const response = await fetch("/api/profile-data");
    const data = await response.json();

    if (!data.success) {
        alert(data.message);
        location.href = "/auth/login";
        return;
    }

    document.querySelector(".user-name").textContent = `${data.user.name}님`;
    document.querySelector(".user-rank").textContent = data.user.rank;

    document.querySelector("#card-total-assets .summary-value").textContent =
        data.summary.total_assets;

    document.querySelector("#card-total-assets .summary-change").textContent =
        data.summary.daily_change;

    document.querySelector("#card-total-assets .summary-change-pct").textContent =
        data.summary.daily_rate;

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
    }
}

loadProfileData();