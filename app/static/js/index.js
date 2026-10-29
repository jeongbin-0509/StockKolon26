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

        const min = Math.min(...data.prices);
        const range = Math.max(...data.prices) - min;
        const points = data.prices.map((price, index) => {
            const x = 10 + index * 980 / (data.prices.length - 1);
            const y = range ? 95 - (price - min) / range * 90 : 50;
            return `${x},${y}`;
        }).join(' ');
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('viewBox', '0 0 1000 100');
        svg.setAttribute('preserveAspectRatio', 'none');
        svg.setAttribute('aria-label', '최근 5분 주가 그래프');
        svg.setAttribute('role', 'img');
        svg.classList.add(isUp ? 'up-chart' : 'down-chart');
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'polyline');
        line.setAttribute('points', points);
        svg.append(line);
        this.chart.append(svg);
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
