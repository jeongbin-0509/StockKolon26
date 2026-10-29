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
        if (!Array.isArray(data.prices) || data.prices.length < 2) return;

        const times = Array.isArray(data.timestamps) ? data.timestamps : [];
        const formatTime = timestamp => new Date(timestamp * 1000).toLocaleTimeString('ko-KR', {
            timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit', hour12: false
        });
        StockolonCharts.renderLineChart(this.chart, {
            prices: data.prices,
            tone: isUp ? 'up' : 'down',
            startLabel: times.length ? formatTime(times[0]) : '5분 전',
            endLabel: times.length ? formatTime(times.at(-1)) : '현재',
            ariaLabel: `${data.name} 최근 5분 가격 변화`
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

async function loadIndexData() {
    try {
        const response = await fetch("/api/index-data");
        const data = await response.json();

        if (!data.success) {
            alert(data.message);
            location.href = "/auth/login";
            return;
        }

        updateAllPageData(data);

    } catch (error) {
        console.error(error);
        alert("데이터를 불러오지 못했습니다.");
    }
}

loadIndexData();
setInterval(loadIndexData, 30000);
