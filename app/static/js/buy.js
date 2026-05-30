const stockGrid = document.querySelector(".stock-grid");
const categoryFilter = document.querySelector(".stock-category-filter");
const imageBase = stockGrid?.dataset.imageBase || "/static/images/";
const defaultLogo = `${imageBase}default_stock_logo.png`;
const clubImageFiles = {
    1: "1.jpg",
    2: "2.jpg",
    12: "12.jpg",
    13: "13.png",
    14: "14.png",
    21: "21.png",
    31: "31.png",
    32: "32.jpg",
    41: "41.png",
    43: "43.jpg",
    54: "54.jpg",
    61: "61.jpg",
    71: "71.jpg",
    72: "72.jpg",
    73: "73.png",
    75: "75.jpg",
    76: "76.jpg",
    83: "83.png",
    84: "84.jpg"
};

const categoryNames = {
    0: "공식",
    1: "수학",
    2: "물리/지구",
    3: "화학",
    4: "생명",
    5: "실험/공학",
    6: "정보",
    7: "문과",
    8: "기타"
};

function categoryKey(clubNum) {
    return Math.floor(Number(clubNum) / 10);
}

function categoryOf(clubNum) {
    return categoryNames[categoryKey(clubNum)] || "기타";
}

function formatWon(value) {
    return `${Math.round(value).toLocaleString("ko-KR")}원`;
}

function seededValue(seed, min, max) {
    const x = Math.sin(seed * 999) * 10000;
    return Math.floor((x - Math.floor(x)) * (max - min + 1)) + min;
}

function stockDataFor(club) {
    const seed = Number(club.club_num);
    const price = seededValue(seed, 6700, 102400);
    const changeRate = (seed % 5 === 2 ? -1 : 1) * (seededValue(seed + 4, 180, 730) / 100);
    const changeWon = Math.round(price * Math.abs(changeRate) / 100);

    return {
        ...club,
        price,
        changeRate,
        changeWon,
        trend: changeRate >= 0 ? "up" : "down",
        categoryKey: categoryKey(club.club_num),
        category: categoryOf(club.club_num),
        owned: seededValue(seed + 9, 0, 19),
        high: price + seededValue(seed + 1, 8000, 36000),
        low: Math.max(1000, price - seededValue(seed + 2, 3000, 18000))
    };
}

function setClubImage(img, clubNum) {
    const fileName = clubImageFiles[Number(clubNum)];
    img.onerror = () => {
        img.onerror = null;
        img.src = defaultLogo;
    };
    img.src = fileName ? `${imageBase}${fileName}` : defaultLogo;
}

function chartPoints(seed, trend, width = 420, height = 150) {
    const points = [];
    const count = 13;

    for (let i = 0; i < count; i += 1) {
        const x = 10 + (i * (width - 20)) / (count - 1);
        const drift = trend === "up" ? (count - i) * 5 : i * 5;
        const noise = seededValue(seed + i, 16, height - 38);
        const y = Math.max(18, Math.min(height - 18, noise + drift));
        points.push(`${Math.round(x)},${Math.round(y)}`);
    }

    return points.join(" ");
}

function createStockCard(rawClub) {
    const stock = stockDataFor(rawClub);
    const card = document.createElement("article");
    card.className = "stock-card";
    card.tabIndex = 0;
    card.setAttribute("role", "button");
    card.dataset.stock = JSON.stringify(stock);

    card.innerHTML = `
        <div class="stock-top">
            <img alt="${stock.club_name} 로고" class="stock-logo">
            <div>
                <h2>${stock.club_name}</h2>
                <p>${stock.category}</p>
            </div>
        </div>
        <div class="stock-value ${stock.trend}">
            <strong>${formatWon(stock.price)}</strong>
            <span>${stock.changeRate > 0 ? "+" : ""}${stock.changeRate.toFixed(2)}% ${stock.trend === "up" ? "↗" : "↘"}</span>
        </div>
        <svg class="stock-chart ${stock.trend}-chart" viewBox="0 0 420 150" aria-hidden="true">
            <polyline points="${chartPoints(stock.club_num, stock.trend)}" />
        </svg>
    `;

    setClubImage(card.querySelector(".stock-logo"), stock.club_num);
    return card;
}

function renderStockCards(category = "all") {
    if (!stockGrid || !Array.isArray(window.clubList)) return;

    const selectedCategory = category === "all" ? "all" : Number(category);
    const visibleClubs = selectedCategory === "all"
        ? window.clubList
        : window.clubList.filter((club) => categoryKey(club.club_num) === selectedCategory);

    stockGrid.replaceChildren();
    visibleClubs.forEach((club) => {
        stockGrid.appendChild(createStockCard(club));
    });
}

const modal = document.querySelector("#trade-modal");
const closeButton = document.querySelector(".modal-close");
const tabs = document.querySelectorAll(".trade-tab");
const amountInput = document.querySelector("#order-amount");
const submitButton = document.querySelector(".order-submit");
const submitCount = document.querySelector("#submit-count");
const submitTotal = document.querySelector("#submit-total");
const submitLabel = document.querySelector("#submit-label");
const modalPrice = document.querySelector("#modal-price");
const modalChange = document.querySelector(".modal-change");
const modalChart = document.querySelector(".modal-chart");
const modalName = document.querySelector("#modal-stock-name");
const modalCategory = document.querySelector(".modal-stock p");
const modalLogo = document.querySelector(".modal-logo");
const modalStats = document.querySelectorAll(".modal-stats dd");
let currentMode = "buy";
let currentPrice = 12345;

function updateSubmit() {
    const amount = Math.max(0, Number(amountInput.value) || 0);
    submitCount.textContent = `${amount}주`;
    submitTotal.textContent = `(${formatWon(amount * currentPrice)})`;
    submitLabel.textContent = currentMode === "buy" ? "매수 주문하기" : "매도 주문하기";
    submitButton.classList.toggle("sell-mode", currentMode === "sell");
}

function openModal(card) {
    const stock = JSON.parse(card.dataset.stock);
    currentPrice = stock.price;

    modalName.textContent = stock.club_name;
    modalCategory.textContent = stock.category;
    modalPrice.textContent = formatWon(stock.price);
    modalChange.textContent = `${stock.changeRate > 0 ? "+" : "-"}${formatWon(stock.changeWon)} ( ${stock.changeRate > 0 ? "+" : ""}${stock.changeRate.toFixed(2)}% )`;
    modalChange.classList.toggle("up", stock.trend === "up");
    modalChange.classList.toggle("down", stock.trend === "down");
    modalChart.classList.toggle("up-chart", stock.trend === "up");
    modalChart.classList.toggle("down-chart", stock.trend === "down");
    modalChart.querySelector("polyline").setAttribute("points", chartPoints(stock.club_num + 20, stock.trend, 820, 260));
    setClubImage(modalLogo, stock.club_num);

    modalStats[0].textContent = stock.owned;
    modalStats[1].textContent = stock.high.toLocaleString("ko-KR");
    modalStats[2].textContent = stock.low.toLocaleString("ko-KR");

    modal.hidden = false;
    updateSubmit();
}

renderStockCards();

categoryFilter?.addEventListener("click", (event) => {
    const button = event.target.closest(".category-btn");
    if (!button) return;

    categoryFilter.querySelectorAll(".category-btn").forEach((item) => {
        item.classList.toggle("active", item === button);
    });

    renderStockCards(button.dataset.category);
});

stockGrid?.addEventListener("click", (event) => {
    const card = event.target.closest(".stock-card");
    if (card) openModal(card);
});

stockGrid?.addEventListener("keydown", (event) => {
    const card = event.target.closest(".stock-card");
    if (card && (event.key === "Enter" || event.key === " ")) {
        event.preventDefault();
        openModal(card);
    }
});

closeButton.addEventListener("click", () => {
    modal.hidden = true;
});

modal.addEventListener("click", (event) => {
    if (event.target === modal) {
        modal.hidden = true;
    }
});

tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
        currentMode = tab.dataset.mode;
        tabs.forEach((item) => item.classList.toggle("active", item === tab));
        updateSubmit();
    });
});

document.querySelectorAll(".amount-btn").forEach((button) => {
    button.addEventListener("click", () => {
        amountInput.value = Math.max(0, (Number(amountInput.value) || 0) + Number(button.dataset.step));
        updateSubmit();
    });
});

document.querySelectorAll(".shortcut-btn").forEach((button) => {
    button.addEventListener("click", () => {
        amountInput.value = button.dataset.value === "max" ? 16 : button.dataset.value;
        updateSubmit();
    });
});

amountInput.addEventListener("input", updateSubmit);

document.querySelector(".order-form").addEventListener("submit", (event) => {
    event.preventDefault();
});
