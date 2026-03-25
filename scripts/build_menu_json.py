#!/usr/bin/env python3
"""Convert the provided menu document into structured JSON for the menu UI."""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional

CATEGORY_MAP = {
    'PHỞ NOODLE SOUP': 'Pho Noodle Soup',
    'PHO CUPS': 'Pho Cups',
    'PHO COMBO': 'Pho Combo',
    'RICE DISHES': 'Rice Dishes',
    'MCQ SIZZLING HOT PLATES': 'MCQ Sizzling Hot Plates',
    'DRY NOODLES': 'Dry Noodles',
    'BÁNH MÌ': 'Bánh Mì',
    'RICE PAPER ROLLS': 'Rice Paper Rolls',
    'MIXED JUICES': 'Mixed Juices',
    'SMOOTHIES': 'Smoothies',
    'VIETNAMESE COFFEE': 'Vietnamese Coffee',
    'LEMONADE DRINKS': 'Lemonade Drinks',
}

CATEGORY_IMAGES = {
    'PHỞ NOODLE SOUP': 'pho-classic.jpg',
    'PHO CUPS': 'pho-cup.jpg',
    'PHO COMBO': 'pho-combo.jpg',
    'RICE DISHES': 'rice-dishes.jpg',
    'MCQ SIZZLING HOT PLATES': 'sizzling-plate.jpg',
    'DRY NOODLES': 'dry-noodles.jpg',
    'BÁNH MÌ': 'banh-mi.jpg',
    'RICE PAPER ROLLS': 'rice-paper-roll.jpg',
    'MIXED JUICES': 'juices.jpg',
    'SMOOTHIES': 'smoothies.jpg',
    'VIETNAMESE COFFEE': 'coffee.jpg',
    'LEMONADE DRINKS': 'lemonade.jpg',
}

CATEGORY_LEVEL_LABELS = {
    'SMOOTHIES': {'Smoothie Base Ingredients'},
}

SUMMARY_HINTS = {
    'PHỞ NOODLE SOUP': 'Slow-simmered broth ladled over silky rice noodles with chef-selected toppings.',
    'PHO CUPS': 'Compact takeaway-friendly cups packed with the same pho flavors.',
    'PHO COMBO': 'Bundle a pho bowl with a drink for an easy pickup meal.',
    'RICE DISHES': 'Comforting rice plates built for hearty lunches.',
    'MCQ SIZZLING HOT PLATES': 'Tableside sizzle platters served with rice and egg.',
    'DRY NOODLES': 'Vermicelli bowls tossed with greens, pickles, and house sauces.',
    'BÁNH MÌ': 'Crispy baguettes packed with proteins, pickles, and herbs.',
    'RICE PAPER ROLLS': 'Fresh rolls with herbs and dual dipping sauces.',
    'MIXED JUICES': 'Made-to-order juice blends.',
    'SMOOTHIES': 'Blended fruit smoothies with a creamy base.',
    'VIETNAMESE COFFEE': 'Traditional phin-brewed iced coffee.',
    'LEMONADE DRINKS': 'House lemonade infusions.',
}


def slugify(value: str) -> str:
    cleaned = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    cleaned = re.sub(r'[^a-zA-Z0-9]+', '-', cleaned).strip('-').lower()
    return cleaned or 'section'


def parse_lines(lines: List[str]):
    items_by_category: Dict[str, List[dict]] = {key: [] for key in CATEGORY_MAP}
    category_order: List[str] = []
    category_notes: Dict[str, dict] = {}
    current_category: Optional[str] = None
    current_item: Optional[dict] = None
    current_section: Optional[dict] = None
    collecting_note: Optional[dict] = None

    def flush_section():
        nonlocal current_section, current_item
        if current_section and current_item and current_section['items']:
            current_item['sections'].append(current_section)
        current_section = None

    def flush_item():
        nonlocal current_item, current_category
        flush_section()
        if current_item and current_category:
            items_by_category[current_category].append(current_item)
        current_item = None

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        upper = line.upper()
        if upper in CATEGORY_MAP:
            flush_item()
            current_category = upper
            collecting_note = None
            if upper not in category_order:
                category_order.append(upper)
            continue
        item_match = re.match(r'^(\d+)\.\s+(.*)$', line)
        if item_match and current_category:
            flush_item()
            current_item = {'name': item_match.group(2).strip(), 'sections': []}
            continue
        if line.endswith(':'):
            label = line[:-1].strip()
            if current_category and label in CATEGORY_LEVEL_LABELS.get(current_category, set()):
                collecting_note = category_notes.setdefault(current_category, {'label': label, 'items': []})
                current_section = None
                continue
            flush_section()
            current_section = {'label': label, 'items': []}
            collecting_note = None
            continue
        text = line
        if text.startswith('•') or text.startswith('-'):
            text = text.lstrip('•-\t ').strip()
        if collecting_note is not None:
            if text:
                collecting_note['items'].append(text)
            continue
        if current_section is not None:
            if text:
                current_section['items'].append(text)
            continue
        if current_item is not None and text:
            current_item.setdefault('notes', []).append(text)

    flush_item()
    return items_by_category, category_order, category_notes


def build_payload(items_by_category, category_order, category_notes):
    categories_output = []
    for key in category_order:
        display = CATEGORY_MAP[key]
        image_file = CATEGORY_IMAGES.get(key)
        category_entry = {
            'id': slugify(display),
            'title': display,
            'image': f"images/menu/{image_file}" if image_file else None,
            'items': [],
            'note': category_notes.get(key),
        }
        for item in items_by_category.get(key, []):
            notes = item.pop('notes', None)
            if notes:
                item['sections'].append({'label': 'Notes', 'items': notes})
            price = None
            cleaned_sections = []
            for section in item['sections']:
                if section['label'].lower() == 'price' and section['items']:
                    price = section['items'][0]
                else:
                    cleaned_sections.append(section)
            item['sections'] = cleaned_sections
            item['price'] = price
            main_section = next((sec for sec in item['sections'] if sec['items']), None)
            if main_section and main_section['items']:
                sample = ', '.join(main_section['items'][:3]).lower()
                summary = f"{CATEGORY_MAP[key]} favourite featuring {sample}."
            else:
                summary = SUMMARY_HINTS.get(key, 'House-made specialty from MCQ.')
            item['summary'] = summary
            item['image'] = f"images/menu/{image_file}" if image_file else None
            category_entry['items'].append(item)
        categories_output.append(category_entry)
    return categories_output


def main():
    parser = argparse.ArgumentParser(description='Convert the menu doc to JSON.')
    parser.add_argument('--source', default='data/menu-source.txt', help='Plain-text menu input')
    parser.add_argument('--output', default='static/data/menu.json', help='Where to write the JSON payload')
    args = parser.parse_args()

    source_path = Path(args.source)
    if not source_path.exists():
        raise SystemExit(f'Source file not found: {source_path}')

    lines = source_path.read_text(encoding='utf-8').splitlines()
    items_by_category, category_order, category_notes = parse_lines(lines)
    payload = {
        'generated_from': str(source_path),
        'categories': build_payload(items_by_category, category_order, category_notes),
    }

    output_path = Path(args.output)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'Wrote {output_path} with {sum(len(cat["items"]) for cat in payload["categories"])} items.')


if __name__ == '__main__':
    main()
