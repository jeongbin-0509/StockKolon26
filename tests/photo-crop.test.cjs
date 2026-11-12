const test = require('node:test');
const assert = require('node:assert/strict');
const {fit, move, zoom} = require('../app/static/js/photo-crop.js');

test('landscape and portrait start with the largest centered square', () => {
    assert.deepEqual([fit(800, 400).x, fit(800, 400).y, fit(800, 400).size], [200, 0, 400]);
    assert.deepEqual([fit(400, 800).x, fit(400, 800).y, fit(400, 800).size], [0, 200, 400]);
});
test('drag translates from screen to source pixels and clamps at every edge', () => {
    let crop = zoom(fit(800, 400), 2);
    crop = move(crop, 140, 0, 280);
    assert.equal(crop.cx, 300);
    assert.equal(crop.size, 200);
    for (const [dx, dy] of [[1e5, 1e5], [-1e5, -1e5]]) {
        const result = move(crop, dx, dy, 280);
        assert.ok(result.x >= 0 && result.y >= 0);
        assert.ok(result.x + result.size <= 800 && result.y + result.size <= 400);
    }
});
test('zoom keeps the chosen center where possible and never shows empty margins', () => {
    const crop = fit(800, 400, 4, 60, 60);
    assert.equal(zoom(crop, 3).zoom, 3);
    const expanded = zoom(crop, 1);
    assert.equal(expanded.x, 0);
    assert.equal(expanded.y, 0);
    assert.equal(zoom(crop, 0).zoom, 1);
    assert.equal(zoom(crop, 100).zoom, 4);
});
test('same drag proportion gives the same crop on desktop and mobile', () => {
    const crop = fit(1000, 700, 2);
    assert.deepEqual(move(crop, 28, -56, 280), move(crop, 20, -40, 200));
});
test('selected crop coordinates stay within the source after repeated drag and zoom', () => {
    let crop = fit(4032, 3024);
    for (let i = 0; i < 200; i++) {
        crop = move(zoom(crop, (i % 7) / 2), (i % 2 ? 1 : -1) * 500, i - 100, 257);
        assert.ok(crop.x >= 0 && crop.y >= 0);
        assert.ok(crop.x + crop.size <= crop.width + 1e-8);
        assert.ok(crop.y + crop.size <= crop.height + 1e-8);
    }
});
