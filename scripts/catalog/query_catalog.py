#!/usr/bin/env python3
"""
Quick Catalog Query Tool
========================
Simple interface to query the product catalog.

Usage:
    python query_catalog.py "comfortable grey sofa"
    python query_catalog.py "outdoor dining table" --source kavehome --max-price 1000
    python query_catalog.py "oak table" --category dining_table --material oak --max-width 200
    python query_catalog.py "eco-friendly furniture" --json

Requires: chromadb (pip install chromadb)
The catalog_vector_db/ directory must contain both the ChromaDB data
and the bundled ONNX model (created by: python catalog_vectordb.py build).
"""

import sys
import json
import argparse

try:
    from catalog_vectordb import (
        CatalogVectorDB, CATEGORY_VOCAB, STYLE_VOCAB, COLOR_FAMILIES,
        MATERIAL_VOCAB,
    )
except ImportError:
    print("Error: catalog_vectordb.py not found in the same directory")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Query the product catalog"
    )
    parser.add_argument("query", help="Natural language search query")
    parser.add_argument("-n", "--num", type=int, default=5, help="Number of results (default: 5)")
    parser.add_argument("-s", "--source", choices=["sweeek", "kavehome", "zarahome"],
                        help="Filter by catalog source")
    parser.add_argument("--max-price", type=float, help="Maximum price in EUR")
    parser.add_argument("--min-price", type=float, help="Minimum price in EUR")
    parser.add_argument("--min-rating", type=float, help="Minimum rating (0-5)")
    parser.add_argument("--category", choices=CATEGORY_VOCAB, help="Controlled category")
    parser.add_argument("--style", choices=STYLE_VOCAB, help="Style (set after enrichment)")
    parser.add_argument("--color-family", choices=COLOR_FAMILIES, help="Color family")
    parser.add_argument("--material", choices=MATERIAL_VOCAB, help="Primary material")
    parser.add_argument("--max-width", type=float,
                        help="Max width in cm (items with unknown dims pass, flagged dims_unknown)")
    parser.add_argument("--max-depth", type=float, help="Max depth in cm")
    parser.add_argument("--max-height", type=float, help="Max height in cm")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--full", action="store_true", help="Include full product data")

    args = parser.parse_args()

    # Initialize database
    print("Loading catalog database...", file=sys.stderr, flush=True)
    db = CatalogVectorDB()
    count = db.collection.count()
    print(f"Database loaded ({count} products)", file=sys.stderr, flush=True)

    if count == 0:
        print("Database is empty!")
        print("Run this first: python catalog_vectordb.py build")
        sys.exit(1)

    # Query
    results = db.query(
        query_text=args.query,
        n_results=args.num,
        source=args.source,
        max_price=args.max_price,
        min_price=args.min_price,
        min_rating=args.min_rating,
        category=args.category,
        style=args.style,
        color_family=args.color_family,
        material=args.material,
        max_width=args.max_width,
        max_depth=args.max_depth,
        max_height=args.max_height,
    )

    if args.json:
        if not args.full:
            for r in results:
                del r['full_product']
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        if not results:
            print("No results found.")
            return

        for i, r in enumerate(results, 1):
            sim = f"{r['similarity']*100:.0f}%" if r['similarity'] is not None else ""
            price = f"EUR {r['price']:.0f}" if r['price'] else ""

            print(f"\n{i}. {r['name']}")
            print(f"   Source: {r['source']} | Price: {price} | Match: {sim}")
            facts = [f"category: {r['category']}"]
            if r.get('primary_material'):
                facts.append(f"material: {r['primary_material']}")
            if r.get('color_family'):
                facts.append(f"color: {r['color_family']}")
            if r.get('dims_unknown'):
                facts.append("dims: unknown")
            else:
                facts.append(
                    f"dims: {r['width_cm']:.0f}x{r['depth_cm']:.0f}x{r['height_cm']:.0f}cm"
                    + (" (est.)" if r.get('dims_estimated') else "")
                )
            print(f"   {' | '.join(facts)}")
            print(f"   URL: {r['url']}")

            if args.full and r.get('full_product'):
                print(f"   Details: {json.dumps(r['full_product'], ensure_ascii=False)[:200]}...")


if __name__ == "__main__":
    main()
