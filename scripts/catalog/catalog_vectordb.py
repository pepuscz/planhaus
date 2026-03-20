"""
Catalog Vector Database
=======================
A vector database for semantic search across multiple product catalogs.
Supports: sweeek, kavehome, zarahome catalogs with different schemas.

Features:
- Automatic schema normalization
- Incremental updates (only re-indexes changed products)
- Semantic search with natural language queries
- Filtering by source, price, color, etc.

Usage:
    # Build/update database
    python catalog_vectordb.py build
    
    # Query
    python catalog_vectordb.py query "comfortable grey sofa for small apartment"
    
    # Query with filters
    python catalog_vectordb.py query "outdoor dining table" --source kavehome --max-price 1000
"""

import json
import hashlib
import os
import re
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import argparse

try:
    import chromadb
    from chromadb.config import Settings
except ImportError:
    print("ChromaDB not installed. Run: pip install chromadb")
    exit(1)

def _setup_onnx_model_path(db_path: str) -> None:
    """Point ChromaDB's ONNX model to the bundled copy inside the DB directory.

    When building, the model is downloaded and cached into db_path/onnx_model/.
    At query time, we monkey-patch DOWNLOAD_PATH so ChromaDB finds it locally
    and never attempts a network download (which fails in sandboxed VMs).
    """
    from pathlib import Path
    model_dir = os.path.join(db_path, "onnx_model")
    onnx_dir = os.path.join(model_dir, "onnx")
    if os.path.isdir(onnx_dir):
        try:
            from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2
            ONNXMiniLM_L6_V2.DOWNLOAD_PATH = Path(model_dir)
        except ImportError:
            pass  # older chromadb version, skip


# =============================================================================
# Configuration
# =============================================================================

# Source catalogs — set CRAWL4AI_DIR env var to override default location
CRAWL4AI_DIR = os.environ.get("CRAWL4AI_DIR", os.path.expanduser("~/Documents/MCP/crawl4ai"))

CATALOG_CONFIGS = {
    "sweeek": {
        "path": f"{CRAWL4AI_DIR}/sweeek_catalog/catalog_llm.json",
        "id_prefix": "sw_",
    },
    "kavehome": {
        "path": f"{CRAWL4AI_DIR}/kavehome_catalog/catalog_llm.json",
        "id_prefix": "kh_",
    },
    "zarahome": {
        "path": f"{CRAWL4AI_DIR}/zarahome_catalog/catalog_llm.json",
        "id_prefix": "zh_",
    },
}

# Vector DB location — search order:
# 1. CATALOG_DB_PATH env var (explicit override)
# 2. ./catalog_vector_db (in current working directory / user project)
# 3. Next to this script (plugin directory, legacy)
def _find_db_path():
    if os.environ.get("CATALOG_DB_PATH"):
        return os.environ["CATALOG_DB_PATH"]
    cwd_path = os.path.join(os.getcwd(), "catalog_vector_db")
    if os.path.isdir(cwd_path):
        return cwd_path
    return os.path.join(os.path.dirname(__file__), "catalog_vector_db")

DB_PATH = _find_db_path()
COLLECTION_NAME = "products"
HASH_STORE_PATH = os.path.join(DB_PATH, "product_hashes.json")


# =============================================================================
# Schema Normalizers - Handle different catalog formats
# =============================================================================

def normalize_sweeek(product: Dict) -> Dict:
    """Normalize sweeek catalog product."""
    # Extract text for embedding
    text_parts = [
        product.get("name", ""),
        product.get("short_description", ""),
        product.get("description", ""),
    ]
    
    # Add specifications
    specs = product.get("specifications") or {}
    if specs:
        for key, value in specs.items():
            text_parts.append(f"{key}: {value}")
    
    # Add breadcrumbs for category context
    breadcrumbs = product.get("breadcrumbs") or []
    for bc in breadcrumbs:
        if bc:
            text_parts.append(bc.get("name", ""))
    
    # Parse price
    price = parse_price(product.get("current_price", ""))
    
    # Extract colors
    colors = []
    if product.get("color"):
        colors.append(product["color"].lower())
    for variant in (product.get("color_variants") or []):
        if variant and variant.get("name"):
            colors.append(variant["name"].lower())
    
    return {
        "id": product.get("id", ""),
        "source": "sweeek",
        "name": product.get("name", ""),
        "embedding_text": " ".join(filter(None, text_parts)),
        "price": price,
        "colors": colors,
        "category": breadcrumbs[-1]["name"] if breadcrumbs else "",
        "rating": float(product.get("rating", 0) or 0),
        "url": product.get("url", ""),
        "full_product": product,
    }


def normalize_kavehome(product: Dict) -> Dict:
    """Normalize kavehome catalog product."""
    # Extract text for embedding
    text_parts = [
        product.get("name", ""),
        product.get("collection", ""),
    ]
    
    # Add materials
    materials = product.get("materials") or []
    text_parts.extend(materials)
    
    # Add key details (kavehome has very rich details)
    details = product.get("details") or {}
    important_keys = [
        "Style", "Main material", "Fabric type  specifications",
        "Use", "Seating capacity", "Product shape"
    ]
    for key in important_keys:
        if key in details:
            text_parts.append(f"{key}: {details[key]}")
    
    # Add all yes/no features that are "Yes"
    for key, value in details.items():
        if value == "Yes" and "(yes/no)" in key:
            feature = key.replace(" (yes/no)", "")
            text_parts.append(feature)
    
    # Parse price
    price = parse_price(product.get("price", ""))
    
    # Colors
    colors = [c.lower() for c in (product.get("colors") or [])]
    
    return {
        "id": product.get("id", ""),
        "source": "kavehome",
        "name": product.get("name", ""),
        "embedding_text": " ".join(filter(None, text_parts)),
        "price": price,
        "colors": colors,
        "materials": materials,
        "category": product.get("collection", ""),
        "rating": 0.0,
        "url": product.get("url", ""),
        "full_product": product,
    }


def normalize_zarahome(product: Dict) -> Dict:
    """Normalize zarahome catalog product."""
    # Extract text for embedding
    text_parts = [
        product.get("name", ""),
        product.get("description", ""),
    ]
    
    # Add variant materials (these are actually related products, but contain category info)
    variants = product.get("variants") or {}
    
    # Colors from variants
    colors = [c.lower() for c in (variants.get("colors") or [])]
    
    # Parse price (zarahome has messy price format)
    price_str = product.get("price", "")
    price = parse_price(price_str)
    
    return {
        "id": product.get("id", ""),
        "source": "zarahome",
        "name": product.get("name", ""),
        "embedding_text": " ".join(filter(None, text_parts)),
        "price": price,
        "colors": colors,
        "category": "",
        "rating": 0.0,
        "url": product.get("url", ""),
        "full_product": product,
    }


def parse_price(price_str: str) -> float:
    """Extract numeric price from various formats."""
    if not price_str:
        return 0.0
    
    # Find all numbers (handle European format with comma as decimal)
    # Look for patterns like "1.499 €" or "69,99 €" or "27,99 € - 35,99 €"
    matches = re.findall(r'[\d.,]+', str(price_str))
    
    for match in matches:
        try:
            # Handle European format: 1.499 (thousands) or 69,99 (decimal)
            clean = match.replace('.', '').replace(',', '.')
            value = float(clean)
            if value > 0:
                return value
        except ValueError:
            continue
    
    return 0.0


NORMALIZERS = {
    "sweeek": normalize_sweeek,
    "kavehome": normalize_kavehome,
    "zarahome": normalize_zarahome,
}


# =============================================================================
# Vector Database Class
# =============================================================================

class CatalogVectorDB:
    """Vector database for product catalogs with incremental update support."""
    
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.hash_store_path = os.path.join(db_path, "product_hashes.json")

        # Use bundled ONNX model if available (avoids network download)
        _setup_onnx_model_path(db_path)

        # Initialize ChromaDB with persistent storage
        if not os.path.isdir(db_path):
            os.makedirs(db_path, exist_ok=True)
        self.client = chromadb.PersistentClient(path=db_path)
        
        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"description": "Multi-catalog product search"}
        )
        
        # Load existing hashes for change detection
        self.product_hashes = self._load_hashes()
    
    def _load_hashes(self) -> Dict[str, str]:
        """Load stored product hashes for change detection."""
        if os.path.exists(self.hash_store_path):
            with open(self.hash_store_path, 'r') as f:
                return json.load(f)
        return {}
    
    def _save_hashes(self):
        """Save product hashes."""
        with open(self.hash_store_path, 'w') as f:
            json.dump(self.product_hashes, f)
    
    def _compute_hash(self, product: Dict) -> str:
        """Compute hash of product for change detection."""
        # Hash the full product JSON
        content = json.dumps(product, sort_keys=True)
        return hashlib.md5(content.encode()).hexdigest()
    
    def load_catalog(self, source: str, config: Dict) -> List[Dict]:
        """Load and normalize a catalog file."""
        path = Path(config["path"])
        if not path.exists():
            print(f"  ⚠️  Catalog not found: {path}")
            return []
        
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Handle both array and object formats
        products = data.get("products", data) if isinstance(data, dict) else data
        
        # Normalize each product
        normalizer = NORMALIZERS[source]
        normalized = []
        for product in products:
            try:
                norm = normalizer(product)
                norm["_hash"] = self._compute_hash(product)
                normalized.append(norm)
            except Exception as e:
                print(f"  ⚠️  Error normalizing product: {e}")
        
        return normalized
    
    def build(self, force: bool = False):
        """Build or update the vector database from all catalogs."""
        print("🔄 Building/updating vector database...")
        
        all_products = []
        for source, config in CATALOG_CONFIGS.items():
            print(f"\n📦 Loading {source} catalog...")
            products = self.load_catalog(source, config)
            print(f"   Found {len(products)} products")
            all_products.extend(products)
        
        # Deduplicate by ID (keep first occurrence)
        seen_ids = set()
        unique_products = []
        duplicates = 0
        for product in all_products:
            if product["id"] not in seen_ids:
                seen_ids.add(product["id"])
                unique_products.append(product)
            else:
                duplicates += 1
        
        if duplicates > 0:
            print(f"\n⚠️  Removed {duplicates} duplicate products")
        
        all_products = unique_products
        print(f"\n📊 Total unique products: {len(all_products)}")
        
        # Determine what needs updating
        current_ids = set()
        to_add = []
        to_update = []
        
        for product in all_products:
            pid = product["id"]
            current_ids.add(pid)
            
            old_hash = self.product_hashes.get(pid)
            new_hash = product["_hash"]
            
            if force or old_hash is None:
                to_add.append(product)
            elif old_hash != new_hash:
                to_update.append(product)
        
        # Find products to remove (no longer in catalogs)
        existing_ids = set(self.product_hashes.keys())
        to_remove = existing_ids - current_ids
        
        print(f"\n📝 Changes detected:")
        print(f"   • New products: {len(to_add)}")
        print(f"   • Updated products: {len(to_update)}")
        print(f"   • Removed products: {len(to_remove)}")
        
        # Remove deleted products
        if to_remove:
            print(f"\n🗑️  Removing {len(to_remove)} products...")
            self.collection.delete(ids=list(to_remove))
            for pid in to_remove:
                del self.product_hashes[pid]
        
        # Update changed products (delete then add)
        if to_update:
            print(f"\n🔄 Updating {len(to_update)} products...")
            update_ids = [p["id"] for p in to_update]
            self.collection.delete(ids=update_ids)
            self._add_products(to_update)
        
        # Add new products
        if to_add:
            print(f"\n➕ Adding {len(to_add)} products...")
            self._add_products(to_add)
        
        # Save hashes
        self._save_hashes()

        # Bundle ONNX embedding model into the DB directory for offline use
        self._cache_onnx_model()

        print(f"\n✅ Database ready! Total products indexed: {self.collection.count()}")
    
    def _cache_onnx_model(self):
        """Download and cache the ONNX embedding model inside the DB directory.

        This makes the DB self-contained: queries work without network access.
        The model (~80MB) is downloaded from ChromaDB's S3 bucket on first build,
        then bundled at db_path/onnx_model/ for offline use.
        """
        import shutil
        from pathlib import Path

        dest = os.path.join(self.db_path, "onnx_model")
        onnx_dest = os.path.join(dest, "onnx")
        if os.path.isdir(onnx_dest) and len(os.listdir(onnx_dest)) >= 5:
            print("\n📦 ONNX model already bundled, skipping.")
            return

        try:
            from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2

            print("\n📦 Caching ONNX embedding model for offline use...")

            # Trigger download to default cache location
            ef = ONNXMiniLM_L6_V2()
            ef(["trigger download"])

            # Copy from default cache to DB directory
            src = Path.home() / ".cache" / "chroma" / "onnx_models" / "all-MiniLM-L6-v2"
            src_onnx = src / "onnx"
            if src_onnx.is_dir():
                os.makedirs(dest, exist_ok=True)
                if os.path.exists(onnx_dest):
                    shutil.rmtree(onnx_dest)
                shutil.copytree(str(src_onnx), onnx_dest)
                print(f"   ✅ Model cached at {dest}")
            else:
                print(f"   ⚠️  Model source not found at {src_onnx}")
        except Exception as e:
            print(f"   ⚠️  Could not cache ONNX model: {e}")
            print("   Queries will require network access to download the model.")

    def _add_products(self, products: List[Dict], batch_size: int = 500):
        """Add products to the collection in batches."""
        for i in range(0, len(products), batch_size):
            batch = products[i:i + batch_size]
            
            ids = []
            documents = []
            metadatas = []
            
            for product in batch:
                ids.append(product["id"])
                documents.append(product["embedding_text"])
                
                # Prepare metadata (ChromaDB requires flat structure for filtering)
                metadata = {
                    "source": product["source"],
                    "name": product["name"],
                    "price": product["price"],
                    "category": product["category"],
                    "rating": product["rating"],
                    "url": product["url"],
                    "colors": json.dumps(product.get("colors", [])),
                    "full_product": json.dumps(product["full_product"]),
                }
                metadatas.append(metadata)
                
                # Update hash store
                self.product_hashes[product["id"]] = product["_hash"]
            
            self.collection.add(
                ids=ids,
                documents=documents,
                metadatas=metadatas
            )
            
            print(f"   Indexed {min(i + batch_size, len(products))}/{len(products)} products")
    
    def query(
        self,
        query_text: str,
        n_results: int = 10,
        source: Optional[str] = None,
        max_price: Optional[float] = None,
        min_rating: Optional[float] = None,
    ) -> List[Dict]:
        """
        Query the vector database with natural language.
        
        Args:
            query_text: Natural language query
            n_results: Number of results to return
            source: Filter by catalog source (sweeek, kavehome, zarahome)
            max_price: Maximum price filter
            min_rating: Minimum rating filter
        
        Returns:
            List of matching products with similarity scores
        """
        # Build where clause for filtering
        where = None
        where_conditions = []
        
        if source:
            where_conditions.append({"source": source})
        if max_price is not None:
            where_conditions.append({"price": {"$lte": max_price}})
        if min_rating is not None:
            where_conditions.append({"rating": {"$gte": min_rating}})
        
        if len(where_conditions) == 1:
            where = where_conditions[0]
        elif len(where_conditions) > 1:
            where = {"$and": where_conditions}
        
        # Query the collection
        results = self.collection.query(
            query_texts=[query_text],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"]
        )
        
        # Format results
        formatted = []
        if results and results['ids'] and results['ids'][0]:
            for i, pid in enumerate(results['ids'][0]):
                metadata = results['metadatas'][0][i]
                distance = results['distances'][0][i] if results.get('distances') else None
                
                # Parse full product from metadata
                full_product = json.loads(metadata.get('full_product', '{}'))
                
                formatted.append({
                    "id": pid,
                    "name": metadata.get("name", ""),
                    "source": metadata.get("source", ""),
                    "price": metadata.get("price", 0),
                    "url": metadata.get("url", ""),
                    "similarity": 1 - distance if distance else None,  # Convert distance to similarity
                    "colors": json.loads(metadata.get("colors", "[]")),
                    "full_product": full_product,
                })
        
        return formatted
    
    def stats(self) -> Dict:
        """Get database statistics."""
        count = self.collection.count()
        
        # Count by source
        sources = {}
        for source in CATALOG_CONFIGS.keys():
            try:
                result = self.collection.get(where={"source": source}, include=[])
                sources[source] = len(result['ids'])
            except:
                sources[source] = 0
        
        return {
            "total_products": count,
            "by_source": sources,
            "db_path": self.db_path,
        }


# =============================================================================
# CLI Interface
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Catalog Vector Database - Semantic search across product catalogs"
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Build command
    build_parser = subparsers.add_parser("build", help="Build or update the vector database")
    build_parser.add_argument("--force", action="store_true", help="Force full rebuild")
    
    # Query command
    query_parser = subparsers.add_parser("query", help="Query the database")
    query_parser.add_argument("text", help="Search query")
    query_parser.add_argument("-n", "--num-results", type=int, default=5, help="Number of results")
    query_parser.add_argument("-s", "--source", choices=["sweeek", "kavehome", "zarahome"], help="Filter by source")
    query_parser.add_argument("--max-price", type=float, help="Maximum price")
    query_parser.add_argument("--min-rating", type=float, help="Minimum rating")
    query_parser.add_argument("--full", action="store_true", help="Show full product details")
    query_parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    # Stats command
    stats_parser = subparsers.add_parser("stats", help="Show database statistics")
    
    args = parser.parse_args()
    
    if args.command == "build":
        db = CatalogVectorDB()
        db.build(force=args.force)
    
    elif args.command == "query":
        db = CatalogVectorDB()
        
        if db.collection.count() == 0:
            print("❌ Database is empty. Run 'python catalog_vectordb.py build' first.")
            return
        
        results = db.query(
            query_text=args.text,
            n_results=args.num_results,
            source=args.source,
            max_price=args.max_price,
            min_rating=args.min_rating,
        )
        
        if args.json:
            print(json.dumps(results, indent=2, ensure_ascii=False))
        else:
            print(f"\n🔍 Query: \"{args.text}\"")
            print(f"📊 Found {len(results)} results:\n")
            
            for i, result in enumerate(results, 1):
                similarity_pct = f"{result['similarity']*100:.1f}%" if result['similarity'] else "N/A"
                price_str = f"€{result['price']:.2f}" if result['price'] else "N/A"
                
                print(f"{i}. [{result['source']}] {result['name']}")
                print(f"   💰 {price_str}  |  📊 Similarity: {similarity_pct}")
                print(f"   🔗 {result['url']}")
                
                if args.full:
                    print(f"   📦 Full data: {json.dumps(result['full_product'], indent=6, ensure_ascii=False)[:500]}...")
                
                print()
    
    elif args.command == "stats":
        db = CatalogVectorDB()
        stats = db.stats()
        
        print("\n📊 Database Statistics")
        print("=" * 40)
        print(f"Total products: {stats['total_products']}")
        print(f"\nBy source:")
        for source, count in stats['by_source'].items():
            print(f"  • {source}: {count}")
        print(f"\nDatabase path: {stats['db_path']}")
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
