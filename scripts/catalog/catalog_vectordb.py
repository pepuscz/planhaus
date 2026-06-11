"""
Catalog Vector Database
=======================
A vector database for semantic search across multiple product catalogs.
Supports: sweeek, kavehome, zarahome catalogs with different schemas.

Features:
- Automatic schema normalization
- Enriched flat metadata (dimensions, category, material, color family, style)
- Incremental updates (only re-indexes changed products)
- Semantic search with natural language queries (cosine similarity)
- Multi-criteria filtering (source, price, category, style, color, material, dims)
- LLM enrichment loop: `enrich export` / `enrich import` (no re-embedding)

Usage:
    # Build/update database (use --force after upgrading to v2 metadata)
    python catalog_vectordb.py build [--force]

    # Query
    python catalog_vectordb.py query "comfortable grey sofa for small apartment"

    # Query with filters
    python catalog_vectordb.py query "dining table" --category dining_table \
        --max-price 800 --max-width 200 --material oak

    # Enrichment round-trip
    python catalog_vectordb.py enrich export --missing style --out pending.jsonl
    python catalog_vectordb.py enrich import --in enriched.jsonl
"""

import json
import hashlib
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Optional, List, Dict, Tuple
import argparse

# NOTE: chromadb is imported lazily (inside CatalogVectorDB) so the pure
# helpers below (parse_price, parse_dims_*, classify_category, ...) are
# usable and testable without chromadb installed.


def _require_chromadb():
    try:
        import chromadb
        return chromadb
    except ImportError:
        print("ChromaDB not installed. Run: pip install chromadb", file=sys.stderr)
        raise SystemExit(1)


def _setup_onnx_model_path(db_path: str) -> None:
    """Point ChromaDB's ONNX model to the bundled copy inside the DB directory.

    When building, the model is downloaded and cached into db_path/onnx_model/.
    At query time, we monkey-patch DOWNLOAD_PATH so ChromaDB finds it locally
    and never attempts a network download (which fails in sandboxed VMs).
    """
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
DB_VERSION = 2  # stamped in db_meta.json; v2 = enriched metadata + cosine space


# =============================================================================
# Controlled vocabularies (single source of truth: docs/architecture.md)
# =============================================================================

CATEGORY_VOCAB = [
    "sofa", "armchair", "dining_table", "dining_chair", "coffee_table",
    "side_table", "bed", "nightstand", "wardrobe", "dresser", "bookshelf",
    "rug", "floor_lamp", "table_lamp", "pendant", "mirror", "decor",
    "outdoor", "other",
]

SEATING_CATEGORIES = {"sofa", "armchair", "dining_chair"}

MATERIAL_VOCAB = [
    "oak", "walnut", "pine", "rattan", "metal", "glass", "boucle",
    "linen", "velvet", "leather", "marble", "ceramic", "other",
]

COLOR_FAMILIES = [
    "white", "cream", "beige", "grey", "charcoal", "black", "brown",
    "natural_wood", "green", "blue", "terracotta", "pink", "yellow",
    "multicolor",
]

STYLE_VOCAB = [
    "scandinavian", "midcentury", "modern", "industrial", "rustic",
    "traditional", "coastal", "japandi", "mediterranean", "bohemian",
    "eclectic",
]


# =============================================================================
# Text helpers (pure, no chromadb needed)
# =============================================================================

def _fold(s: str) -> str:
    """Lowercase + strip accents (canapé -> canape) for keyword matching."""
    s = unicodedata.normalize("NFKD", str(s).lower()).replace("’", "'")
    return "".join(c for c in s if not unicodedata.combining(c))


def _phrase_regex(phrase: str) -> "re.Pattern":
    """Word-boundary regex for a (folded) phrase, tolerating simple plurals."""
    pattern = r"\s+".join(re.escape(w) + r"s?" for w in phrase.split())
    return re.compile(r"(?<![a-z0-9])" + pattern + r"(?![a-z0-9])")


_REGEX_CACHE: Dict[str, "re.Pattern"] = {}


def _match_phrase(phrase: str, folded_text: str) -> bool:
    rx = _REGEX_CACHE.get(phrase)
    if rx is None:
        rx = _phrase_regex(phrase)
        _REGEX_CACHE[phrase] = rx
    return bool(rx.search(folded_text))


# =============================================================================
# Price parsing
# =============================================================================

def parse_price(price_str: str) -> float:
    """Extract numeric price from various formats.

    Handles EU decimals ("69,99 €"), dot thousands ("1.499 €"), US format
    ("€1,499.00") and space/nbsp thousands ("1 299,00 €").
    """
    if not price_str:
        return 0.0
    s = str(price_str)
    # Join space/nbsp-grouped thousands: "1 299,00" -> "1299,00"
    s = re.sub(r"(\d)[\s  ]+(?=\d{3}\b)", r"\1", s)

    best = 0.0
    for match in re.findall(r"[\d.,]+", s):
        try:
            # A trailing ".dd" / ",dd" group is the decimal part; other
            # separators are thousands groupers.
            m = re.fullmatch(r"(\d{1,3}(?:[.,\s]\d{3})*|\d+)(?:([.,])(\d{1,2}))?", match)
            if m:
                whole = re.sub(r"[.,\s]", "", m.group(1))
                value = float(f"{whole}.{m.group(3)}" if m.group(3) else whole)
            else:
                value = float(match.replace(".", "").replace(",", "."))
        except ValueError:
            continue
        # Prefer the first complete price, not a stray leading digit
        if value > 0 and best == 0.0:
            best = value
    return best


# =============================================================================
# Dimension parsing
# =============================================================================

_NUM = r"(\d+(?:[.,]\d+)?)"

# "W200 x D90 x H75 cm" / "L 200 x P 90 x H 75" (labelled → not estimated)
_LABELED_TRIPLE_RE = re.compile(
    r"(?<![a-z0-9])[lw]\.?\s*:?\s*" + _NUM +
    r"\s*(?:cm)?\s*[x×*]\s*[dp]\.?\s*:?\s*" + _NUM +
    r"\s*(?:cm)?\s*[x×*]\s*h\.?\s*:?\s*" + _NUM + r"\s*(?:cm)?(?![0-9])",
    re.IGNORECASE,
)

# "200 x 90 x 75 cm" (unlabelled, assume W x D x H → estimated)
_TRIPLE_RE = re.compile(
    _NUM + r"\s*(?:cm)?\s*[x×*]\s*" + _NUM + r"\s*(?:cm)?\s*[x×*]\s*" + _NUM + r"\s*cm(?![a-z0-9])",
    re.IGNORECASE,
)

# "160 x 230 cm" (pair, assume W x D → estimated; common for rugs/tables)
_PAIR_RE = re.compile(
    _NUM + r"\s*(?:cm)?\s*[x×*]\s*" + _NUM + r"\s*cm(?![a-z0-9])",
    re.IGNORECASE,
)

_MEASURE_RE = re.compile(_NUM + r"\s*(cm|mm|m)?(?![a-z0-9])", re.IGNORECASE)

_WIDTH_TOKENS = ("width", "largeur", "ancho", "anchura", "breite")
_DEPTH_TOKENS = ("depth", "profondeur", "fondo", "profundidad", "tiefe")
_HEIGHT_TOKENS = ("height", "hauteur", "alto", "altura", "hohe")
_LENGTH_TOKENS = ("length", "longueur", "largo")
# Keys that measure a part, not the whole product
_EXCLUDE_KEY_TOKENS = (
    "seat", "assise", "asiento", "arm", "armrest", "accoudoir", "reposabrazos",
    "leg", "pied", "pata", "package", "packaging", "box", "colis", "emballage",
    "embalaje", "mattress", "matelas", "colchon", "drawer", "tiroir", "cajon",
    "inside", "interior", "inner", "shade",
)


def _num_to_float(s: str) -> float:
    return float(s.replace(",", "."))


def _to_cm(value: float, unit: Optional[str]) -> float:
    unit = (unit or "cm").lower()
    if unit == "mm":
        return value / 10.0
    if unit == "m":
        return value * 100.0
    return value


def _parse_measure(value) -> Optional[float]:
    """First number (with optional cm/mm/m unit) in a string → cm, or None."""
    m = _MEASURE_RE.search(_fold(value))
    if not m:
        return None
    cm = _to_cm(_num_to_float(m.group(1)), m.group(2))
    return cm if cm > 0 else None


def _key_has_token(key_folded: str, tokens) -> bool:
    return any(re.search(r"(?<![a-z])" + re.escape(t) + r"(?![a-z])", key_folded)
               for t in tokens)


def parse_dims_from_text(text: str) -> Tuple[float, float, float, bool]:
    """Parse (width_cm, depth_cm, height_cm, estimated) from free text.

    Labelled "W.. x D.. x H.." patterns are trusted (estimated=False).
    Unlabelled "200 x 90 x 75 cm" triples assume W x D x H order and
    "160 x 230 cm" pairs assume W x D (estimated=True).
    """
    if not text:
        return 0.0, 0.0, 0.0, False
    folded = _fold(text)

    m = _LABELED_TRIPLE_RE.search(folded)
    if m:
        return (_num_to_float(m.group(1)), _num_to_float(m.group(2)),
                _num_to_float(m.group(3)), False)

    m = _TRIPLE_RE.search(folded)
    if m:
        a, b, c = (_num_to_float(m.group(i)) for i in (1, 2, 3))
        # Quantity pattern guard: "set of 2 x 45 x 45 cm" / "pair ... 2 x 140 x 260 cm"
        # — a small leading integer next to two real measures is a count, not a width.
        prefix = folded[max(0, m.start() - 12):m.start()]
        count_context = any(t in prefix for t in
                            ("set of", "pack", "pair", "lot de", "juego de", "set de"))
        if (a < 10 and a == int(a) and b >= 20 and c >= 20) or count_context:
            return b, c, 0.0, True   # treat as count × W × H → keep the two measures
        return a, b, c, True

    m = _PAIR_RE.search(folded)
    if m:
        return _num_to_float(m.group(1)), _num_to_float(m.group(2)), 0.0, True

    return 0.0, 0.0, 0.0, False


def parse_dims_from_dict(spec: Dict) -> Tuple[float, float, float, bool]:
    """Parse (width_cm, depth_cm, height_cm, estimated) from a specs/details dict.

    Handles explicit per-dimension keys in EN/FR/ES/DE ("Width", "Largeur",
    "Ancho", "Total height measurement"...) and full "W x D x H" strings in
    values. Part measurements (seat/arm/leg/package...) are ignored.
    """
    if not spec:
        return 0.0, 0.0, 0.0, False

    w = d = h = None
    estimated = False

    # Pass 1 — explicit per-dimension keys (trusted, not estimated)
    for key, value in spec.items():
        key_f = _fold(key)
        if _key_has_token(key_f, _EXCLUDE_KEY_TOKENS):
            continue
        if w is None and _key_has_token(key_f, _WIDTH_TOKENS):
            w = _parse_measure(value)
        elif h is None and _key_has_token(key_f, _HEIGHT_TOKENS):
            h = _parse_measure(value)
        elif d is None and _key_has_token(key_f, _DEPTH_TOKENS):
            d = _parse_measure(value)

    # Length as depth fallback (tables: "Length 200 x Width 90")
    if d is None:
        for key, value in spec.items():
            key_f = _fold(key)
            if _key_has_token(key_f, _EXCLUDE_KEY_TOKENS):
                continue
            if _key_has_token(key_f, _LENGTH_TOKENS):
                d = _parse_measure(value)
                if d is not None:
                    break

    # Pass 2 — "200 x 90 x 75 cm" style strings inside values
    if w is None or d is None or h is None:
        for key, value in spec.items():
            key_f = _fold(key)
            if _key_has_token(key_f, _EXCLUDE_KEY_TOKENS):
                continue
            tw, td, th, test = parse_dims_from_text(str(value))
            if tw or td or th:
                if w is None and tw:
                    w = tw
                if d is None and td:
                    d = td
                if h is None and th:
                    h = th
                estimated = estimated or test
                break

    return (w or 0.0, d or 0.0, h or 0.0, estimated)


def parse_seat_height(spec: Optional[Dict] = None, text: str = "") -> Optional[float]:
    """Seat height in cm from a specs dict or free text, or None."""
    if spec:
        for key, value in spec.items():
            key_f = _fold(key)
            seatish = _key_has_token(key_f, ("seat", "assise", "asiento"))
            heightish = _key_has_token(key_f, _HEIGHT_TOKENS)
            if seatish and heightish:
                v = _parse_measure(value)
                if v:
                    return v
    if text:
        m = re.search(
            r"(?:seat height|hauteur d'assise|hauteur assise|altura (?:del? )?asiento)"
            r"\s*:?\s*" + _NUM + r"\s*cm",
            _fold(text),
        )
        if m:
            return _num_to_float(m.group(1))
    return None


# =============================================================================
# Category classification (shared across normalizers)
# =============================================================================

# Ordered: first matching rule wins. Keywords are accent-folded; simple
# plurals (trailing s) are tolerated automatically.
_CATEGORY_RULES = [
    ("outdoor", ["outdoor", "garden", "jardin", "exterieur", "exterior",
                 "terrasse", "terrace", "patio", "balcony", "balcon"]),
    # Strong decor/textile phrases that would otherwise leak into bed/table/...
    ("decor", ["bed linen", "duvet", "pillowcase", "cushion", "coussin",
               "cojin", "throw", "blanket", "manta", "candle", "bougie",
               "vela", "vase", "jarron", "basket", "panier", "cesta",
               "curtain", "rideau", "cortina", "towel", "serviette", "toalla",
               "tablecloth", "nappe", "bedspread", "couvre-lit",
               "photo frame", "picture frame", "plant", "plante", "planta",
               "wall art", "poster", "ornament", "figurine", "candleholder",
               "candlestick", "lantern", "lanterne", "farol", "tray",
               "bandeja"]),
    ("floor_lamp", ["floor lamp", "lampadaire", "lampara de pie",
                    "standing lamp"]),
    ("table_lamp", ["table lamp", "desk lamp", "bedside lamp",
                    "lampe a poser", "lampe de table", "lampe de chevet",
                    "lampe de bureau", "lampara de mesa",
                    "lampara de sobremesa"]),
    ("pendant", ["pendant", "suspension", "ceiling lamp", "ceiling light",
                 "chandelier", "lampara de techo", "plafonnier",
                 "hanging lamp", "lustre"]),
    ("coffee_table", ["coffee table", "table basse", "mesa de centro",
                      "mesa de cafe"]),
    ("side_table", ["side table", "end table", "table d'appoint",
                    "bout de canape", "mesa auxiliar", "console table",
                    "console"]),
    ("nightstand", ["nightstand", "night stand", "bedside table", "bedside",
                    "table de chevet", "chevet", "mesita de noche",
                    "mesilla de noche", "mesilla", "mesita"]),
    ("dining_table", ["dining table", "table a manger",
                      "table de salle a manger", "table de repas",
                      "mesa de comedor", "extendable table",
                      "table extensible", "round table", "table ronde"]),
    ("armchair", ["armchair", "fauteuil", "sillon", "lounge chair",
                  "accent chair", "rocking chair", "butaca"]),
    ("sofa", ["sofa", "canape", "couch", "loveseat", "settee", "divan",
              "sectional", "chaise longue", "sofa bed"]),
    ("dining_chair", ["dining chair", "chaise", "silla", "chair", "stool",
                      "tabouret", "taburete"]),
    ("bed", ["bed", "lit", "cama", "headboard", "tete de lit", "cabecero",
             "sommier", "bed frame", "daybed"]),
    ("wardrobe", ["wardrobe", "armoire", "armario", "closet", "penderie",
                  "ropero", "dressing"]),
    ("dresser", ["dresser", "commode", "comoda", "chest of drawers",
                 "sideboard", "buffet", "aparador", "credenza", "tv stand",
                 "meuble tv", "mueble tv", "tv unit", "media unit"]),
    ("bookshelf", ["bookshelf", "bookcase", "shelving", "shelf",
                   "bibliotheque", "etagere", "estanteria", "libreria",
                   "estante"]),
    ("rug", ["rug", "tapis", "alfombra", "carpet"]),
    ("mirror", ["mirror", "miroir", "espejo"]),
    ("decor", ["decoration", "deco", "decorative", "accessoire",
               "accessory"]),
]


def classify_category(name: str, breadcrumb_text: str = "") -> str:
    """Map product name + breadcrumb/collection text to the controlled
    category vocab. Shared by all normalizers. Returns "other" when nothing
    matches."""
    text = _fold(f"{name or ''} {breadcrumb_text or ''}")
    for category, phrases in _CATEGORY_RULES:
        for phrase in phrases:
            if _match_phrase(phrase, text):
                return category
    return "other"


# =============================================================================
# Material extraction
# =============================================================================

_MATERIAL_SYNONYMS = {
    "oak": ["oak", "chene", "roble"],
    "walnut": ["walnut", "noyer", "nogal"],
    "pine": ["pine", "pin", "pino"],
    "rattan": ["rattan", "rotin", "ratan", "wicker", "osier", "mimbre",
               "cane"],
    "metal": ["metal", "steel", "acier", "acero", "iron", "hierro",
              "aluminium", "aluminum", "aluminio", "brass", "laiton",
              "laton"],
    "glass": ["glass", "verre", "vidrio", "cristal"],
    "boucle": ["boucle"],
    "linen": ["linen", "lin", "lino"],
    "velvet": ["velvet", "velours", "terciopelo"],
    "leather": ["leather", "cuir", "cuero", "piel"],
    "marble": ["marble", "marbre", "marmol"],
    "ceramic": ["ceramic", "ceramique", "ceramica", "porcelain",
                "porcelaine", "porcelana", "stoneware", "gres"],
}


def extract_primary_material(texts: List[str]) -> str:
    """Scan text blobs (in priority order) for materials. Within each blob,
    the doc's vocab order decides; the first blob with any hit wins. Returns
    "other" when nothing matches."""
    for text in texts:
        if not text:
            continue
        folded = _fold(text)
        for material in MATERIAL_VOCAB:
            if material == "other":
                continue
            for syn in _MATERIAL_SYNONYMS.get(material, []):
                if _match_phrase(syn, folded):
                    return material
    return "other"


# =============================================================================
# Color family mapping
# =============================================================================

# Ordered per-color matching (charcoal before grey, cream before white...).
_COLOR_FAMILY_RULES = [
    ("multicolor", ["multicolor", "multicolour", "multicolore", "multi"]),
    ("charcoal", ["charcoal", "anthracite", "antracita", "graphite",
                  "grafito"]),
    ("black", ["black", "noir", "negro", "ebony"]),
    ("cream", ["cream", "creme", "crema", "ivory", "ivoire", "marfil",
               "ecru", "off white", "off-white", "offwhite", "vanilla"]),
    ("white", ["white", "blanc", "blanco", "snow"]),
    ("beige", ["beige", "sand", "sable", "arena", "taupe", "camel", "tan",
               "greige", "stone", "linen"]),
    ("natural_wood", ["natural", "oak", "chene", "roble", "walnut", "noyer",
                      "nogal", "teak", "teck", "wood", "bois", "madera",
                      "acacia", "wenge", "beech", "hetre", "haya",
                      "fresno"]),
    ("brown", ["brown", "marron", "chocolate", "cognac", "coffee", "mocha",
               "espresso", "chestnut", "caramel", "hazelnut", "tobacco",
               "tabaco"]),
    ("grey", ["grey", "gray", "gris", "silver", "plata", "slate"]),
    ("green", ["green", "vert", "verde", "olive", "sage", "mint", "emerald",
               "khaki", "forest"]),
    ("blue", ["blue", "bleu", "azul", "navy", "indigo", "denim", "turquoise",
              "teal", "petrol", "sky", "cobalt", "marine"]),
    ("terracotta", ["terracotta", "terre cuite", "teja", "rust", "rouille",
                    "brick", "clay", "sienna", "red", "rouge", "rojo",
                    "burgundy", "bordeaux", "coral"]),
    ("pink", ["pink", "rose", "rosa", "blush", "fuchsia", "mauve", "lilac",
              "purple", "violet", "lavender", "lavande", "lila", "salmon"]),
    ("yellow", ["yellow", "jaune", "amarillo", "mustard", "moutarde",
                "mostaza", "gold", "dore", "dorado", "ochre", "ocre",
                "honey", "miel"]),
]


def _match_color_family(color: str) -> str:
    folded = _fold(color)
    for family, phrases in _COLOR_FAMILY_RULES:
        for phrase in phrases:
            if _match_phrase(phrase, folded):
                return family
    return ""


def map_color_family(colors: List[str]) -> str:
    """Map a product's colors list to one color family. First match wins;
    3+ distinct families → multicolor; no match → ""."""
    families: List[str] = []
    for color in colors or []:
        fam = _match_color_family(color)
        if fam == "multicolor":
            return "multicolor"
        if fam and fam not in families:
            families.append(fam)
    if len(families) >= 3:
        return "multicolor"
    return families[0] if families else ""


# =============================================================================
# Schema Normalizers - Handle different catalog formats
# =============================================================================

def _enriched_fields(name: str, breadcrumb_text: str, spec_dict: Optional[Dict],
                     free_text: str, material_texts: List[str],
                     colors: List[str]) -> Dict:
    """Shared enrichment: flat filterable metadata written at build time.
    Never produces None values (ChromaDB metadata constraint)."""
    category = classify_category(name, breadcrumb_text)

    w = d = h = 0.0
    estimated = False
    if spec_dict:
        w, d, h, estimated = parse_dims_from_dict(spec_dict)
    if not (w or d or h) and free_text:
        w, d, h, estimated = parse_dims_from_text(free_text)

    seat_height = None
    if category in SEATING_CATEGORIES:
        seat_height = parse_seat_height(spec_dict, free_text)

    return {
        "category": category,
        "width_cm": float(w),
        "depth_cm": float(d),
        "height_cm": float(h),
        "dims_estimated": bool(estimated),
        "primary_material": extract_primary_material(material_texts),
        "color_family": map_color_family(colors),
        "style": "",  # filled by `enrich import` (LLM enrichment)
        "seat_height_cm": float(seat_height or 0.0),
    }


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
    breadcrumb_names = [bc.get("name", "") for bc in breadcrumbs if bc]
    text_parts.extend(breadcrumb_names)

    # Parse price
    price = parse_price(product.get("current_price", ""))

    # Extract colors
    colors = []
    if product.get("color"):
        colors.append(product["color"].lower())
    for variant in (product.get("color_variants") or []):
        if variant and variant.get("name"):
            colors.append(variant["name"].lower())

    free_text = " ".join(filter(None, [
        product.get("short_description", ""), product.get("description", "")
    ]))
    spec_text = " ".join(f"{k}: {v}" for k, v in specs.items())

    norm = {
        "id": product.get("id", ""),
        "source": "sweeek",
        "name": product.get("name", ""),
        "embedding_text": " ".join(filter(None, text_parts)),
        "price": price,
        "colors": colors,
        "rating": float(product.get("rating", 0) or 0),
        "url": product.get("url", ""),
        "full_product": product,
    }
    norm.update(_enriched_fields(
        name=norm["name"],
        breadcrumb_text=" ".join(breadcrumb_names),
        spec_dict=specs,
        free_text=free_text,
        material_texts=[spec_text, free_text, norm["name"]],
        colors=colors,
    ))
    return norm


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

    details_text = " ".join(f"{k}: {v}" for k, v in details.items())

    norm = {
        "id": product.get("id", ""),
        "source": "kavehome",
        "name": product.get("name", ""),
        "embedding_text": " ".join(filter(None, text_parts)),
        "price": price,
        "colors": colors,
        "materials": materials,
        "rating": 0.0,
        "url": product.get("url", ""),
        "full_product": product,
    }
    norm.update(_enriched_fields(
        name=norm["name"],
        breadcrumb_text=product.get("collection", ""),
        spec_dict=details,
        free_text=details_text,
        # materials list first (most reliable, in listed order), then details, then name
        material_texts=[*materials, details_text, norm["name"]],
        colors=colors,
    ))
    return norm


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

    description = product.get("description", "")

    norm = {
        "id": product.get("id", ""),
        "source": "zarahome",
        "name": product.get("name", ""),
        "embedding_text": " ".join(filter(None, text_parts)),
        "price": price,
        "colors": colors,
        "rating": 0.0,
        "url": product.get("url", ""),
        "full_product": product,
    }
    norm.update(_enriched_fields(
        name=norm["name"],
        breadcrumb_text="",
        spec_dict=None,
        free_text=description,  # zarahome dims live in prose → dims_estimated
        material_texts=[description, norm["name"]],
        colors=colors,
    ))
    return norm


NORMALIZERS = {
    "sweeek": normalize_sweeek,
    "kavehome": normalize_kavehome,
    "zarahome": normalize_zarahome,
}


def best_description(full_product: Dict) -> str:
    """Pick the most informative description text from a raw product."""
    for key in ("description", "short_description"):
        val = full_product.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    for key in ("details", "specifications"):
        d = full_product.get(key)
        if isinstance(d, dict) and d:
            return " | ".join(f"{k}: {v}" for k, v in d.items())
    return str(full_product.get("collection", "") or "")


# =============================================================================
# Vector Database Class
# =============================================================================

class CatalogVectorDB:
    """Vector database for product catalogs with incremental update support."""

    def __init__(self, db_path: str = DB_PATH):
        chromadb = _require_chromadb()
        self.db_path = db_path
        self.hash_store_path = os.path.join(db_path, "product_hashes.json")
        self.db_meta_path = os.path.join(db_path, "db_meta.json")
        self._version_warned = False

        # Use bundled ONNX model if available (avoids network download)
        _setup_onnx_model_path(db_path)

        # Initialize ChromaDB with persistent storage
        if not os.path.isdir(db_path):
            os.makedirs(db_path, exist_ok=True)
        self.client = chromadb.PersistentClient(path=db_path)

        # Get or create collection (cosine space for interpretable similarity)
        self.collection = self._get_collection()

        # Load existing hashes for change detection
        self.product_hashes = self._load_hashes()

    def _get_collection(self):
        return self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={
                "hnsw:space": "cosine",
                "description": "Multi-catalog product search",
            },
        )

    # --- db version stamp ---

    def _read_db_version(self) -> int:
        try:
            with open(self.db_meta_path, "r") as f:
                return int(json.load(f).get("db_version", 0))
        except (OSError, ValueError, TypeError):
            return 0

    def _write_db_meta(self):
        with open(self.db_meta_path, "w") as f:
            json.dump({"db_version": DB_VERSION}, f)

    def _warn_if_old_db(self):
        if self._version_warned:
            return
        self._version_warned = True
        if self._read_db_version() < DB_VERSION:
            print(
                "WARNING: catalog DB has no v2 stamp — filters on category/"
                "material/color/dims and cosine similarity need a rebuild. "
                "Rebuild with --force for v2 metadata + cosine space "
                "(python catalog_vectordb.py build --force).",
                file=sys.stderr,
            )

    # --- hashes ---

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

        # A pre-v2 DB cannot be fixed incrementally: the collection keeps its
        # old (l2) space and unchanged products keep v1 metadata. Refuse rather
        # than stamping v2 over a half-migrated database.
        stale = self._read_db_version() < DB_VERSION and self.collection.count() > 0
        if stale and not force:
            print(
                "❌ Existing database predates v2 (old metadata + l2 space).\n"
                "   An incremental build cannot migrate it. Rebuild with:\n"
                "   python catalog_vectordb.py build --force"
            )
            return

        if force:
            # Recreate the collection so v2 settings (cosine space) apply
            print("♻️  --force: recreating collection (cosine space, v2 metadata)")
            try:
                self.client.delete_collection(COLLECTION_NAME)
            except Exception:
                pass
            self.collection = self._get_collection()
            self.product_hashes = {}

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

        # Stamp the DB version (v2 = enriched metadata + cosine space)
        self._write_db_meta()

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

                # Prepare metadata (ChromaDB requires flat structure, no None)
                metadata = {
                    "source": product["source"],
                    "name": product["name"],
                    "price": product["price"],
                    "category": product.get("category", "other"),
                    "rating": product["rating"],
                    "url": product["url"],
                    "width_cm": product.get("width_cm", 0.0),
                    "depth_cm": product.get("depth_cm", 0.0),
                    "height_cm": product.get("height_cm", 0.0),
                    "dims_estimated": product.get("dims_estimated", False),
                    "primary_material": product.get("primary_material", "other"),
                    "color_family": product.get("color_family", ""),
                    "style": product.get("style", ""),
                    "seat_height_cm": product.get("seat_height_cm", 0.0) or 0.0,
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
        min_price: Optional[float] = None,
        min_rating: Optional[float] = None,
        category: Optional[str] = None,
        style: Optional[str] = None,
        color_family: Optional[str] = None,
        material: Optional[str] = None,
        max_width: Optional[float] = None,
        max_depth: Optional[float] = None,
        max_height: Optional[float] = None,
    ) -> List[Dict]:
        """
        Query the vector database with natural language + filters.

        Args:
            query_text: Natural language query
            n_results: Number of results to return
            source: Catalog source (sweeek, kavehome, zarahome)
            max_price / min_price: Price bounds in EUR
            min_rating: Minimum rating filter
            category: Controlled category (see CATEGORY_VOCAB)
            style: Controlled style (see STYLE_VOCAB; only set after enrichment)
            color_family: Controlled color family (see COLOR_FAMILIES)
            material: Primary material (see MATERIAL_VOCAB)
            max_width / max_depth / max_height: Dimension bounds in cm.
                Items with unknown dimensions PASS these filters but are
                flagged with "dims_unknown": true in the result.

        Returns:
            List of matching products with cosine similarity scores in [0, 1].
        """
        self._warn_if_old_db()

        # Build $and where clause for metadata filters
        where = None
        where_conditions = []

        if source:
            where_conditions.append({"source": {"$eq": source}})
        if max_price is not None:
            where_conditions.append({"price": {"$lte": max_price}})
        if min_price is not None:
            where_conditions.append({"price": {"$gte": min_price}})
        if min_rating is not None:
            where_conditions.append({"rating": {"$gte": min_rating}})
        if category:
            where_conditions.append({"category": {"$eq": category}})
        if style:
            where_conditions.append({"style": {"$eq": style}})
        if color_family:
            where_conditions.append({"color_family": {"$eq": color_family}})
        if material:
            where_conditions.append({"primary_material": {"$eq": material}})

        if len(where_conditions) == 1:
            where = where_conditions[0]
        elif len(where_conditions) > 1:
            where = {"$and": where_conditions}

        # Dimension filters are applied Python-side (post-filter) so items
        # with missing dims (0/absent metadata) still pass — over-fetch 3x.
        dim_filters = {
            "width_cm": max_width,
            "depth_cm": max_depth,
            "height_cm": max_height,
        }
        active_dims = {k: v for k, v in dim_filters.items() if v is not None}
        fetch_n = n_results * 3 if active_dims else n_results

        # Query the collection
        results = self.collection.query(
            query_texts=[query_text],
            n_results=fetch_n,
            where=where,
            include=["documents", "metadatas", "distances"]
        )

        # Format results
        formatted = []
        if results and results['ids'] and results['ids'][0]:
            for i, pid in enumerate(results['ids'][0]):
                metadata = results['metadatas'][0][i]
                distance = results['distances'][0][i] if results.get('distances') else None

                # Cosine distance = 1 - cosine similarity; clamp to [0, 1]
                similarity = None
                if distance is not None:
                    similarity = max(0.0, min(1.0, 1.0 - distance))

                # Parse full product from metadata
                full_product = json.loads(metadata.get('full_product', '{}'))

                dims = {
                    k: float(metadata.get(k) or 0.0)
                    for k in ("width_cm", "depth_cm", "height_cm")
                }

                item = {
                    "id": pid,
                    "name": metadata.get("name", ""),
                    "source": metadata.get("source", ""),
                    "price": metadata.get("price", 0),
                    "rating": metadata.get("rating", 0),
                    "url": metadata.get("url", ""),
                    "similarity": similarity,
                    "category": metadata.get("category", ""),
                    "primary_material": metadata.get("primary_material", ""),
                    "color_family": metadata.get("color_family", ""),
                    "style": metadata.get("style", ""),
                    "width_cm": dims["width_cm"],
                    "depth_cm": dims["depth_cm"],
                    "height_cm": dims["height_cm"],
                    "dims_estimated": bool(metadata.get("dims_estimated", False)),
                    "colors": json.loads(metadata.get("colors", "[]")),
                    "full_product": full_product,
                }
                seat_h = float(metadata.get("seat_height_cm") or 0.0)
                if seat_h > 0:
                    item["seat_height_cm"] = seat_h

                if active_dims:
                    # Pass when the dim is unknown (0) or within bound
                    passes = all(
                        dims[k] <= 0 or dims[k] <= vmax
                        for k, vmax in active_dims.items()
                    )
                    if not passes:
                        continue
                    item["dims_unknown"] = any(dims[k] <= 0 for k in active_dims)
                else:
                    item["dims_unknown"] = all(v <= 0 for v in dims.values())

                formatted.append(item)

        return formatted[:n_results]

    # --- Enrichment (LLM fills style/color/material; no re-embedding) ---

    def enrich_export(self, missing_field: str = "style",
                      out_path: str = "pending.jsonl",
                      batch_size: int = 500) -> int:
        """Export products whose `missing_field` metadata is empty/absent as
        JSONL lines: {id, name, category, description (first 400 chars)}."""
        exported = 0
        offset = 0
        with open(out_path, "w", encoding="utf-8") as f:
            while True:
                res = self.collection.get(
                    include=["metadatas"], limit=batch_size, offset=offset
                )
                ids = res.get("ids") or []
                if not ids:
                    break
                for pid, md in zip(ids, res.get("metadatas") or []):
                    md = md or {}
                    value = md.get(missing_field)
                    if value not in (None, "", 0, 0.0, "other"):
                        continue  # already enriched / classified
                    try:
                        full = json.loads(md.get("full_product", "{}"))
                    except (ValueError, TypeError):
                        full = {}
                    record = {
                        "id": pid,
                        "name": md.get("name", ""),
                        "category": md.get("category", ""),
                        "description": best_description(full)[:400],
                    }
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    exported += 1
                offset += len(ids)
                if len(ids) < batch_size:
                    break
        print(f"✅ Exported {exported} products missing '{missing_field}' → {out_path}")
        return exported

    def enrich_import(self, in_path: str) -> Dict[str, int]:
        """Import enriched JSONL lines {id, style, color_family?,
        primary_material?} and update collection metadata in place
        (no re-embedding). Invalid values are skipped and reported."""
        updates: Dict[str, Dict] = {}
        skipped: List[str] = []

        with open(in_path, "r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    skipped.append(f"line {lineno}: invalid JSON")
                    continue
                pid = rec.get("id")
                if not pid:
                    skipped.append(f"line {lineno}: missing id")
                    continue
                style = rec.get("style", "")
                if style == "":
                    # Explicit empty style = "deliberately unclassified": leave the
                    # style field untouched (allows color/material-only fixes).
                    patch = {}
                elif style not in STYLE_VOCAB:
                    skipped.append(
                        f"line {lineno} ({pid}): invalid style '{style}' "
                        f"(allowed: {', '.join(STYLE_VOCAB)})"
                    )
                    continue
                else:
                    patch = {"style": style}
                cf = rec.get("color_family")
                if cf is not None:
                    if cf not in COLOR_FAMILIES:
                        skipped.append(
                            f"line {lineno} ({pid}): invalid color_family '{cf}'"
                        )
                        continue
                    patch["color_family"] = cf
                pm = rec.get("primary_material")
                if pm is not None:
                    if pm not in MATERIAL_VOCAB:
                        skipped.append(
                            f"line {lineno} ({pid}): invalid primary_material '{pm}'"
                        )
                        continue
                    patch["primary_material"] = pm
                if patch:
                    updates[pid] = patch

        updated = 0
        missing_ids: List[str] = []
        pending_ids = list(updates.keys())
        for i in range(0, len(pending_ids), 100):
            chunk = pending_ids[i:i + 100]
            res = self.collection.get(ids=chunk, include=["metadatas"])
            found_ids = res.get("ids") or []
            found = dict(zip(found_ids, res.get("metadatas") or []))
            upd_ids, upd_metas = [], []
            for pid in chunk:
                if pid not in found:
                    missing_ids.append(pid)
                    continue
                merged = dict(found[pid] or {})
                merged.update(updates[pid])
                upd_ids.append(pid)
                upd_metas.append(merged)
            if upd_ids:
                self.collection.update(ids=upd_ids, metadatas=upd_metas)
                updated += len(upd_ids)

        for pid in missing_ids:
            skipped.append(f"{pid}: not found in collection")

        print(f"✅ Updated metadata for {updated} products")
        if skipped:
            print(f"⚠️  Skipped {len(skipped)} records:")
            for msg in skipped[:20]:
                print(f"   • {msg}")
            if len(skipped) > 20:
                print(f"   … and {len(skipped) - 20} more")
        return {"updated": updated, "skipped": len(skipped)}

    def stats(self) -> Dict:
        """Get database statistics."""
        count = self.collection.count()

        # Count by source
        sources = {}
        for source in CATALOG_CONFIGS.keys():
            try:
                result = self.collection.get(where={"source": source}, include=[])
                sources[source] = len(result['ids'])
            except Exception:
                sources[source] = 0

        return {
            "total_products": count,
            "by_source": sources,
            "db_path": self.db_path,
            "db_version": self._read_db_version(),
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
    build_parser.add_argument("--force", action="store_true",
                              help="Force full rebuild (required to upgrade to v2 metadata + cosine space)")

    # Query command
    query_parser = subparsers.add_parser("query", help="Query the database")
    query_parser.add_argument("text", help="Search query")
    query_parser.add_argument("-n", "--num-results", type=int, default=5, help="Number of results")
    query_parser.add_argument("-s", "--source", choices=["sweeek", "kavehome", "zarahome"], help="Filter by source")
    query_parser.add_argument("--max-price", type=float, help="Maximum price")
    query_parser.add_argument("--min-price", type=float, help="Minimum price")
    query_parser.add_argument("--min-rating", type=float, help="Minimum rating")
    query_parser.add_argument("--category", choices=CATEGORY_VOCAB, help="Controlled category")
    query_parser.add_argument("--style", choices=STYLE_VOCAB, help="Style (set after enrichment)")
    query_parser.add_argument("--color-family", choices=COLOR_FAMILIES, help="Color family")
    query_parser.add_argument("--material", choices=MATERIAL_VOCAB, help="Primary material")
    query_parser.add_argument("--max-width", type=float, help="Max width in cm (unknown dims pass, flagged)")
    query_parser.add_argument("--max-depth", type=float, help="Max depth in cm (unknown dims pass, flagged)")
    query_parser.add_argument("--max-height", type=float, help="Max height in cm (unknown dims pass, flagged)")
    query_parser.add_argument("--full", action="store_true", help="Show full product details")
    query_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # Stats command
    subparsers.add_parser("stats", help="Show database statistics")

    # Enrich command (export products for LLM enrichment, import results)
    enrich_parser = subparsers.add_parser(
        "enrich", help="Export/import LLM metadata enrichment (style, ...)")
    enrich_sub = enrich_parser.add_subparsers(dest="enrich_command")
    exp = enrich_sub.add_parser("export", help="Export products with missing metadata as JSONL")
    exp.add_argument("--missing", default="style",
                     help="Metadata field to export when empty (default: style)")
    exp.add_argument("--out", default="pending.jsonl", help="Output JSONL path")
    imp = enrich_sub.add_parser("import", help="Import enriched JSONL and update metadata in place")
    imp.add_argument("--in", dest="in_path", required=True, help="Input JSONL path")

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
            print(json.dumps(results, indent=2, ensure_ascii=False))
        else:
            print(f"\n🔍 Query: \"{args.text}\"")
            print(f"📊 Found {len(results)} results:\n")

            for i, result in enumerate(results, 1):
                similarity_pct = f"{result['similarity']*100:.1f}%" if result['similarity'] is not None else "N/A"
                price_str = f"€{result['price']:.2f}" if result['price'] else "N/A"

                print(f"{i}. [{result['source']}] {result['name']}")
                print(f"   💰 {price_str}  |  📊 Similarity: {similarity_pct}")
                facts = [f"category: {result['category']}"]
                if result.get("primary_material"):
                    facts.append(f"material: {result['primary_material']}")
                if result.get("color_family"):
                    facts.append(f"color: {result['color_family']}")
                if result.get("dims_unknown"):
                    facts.append("dims: unknown")
                else:
                    facts.append(
                        f"dims: {result['width_cm']:.0f}×{result['depth_cm']:.0f}×{result['height_cm']:.0f}cm"
                        + (" (est.)" if result.get("dims_estimated") else "")
                    )
                print(f"   🏷️  {'  |  '.join(facts)}")
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
        print(f"DB version: {stats['db_version']}"
              + ("" if stats['db_version'] >= DB_VERSION else "  (rebuild with --force for v2)"))

    elif args.command == "enrich":
        db = CatalogVectorDB()
        if args.enrich_command == "export":
            db.enrich_export(missing_field=args.missing, out_path=args.out)
        elif args.enrich_command == "import":
            db.enrich_import(in_path=args.in_path)
        else:
            enrich_parser.print_help()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
