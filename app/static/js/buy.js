const stockGrid = document.querySelector(".stock-grid");
const categoryFilter = document.querySelector(".stock-category-filter");
const imageBase = stockGrid?.dataset.imageBase || "/static/images/";
const defaultLogo = `${imageBase}default_stock_logo.png`;
const clubImageFiles = {
    1: "1.png",
    2: "2.png",
    11: "11.png",
    12: "12.png",
    13: "13.png",
    14: "14.png",
    21: "21.png",
    22: "22.png",
    23: "23.png",
    31: "31.png",
    32: "32.png",
    33: "33.png",
    41: "41.png",
    42: "42.png",
    43: "43.png",
    44: "44.png",
    45: "45.png",
    51: "51.png",
    52: "52.png",
    53: "53.png",
    54: "54.png",
    55: "55.png",
    61: "61.png",
    62: "62.png",
    71: "71.png",
    72: "72.png",
    73: "73.png",
    74: "74.png",
    75: "75.png",
    76: "76.png",
    81: "81.png",
    83: "83.png",
    84: "84.png"
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

function chartPrices(stock, seedOffset = 0) {
    const prices = [];
    const count = 13;
    const startPrice = stock.trend === "up"
        ? stock.price - stock.changeWon
        : stock.price + stock.changeWon;
    const volatility = Math.max(stock.price * 0.08, 1000);

    for (let i = 0; i < count; i += 1) {
        const progress = i / (count - 1);
        const basePrice = startPrice + (stock.price - startPrice) * progress;
        const noiseRatio = (seededValue(stock.club_num + seedOffset + i * 7, 0, 2000) - 1000) / 1000;
        const noise = noiseRatio * volatility * Math.sin(Math.PI * progress);
        prices.push(Math.max(100, Math.round(basePrice + noise)));
    }

    prices[prices.length - 1] = stock.price;
    return prices;
}

function nicePriceStep(value) {
    const power = 10 ** Math.floor(Math.log10(Math.max(1, value)));
    const fraction = value / power;
    const multiplier = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10;
    return multiplier * power;
}

function chartMarkup(stock, width = 420, height = 150, seedOffset = 0) {
    const prices = chartPrices(stock, seedOffset);
    const rawMin = Math.min(...prices);
    const rawMax = Math.max(...prices);
    const padding = Math.max((rawMax - rawMin) * 0.15, stock.price * 0.02, 100);
    const step = nicePriceStep((rawMax - rawMin + padding * 2) / 4);
    const scaleMin = Math.max(0, Math.floor((rawMin - padding) / step) * step);
    const scaleMax = Math.ceil((rawMax + padding) / step) * step;
    const scaleRange = scaleMax - scaleMin || step;
    const left = 10;
    const top = 10;
    const bottom = height - 10;
    const plotRight = width - (width <= 500 ? 70 : 105);
    const plotWidth = plotRight - left;
    const plotHeight = bottom - top;

    const priceToY = (price) => bottom - ((price - scaleMin) / scaleRange) * plotHeight;

    const horizontalGrid = [];
    for (let price = scaleMin; price <= scaleMax; price += step) {
        const y = priceToY(price);
        horizontalGrid.push(`
            <line class="chart-grid-line" x1="${left}" y1="${y}" x2="${plotRight}" y2="${y}" />
            <text class="chart-price-label" x="${plotRight + 7}" y="${y}">${price.toLocaleString("ko-KR")}원</text>
        `);
    }

    const verticalGrid = Array.from({ length: 7 }, (_, index) => {
        const x = left + (index / 6) * plotWidth;
        return `<line class="chart-grid-line chart-grid-line-minor" x1="${x}" y1="${top}" x2="${x}" y2="${bottom}" />`;
    }).join("");

    const points = prices.map((price, index) => {
        const x = left + (index / (prices.length - 1)) * plotWidth;
        return `${Math.round(x)},${Math.round(priceToY(price))}`;
    }).join(" ");

    return `
        <g class="chart-grid">${verticalGrid}${horizontalGrid.join("")}</g>
        <polyline points="${points}" />
    `;
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
            ${chartMarkup(stock)}
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
    modalChart.innerHTML = chartMarkup(stock, 820, 260, 20);
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
        const shortcutAmount = button.dataset.value === "max" ? 16 : Number(button.dataset.value) || 0;
        amountInput.value = Math.max(0, (Number(amountInput.value) || 0) + shortcutAmount);
        updateSubmit();
    });
});

amountInput.addEventListener("input", updateSubmit);

document.querySelector(".order-form").addEventListener("submit", (event) => {
    event.preventDefault();
});
