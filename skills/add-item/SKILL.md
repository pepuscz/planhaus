---
name: add-item
description: Add a product to the registry from a URL or description
args: "<url-or-description>"
---

# Add Item to Registry

Discover a product and add it to the project registry.

## Steps

1. If a URL is provided:
   - Fetch the product page
   - Extract: name, price, dimensions (width × depth × height in cm), materials, colors, finish
   - Download the main product image and save to `registry/<category>/<item-name>.jpg`

2. If a text description is provided:
   - Use it as the basis for the registry entry
   - Ask the user for any missing critical info (dimensions, price)

3. Create a registry YAML file at `registry/<category>/<item-name>.yaml`:
   ```yaml
   name: "<Product Name>"
   url: "<source URL>"
   price: <amount> <currency>

   status: considering

   dimensions:
     width: <cm>
     depth: <cm>
     height: <cm>

   materials: [<list>]
   colors: [<list>]
   finish: "<finish>"
   style: "<style>"

   description: |
     <Objective description of form, proportions, visual weight,
      texture, materials, craftsmanship. NO recommendations.>

   image: "<category>/<item-name>.jpg"

   notes: |
     <date>: Discovered at <source>
   ```

4. Set `status: considering` — the designer evaluates fit later.

## Notes

- Registry entries describe WHAT the item IS, not where it goes or why.
- Keep descriptions objective: form, proportions, visual weight, texture.
- Do NOT include: certifications, load capacity, assembly instructions, delivery info.
- Category folders: `furniture/`, `lighting/`, `accessories/`, `textiles/`, etc.
