(() => {
    function svgElement(name, attributes = {}) {
        const element = document.createElementNS('http://www.w3.org/2000/svg', name);
        for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, value);
        return element;
    }

    function aggregateCandles(candles, intervalSeconds = 300) {
        if (!Number.isInteger(intervalSeconds) || intervalSeconds < 300 || intervalSeconds % 300) {
            throw new RangeError('봉 간격은 5분의 배수여야 합니다.');
        }
        const valid = (Array.isArray(candles) ? candles : []).filter(candle => candle &&
            ['timestamp', 'open', 'high', 'low', 'close', 'volume'].every(key =>
                typeof candle[key] === 'number' && Number.isFinite(candle[key])) &&
            candle.timestamp >= 0 && candle.low > 0 && candle.volume >= 0 &&
            candle.high >= Math.max(candle.open, candle.close) &&
            candle.low <= Math.min(candle.open, candle.close))
            .slice().sort((a, b) => a.timestamp - b.timestamp);
        const buckets = new Map();
        for (const candle of valid) {
            const timestamp = Math.floor(candle.timestamp / intervalSeconds) * intervalSeconds;
            const bucket = buckets.get(timestamp);
            if (bucket) {
                bucket.high = Math.max(bucket.high, candle.high);
                bucket.low = Math.min(bucket.low, candle.low);
                bucket.close = candle.close;
                bucket.volume += candle.volume;
            } else buckets.set(timestamp, {...candle, timestamp});
        }
        return [...buckets.values()];
    }

    const chartStates = new WeakMap();
    const number = new Intl.NumberFormat('ko-KR', {maximumFractionDigits: 2});
    const time = new Intl.DateTimeFormat('ko-KR', {
        timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit', hour12: false
    });
    const dateTime = new Intl.DateTimeFormat('ko-KR', {
        timeZone: 'Asia/Seoul', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit', hour12: false
    });
    const resizeObserver = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(entries => {
        for (const entry of entries) {
            const state = chartStates.get(entry.target);
            if (state && entry.contentRect.width > 0 && Math.abs(state.width - entry.contentRect.width) > 1) {
                drawCandles(entry.target, state);
            }
        }
    });

    function renderCandlestickChart(container, options = {}) {
        if (!container) return;
        let state = chartStates.get(container);
        if (!state) {
            state = {options, selected: null, width: 0};
            chartStates.set(container, state);
            resizeObserver?.observe(container);
        }
        state.options = options;
        drawCandles(container, state);
    }

    function disposeChart(container) {
        resizeObserver?.unobserve(container);
        chartStates.delete(container);
    }

    function drawCandles(container, state) {
        const options = state.options;
        const compact = Boolean(options.compact);
        const interval = options.intervalSeconds || 300;
        const allCandles = aggregateCandles(options.candles, interval);
        const historyStart = aggregateCandles(options.candles)[0]?.timestamp;
        // 닫힌 모달은 폭이 0이다. 열리면 ResizeObserver가 실제 크기로 다시 그린다.
        const measured = container.clientWidth;
        const width = Math.max(measured || (compact ? 320 : 760), 80);
        state.width = measured;
        const height = compact ? (container.clientHeight || 140) : 310;
        const left = 8, right = width - (compact ? 8 : 76);
        const top = compact ? 10 : 14, bottom = compact ? height - 10 : 224;
        const volumeTop = 247, volumeBottom = 280;
        const slots = Math.max(1, Math.min(options.maxCandles || 60, Math.floor((right - left) / (compact ? 6 : 8))));
        const candles = allCandles.slice(-slots);
        const hadFocus = container.contains(document.activeElement);
        container.replaceChildren();
        container.classList.add('candlestick-host');
        container.classList.toggle('candlestick-compact', compact);
        if (!candles.length) {
            const empty = document.createElement('span');
            empty.className = 'chart-empty';
            empty.textContent = '가격 기록을 모으는 중';
            container.append(empty);
            return;
        }
        let details;
        if (!compact) {
            details = document.createElement('div');
            details.className = 'candle-details';
            container.append(details);
        }
        const svg = svgElement('svg', {
            viewBox: `0 0 ${width} ${height}`, preserveAspectRatio: 'none',
            role: compact ? 'img' : 'group',
            'aria-label': options.ariaLabel || `${interval / 60}분 캔들 차트`
        });
        svg.classList.add('candlestick-chart');
        function text(attributes, value) {
            const node = svgElement('text', attributes);
            node.textContent = value;
            return node;
        }
        if (!compact) {
            svg.setAttribute('tabindex', '0');
            const description = svgElement('desc');
            description.textContent = '좌우 방향키로 봉을 선택하세요. Home은 첫 봉, End는 최신 봉입니다.';
            svg.append(description);
        }
        const low = Math.min(...candles.map(c => c.low)), high = Math.max(...candles.map(c => c.high));
        const padding = Math.max((high - low) * 0.12, candles.at(-1).close * 0.0001, 0.01);
        const min = Math.max(0, low - padding), max = high + padding;
        const yFor = value => bottom - (value - min) / (max - min) * (bottom - top);
        // 기록이 적을 때도 한 봉을 화면 전체 폭으로 늘리지 않는다.
        const count = Math.max(candles.length, Math.min(compact ? 12 : 24, slots));
        const step = (right - left) / count;
        const xFor = index => left + (index + 0.5) * step;
        const bodyWidth = Math.max(1, Math.min(16, step * 0.62));
        const gridCount = compact ? 3 : 5;
        for (let i = 0; i < gridCount; i++) {
            const value = max - (max - min) * i / (gridCount - 1), y = yFor(value);
            svg.append(svgElement('line', {class: 'candle-grid', x1: left, y1: y, x2: right, y2: y}));
            if (!compact) svg.append(text({class: 'candle-axis', x: right + 8, y}, number.format(value)));
        }
        const maxVolume = Math.max(1, ...candles.map(c => c.volume));
        if (!compact) {
            svg.append(svgElement('line', {class: 'candle-grid', x1: left, y1: volumeTop - 12, x2: right, y2: volumeTop - 12}));
            svg.append(text({class: 'candle-axis', x: right + 8, y: volumeTop + 4}, '거래량'));
            svg.append(text({class: 'candle-axis', x: right + 8, y: volumeTop + 20}, '주'));
        }
        candles.forEach((candle, index) => {
            const x = xFor(index);
            const tone = candle.close > candle.open ? 'up' : candle.close < candle.open ? 'down' : 'flat';
            const group = svgElement('g', {class: `candle candle-${tone}`, 'data-timestamp': candle.timestamp});
            // 꼬리와 몸통은 저장된 OHLC 범위만 사용한다.
            group.append(svgElement('line', {class: 'candle-wick', x1: x, x2: x,
                y1: yFor(candle.high), y2: yFor(candle.low)}));
            const bodyTop = yFor(Math.max(candle.open, candle.close));
            const bodyBottom = yFor(Math.min(candle.open, candle.close));
            if (bodyBottom - bodyTop < 1) {
                group.append(svgElement('line', {class: 'candle-doji', x1: x - bodyWidth / 2,
                    x2: x + bodyWidth / 2, y1: (bodyTop + bodyBottom) / 2, y2: (bodyTop + bodyBottom) / 2}));
            } else group.append(svgElement('rect', {class: 'candle-body', x: x - bodyWidth / 2,
                y: bodyTop, width: bodyWidth, height: bodyBottom - bodyTop}));
            if (!compact && candle.volume > 0) {
                const volumeHeight = candle.volume / maxVolume * (volumeBottom - volumeTop);
                group.append(svgElement('rect', {class: 'candle-volume', x: x - bodyWidth / 2,
                    y: volumeBottom - volumeHeight, width: bodyWidth, height: volumeHeight}));
            }
            svg.append(group);
        });
        if (!compact) {
            const latest = candles.at(-1), lastY = yFor(latest.close);
            const lastTone = latest.close > latest.open ? 'up' : latest.close < latest.open ? 'down' : 'flat';
            const marker = svgElement('g', {class: `candle-${lastTone}`});
            marker.append(svgElement('line', {class: 'candle-last-line', x1: left, y1: lastY, x2: right, y2: lastY}));
            marker.append(svgElement('rect', {class: 'candle-last-tag', x: right + 2, y: lastY - 10, width: 72, height: 20, rx: 3}));
            marker.append(text({class: 'candle-last-text', x: right + 38, y: lastY}, number.format(latest.close)));
            svg.append(marker);
            const labelCount = width < 440 ? 2 : 4;
            const labelIndices = [...new Set(Array.from({length: labelCount}, (_, i) =>
                Math.round(i * (candles.length - 1) / (labelCount - 1))))];
            for (const index of labelIndices) svg.append(text({class: 'candle-time', x: xFor(index), y: height - 9,
                'text-anchor': index === 0 ? 'start' : index === candles.length - 1 ? 'end' : 'middle'},
                time.format(new Date(candles[index].timestamp * 1000))));
            const crosshair = svgElement('g', {class: 'candle-crosshair', visibility: 'hidden', 'pointer-events': 'none'});
            const vertical = svgElement('line', {y1: top, y2: volumeBottom});
            const horizontal = svgElement('line', {x1: left, x2: right});
            const dot = svgElement('circle', {r: 3});
            crosshair.append(vertical, horizontal, dot);
            svg.append(crosshair);
            let selectedIndex = candles.findIndex(c => c.timestamp === state.selected);
            if (selectedIndex < 0) selectedIndex = candles.length - 1;
            function select(index, showCrosshair) {
                selectedIndex = Math.max(0, Math.min(candles.length - 1, index));
                const candle = candles[selectedIndex];
                state.selected = showCrosshair ? candle.timestamp : null;
                const x = xFor(selectedIndex), y = yFor(candle.close);
                vertical.setAttribute('x1', x); vertical.setAttribute('x2', x);
                horizontal.setAttribute('y1', y); horizontal.setAttribute('y2', y);
                dot.setAttribute('cx', x); dot.setAttribute('cy', y);
                crosshair.setAttribute('visibility', showCrosshair ? 'visible' : 'hidden');
                details.replaceChildren();
                const stamp = document.createElement('span');
                stamp.className = 'candle-detail-time';
                const inProgress = Number.isFinite(options.timestamp) &&
                    candle.timestamp === Math.floor(options.timestamp / interval) * interval;
                const partialStart = candle.timestamp < historyStart;
                stamp.textContent = `${dateTime.format(new Date(candle.timestamp * 1000))}${inProgress ? ' · 진행 중' : ''}${partialStart ? ' · 일부 구간' : ''}`;
                details.append(stamp);
                for (const [label, value] of [['시', candle.open], ['고', candle.high], ['저', candle.low], ['종', candle.close], ['거래량', candle.volume]]) {
                    const item = document.createElement('span'), labelNode = document.createElement('span');
                    labelNode.textContent = label;
                    const valueNode = document.createElement('strong');
                    valueNode.textContent = `${number.format(value)}${label === '거래량' ? '주' : ''}`;
                    item.append(labelNode, valueNode);
                    details.append(item);
                }
                svg.setAttribute('aria-label', `${options.ariaLabel || '캔들 차트'}. ${stamp.textContent}. 시가 ${number.format(candle.open)}, 고가 ${number.format(candle.high)}, 저가 ${number.format(candle.low)}, 종가 ${number.format(candle.close)}, 거래량 ${number.format(candle.volume)}주`);
            }
            function selectPointer(event) {
                const rect = svg.getBoundingClientRect();
                const x = (event.clientX - rect.left) / rect.width * width;
                const y = (event.clientY - rect.top) / rect.height * height;
                if (x < left || x > right || y < top || y > volumeBottom) return;
                select(Math.floor((x - left) / step), true);
            }
            svg.addEventListener('pointermove', selectPointer);
            svg.addEventListener('pointerdown', selectPointer);
            svg.addEventListener('pointerleave', () => select(candles.length - 1, false));
            svg.addEventListener('keydown', event => {
                const indices = {ArrowLeft: selectedIndex - 1, ArrowRight: selectedIndex + 1, Home: 0, End: candles.length - 1};
                if (event.key in indices) { event.preventDefault(); select(indices[event.key], true); }
                if (event.key === 'Escape') select(candles.length - 1, false);
            });
            select(selectedIndex, state.selected !== null);
        }
        container.append(svg);
        if (hadFocus && !compact) svg.focus({preventScroll: true});
    }

    window.StockolonCharts = {aggregateCandles, renderCandlestickChart, disposeChart};
})();
