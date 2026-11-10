const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const vm = require('node:vm');
const context = {window: {}};
vm.runInNewContext(readFileSync(join(__dirname, '../app/static/js/charts.js'), 'utf8'), context);
const aggregate = (rows, interval) => JSON.parse(JSON.stringify(context.window.StockolonCharts.aggregateCandles(rows, interval)));
const candle = (timestamp, open, high, low, close, volume = 0) => ({timestamp, open, high, low, close, volume});

test('15-minute bodies, wicks and volume come from all constituent candles', () => {
    const rows = [candle(600, 99, 104, 96, 103, 40), candle(0, 100, 108, 98, 105, 120),
        candle(300, 105, 106, 95, 99, 80), candle(900, 103, 109, 102, 107, 0)];
    const before = JSON.stringify(rows);
    assert.deepEqual(aggregate(rows, 900), [candle(0, 100, 108, 95, 103, 240), candle(900, 103, 109, 102, 107, 0)]);
    assert.equal(JSON.stringify(rows), before);
});

test('5-minute data preserves fractional prices and actual wick extremes', () => {
    const rows = [candle(300, 10000.1, 10000.9, 9999.7, 10000.4, 22)];
    assert.deepEqual(aggregate(rows, 300), rows);
});

test('flat, single and incomplete candles never acquire invented wicks or volume', () => {
    const rows = [candle(3600, 1, 1, 1, 1)];
    assert.deepEqual(aggregate(rows, 3600), rows);
    assert.deepEqual(aggregate([], 300), []);
});

test('missing intervals are not filled with synthetic prices', () => {
    const rows = [candle(0, 100, 105, 98, 101), candle(7200, 90, 93, 88, 91)];
    assert.deepEqual(aggregate(rows, 3600), rows);
});

test('invalid candles are omitted without distorting valid history', () => {
    const valid = candle(0, 100, 110, 90, 105);
    assert.deepEqual(aggregate([valid, candle(300, 100, 95, 90, 105),
        candle(600, 100, 110, 0, 105), candle(900, 100, Infinity, 90, 105), null], 300), [valid]);
    assert.throws(() => aggregate([valid], 60), /5분/);
});

test('price axes use readable ticks and keep every real high and low in view', () => {
    for (const [low, high] of [[9296.43, 9395.98], [1, 1], [10000, 10000], [9999.99, 10000.01], [1, 900000]]) {
        const scale = context.window.StockolonCharts.priceScale(low, high);
        assert.ok(scale.min >= 0 && scale.min <= low);
        assert.ok(scale.max >= high && scale.max > scale.min);
        assert.ok(scale.ticks.length >= 2 && scale.ticks.length <= 8);
        const labels = scale.ticks.map(value => value.toFixed(scale.decimals));
        assert.equal(new Set(labels).size, labels.length, 'adjacent price labels must stay distinct');
    }
    const scale = context.window.StockolonCharts.priceScale(9296.43, 9395.98);
    assert.equal(scale.decimals, 0);
    assert.ok(scale.ticks.every(value => Number.isInteger(value)));
});

test('zoom and pan keep the requested number of candles within available history', () => {
    const range = (...args) => JSON.parse(JSON.stringify(context.window.StockolonCharts.candleWindow(...args)));
    assert.deepEqual(range(60, 24), {start: 36, end: 60, count: 24, offset: 0});
    assert.deepEqual(range(60, 24, 12), {start: 24, end: 48, count: 24, offset: 12});
    assert.deepEqual(range(60, 24, 999), {start: 0, end: 24, count: 24, offset: 36});
    assert.deepEqual(range(60, 24, -8), {start: 36, end: 60, count: 24, offset: 0});
    assert.deepEqual(range(5, 32, 10), {start: 0, end: 5, count: 5, offset: 0});
    assert.deepEqual(range(0, 32), {start: 0, end: 0, count: 0, offset: 0});
});
