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

    // Rounded price ticks avoid arbitrary decimals and always include every wick.
    function priceScale(low, high) {
        const span = Math.max(high - low, Math.abs(high) * 0.001, 0.04);
        const padding = span * 0.12;
        const rough = span / 4;
        const power = 10 ** Math.floor(Math.log10(rough));
        const multiple = [1, 2, 2.5, 5, 10].find(n => n * power >= rough);
        const step = multiple * power;
        const min = Math.max(0, Math.floor((low - padding) / step) * step);
        const max = Math.ceil((high + padding) / step) * step;
        const ticks = [];
        for (let value = min; value <= max + step * 0.001; value += step) {
            ticks.push(Number(value.toPrecision(12)));
        }
        return {min, max, ticks, decimals: Math.max(0, -Math.floor(Math.log10(power)) + (multiple === 2.5 ? 1 : 0))};
    }

    function candleWindow(total, count, offset = 0) {
        count = Math.min(total, Math.max(1, Math.round(count)));
        offset = Math.max(0, Math.min(Math.round(offset), total - count));
        return {start: total - offset - count, end: total - offset, count, offset};
    }

    const chartStates = new WeakMap();
    const number = new Intl.NumberFormat('ko-KR', {maximumFractionDigits: 2});
    const integer = new Intl.NumberFormat('ko-KR', {maximumFractionDigits: 0});
    const time = new Intl.DateTimeFormat('ko-KR', {
        timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit', hour12: false
    });
    const dateTime = new Intl.DateTimeFormat('ko-KR', {
        timeZone: 'Asia/Seoul', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit', hour12: false
    });
    const dayKey = timestamp => Math.floor((timestamp + 9 * 3600) / 86400);
    const toneOf = candle => candle.close > candle.open ? 'up' : candle.close < candle.open ? 'down' : 'flat';
    const crisp = value => Math.round(value) + 0.5;
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
        const key = String(options.seriesKey ?? options.ariaLabel ?? '') + ':' + (options.intervalSeconds || 300);
        if (!state) {
            state = {width: 0};
            chartStates.set(container, state);
            resizeObserver?.observe(container);
        }
        if (state.key !== key) Object.assign(state, {key, selected: null, count: null, offset: 0, lastTimestamp: null});
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
        const measured = container.clientWidth;
        const width = Math.max(measured || (compact ? 320 : 760), 80);
        state.width = measured;
        const height = compact ? (container.clientHeight || 140) : 340;
        const left = compact ? 6 : 4, right = Math.max(left + 10, width - (compact ? 6 : 78));
        const top = compact ? 9 : 12, bottom = compact ? height - 9 : 234;
        const volumeTop = 263, volumeBottom = 301;
        const maxCount = Math.min(allCandles.length, options.maxCandles || 60);
        if (state.offset && state.lastTimestamp !== null) {
            state.offset += allCandles.filter(c => c.timestamp > state.lastTimestamp).length;
        }
        state.lastTimestamp = allCandles.at(-1)?.timestamp ?? null;
        const requested = compact ? Math.min(maxCount, Math.max(1, Math.floor((right - left) / 5)))
            : Math.min(state.count ?? (width < 500 ? 24 : 32), maxCount);
        const view = candleWindow(allCandles.length, requested, compact ? 0 : state.offset);
        state.offset = view.offset;
        const candles = allCandles.slice(view.start, view.end);
        const active = document.activeElement;
        const focusAction = container.contains(active) ? active?.dataset?.chartAction : null;
        const hadChartFocus = container.contains(active) && active?.tagName?.toLowerCase() === 'svg';
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

        const details = document.createElement('div');
        details.className = 'candle-details';
        if (!compact) container.append(details);
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
            description.textContent = '좌우 방향키로 봉 선택, +와 -로 확대·축소, Shift와 방향키로 구간 이동, End로 최신 봉을 확인하세요.';
            svg.append(description);
        }
        const low = Math.min(...candles.map(c => c.low)), high = Math.max(...candles.map(c => c.high));
        const scale = priceScale(low, high);
        const axisNumber = new Intl.NumberFormat('ko-KR', {minimumFractionDigits: scale.decimals, maximumFractionDigits: scale.decimals});
        const yFor = value => bottom - (value - scale.min) / (scale.max - scale.min) * (bottom - top);
        const step = (right - left) / (Math.max(candles.length, compact ? 8 : 12) + (compact ? 0 : 2));
        const firstX = right - (compact ? 0 : step * 1.5) - (candles.length - 0.5) * step;
        const xFor = index => crisp(firstX + index * step);
        const bodyWidth = Math.max(1, Math.min(compact ? 9 : 15, Math.floor(step * 0.68))) | 1;
        if (!compact) {
            svg.append(svgElement('rect', {class: 'candle-axis-background', x: right, y: 0, width: width - right, height}));
            svg.append(svgElement('line', {class: 'candle-separator', x1: crisp(right), x2: crisp(right), y1: 0, y2: height}));
            svg.append(svgElement('line', {class: 'candle-separator', x1: left, x2: width, y1: 249.5, y2: 249.5}));
            svg.append(svgElement('line', {class: 'candle-separator', x1: left, x2: width, y1: 311.5, y2: 311.5}));
        }
        const latest = allCandles.at(-1);
        const lastY = yFor(latest.close);
        const latestVisible = !state.offset;
        for (const value of scale.ticks) {
            const y = crisp(yFor(value));
            svg.append(svgElement('line', {class: 'candle-grid', x1: left, y1: y, x2: right, y2: y}));
            if (!compact && (!latestVisible || Math.abs(y - lastY) > 15)) {
                svg.append(text({class: 'candle-axis', x: right + 10, y}, axisNumber.format(value)));
            }
        }
        const labelCount = width < 440 ? 3 : 5;
        const labelIndices = [...new Set(Array.from({length: labelCount}, (_, i) =>
            Math.round(i * (candles.length - 1) / (labelCount - 1))))];
        if (!compact) {
            for (const index of labelIndices) {
                const x = xFor(index), candle = candles[index];
                svg.append(svgElement('line', {class: 'candle-grid candle-grid-vertical', x1: x, x2: x, y1: top, y2: volumeBottom}));
                const newDay = index > 0 && dayKey(candle.timestamp) !== dayKey(candles[labelIndices[labelIndices.indexOf(index) - 1]].timestamp);
                const label = newDay ? dateTime.format(new Date(candle.timestamp * 1000)).split(' ').slice(0, 2).join(' ') : time.format(new Date(candle.timestamp * 1000));
                svg.append(text({class: 'candle-time', x, y: 330,
                    'text-anchor': index === 0 ? 'start' : index === candles.length - 1 ? 'end' : 'middle'}, label));
            }
        }
        const maxVolume = Math.max(1, ...candles.map(c => c.volume));
        if (!compact) {
            svg.append(text({class: 'candle-volume-label', x: left + 5, y: volumeTop - 3}, '거래량'));
            svg.append(text({class: 'candle-axis', x: right + 10, y: volumeTop + 5}, integer.format(maxVolume === 1 && candles.every(c => !c.volume) ? 0 : maxVolume)));
            if (candles.every(c => !c.volume)) {
                svg.append(text({class: 'candle-volume-empty', x: (left + right) / 2, y: volumeTop + 24, 'text-anchor': 'middle'}, '이 구간의 체결 내역 없음'));
            }
        }
        candles.forEach((candle, index) => {
            const x = xFor(index);
            const group = svgElement('g', {class: `candle candle-${toneOf(candle)}`, 'data-timestamp': candle.timestamp});
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
                const h = candle.volume / maxVolume * (volumeBottom - volumeTop);
                group.append(svgElement('rect', {class: 'candle-volume', x: x - bodyWidth / 2,
                    y: volumeBottom - h, width: bodyWidth, height: h}));
            }
            svg.append(group);
        });
        if (!compact && latestVisible) {
            const marker = svgElement('g', {class: `candle-${toneOf(latest)}`});
            marker.append(svgElement('line', {class: 'candle-last-line', x1: left, y1: lastY, x2: right, y2: lastY}));
            marker.append(svgElement('rect', {class: 'candle-last-tag', x: right + 1, y: lastY - 11, width: width - right - 1, height: 22}));
            marker.append(text({class: 'candle-last-text', x: right + (width - right) / 2, y: lastY}, number.format(latest.close)));
            svg.append(marker);
        }
        container.append(svg);
        if (compact) return;

        const crosshair = svgElement('g', {class: 'candle-crosshair', visibility: 'hidden', 'pointer-events': 'none'});
        const vertical = svgElement('line', {y1: top, y2: volumeBottom});
        const horizontal = svgElement('line', {x1: left, x2: right});
        const priceTag = svgElement('g');
        priceTag.append(svgElement('rect', {class: 'candle-crosshair-tag', x: right + 1, y: -11, width: width - right - 1, height: 22}));
        const priceText = text({class: 'candle-last-text', x: right + (width - right) / 2, y: 0}, '');
        priceTag.append(priceText);
        const timeTag = svgElement('g');
        timeTag.append(svgElement('rect', {class: 'candle-crosshair-tag', x: -57, y: 313, width: 114, height: 26, rx: 3}));
        const timeText = text({class: 'candle-last-text', x: 0, y: 326}, '');
        timeTag.append(timeText);
        crosshair.append(vertical, horizontal, priceTag, timeTag);
        svg.append(crosshair);

        let selectedIndex = candles.findIndex(c => c.timestamp === state.selected);
        if (selectedIndex < 0) selectedIndex = candles.length - 1;
        function select(index, showCrosshair, pointerY) {
            selectedIndex = Math.max(0, Math.min(candles.length - 1, index));
            const candle = candles[selectedIndex];
            state.selected = showCrosshair ? candle.timestamp : null;
            const x = xFor(selectedIndex), y = Math.max(top, Math.min(bottom, pointerY ?? yFor(candle.close)));
            vertical.setAttribute('x1', x); vertical.setAttribute('x2', x);
            horizontal.setAttribute('y1', y); horizontal.setAttribute('y2', y);
            priceTag.setAttribute('transform', `translate(0 ${y})`);
            priceText.textContent = number.format(scale.min + (bottom - y) / (bottom - top) * (scale.max - scale.min));
            timeTag.setAttribute('transform', `translate(${Math.max(58, Math.min(right - 58, x))} 0)`);
            timeText.textContent = dateTime.format(new Date(candle.timestamp * 1000));
            crosshair.setAttribute('visibility', showCrosshair ? 'visible' : 'hidden');
            const inProgress = Number.isFinite(options.timestamp) && candle.timestamp === Math.floor(options.timestamp / interval) * interval;
            const partialStart = candle.timestamp < historyStart;
            details.replaceChildren();
            const meta = document.createElement('div');
            meta.className = 'candle-detail-meta';
            const stamp = document.createElement('span');
            stamp.textContent = dateTime.format(new Date(candle.timestamp * 1000));
            const status = document.createElement('span');
            status.className = inProgress ? 'candle-live' : '';
            status.textContent = `${inProgress ? '진행 중' : '완료'}${partialStart ? ' · 일부 구간' : ''}`;
            const volume = document.createElement('span');
            volume.className = 'candle-detail-volume';
            volume.textContent = `거래량 ${integer.format(candle.volume)}주`;
            meta.append(stamp, status, volume);
            details.append(meta);
            const values = document.createElement('div');
            values.className = `candle-detail-values candle-${toneOf(candle)}`;
            for (const [label, value] of [['시가', candle.open], ['고가', candle.high], ['저가', candle.low], ['종가', candle.close]]) {
                const item = document.createElement('span'), labelNode = document.createElement('span');
                labelNode.textContent = label;
                const valueNode = document.createElement('strong');
                valueNode.textContent = number.format(value);
                item.append(labelNode, valueNode);
                values.append(item);
            }
            details.append(values);
            svg.setAttribute('aria-label', `${options.ariaLabel || '캔들 차트'}. ${stamp.textContent}. ${status.textContent}. 시가 ${number.format(candle.open)}, 고가 ${number.format(candle.high)}, 저가 ${number.format(candle.low)}, 종가 ${number.format(candle.close)}, 거래량 ${integer.format(candle.volume)}주`);
        }
        function redraw() { state.selected = null; drawCandles(container, state); }
        function zoom(factor) {
            state.count = Math.min(maxCount, Math.max(Math.min(8, maxCount), Math.round(view.count * factor)));
            redraw();
        }
        function pan(delta) { state.offset = view.offset + delta; redraw(); }
        function pointerPosition(event) {
            const rect = svg.getBoundingClientRect();
            return {x: (event.clientX - rect.left) / rect.width * width, y: (event.clientY - rect.top) / rect.height * height};
        }
        function selectPointer(event) {
            const p = pointerPosition(event);
            if (p.x < left || p.x > right || p.y < top || p.y > volumeBottom) {
                select(candles.length - 1, false); return;
            }
            select(Math.round((p.x - firstX) / step), true, p.y <= bottom ? p.y : undefined);
        }
        let dragStart = null;
        svg.addEventListener('pointerdown', event => {
            if (event.button !== 0) return;
            const p = pointerPosition(event);
            if (p.x > right) return;
            dragStart = {x: p.x, y: p.y, id: event.pointerId};
            svg.setPointerCapture(event.pointerId);
            selectPointer(event);
        });
        svg.addEventListener('pointermove', selectPointer);
        svg.addEventListener('pointerup', event => {
            if (!dragStart || dragStart.id !== event.pointerId) return;
            const p = pointerPosition(event), delta = p.x - dragStart.x;
            dragStart = null;
            if (svg.hasPointerCapture(event.pointerId)) svg.releasePointerCapture(event.pointerId);
            if (Math.abs(delta) > Math.max(8, step / 2)) pan(Math.round(delta / step));
        });
        svg.addEventListener('pointercancel', () => { dragStart = null; select(candles.length - 1, false); });
        svg.addEventListener('pointerleave', () => { if (!dragStart) select(candles.length - 1, false); });
        svg.addEventListener('keydown', event => {
            if (event.key === '+' || event.key === '=') { event.preventDefault(); zoom(0.75); return; }
            if (event.key === '-') { event.preventDefault(); zoom(1.4); return; }
            if (event.shiftKey && ['ArrowLeft', 'ArrowRight'].includes(event.key)) {
                event.preventDefault(); pan(Math.round(view.count / 3) * (event.key === 'ArrowLeft' ? 1 : -1)); return;
            }
            if (event.key === 'End' && state.offset) { event.preventDefault(); state.offset = 0; redraw(); return; }
            const indices = {ArrowLeft: selectedIndex - 1, ArrowRight: selectedIndex + 1, Home: 0, End: candles.length - 1};
            if (event.key in indices) { event.preventDefault(); select(indices[event.key], true); }
            if (event.key === 'Escape') select(candles.length - 1, false);
        });
        select(selectedIndex, state.selected !== null);
        const nav = document.createElement('div');
        nav.className = 'candle-navigation';
        const range = document.createElement('span');
        range.className = 'candle-range';
        range.textContent = `${time.format(new Date(candles[0].timestamp * 1000))} — ${time.format(new Date(candles.at(-1).timestamp * 1000))} · ${candles.length}개 봉`;
        nav.append(range);
        const controls = document.createElement('div');
        controls.className = 'candle-controls';
        for (const [action, label, title, disabled, handler] of [
            ['previous', '‹', '이전 구간', view.start === 0, () => pan(Math.max(1, Math.round(view.count / 2)))],
            ['next', '›', '다음 구간', view.offset === 0, () => pan(-Math.max(1, Math.round(view.count / 2)))],
            ['out', '−', '차트 축소', view.count >= maxCount, () => zoom(1.4)],
            ['in', '+', '차트 확대', view.count <= Math.min(8, maxCount), () => zoom(0.75)],
            ['reset', '전체', '전체 기록 보기', false, () => { state.count = maxCount; state.offset = 0; redraw(); }]
        ]) {
            const button = document.createElement('button');
            button.type = 'button';
            button.dataset.chartAction = action;
            button.setAttribute('aria-label', title);
            button.title = title;
            button.textContent = label;
            button.disabled = disabled;
            button.addEventListener('click', handler);
            controls.append(button);
        }
        nav.append(controls);
        container.append(nav);
        if (focusAction) controls.querySelector(`[data-chart-action="${focusAction}"]`)?.focus({preventScroll: true});
        else if (hadChartFocus) svg.focus({preventScroll: true});
    }

    window.StockolonCharts = {aggregateCandles, priceScale, candleWindow, renderCandlestickChart, disposeChart};
})();
