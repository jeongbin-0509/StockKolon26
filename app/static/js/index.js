class ProfileSection {
    constructor() {
        this.username = document.getElementById("username");
        this.profileImg = document.getElementById("profile-img");
    }

    update(data) {
        if (!data) return;

        if (data.username) {
            this.username.textContent = `${data.username} 님👋`;
        }

        if (data.profileImg) {
            this.profileImg.src = data.profileImg;
            this.profileImg.alt = data.clubName ? `${data.clubName} 로고` : '기본 프로필 이미지';
        }
        updateHeaderProfile(data);
    }
}

class PortfolioSection {
    constructor() {
        this.todayRate = document.getElementById("today-rate");
        this.totalAssets = document.getElementById("total-assets");
        this.chart = document.getElementById("portfolio-chart");
    }

    update(data) {
        if (!data) return;

        if (data.assets) {
            this.totalAssets.textContent = data.assets;
        }

        if (data.rate !== undefined) {
            this.todayRate.textContent = data.rate;

            if (parseFloat(data.rate) >= 0) {
                this.todayRate.className = "head2 up";
            } else {
                this.todayRate.className = "head2 down";
            }
        }
        const total = Number(data.cash || 0) + Number(data.stockValue || 0);
        const stockRatio = total ? Number(data.stockValue || 0) / total * 100 : 0;
        this.chart.replaceChildren();
        const bar = document.createElement('div');
        bar.className = 'allocation-bar';
        bar.setAttribute('role', 'img');
        bar.setAttribute('aria-label', `주식 ${stockRatio.toFixed(0)}%, 현금 ${(100 - stockRatio).toFixed(0)}%`);
        const stock = document.createElement('span');
        stock.className = 'allocation-stock';
        stock.style.width = `${stockRatio}%`;
        const cash = document.createElement('span');
        cash.className = 'allocation-cash';
        cash.style.width = `${100 - stockRatio}%`;
        bar.append(stock, cash);
        const legend = document.createElement('div');
        legend.className = 'allocation-legend';
        legend.innerHTML = `<span><i class="stock-dot"></i>주식 ${stockRatio.toFixed(0)}%</span><span><i class="cash-dot"></i>현금 ${(100 - stockRatio).toFixed(0)}%</span>`;
        this.chart.append(bar, legend);
    }
}

class StockCard {
    constructor(containerId) {
        this.container = document.getElementById(containerId);

        if (!this.container) return;

        this.logo = this.container.querySelector(".stock-logo");
        this.name = this.container.querySelector(".stock-name");
        this.sub = this.container.querySelector(".stock-sub");
        this.change = this.container.querySelector(".stock-change");
        this.chart = this.container.querySelector(".stock-chart");
    }

    update(data) {
        if (!data || !this.container) return;

        if (data.logo) this.logo.src = data.logo;
        if (data.name) this.name.textContent = data.name;
        if (data.sub) this.sub.textContent = data.sub;

        this.change.textContent = '—';
        this.change.className = 'stock-change head2';
        this.chart.replaceChildren();
        if (data.change === undefined || data.change === null) return;

        const isUp = data.change > 0;
        this.change.textContent = `${isUp ? '+' : ''}${Number(data.change).toFixed(2)}% ${isUp ? '↗' : '↘'}`;
        this.change.classList.add(isUp ? 'up' : 'down');
        StockolonCharts.renderCandlestickChart(this.chart, {
            candles: data.candles,
            compact: true,
            ariaLabel: `${data.name} 최근 1시간 5분봉 가격 차트`
        });
    }
}

const profileSection = new ProfileSection();
const portfolioSection = new PortfolioSection();
const topUpCard = new StockCard("top-up-card");
const topDownCard = new StockCard("top-down-card");

function updateAllPageData(data) {
    profileSection.update(data.profile);
    portfolioSection.update(data.portfolio);
    topUpCard.update(data.topUpStock);
    topDownCard.update(data.topDownStock);
}

let indexLoading = false;
async function loadIndexData() {
    if (indexLoading || document.hidden) return;
    indexLoading = true;
    try {
        const response = await fetch("/api/index-data", {cache: "no-store", signal: AbortSignal.timeout(20000)});
        const data = await response.json();

        if (!data.success) {
            alert(data.message);
            location.href = "/auth/login";
            return;
        }

        updateAllPageData(data);

    } catch (error) {
        console.error(error);
        document.getElementById("total-assets").title = "연결 지연으로 다음 갱신 때 다시 시도합니다.";
    } finally { indexLoading = false; }
}

loadIndexData();
setInterval(loadIndexData, 30000);
