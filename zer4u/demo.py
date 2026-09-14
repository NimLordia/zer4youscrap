"""Invented examples of the original selectors; no scraped production content."""

BASE_URL = "https://example.invalid/"
HTML = """
<!doctype html><html lang="he"><meta charset="utf-8"><title>Synthetic demo</title>
<body><p>All names, prices and image URLs below are synthetic demonstration data.</p>
<div class="product_in_list">
  <a href="/demo/red-bouquet"><h2 data-equalheight="prodTitle">זר הדגמה סינתטי – אדום</h2></a>
  <span class="saleprice">₪123.00</span>
  <div class="image"><picture><source type="image/webp"
    srcset="/demo/red-small.webp 320w, /demo/red-large.webp 960w"></picture></div>
</div>
<div class="product_in_list">
  <a href="/demo/white-bouquet"><h2 data-equalheight="prodTitle">זר הדגמה סינתטי – לבן</h2></a>
  <span class="saleprice">₪234.00</span>
  <div class="image"><img src="/Media/PreloadImages/blank.gif" data-src="/demo/white.jpg"></div>
</div></body></html>
"""
