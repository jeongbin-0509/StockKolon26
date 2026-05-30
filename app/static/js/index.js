// 프로필창으로 이동하는 기능
const moveBtn = document.getElementById("profile_btn");

if (moveBtn) {
    moveBtn.addEventListener("click", () => {
        location.href = "/profile";
    });
}

function makeChartPoints(seed, trend, width = 420, height = 150) {
    const points = [];
    const count = 13;

    for (let i = 0; i < count; i += 1) {
        const x = 10 + (i * (width - 20)) / (count - 1);
        const wave = Math.sin((seed + i) * 1.8) * 34;
        const noise = Math.cos((seed + i) * 0.9) * 22;
        const trendDrift = trend === "up" ? (count - i) * 4 : i * 4;
        const y = Math.max(18, Math.min(height - 18, height / 2 + wave + noise + trendDrift));
        points.push(`${Math.round(x)},${Math.round(y)}`);
    }

    return points.join(" ");
}

function renderLineChart(container, trend = "up", seed = 1) {
    if (!container) return;

    container.classList.toggle("up-chart", trend === "up");
    container.classList.toggle("down-chart", trend === "down");
    container.innerHTML = `
        <svg viewBox="0 0 420 150" aria-hidden="true">
            <polyline points="${makeChartPoints(seed, trend)}"></polyline>
        </svg>
    `;
}

// ==========================================
// 1. 프로필 섹션 (Profile Section)
// ==========================================
const usernameDOM = document.getElementById("username");
const profileImgDOM = document.getElementById("profile-img");

// ==========================================
// 2. 내 포트폴리오 섹션 (Portfolio Section)
// ==========================================
const todayRateDOM = document.getElementById("today-rate");         // 오늘 수익률
const totalAssetsDOM = document.getElementById("total-assets");     // 총 자산액 text
const portfolioChartDOM = document.getElementById("portfolio-chart"); // 포트폴리오 차트 영역

// ==========================================
// 3. 가장 많이 상승한 주식 섹션 (Top Up Card)
// ==========================================
const topUpLogoDOM = document.querySelector("#top-up-card .stock-logo");     // 주식 로고 이미지
const topUpNameDOM = document.querySelector("#top-up-card .stock-name");     // 주식 이름
const topUpSubDOM = document.querySelector("#top-up-card .stock-sub");       // 주식 서브 정보(분류 등)
const topUpChangeDOM = document.querySelector("#top-up-card .stock-change"); // 변동률 (+4.14% ↗)
const topUpChartDOM = document.querySelector("#top-up-card .stock-chart");   // 미니 차트 영역

// ==========================================
// 4. 가장 많이 하락한 주식 섹션 (Top Down Card)
// ==========================================
const topDownLogoDOM = document.querySelector("#top-down-card .stock-logo");     // 주식 로고 이미지
const topDownNameDOM = document.querySelector("#top-down-card .stock-name");     // 주식 이름
const topDownSubDOM = document.querySelector("#top-down-card .stock-sub");       // 주식 서브 정보
const topDownChangeDOM = document.querySelector("#top-down-card .stock-change"); // 변동률 (-4.14% ↘)
const topDownChartDOM = document.querySelector("#top-down-card .stock-chart");// 미니 차트 영역

// ==========================================
// 1. 프로필 섹션 관리 클래스
// ==========================================
class ProfileSection {
    constructor() {
        this.username = document.getElementById("username");
        this.profileImg = document.getElementById("profile-img");
    }

    update(data) {
        if (data.username) this.username.textContent = `${data.username} 님👋`;
        if (data.profileImg) this.profileImg.src = data.profileImg;
    }
}

// ==========================================
// 2. 포트폴리오 섹션 관리 클래스
// ==========================================
class PortfolioSection {
    constructor() {
        this.todayRate = document.getElementById("today-rate");
        this.totalAssets = document.getElementById("total-assets");
        this.chart = document.getElementById("portfolio-chart");
    }

    update(data) {
        if (data.assets) this.totalAssets.textContent = data.assets;
        
        if (data.rate !== undefined) {
            this.todayRate.textContent = data.rate;
            
            // 수치에 따라 up/down 클래스 동적 변경 (음수면 down, 양수면 up)
            if (parseFloat(data.rate) >= 0) {
                this.todayRate.className = "head2 up";
            } else {
                this.todayRate.className = "head2 down";
            }
        }

        renderLineChart(this.chart, parseFloat(data.rate) >= 0 ? "up" : "down", data.seed || 3);
    }
}

// ==========================================
// 3. 주식 카드 관리 클래스 (상승/하락 공용)
// ==========================================
class StockCard {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.logo = this.container.querySelector(".stock-logo");
        this.name = this.container.querySelector(".stock-name");
        this.sub = this.container.querySelector(".stock-sub");
        this.change = this.container.querySelector(".stock-change");
        this.chart = this.container.querySelector(".stock-chart");
    }

    update(data) {
        if (data.logo) this.logo.src = data.logo;
        if (data.name) this.name.textContent = data.name;
        if (data.sub) this.sub.textContent = data.sub;
        
        if (data.change !== undefined) {
            const isUp = parseFloat(data.change) >= 0;
            this.change.textContent = `${data.change}% ${isUp ? '↗' : '↘'}`;
            this.change.className = `stock-change head2 ${isUp ? 'up' : 'down'}`;
            renderLineChart(this.chart, isUp ? "up" : "down", data.seed || (isUp ? 8 : 14));
        }
    }
}

/* 이런 느낌으로 데이터 불러오면 될듯 정빈아 */

// [1] 페이지 로드 시 각 섹션 객체 생성
const profileSection = new ProfileSection();
const portfolioSection = new PortfolioSection();
const topUpCard = new StockCard("top-up-card");
const topDownCard = new StockCard("top-down-card");


// [2] 업데이트용 통합 함수 생성
function updateAllPageData(mockData) {
    profileSection.update(mockData.profile);
    portfolioSection.update(mockData.portfolio);
    topUpCard.update(mockData.topUpStock);
    topDownCard.update(mockData.topDownStock);
}


// [3] 예시 데이터 (서버에서 받은 JSON 데이터 형태)
const incomingData = {
    profile: {
        username: "세미",
        profileImg: "/static/images/61.png"
    },
    portfolio: {
        assets: "15,450,000원",
        rate: "+12.5%",
        seed: 4
    },
    topUpStock: {
        name: "세미콜론",
        sub: "정보",
        change: "+4.14",
        logo: "/static/images/61.jpg",
        seed: 9
    },
    topDownStock: {
        name: "세미콜론",
        sub: "정보",
        change: "-4.14",
        logo: "/static/images/61.jpg",
        seed: 15
    }
};

// [4] 실행! (이 코드가 실행되면 화면 전체가 한 번에 바뀝니다)
updateAllPageData(incomingData);
