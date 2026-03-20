#!/usr/bin/env python3
"""
Quick Catalog Query Tool
========================
Simple interface for Cursor agent to query the product catalog.

Usage:
    python query_catalog.py "comfortable grey sofa"
    python query_catalog.py "outdoor dining table" --source kavehome --max-price 1000
    python query_catalog.py "eco-friendly furniture" --json

Note: Requires "all" permissions. First query per session takes 30-60s to load vector DB.
"""

import sys
import json
import argparse

try:
    from catalog_vectordb import CatalogVectorDB
except ImportError:
    print("Error: catalog_vectordb.py not found in the same directory")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Query the product catalog (requires 'all' permissions; first query takes 30-60s)"
    )
    parser.add_argument("query", help="Natural language search query")
    parser.add_argument("-n", "--num", type=int, default=5, help="Number of results (default: 5)")
    parser.add_argument("-s", "--source", choices=["sweeek", "kavehome", "zarahome"], 
                        help="Filter by catalog source")
    parser.add_argument("--max-price", type=float, help="Maximum price in EUR")
    parser.add_argument("--min-rating", type=float, help="Minimum rating (0-5)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--full", action="store_true", help="Include full product data")
    
    args = parser.parse_args()
    
    # Initialize database (first load can take 30-60s for 314MB DB)
    print("Loading catalog database (10,865 products)...", file=sys.stderr, flush=True)
    db = CatalogVectorDB()
    print("✓ Database loaded", file=sys.stderr, flush=True)
    
    if db.collection.count() == 0:
        print("❌ Database is empty!")
        print("Run this first: python catalog_vectordb.py build")
        sys.exit(1)
    
    # Query
    results = db.query(
        query_text=args.query,
        n_results=args.num,
        source=args.source,
        max_price=args.max_price,
        min_rating=args.min_rating,
    )
    
    if args.json:
        # Clean output for JSON (remove full_product if not requested)
        if not args.full:
            for r in results:
                del r['full_product']
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        # Human-readable output
        if not results:
            print("No results found.")
            return
        
        for i, r in enumerate(results, 1):
            sim = f"{r['similarity']*100:.0f}%" if r['similarity'] else ""
            price = f"€{r['price']:.0f}" if r['price'] else ""
            
            print(f"\n{i}. {r['name']}")
            print(f"   Source: {r['source']} | Price: {price} | Match: {sim}")
            print(f"   URL: {r['url']}")
            
            if args.full and r.get('full_product'):
                print(f"   Details: {json.dumps(r['full_product'], ensure_ascii=False)[:200]}...")


if __name__ == "__main__":
    main()
