(() => {
    let chartId = 0;

    function svgElement(name, attributes = {}) {
        const element = document.createElementNS('http://www.w3.org/2000/svg', name);
        for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, value);
        return element;
    }

    function renderLineChart(container, options) {
        const prices = (options.prices || []).map(Number).filter(Number.isFinite);
        container.replaceChildren();
        if (prices.length < 2) {
            const empty = document.createElement('span');
            empty.className = 'chart-empty';
            empty.textContent = '가격 기록을 모으는 중';
            container.append(empty);
            return;
        }

        const compact = Boolean(options.compact);
        const width = 1000;
        const height = compact ? 180 : 260;
        const left = compact ? 18 : 30;
        const right = compact ? 982 : 835;
        const top = 20;
        const bottom = compact ? 160 : 210;
        const rawMin = Math.min(...prices);
        const rawMax = Math.max(...prices);
        const padding = Math.max((rawMax - rawMin) * 0.14, Math.abs(prices.at(-1)) * 0.0005, 1);
        const min = rawMin - padding;
        const max = rawMax + padding;
        const yFor = price => bottom - (price - min) / (max - min) * (bottom - top);
        const xFor = index => left + index * (right - left) / (prices.length - 1);
        const formatValue = options.formatValue || (value => `${Math.round(value).toLocaleString('ko-KR')}원`);
        const tone = options.tone === 'down' ? 'down' : options.tone === 'neutral' ? 'neutral' : 'up';
        const svg = svgElement('svg', {
            viewBox: `0 0 ${width} ${height}`,
            preserveAspectRatio: 'none',
            role: 'img',
            'aria-label': options.ariaLabel || '가격 변화 그래프'
        });
        svg.classList.add('readable-chart', `${tone}-chart`);

        for (let index = 0; index < 4; index += 1) {
            const ratio = index / 3;
            const value = max - (max - min) * ratio;
            const y = top + (bottom - top) * ratio;
            svg.append(svgElement('line', {class: 'chart-grid', x1: left, y1: y, x2: right, y2: y}));
            if (!compact) {
                const label = svgElement('text', {class: 'chart-axis-label', x: right + 18, y});
                label.textContent = formatValue(value);
                svg.append(label);
            }
        }

        const firstY = yFor(prices[0]);
        svg.append(svgElement('line', {class: 'chart-baseline', x1: left, y1: firstY, x2: right, y2: firstY}));
        const points = prices.map((price, index) => `${xFor(index)},${yFor(price)}`).join(' ');
        svg.append(svgElement('polygon', {
            class: 'chart-area',
            points: `${left},${bottom} ${points} ${right},${bottom}`
        }));
        svg.append(svgElement('polyline', {class: 'chart-line', points}));
        svg.append(svgElement('circle', {
            class: 'chart-current-point', cx: right, cy: yFor(prices.at(-1)), r: compact ? 6 : 8
        }));

        if (!compact) {
            const start = svgElement('text', {class: 'chart-time-label', x: left, y: height - 13});
            start.textContent = options.startLabel || '시작';
            const end = svgElement('text', {class: 'chart-time-label', x: right, y: height - 13, 'text-anchor': 'end'});
            end.textContent = options.endLabel || '현재';
            svg.append(start, end);
        }
        container.append(svg);
    }

    window.StockolonCharts = {renderLineChart};
})();
