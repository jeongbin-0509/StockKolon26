"""Import the supplied article manuscript; never interpret its prose as commands."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import runpy
from xml.etree import ElementTree
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
CLUBS = runpy.run_path(str(ROOT / 'app/market_catalog.py'))['CLUBS']
ALIASES = {'볼택스': 'Vortex', '데이터 무제한': '데이터무제한'}
DIFFICULTIES = {'쉬움': 'easy', '보통': 'normal', '어려움': 'hard'}


def import_articles(source):
    with ZipFile(source) as archive:
        root = ElementTree.fromstring(archive.read('word/document.xml'))
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    paragraphs = [''.join(node.text or '' for node in p.findall('.//w:t', ns)).strip()
                  for p in root.findall('.//w:p', ns)]
    numbers = {name: number for number, name in CLUBS.items()}
    counts, entries = Counter(), []
    club, difficulty, pending = None, None, None
    for line in paragraphs:
        if not line:
            continue
        if pending is not None:
            pending['body'] = line
            entries.append(pending)
            pending = None
            continue
        heading = re.fullmatch(r'\d{2}\. (.+)', line)
        if heading:
            name = heading[1]
            club = numbers[ALIASES.get(name, name)]
            difficulty = None
        elif club is not None and line in DIFFICULTIES:
            difficulty = DIFFICULTIES[line]
        elif club is not None and (article := re.fullmatch(r'(호재|악재) [12] \| (.+)', line)):
            if difficulty is None:
                raise ValueError('Article without a difficulty group')
            sentiment = 'good' if article[1] == '호재' else 'bad'
            counts[club, sentiment] += 1
            # Keep the previous 0.4–2.4% game range; inference difficulty is NOT impact strength.
            magnitude = (40 + int(hashlib.sha256(article[2].encode()).hexdigest()[:8], 16) % 201) / 10000
            pending = {'id': f'c{club}-{sentiment}-{counts[club, sentiment]}', 'club_num': club,
                       'sentiment': sentiment, 'difficulty': difficulty, 'title': article[2],
                       'impact': magnitude if sentiment == 'good' else -magnitude}
    expected = {(number, sentiment) for number in CLUBS for sentiment in ('good', 'bad')}
    if pending or set(counts) != expected or set(counts.values()) != {6}:
        raise ValueError('Expected exactly six good and six bad articles for all 33 clubs')
    return entries


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'app/data/news_presets.json')
    args = parser.parse_args()
    entries = import_articles(args.source)
    args.output.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Imported {len(entries)} articles for {len(CLUBS)} clubs.')
