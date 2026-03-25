#!/usr/bin/env python3
"""Download per-item menu images and save a source manifest."""
from __future__ import annotations

import io
import argparse
import json
import subprocess
import tempfile
import unicodedata
from pathlib import Path
from typing import Dict, Iterable, List

import requests
from PIL import Image, ImageOps

OPENVERSE_API = "https://api.openverse.org/v1/images/"
OUTPUT_DIR = Path("static/images/menu/items")
MANIFEST_PATH = Path("data/menu-image-sources.json")
TARGET_SIZE = (1200, 900)

ITEM_SOURCES: Dict[str, Dict[str, object]] = {
    "Raw Beef Pho": {"copy_from": "/Users/nhungpham/Downloads/raw_beef_pho.jpg"},
    "Raw Beef and Beef Balls Pho": {"queries": ["beef meatball pho", "pho bo vien"]},
    "Beef Brisket Pho": {"copy_from": "/Users/nhungpham/Downloads/Brisket-pho.jpg"},
    "Slow-Cooked Beef Rib Pho": {"copy_from": "/Users/nhungpham/Downloads/Slow_Cooked_Beef_Rib.jpg"},
    "MCQ Special Pho": {"copy_from": "/Users/nhungpham/Downloads/mcq_special_pho.jpg"},
    "Chicken Pho": {"copy_from": "/Users/nhungpham/Downloads/Chicken-Pho..webp"},
    "Beef Balls Pho": {"copy_from": "/Users/nhungpham/Downloads/beef_balls_pho.jpg"},
    "Bun Bo Hue": {"copy_from": "/Users/nhungpham/Downloads/Bun-Bo-Hue-Spicy.jpg"},
    "Beef Pho Cup": {"copy_from": "static/images/menu/pho-cup.jpg"},
    "Chicken Pho Cup": {"copy_from": "/Users/nhungpham/Downloads/chicken-pho-cup.jpg"},
    "Bun Bo Hue Cup": {"copy_from": "/Users/nhungpham/Downloads/BUNBOHUE_CUP.JPG"},
    "Pho Combo": {"copy_from": "static/images/menu/pho-combo.jpg"},
    "Grilled Pork Chop with Broken Rice": {"copy_from": "/Users/nhungpham/Downloads/Grilled Pork Chop with Broken Rice.jpg"},
    "Roast Pork Rice": {"copy_from": "/Users/nhungpham/Downloads/roast_pork_rice_hotplate.jpg"},
    "Grilled Chicken Rice": {"copy_from": "/Users/nhungpham/Downloads/grilled_chicken_rice.jpg"},
    "Grilled Beef Rice": {"copy_from": "/Users/nhungpham/Downloads/grilled_beef_rice.jpg"},
    "Stir-Fried Tofu Rice": {"copy_from": "/Users/nhungpham/Downloads/tofu-stir-fry-rice.jpg"},
    "Chicken Sizzling Hot Plate": {"copy_from": "/Users/nhungpham/Downloads/fried-chicken-rice-hot-plate.jpg"},
    "Beef Sizzling Hot Plate": {"copy_from": "/Users/nhungpham/Downloads/beef-sizzling.jpg"},
    "Pork Sizzling Hot Plate": {"copy_from": "/Users/nhungpham/Downloads/roastpork-rice-hotplate.png"},
    "Tofu Sizzling Hot Plate": {"copy_from": "/Users/nhungpham/Downloads/Tofu-rice-sizzling-hotplate.jpg"},
    "MCQ Sizzling Beef with Bread": {"copy_from": "/Users/nhungpham/Downloads/MCQ Sizzling Beef with Bread.jpg"},
    "Roast Pork Dry Noodles": {"copy_from": "/Users/nhungpham/Downloads/roast_pork_dry_noodles.jpg"},
    "Grilled Lemongrass Chicken Dry Noodles": {"queries": ["grilled lemongrass chicken vermicelli"]},
    "Grilled Lemongrass Beef Dry Noodles": {"copy_from": "/Users/nhungpham/Downloads/lemongrass-beef-noodles-salad..jpg"},
    "Grilled Lemongrass Pork Dry Noodles": {"copy_from": "/Users/nhungpham/Downloads/Grilled Lemongrass Pork Dry Noodle.jpgs.jpeg"},
    "Stir-Fried Tofu Dry Noodles": {
        "fixed": {
            "query": "lemongrass tofu vermicelli bowl",
            "title": "44. Lemongrass Organic Tofu Rice Vermicelli Noodle Bowl",
            "creator": "Martha Merry",
            "url": "https://live.staticflickr.com/7146/6824396059_9a161a8760_b.jpg",
        }
    },
    "Roast Pork Bánh Mì": {"copy_from": "/Users/nhungpham/Downloads/roast_pork_banhmi.jpg"},
    "Traditional Pork Bánh Mì": {
        "fixed": {
            "query": None,
            "title": "vietnamese-sandwich-banh-mi-image.jpg",
            "creator": "Extracted from user-provided HTML",
            "url": "https://www.happyfoodstube.com/wp-content/uploads/2018/08/vietnamese-sandwich-banh-mi-image.jpg",
            "landing_page": "https://www.happyfoodstube.com/vietnamese-sandwich-banh-mi/",
            "license": None,
            "license_version": None,
            "source": "derived-from-html",
        }
    },
    "Grilled Chicken Bánh Mì": {
        "fixed": {
            "query": None,
            "title": "lemongrass-chicken-banh-mi-10.jpg",
            "creator": "Extracted from user-provided HTML",
            "url": "https://thewoksoflife.com/wp-content/uploads/2019/06/lemongrass-chicken-banh-mi-10.jpg",
            "landing_page": "https://thewoksoflife.com/chicken-banh-mi/",
            "license": None,
            "license_version": None,
            "source": "derived-from-html",
        }
    },
    "Grilled Pork Bánh Mì": {"copy_from": "/Users/nhungpham/Downloads/Grilled-Pork-Bahn-Mi..jpg"},
    "Grilled Beef Bánh Mì": {"copy_from": "/Users/nhungpham/Downloads/grilled_beef_banhmi.jpg"},
    "Chicken Rice Paper Roll": {"queries": ["chicken spring rolls", "fresh chicken spring rolls"]},
    "Prawn and Pork Rice Paper Roll": {"queries": ["fresh spring rolls prawn pork", "prawn pork rice paper rolls"]},
    "Grilled Beef Rice Paper Roll": {"queries": ["beef spring rolls", "fresh beef spring rolls"]},
    "Detox Juice": {"copy_from": "/Users/nhungpham/Downloads/detox_jpg.jpeg"},
    "Immunity Juice": {"copy_from": "/Users/nhungpham/Downloads/immunity_juice.jpg"},
    "Sweet Beets Juice": {"queries": ["beet juice"]},
    "Green Glow Juice": {"queries": ["kiwi cucumber juice", "green juice"]},
    "Tropical Juice": {"copy_from": "/Users/nhungpham/Downloads/tropical_juice.jpg"},
    "Sugarcane Juice": {"copy_from": "/Users/nhungpham/Downloads/sugarcane.jpg"},
    "Avocado Smoothie": {"copy_from": "/Users/nhungpham/Downloads/avocado smothie.jpg"},
    "Strawberry Smoothie": {"copy_from": "/Users/nhungpham/Downloads/strawberry smothie.jpg"},
    "Mango Smoothie": {
        "fixed": {
            "query": "mango smoothie",
            "title": "Mango Smoothie",
            "creator": "Varin Tsai",
            "url": "https://live.staticflickr.com/2525/3939990857_cdb4e6dc49_b.jpg",
        }
    },
    "Mixed Berry Smoothie": {"queries": ["mixed berry smoothie"]},
    "Coconut Smoothie": {"queries": ["coconut smoothie"]},
    "Black Coffee": {"copy_from": "/Users/nhungpham/Downloads/black_coffee.jpg"},
    "Milk Coffee": {"copy_from": "/Users/nhungpham/Downloads/milk coffee.jpg"},
    "Kiwi Lemonade": {"copy_from": "/Users/nhungpham/Downloads/kiwi_lemonade.jpeg"},
    "Strawberry Lemonade": {"queries": ["strawberry lemonade"]},
    "Watermelon Lemonade": {"queries": ["watermelon lemonade"]},
    "Coconut Lemonade": {
        "fixed": {
            "query": "coconut lemonade",
            "title": "Coconut Lemonade. Hella good.",
            "creator": "permanently scatterbrained",
            "url": "https://live.staticflickr.com/8364/8310973477_ccb79b7059.jpg",
        }
    },
    "Pineapple Lemonade": {
        "fixed": {
            "query": "pineapple drink",
            "title": "The Pineapple Drink",
            "creator": "Studio Sarah Lou",
            "url": "https://live.staticflickr.com/2723/4376623293_8d17760ddc_b.jpg",
        }
    },
    "Aloe Vera Lemonade": {"copy_from": "/Users/nhungpham/Downloads/Aloe-Vera-Lemonade.jpg"},
    "Thai Dessert (Che Thai)": {"copy_from": "/Users/nhungpham/Downloads/che_thai.jpg"},
    "Red Bean Dessert": {"copy_from": "/Users/nhungpham/Downloads/red_bean_dessert_jpg.jpg"},
    "Coconut Milk Dessert": {"copy_from": "/Users/nhungpham/Downloads/coconut_milk_dessert.jpg"},
    "Banh Tieu": {"queries": ["banh tieu"]},
    "Chao Quay": {"queries": ["chao quay", "fried dough sticks"]},
    "Mung Bean Sesame Ball": {"copy_from": "/Users/nhungpham/Downloads/mung_bean_sesame_ball.jpg"},
    "Red Bean Sesame Ball": {"copy_from": "/Users/nhungpham/Downloads/red_bean_sesame_ball.jpeg"},
    "Banh Bao": {"copy_from": "/Users/nhungpham/Downloads/banhbao.jpg"},
    "Sticky Rice with Chicken / Savoury Sticky Rice": {"copy_from": "/Users/nhungpham/Downloads/sticky_rice.jpg"},
    "Banh Tai Yen": {"copy_from": "/Users/nhungpham/Downloads/tai_yen.jpg"},
    "Spring Roll": {"queries": ["fried spring roll"]},
    "Batiso": {"copy_from": "/Users/nhungpham/Downloads/batiso.jpg"},
    "Chicken Curry Puff": {"copy_from": "/Users/nhungpham/Downloads/Chicken-Curry-Puff.jpg"},
    "Fried Pork Dumpling": {"copy_from": "/Users/nhungpham/Downloads/fried_pork_dumpling.jpg"},
    "Fried Banana": {"copy_from": "/Users/nhungpham/Downloads/fried-bananas.jpg"},
}


def slugify(value: str) -> str:
    cleaned = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    cleaned = "".join(char.lower() if char.isalnum() else "-" for char in cleaned)
    cleaned = "-".join(filter(None, cleaned.split("-")))
    return cleaned or "item"


def search_openverse(query: str) -> List[dict]:
    response = requests.get(
        OPENVERSE_API,
        params={"q": query, "page_size": 15},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("results", [])


def choose_result(queries: Iterable[str], used_urls: set[str]) -> tuple[dict, str]:
    for query in queries:
        results = search_openverse(query)
        if not results:
            continue
        preferred = [res for res in results if res.get("width", 0) >= 600 and res.get("height", 0) >= 600]
        for result in preferred + results:
            url = result.get("url")
            if url and url not in used_urls:
                return result, query
    raise RuntimeError(f"No unique image result found for queries: {list(queries)}")


def save_processed_image(image: Image.Image, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    processed = ImageOps.fit(
        ImageOps.exif_transpose(image).convert("RGB"),
        TARGET_SIZE,
        method=Image.Resampling.LANCZOS,
    )
    processed.save(output_path, format="JPEG", quality=88, optimize=True)


def load_local_image(path: str) -> Image.Image:
    try:
        return Image.open(path)
    except Exception:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            temp_path = Path(tmp.name)
        try:
            subprocess.run(
                ["sips", "-s", "format", "jpeg", path, "--out", str(temp_path)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            with Image.open(temp_path) as converted:
                return converted.copy()
        finally:
            temp_path.unlink(missing_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download or copy menu item images.")
    parser.add_argument(
        "--items",
        nargs="*",
        help="Only refresh the named menu items. Existing manifest entries for other items are preserved.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    selected_items = args.items or list(ITEM_SOURCES)
    unknown_items = [item for item in selected_items if item not in ITEM_SOURCES]
    if unknown_items:
        raise SystemExit(f"Unknown menu items: {', '.join(unknown_items)}")

    existing_manifest = []
    if MANIFEST_PATH.exists():
        existing_manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    manifest_by_item = {entry["item"]: entry for entry in existing_manifest}
    used_urls: set[str] = set()
    if args.items:
        for entry in existing_manifest:
            item_name = entry.get("item")
            url = entry.get("url")
            if item_name not in selected_items and isinstance(url, str) and url.startswith("http"):
                used_urls.add(url)

    for item_name in selected_items:
        source = ITEM_SOURCES[item_name]
        output_path = OUTPUT_DIR / f"{slugify(item_name)}.jpg"

        copy_from = source.get("copy_from")
        if isinstance(copy_from, str):
            with load_local_image(copy_from) as image:
                save_processed_image(image, output_path)
            local_path = Path(copy_from)
            is_user_provided = local_path.is_absolute()
            manifest_by_item[item_name] = {
                "item": item_name,
                "query": None,
                "title": local_path.name,
                "creator": "User-provided asset" if is_user_provided else "Local project asset",
                "url": copy_from,
                "landing_page": None,
                "license": "local-use",
                "license_version": None,
                "source": "local-file" if is_user_provided else "local-project-asset",
                "output": str(output_path),
            }
            continue

        fixed = source.get("fixed")
        if isinstance(fixed, dict):
            fixed_url = fixed["url"]
            used_urls.add(fixed_url)
            response = requests.get(fixed_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
            response.raise_for_status()
            image = Image.open(io.BytesIO(response.content))
            save_processed_image(image, output_path)
            manifest_by_item[item_name] = {
                "item": item_name,
                "query": fixed.get("query"),
                "title": fixed.get("title"),
                "creator": fixed.get("creator"),
                "url": fixed_url,
                "landing_page": fixed.get("landing_page"),
                "license": fixed.get("license"),
                "license_version": fixed.get("license_version"),
                "source": fixed.get("source", "manual-selection"),
                "output": str(output_path),
            }
            print(f"Saved {output_path} from fixed source")
            continue

        queries = source.get("queries") or [item_name]
        result, matched_query = choose_result(queries, used_urls)
        used_urls.add(result["url"])
        response = requests.get(result["url"], headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        response.raise_for_status()
        image = Image.open(io.BytesIO(response.content))
        save_processed_image(image, output_path)
        manifest_by_item[item_name] = {
            "item": item_name,
            "query": matched_query,
            "title": result.get("title"),
            "creator": result.get("creator"),
            "url": result.get("url"),
            "landing_page": result.get("foreign_landing_url"),
            "license": result.get("license"),
            "license_version": result.get("license_version"),
            "source": result.get("source"),
            "output": str(output_path),
        }
        print(f"Saved {output_path} from query '{matched_query}'")

    manifest = [manifest_by_item[item_name] for item_name in ITEM_SOURCES if item_name in manifest_by_item]
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {MANIFEST_PATH} with {len(manifest)} entries.")


if __name__ == "__main__":
    main()
