"""Server-owned news presets and their hidden market impact values."""

import json
from functools import lru_cache
from pathlib import Path

from app.market_catalog import CLUBS

_CATALOG_PATH = Path(__file__).with_name('data') / 'news_presets_0_4.json'


@lru_cache(maxsize=1)
def _catalog():
    entries = json.loads(_CATALOG_PATH.read_text(encoding='utf-8'))
    catalog = {}
    counts = {}
    for entry in entries:
        preset_id = entry['id']
        club_num = entry['club_num']
        sentiment = entry['sentiment']
        impact = entry['impact']
        if preset_id in catalog:
            raise RuntimeError(f'Duplicate news preset: {preset_id}')
        if club_num not in CLUBS or sentiment not in {'good', 'bad'}:
            raise RuntimeError(f'Invalid news preset: {preset_id}')
        if not 0.004 <= abs(impact) <= 0.024 or (impact > 0) != (sentiment == 'good'):
            raise RuntimeError(f'Invalid news impact: {preset_id}')
        if not entry['title'].strip() or not entry['body'].strip():
            raise RuntimeError(f'Empty news preset: {preset_id}')
        catalog[preset_id] = entry
        counts[(club_num, sentiment)] = counts.get((club_num, sentiment), 0) + 1
    included_clubs = {entry['club_num'] for entry in entries}
    expected_groups = {(club_num, sentiment) for club_num in included_clubs for sentiment in ('good', 'bad')}
    if set(counts) != expected_groups or any(count != 3 for count in counts.values()):
        raise RuntimeError('Each included club must have three good and three bad presets.')
    return catalog


def get_news_preset(preset_id):
    """Return a private preset. Callers must never serialize the impact to a page."""
    return _catalog().get((preset_id or '').strip())


def public_news_options():
    """Return only fields that are safe to embed in the admin HTML."""
    return [
        {
            'id': entry['id'],
            'club_num': entry['club_num'],
            'sentiment': '호재' if entry['sentiment'] == 'good' else '악재',
            'title': entry['title'],
        }
        for entry in _catalog().values()
    ]
