const {test} = require('node:test');
const assert = require('node:assert/strict');
const {podiumSlots} = require('../app/static/js/rank.js');

test('silver, gold, bronze appear in second, first, third order without altering rankings', () => {
    const members = [1, 2, 3, 4].map(rank => ({rank, name: `member-${rank}`}));
    const before = JSON.stringify(members);
    const slots = podiumSlots(members);
    assert.deepEqual(slots.map(s => s.member.rank), [2, 1, 3]);
    assert.deepEqual(slots.map(s => s.tier), [2, 1, 3]);
    assert.equal(JSON.stringify(members), before);
});

test('ties keep their actual medal and height instead of inventing distinct ranks', () => {
    assert.deepEqual(podiumSlots([{rank: 1}, {rank: 1}, {rank: 3}]).map(s => s.tier), [1, 1, 3]);
    assert.deepEqual(podiumSlots([{rank: 1}, {rank: 2}, {rank: 2}]).map(s => s.tier), [2, 1, 2]);
});

test('small groups show empty places, with a lone winner still in the center', () => {
    const [left, center, right] = podiumSlots([{rank: 1, name: 'winner'}]);
    assert.equal(left.member, null);
    assert.equal(center.member.name, 'winner');
    assert.equal(right.member, null);
    assert.ok(podiumSlots([]).every(slot => slot.member === null));
    assert.equal(podiumSlots([{rank: 1}, {rank: 2}]).filter(slot => slot.member).length, 2);
});
