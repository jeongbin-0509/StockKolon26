const stockGrid = document.querySelector(".stock-grid");
const categoryFilter = document.querySelector(".stock-category-filter");
const statusElement = document.querySelector("#market-status");
const imageBase = stockGrid.dataset.imageBase;
const modal = document.querySelector("#trade-modal");
const closeButton = document.querySelector(".modal-close");
const tabs = document.querySelectorAll(".trade-tab");
const amountInput = document.querySelector("#order-amount");
const submitButton = document.querySelector(".order-submit");
let stocks = [];
let selectedCategory = "all";
let selectedClub = null;
let currentMode = "buy";
let currentPrice = 0;
let refreshTimer;
let loading = false;
let lastTimestamp = null;

function formatWon(value) {
    return `${Math.round(value).toLocaleString("ko-KR")}원`;
}

function setClubImage(img, clubNum) {
    img.onerror = () => {
        img.onerror = null;
        img.src = `${imageBase}default_stock_logo.png`;
    };
    img.src = `${imageBase}${clubNum}.png`;
}

function nicePriceStep(value) {
    const power = 10 ** Math.floor(Math.log10(Math.max(1, value)));
    const fraction = value / power;
    return (fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10) * power;
}

function chartMarkup(stock, width = 420, height = 150) {
    const candles = stock.candles;
    if (!candles.length) return "";
    const prices = candles.map((candle) => candle.close);
    const rawMin = Math.min(...prices);
    const rawMax = Math.max(...prices);
    const padding = Math.max((rawMax - rawMin) * 0.15, stock.price * 0.001, 1);
    const step = nicePriceStep((rawMax - rawMin + padding * 2) / 4);
    const scaleMin = Math.max(0, Math.floor((rawMin - padding) / step) * step);
    const scaleMax = Math.ceil((rawMax + padding) / step) * step;
    const left = 10;
    const top = 10;
    const bottom = height - 26;
    const right = width - (width <= 500 ? 70 : 105);
    const priceToY = (price) => bottom - (price - scaleMin) / (scaleMax - scaleMin || 1) * (bottom - top);
    const start = candles[0].timestamp;
    const duration = candles.at(-1).timestamp - start;
    const xFor = (candle) => duration ? left + (candle.timestamp - start) / duration * (right - left) : left;
    let grid = "";
    for (let price = scaleMin; price <= scaleMax; price += step) {
        const y = priceToY(price);
        grid += `<line class="chart-grid-line" x1="${left}" y1="${y}" x2="${right}" y2="${y}" />
            <text class="chart-price-label" x="${right + 7}" y="${y}">${price.toLocaleString("ko-KR")}원</text>`;
    }
    const points = candles.map((candle) => `${xFor(candle)},${priceToY(candle.close)}`).join(" ");
    const timeLabel = (timestamp) => new Date(timestamp * 1000).toLocaleTimeString("ko-KR", {
        timeZone: "Asia/Seoul", hour: "2-digit", minute: "2-digit", hour12: false
    });
    const last = candles.at(-1);
    return `${grid}<polyline points="${points}" />
        <circle class="chart-last-point" cx="${xFor(last)}" cy="${priceToY(last.close)}" r="3" />
        <text class="chart-price-label" x="${left}" y="${height - 7}">${timeLabel(start)}</text>
        ${duration ? `<text class="chart-price-label" text-anchor="end" x="${right}" y="${height - 7}">${timeLabel(last.timestamp)}</text>` : ""}`;
}

function trendOf(stock) {
    return stock.changeRate >= 0 ? "up" : "down";
}

function createStockCard(stock) {
    const trend = trendOf(stock);
    const card = document.createElement("article");
    card.className = "stock-card";
    card.tabIndex = 0;
    card.setAttribute("role", "button");
    card.setAttribute("aria-label", `${stock.club_name} ${formatWon(stock.price)} 상세 보기`);
    card.dataset.club = stock.club_num;
    card.innerHTML = `
        <div class="stock-top">
            <img alt="${stock.club_name} 로고" class="stock-logo">
            <div><h2>${stock.club_name}</h2><p>${stock.category}</p></div>
        </div>
        <div class="stock-value ${trend}">
            <strong>${formatWon(stock.price)}</strong>
            <span>${stock.changeRate > 0 ? "+" : ""}${stock.changeRate.toFixed(2)}% ${stock.changeRate === 0 ? "↔" : trend === "up" ? "↗" : "↘"}</span>
        </div>
        <svg class="stock-chart ${trend}-chart" viewBox="0 0 420 150" aria-hidden="true">${chartMarkup(stock)}</svg>`;
    setClubImage(card.querySelector(".stock-logo"), stock.club_num);
    return card;
}

function renderStockCards() {
    const focusedClub = document.activeElement?.closest(".stock-card")?.dataset.club;
    const visible = stocks.filter((stock) => selectedCategory === "all" || stock.categoryKey === Number(selectedCategory));
    stockGrid.replaceChildren(...visible.map(createStockCard));
    if (focusedClub) stockGrid.querySelector(`[data-club="${focusedClub}"]`)?.focus({ preventScroll: true });
}

function updateSubmit() {
    const amount = Math.max(0, Math.floor(Number(amountInput.value) || 0));
    document.querySelector("#submit-count").textContent = `${amount}주`;
    document.querySelector("#submit-total").textContent = `(${formatWon(amount * currentPrice)})`;
    document.querySelector("#submit-label").textContent = currentMode === "buy" ? "매수 준비 중" : "매도 준비 중";
    submitButton.classList.toggle("sell-mode", currentMode === "sell");
}

function updateModal(stock) {
    const trend = trendOf(stock);
    currentPrice = stock.price;
    document.querySelector("#modal-stock-name").textContent = stock.club_name;
    document.querySelector(".modal-stock p").textContent = stock.category;
    document.querySelector("#modal-price").textContent = formatWon(stock.price);
    const change = document.querySelector(".modal-change");
    change.textContent = `${stock.changeWon > 0 ? "+" : stock.changeWon < 0 ? "−" : ""}${formatWon(Math.abs(stock.changeWon))} (${stock.changeRate > 0 ? "+" : ""}${stock.changeRate.toFixed(2)}%)`;
    change.classList.toggle("up", trend === "up");
    change.classList.toggle("down", trend === "down");
    const chart = document.querySelector(".modal-chart");
    chart.classList.toggle("up-chart", trend === "up");
    chart.classList.toggle("down-chart", trend === "down");
    chart.innerHTML = chartMarkup(stock, 820, 260);
    setClubImage(document.querySelector(".modal-logo"), stock.club_num);
    const stats = document.querySelectorAll(".modal-stats dd");
    stats[0].textContent = "—";
    stats[1].textContent = formatWon(stock.high);
    stats[2].textContent = formatWon(stock.low);
    updateSubmit();
}

function openModal(card) {
    const stock = stocks.find((item) => item.club_num === Number(card.dataset.club));
    if (!stock) return;
    selectedClub = stock.club_num;
    amountInput.value = 0;
    updateModal(stock);
    modal.hidden = false;
    closeButton.focus();
}

function closeModal() {
    modal.hidden = true;
    stockGrid.querySelector(`[data-club="${selectedClub}"]`)?.focus({ preventScroll: true });
    selectedClub = null;
}

async function loadMarket() {
    clearTimeout(refreshTimer);
    if (loading || document.hidden) return;
    loading = true;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    let retryDelay = 10000;
    try {
        const response = await fetch("/api/market", { cache: "no-store", signal: controller.signal });
        if (response.status === 401) {
            location.assign("/auth/login");
            return;
        }
        if (!response.ok) throw new Error("market unavailable");
        const data = await response.json();
        if (!data.success) throw new Error("market unavailable");
        if (lastTimestamp !== data.timestamp) {
            stocks = data.stocks;
            lastTimestamp = data.timestamp;
            renderStockCards();
            if (selectedClub !== null) updateModal(stocks.find((stock) => stock.club_num === selectedClub));
        }
        const updated = new Date(data.timestamp * 1000).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" });
        statusElement.textContent = data.catchingUp
            ? `중단된 기간의 주가를 복구하고 있습니다. 현재 ${updated}`
            : `최근 갱신 ${updated} · 가격 30초마다 갱신 · 5분봉에는 진행 중인 구간 포함`;
        statusElement.classList.remove("error");
        if (data.catchingUp) retryDelay = 1000;
    } catch (error) {
        statusElement.textContent = stocks.length
            ? "연결이 끊겨 마지막으로 받은 주가를 표시하고 있습니다. 자동으로 다시 연결합니다."
            : "주가를 불러오지 못했습니다. 잠시 후 자동으로 다시 시도합니다.";
        statusElement.classList.add("error");
    } finally {
        clearTimeout(timeout);
        loading = false;
        stockGrid.setAttribute("aria-busy", "false");
        refreshTimer = setTimeout(loadMarket, retryDelay);
    }
}

categoryFilter.addEventListener("click", (event) => {
    const button = event.target.closest(".category-btn");
    if (!button) return;
    selectedCategory = button.dataset.category;
    categoryFilter.querySelectorAll(".category-btn").forEach((item) => item.classList.toggle("active", item === button));
    renderStockCards();
});
stockGrid.addEventListener("click", (event) => {
    const card = event.target.closest(".stock-card");
    if (card) openModal(card);
});
stockGrid.addEventListener("keydown", (event) => {
    const card = event.target.closest(".stock-card");
    if (card && (event.key === "Enter" || event.key === " ")) {
        event.preventDefault();
        openModal(card);
    }
});
closeButton.addEventListener("click", closeModal);
modal.addEventListener("click", (event) => { if (event.target === modal) closeModal(); });
document.addEventListener("keydown", (event) => {
    if (modal.hidden) return;
    if (event.key === "Escape") closeModal();
    if (event.key === "Tab") {
        const focusable = [...modal.querySelectorAll("button:not(:disabled), input:not(:disabled)")];
        const next = focusable.indexOf(document.activeElement) + (event.shiftKey ? -1 : 1);
        if (next < 0 || next >= focusable.length) {
            event.preventDefault();
            focusable[event.shiftKey ? focusable.length - 1 : 0].focus();
        }
    }
});
tabs.forEach((tab) => tab.addEventListener("click", () => {
    currentMode = tab.dataset.mode;
    tabs.forEach((item) => item.classList.toggle("active", item === tab));
    updateSubmit();
}));
document.querySelectorAll(".amount-btn, .shortcut-btn:not(:disabled)").forEach((button) => {
    button.addEventListener("click", () => {
        amountInput.value = Math.max(0, Math.floor(Number(amountInput.value) || 0) + Number(button.dataset.step || button.dataset.value));
        updateSubmit();
    });
});
amountInput.addEventListener("input", updateSubmit);
document.querySelector(".order-form").addEventListener("submit", (event) => event.preventDefault());
document.addEventListener("visibilitychange", () => { if (!document.hidden) loadMarket(); });
loadMarket();
