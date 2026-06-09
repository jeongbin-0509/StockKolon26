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
        }
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

        if (typeof renderLineChart === "function") {
            renderLineChart(
                this.chart,
                parseFloat(data.rate) >= 0 ? "up" : "down",
                data.seed || 3
            );
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

        if (data.change !== undefined) {
            const isUp = parseFloat(data.change) >= 0;

            this.change.textContent = `${data.change}% ${isUp ? "↗" : "↘"}`;
            this.change.className = `stock-change head2 ${isUp ? "up" : "down"}`;

            if (typeof renderLineChart === "function") {
                renderLineChart(
                    this.chart,
                    isUp ? "up" : "down",
                    data.seed || (isUp ? 8 : 14)
                );
            }
        }
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

        console.log("받은 데이터:", data);

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