const stockGrid = document.querySelector(".stock-grid");
const categoryFilter = document.querySelector(".stock-category-filter");
const statusElement = document.querySelector("#market-status");
const imageBase = stockGrid.dataset.imageBase;
const modal = document.querySelector("#trade-modal");
const closeButton = document.querySelector(".modal-close");
const tabs = document.querySelectorAll(".trade-tab");
const amountInput = document.querySelector("#order-amount");
const submitButton = document.querySelector(".order-submit");
const orderForm = document.querySelector('.order-form');
const orderStatus = document.querySelector('#order-status');
const confirmDialog = document.querySelector('#order-confirm');
const confirmCancel = document.querySelector('#confirm-cancel');
const confirmSubmit = document.querySelector('#confirm-submit');
const executionToast = document.querySelector('#execution-toast');
let confirmedOrder = null;
let toastTimer;
let portfolio = null;
let submitting = false;
let pendingOrder = null;
try { pendingOrder = JSON.parse(sessionStorage.getItem('stockolon-pending-order') || 'null'); } catch (_) {}
let stocks = [];
let selectedCategory = "all";
let selectedClub = null;
let currentMode = "buy";
let currentPrice = 0;
let refreshTimer;
let loading = false;
let lastTimestamp = null;
let requestedTradeHandled = false;

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

function timeLabel(timestamp) {
    return new Date(timestamp * 1000).toLocaleTimeString("ko-KR", {
        timeZone: "Asia/Seoul", hour: "2-digit", minute: "2-digit", hour12: false
    });
}

function renderStockChart(container, stock, compact = false) {
    const candles = stock.candles || [];
    StockolonCharts.renderLineChart(container, {
        prices: candles.map(candle => candle.close),
        tone: trendOf(stock),
        compact,
        startLabel: candles.length ? timeLabel(candles[0].timestamp) : '',
        endLabel: candles.length ? timeLabel(candles.at(-1).timestamp) : '',
        ariaLabel: `${stock.club_name} 최근 가격 변화`
    });
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
        <div class="stock-chart"></div>`;
    setClubImage(card.querySelector(".stock-logo"), stock.club_num);
    renderStockChart(card.querySelector('.stock-chart'), stock, true);
    return card;
}

function renderStockCards() {
    const focusedClub = document.activeElement?.closest(".stock-card")?.dataset.club;
    const visible = stocks.filter((stock) => selectedCategory === "all" || stock.categoryKey === Number(selectedCategory));
    stockGrid.replaceChildren(...visible.map(createStockCard));
    if (focusedClub) stockGrid.querySelector(`[data-club="${focusedClub}"]`)?.focus({ preventScroll: true });
}

function updateSubmit() {
    const amount = Number(amountInput.value);
    const stock = stocks.find(item => item.club_num === selectedClub);
    currentPrice = stock ? (currentMode === 'buy' ? stock.buyPrice : stock.sellPrice) : 0;
    const valid = Number.isInteger(amount) && amount >= 1 && amount <= 1000;
    document.querySelector("#submit-count").textContent = `${amount}주`;
    document.querySelector("#submit-total").textContent = `(${formatWon(valid ? amount * currentPrice : 0)})`;
    document.querySelector("#submit-label").textContent = currentMode === "buy" ? "매수 주문하기" : "매도 주문하기";
    submitButton.classList.toggle("sell-mode", currentMode === "sell");
    submitButton.disabled = submitting || !valid || !currentPrice || !portfolio;
    const held = portfolio?.holdings.find(item => item.club_num === selectedClub)?.quantity || 0;
    document.querySelector('.modal-stats dd').textContent = `${held.toLocaleString('ko-KR')}주`;
    if (portfolio) document.querySelector('#order-balance').textContent = `보유 현금 ${formatWon(portfolio.user.cash)} · ${currentMode === 'buy' ? '매수가' : '매도가'} ${formatWon(currentPrice)}`;
}

function updateModal(stock) {
    const trend = trendOf(stock);
    document.querySelector("#modal-stock-name").textContent = stock.club_name;
    document.querySelector(".modal-stock p").textContent = stock.category;
    document.querySelector("#modal-price").textContent = formatWon(stock.price);
    const change = document.querySelector(".modal-change");
    change.textContent = `${stock.changeWon > 0 ? "+" : stock.changeWon < 0 ? "−" : ""}${formatWon(Math.abs(stock.changeWon))} (${stock.changeRate > 0 ? "+" : ""}${stock.changeRate.toFixed(2)}%)`;
    change.classList.toggle("up", trend === "up");
    change.classList.toggle("down", trend === "down");
    renderStockChart(document.querySelector(".modal-chart"), stock);
    setClubImage(document.querySelector(".modal-logo"), stock.club_num);
    const stats = document.querySelectorAll(".modal-stats dd");
    stats[1].textContent = formatWon(stock.high);
    stats[2].textContent = formatWon(stock.low);
    updateSubmit();
}

function openModal(card) {
    const stock = stocks.find((item) => item.club_num === Number(card.dataset.club));
    if (!stock) return;
    selectedClub = stock.club_num;
    amountInput.value = 1;
    orderStatus.textContent = pendingOrder ? '이전에 결과를 확인하지 못한 주문이 있습니다. 같은 종목·방향·수량으로 다시 요청하면 중복 체결 없이 결과를 확인합니다.' : '';
    updateModal(stock);
    modal.hidden = false;
    closeButton.focus();
}

function setTradeMode(mode) {
    currentMode = mode === 'sell' ? 'sell' : 'buy';
    tabs.forEach(item => item.classList.toggle('active', item.dataset.mode === currentMode));
    updateSubmit();
}

function openRequestedTrade() {
    if (requestedTradeHandled || !stocks.length || !portfolio) return;
    const params = new URLSearchParams(location.search);
    const clubNum = Number(params.get('club'));
    const side = params.get('side');
    if (!Number.isInteger(clubNum) || !stocks.some(stock => stock.club_num === clubNum) || !['buy', 'sell'].includes(side)) {
        requestedTradeHandled = true;
        return;
    }
    requestedTradeHandled = true;
    selectedCategory = 'all';
    categoryFilter.querySelectorAll('.category-btn').forEach(item => item.classList.toggle('active', item.dataset.category === 'all'));
    renderStockCards();
    setTradeMode(side);
    const card = stockGrid.querySelector(`[data-club="${clubNum}"]`);
    if (card) openModal(card);
    history.replaceState({}, '', location.pathname);
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
            openRequestedTrade();
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
    if (confirmDialog.open) return;
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
tabs.forEach((tab) => tab.addEventListener("click", () => setTradeMode(tab.dataset.mode)));
document.querySelectorAll(".amount-btn, .shortcut-btn:not(:disabled)").forEach((button) => {
    button.addEventListener("click", () => {
        if (button.dataset.value === 'max') {
            const held = portfolio?.holdings.find(item => item.club_num === selectedClub)?.quantity || 0;
            amountInput.value = Math.min(1000, currentMode === 'buy' ? Math.floor((portfolio?.user.cash || 0) / currentPrice) : held);
        } else {
            amountInput.value = Math.min(1000, Math.max(1, Math.floor(Number(amountInput.value) || 0) + Number(button.dataset.step || button.dataset.value)));
        }
        updateSubmit();
    });
});
amountInput.addEventListener("input", updateSubmit);
async function loadPortfolio() {
    try {
        const response = await fetch('/api/profile-data', {cache: 'no-store'});
        if (!response.ok) throw new Error();
        const data = await response.json();
        if (!data.success) throw new Error();
        portfolio = data;
        document.querySelector('#asset-total').textContent = data.summary.total_assets;
        document.querySelector('#asset-cost').textContent = data.summary.purchase_amount;
        document.querySelector('#asset-cash').textContent = data.summary.cash;
        updateSubmit();
        openRequestedTrade();
    } catch (_) {
        portfolio = null;
        document.querySelector('#order-balance').textContent = '잔액을 불러오지 못했습니다. 새로고침해주세요.';
        updateSubmit();
    }
}
orderForm.addEventListener('submit', event => {
    event.preventDefault();
    if (submitting || submitButton.disabled || confirmDialog.open) return;
    const quantity = Number(amountInput.value);
    if (pendingOrder && (pendingOrder.clubNum !== selectedClub || pendingOrder.side !== currentMode || pendingOrder.quantity !== quantity)) {
        orderStatus.textContent = `이전 주문 결과를 먼저 확인해주세요. 종목 ${pendingOrder.clubNum}, ${pendingOrder.side === 'buy' ? '매수' : '매도'} ${pendingOrder.quantity}주로 다시 요청하세요.`;
        return;
    }
    const order = pendingOrder || {orderId: crypto.randomUUID(), clubNum: selectedClub, side: currentMode, quantity};
    const stock = stocks.find(item => item.club_num === order.clubNum);
    if (!stock) return;
    confirmedOrder = order;
    const sideText = order.side === 'buy' ? '매수' : '매도';
    document.querySelector('#confirm-title').textContent = pendingOrder ? '이전 주문 결과를 확인할까요?' : `${sideText} 주문을 체결하시겠습니까?`;
    document.querySelector('#confirm-details').textContent = pendingOrder
        ? '결과를 확인하지 못한 이전 주문을 같은 번호로 다시 확인합니다.'
        : '아래 주문 내용을 확인해주세요.';
    document.querySelector('#confirm-stock').textContent = stock.club_name;
    document.querySelector('#confirm-side').textContent = sideText;
    document.querySelector('#confirm-quantity').textContent = `${order.quantity.toLocaleString('ko-KR')}주`;
    document.querySelector('#confirm-price').textContent = `${formatWon(currentPrice)} 전후`;
    document.querySelector('#confirm-total').textContent = `${formatWon(currentPrice * order.quantity)} 전후`;
    confirmSubmit.textContent = pendingOrder ? '결과 확인' : `${sideText}하기`;
    confirmDialog.showModal();
    confirmCancel.focus();
});
confirmCancel.addEventListener('click', () => confirmDialog.close());
confirmDialog.addEventListener('close', () => { confirmedOrder = null; });
document.querySelector('#execution-close').addEventListener('click', () => {
    clearTimeout(toastTimer);
    executionToast.hidden = true;
});
confirmSubmit.addEventListener('click', async () => {
    if (submitting || !confirmedOrder) return;
    const order = confirmedOrder;
    confirmDialog.close();
    pendingOrder = order;
    sessionStorage.setItem('stockolon-pending-order', JSON.stringify(order));
    submitting = true;
    orderStatus.textContent = '주문을 처리하고 있습니다…';
    updateSubmit();
    try {
        const response = await fetch('/api/orders', {
            method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': orderForm.dataset.csrf},
            body: JSON.stringify(order), signal: AbortSignal.timeout(30000)
        });
        const result = await response.json();
        if (response.status >= 500) throw new Error();
        if (response.status === 401 || response.status === 403) {
            orderStatus.textContent = '로그인 상태를 확인한 뒤 같은 종목·방향·수량으로 다시 요청해주세요.';
            return;
        }
        pendingOrder = null;
        sessionStorage.removeItem('stockolon-pending-order');
        if (!response.ok || !result.success) {
            orderStatus.textContent = result.message || '주문을 처리하지 못했습니다.';
            await loadMarket();
        } else {
            orderStatus.textContent = `${result.order.club_name} ${result.order.quantity}주 ${result.order.side === 'buy' ? '매수' : '매도'} 완료 · ${formatWon(result.order.price)}에 체결`;
            document.querySelector('#execution-title').textContent = result.replayed ? '이전 체결 확인' : `${result.order.side === 'buy' ? '매수' : '매도'} 체결 완료`;
            document.querySelector('#execution-detail').textContent = `${result.order.club_name} ${result.order.quantity.toLocaleString('ko-KR')}주 · ${formatWon(result.order.price)} · 총 ${formatWon(result.order.total)}`;
            executionToast.hidden = false;
            clearTimeout(toastTimer);
            toastTimer = setTimeout(() => { executionToast.hidden = true; }, 9000);
            lastTimestamp = null;
            await Promise.all([loadPortfolio(), loadMarket()]);
        }
    } catch (_) {
        orderStatus.textContent = '주문 결과를 확인하지 못했습니다. 같은 종목·방향·수량으로 다시 요청하면 중복 체결 없이 결과를 확인합니다.';
    } finally {
        submitting = false;
        updateSubmit();
    }
});
document.addEventListener("visibilitychange", () => { if (!document.hidden) loadMarket(); });
loadMarket();
loadPortfolio();
