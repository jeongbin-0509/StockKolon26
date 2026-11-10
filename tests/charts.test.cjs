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
