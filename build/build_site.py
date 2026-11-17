#!/usr/bin/env python3
"""
Ziyaan Élite — static page builder.

Runs on GitHub Actions (see .github/workflows/site.yml) every few hours and on
every change. It reads the live sprays from Supabase and writes a ready-to-publish
copy of the site into the output folder with:

  * one page per spray            sprays/<slug>/
  * one page per category         oud-perfumes-kenya/, niche-perfumes-kenya/ ...
  * an About page                 about/
  * sitemap.xml, robots.txt, 404.html and a share image (og-image.jpg)
  * the spray list written straight into index.html so search engines see it

Only the Python standard library is needed (Pillow is used for the share image
if it is installed, otherwise the logo is used instead).

Usage:  python3 build/build_site.py --out _site --site-url https://www.example.com/
        (add --data products.json to build from a local file instead of Supabase)
"""
import argparse, datetime, html, json, os, re, shutil, sys, unicodedata, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRAND = "Ziyaan Élite"
SKIP = {".git", ".github", "build", "_site", "node_modules"}
SKIP_FILES = re.compile(r"(\.md|\.sql|\.py|\.jfif)$", re.I)

CATS = {
    "oud": {
        "slug": "oud-perfumes-kenya", "nav": "Oud", "h1": "Oud Perfumes in Kenya",
        "title": "Original Oud Perfumes in Kenya", "kicker": "THE OUD COLLECTION",
        "intro": [
            "Oud — also known as agarwood — is one of the most treasured ingredients in perfumery. It is rich, warm, smoky and woody, and it lasts for hours on the skin. For generations it has been at the heart of Arabian perfumery, and today the world’s top designer and niche houses use it in some of their most luxurious creations.",
            "Our oud collection brings together original oud fragrances, from smooth designer interpretations to bold niche blends. Every bottle is 100% authentic. If you are new to oud, message us on WhatsApp and we will help you choose one that suits you.",
        ],
        "match": lambda p: p.get("is_oud"),
    },
    "niche": {
        "slug": "niche-perfumes-kenya", "nav": "Niche", "h1": "Niche Perfumes in Kenya",
        "title": "Original Niche Perfumes in Kenya", "kicker": "NICHE FRAGRANCES",
        "intro": [
            "Niche perfume houses focus purely on fragrance. Instead of following trends, they create distinctive scents with high-quality ingredients, often made in smaller quantities — which is why a niche perfume is rarely something you smell on everyone else.",
            "At Ziyaan Élite we curate original niche fragrances for people who want a scent that feels personal and memorable. Every bottle is 100% authentic, with delivery across Kenya.",
        ],
        "match": lambda p: p.get("category") == "niche",
    },
    "designer": {
        "slug": "designer-perfumes-kenya", "nav": "Designer", "h1": "Designer Perfumes in Kenya",
        "title": "Original Designer Perfumes in Kenya", "kicker": "DESIGNER FRAGRANCES",
        "intro": [
            "Designer fragrances come from the world’s best-known fashion and luxury houses. They are loved for being polished, versatile and easy to wear — perfect as an everyday signature scent, for the office, or for a special evening.",
            "Shop original designer perfumes in Kenya from Ziyaan Élite. Every bottle is 100% authentic, with free delivery on orders over KES 6,500 and payment by M-Pesa or on delivery.",
        ],
        "match": lambda p: p.get("category") == "designer",
    },
    "arabian": {
        "slug": "arabian-perfumes-kenya", "nav": "Arabian", "h1": "Arabian Perfumes in Kenya",
        "title": "Original Arabian Perfumes in Kenya", "kicker": "ARABIAN FRAGRANCES",
        "intro": [
            "Arabian perfume houses are famous for rich, long-lasting fragrances — from sweet and spicy to deep, resinous blends with oud, amber and rose. Many offer outstanding quality at prices that make it easy to build a collection.",
            "Discover original Arabian perfumes at Ziyaan Élite, with delivery across Kenya and payment by M-Pesa or on delivery.",
        ],
        "match": lambda p: p.get("category") == "arabian",
    },
}
LABEL = {"designer": "Designer", "niche": "Niche", "arabian": "Arabian"}


# ---------------------------------------------------------------- helpers
def esc(t):
    return html.escape(str(t if t is not None else ""), quote=True)


def slugify(t):
    t = unicodedata.normalize("NFKD", str(t or ""))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:80].strip("-") or "spray"


def money(n):
    return "KES {:,.0f}".format(float(n or 0))


def read_config():
    txt = open(os.path.join(ROOT, "config.js"), encoding="utf-8").read()
    def val(key):
        m = re.search(r"\b" + key + r"\s*:\s*'([^']*)'", txt)
        return m.group(1).strip() if m else ""
    return {k: val(k) for k in ("supabaseUrl", "supabaseAnonKey", "whatsapp", "phone", "email", "location", "instagram", "tiktok")}


def fetch_products(cfg):
    url = cfg["supabaseUrl"].rstrip("/") + "/rest/v1/products?select=*&active=eq.true&order=sort_order.asc,name.asc"
    req = urllib.request.Request(url, headers={"apikey": cfg["supabaseAnonKey"], "Authorization": "Bearer " + cfg["supabaseAnonKey"]})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def normalise(rows):
    out, used = [], set()
    for p in rows:
        if not p or p.get("active") is False or not p.get("name"):
            continue
        notes = p.get("notes") or []
        if isinstance(notes, str):
            notes = notes.split(",")
        q = dict(p)
        q["notes"] = [n.strip() for n in notes if str(n).strip()]
        q["category"] = p.get("category") if p.get("category") in LABEL else "designer"
        q["price"] = float(p.get("price") or 0)
        q["stock"] = None if p.get("stock") in (None, "") else max(0, int(p.get("stock") or 0))
        q["low_stock_at"] = 3 if p.get("low_stock_at") is None else int(p.get("low_stock_at"))
        q["full"] = (str(p.get("brand") or "") + " " + str(p.get("name"))).strip()
        s = slugify(q["full"]); base, i = s, 2
        while s in used:
            s = "%s-%d" % (base, i); i += 1
        used.add(s); q["slug"] = s
        q["paras"] = [x.strip() for x in re.split(r"\n\s*\n", p.get("story") or "") if x.strip()]
        out.append(q)
    out.sort(key=lambda r: (r.get("sort_order") if r.get("sort_order") is not None else 100, r["name"]))
    return out


def img_src(p, prefix):
    u = p.get("image_url") or ""
    if not u:
        return prefix + "images/logo.png"
    return u if re.match(r"^https?://", u) else prefix + u.lstrip("/")


def img_abs(p, site):
    u = p.get("image_url") or ""
    if not u:
        return site + "images/logo.png"
    return u if re.match(r"^https?://", u) else site + u.lstrip("/")


def out_of_stock(p):
    return p["stock"] is not None and p["stock"] <= 0


def stock_line(p):
    if out_of_stock(p):
        return ("out", "Out of stock — ask us on WhatsApp when it’s back")
    if p["stock"] is not None and p["stock"] <= p["low_stock_at"]:
        return ("low", "Only %d left" % p["stock"])
    return ("ok", "In stock")


def ld(obj):
    return '<script type="application/ld+json">' + json.dumps(obj, ensure_ascii=False).replace("</", "<\\/") + "</script>"


# ---------------------------------------------------------------- page shell
CSS = r"""
:root{--bg:#050505;--ink:#f8ecd2;--soft:#b9a878;--gold:#eab647;--line:#242019;--card:#0e0d0b;--panel:#0a0908;--red:#e0645a;--amber:#f0a35a;--green:#3fbf6b}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{font-family:'Jost',system-ui,sans-serif;background:var(--bg);color:var(--ink);-webkit-font-smoothing:antialiased;line-height:1.5}
a{color:inherit;text-decoration:none}
h1,h2,h3{font-family:'Cormorant Garamond',Georgia,serif;font-weight:500}
.wrap{max-width:1180px;margin:0 auto;padding:0 24px}
.top{border-bottom:1px solid var(--line);background:var(--bg);position:sticky;top:0;z-index:20}
.top .wrap{display:flex;align-items:center;gap:22px;padding-top:8px;padding-bottom:8px}
.top img{height:62px;display:block}
.top nav{display:flex;gap:22px;font-size:14.5px;margin-left:auto}
.top nav a:hover,.top nav a.on{color:var(--gold)}
.cartlink{position:relative;font-size:20px;padding:6px}
.cartlink b{position:absolute;top:-2px;right:-6px;background:var(--gold);color:#000;font-size:10px;min-width:16px;height:16px;border-radius:8px;display:flex;align-items:center;justify-content:center;padding:0 4px}
.cartlink b:empty{display:none}
.crumbs{font-size:12.5px;color:var(--soft);padding:18px 0 4px}
.crumbs a:hover{color:var(--gold)}
.crumbs span{margin:0 6px;opacity:.6}
.hero{padding:26px 0 10px}
.k{font-size:12px;letter-spacing:.16em;color:var(--gold);margin-bottom:8px}
.hero h1{font-size:42px;line-height:1.1;margin-bottom:14px}
.hero p{color:var(--soft);max-width:70ch;font-size:15.5px;line-height:1.75}
.hero p+p{margin-top:10px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:18px;margin:28px 0}
.card{background:var(--card);border:1px solid var(--line);display:flex;flex-direction:column;transition:border-color .2s}
.card:hover{border-color:var(--gold)}
.card .ph{aspect-ratio:1/1;background:var(--panel);overflow:hidden}
.card .ph img{width:100%;height:100%;object-fit:cover;display:block}
.card .in{padding:14px 15px 18px}
.card .b{font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--gold)}
.card h3{font-family:'Jost',sans-serif;font-size:15px;font-weight:400;margin:4px 0 6px;min-height:2.6em}
.card .pr{font-weight:500}
.st{font-size:12.5px;margin-top:4px}
.st.ok{color:var(--green)}.st.low{color:var(--amber)}.st.out{color:var(--red)}
.empty{grid-column:1/-1;color:var(--soft);padding:30px 0}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;background:var(--gold);color:#171410;padding:14px 22px;font:500 13.5px 'Jost',sans-serif;letter-spacing:.08em;border:none;cursor:pointer}
.btn:hover{background:#e3c07e}
.btn.wa{background:transparent;color:var(--ink);border:1px solid #25D366}
.btn.wa:hover{background:#25D366;color:#fff}
.btn:disabled{opacity:.45;cursor:not-allowed;background:transparent;color:var(--soft);border:1px solid var(--line)}
.prod{display:grid;grid-template-columns:1fr 1.05fr;gap:44px;padding:16px 0 30px;align-items:start}
.prod .ph{background:var(--panel);border:1px solid var(--line);aspect-ratio:1/1;overflow:hidden;position:sticky;top:96px}
.prod .ph img{width:100%;height:100%;object-fit:cover;display:block}
.prod h1{font-size:44px;line-height:1.08;margin:6px 0 8px}
.tag{font-family:'Cormorant Garamond',serif;font-style:italic;font-size:21px;color:var(--soft)}
.price{font-size:24px;font-weight:500;margin:16px 0 4px}
.acts{display:flex;gap:10px;flex-wrap:wrap;margin:18px 0 10px}
.perks{font-size:12.5px;color:var(--soft);display:flex;flex-wrap:wrap;gap:6px 16px;margin-bottom:24px}
.sec{margin-top:24px}
.sec h2{font-family:'Jost',sans-serif;font-size:12px;letter-spacing:.16em;color:var(--gold);font-weight:500;margin-bottom:8px;text-transform:uppercase}
.sec p{font-size:15px;line-height:1.8}
.sec p+p{margin-top:10px}
.notes{display:flex;flex-wrap:wrap;gap:8px}
.notes span{border:1px solid var(--line);background:var(--card);padding:6px 12px;font-size:13px;border-radius:30px}
.facts{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.facts div{border:1px solid var(--line);background:var(--card);padding:10px 12px}
.facts b{display:block;font-size:10.5px;letter-spacing:.14em;color:var(--gold);font-weight:500}
.facts span{font-size:13.5px}
.more{border-top:1px solid var(--line);padding:34px 0 10px}
.more h2{font-size:30px}
.faq{border-top:1px solid var(--line);padding:30px 0}
.faq h2{font-size:28px;margin-bottom:12px}
.faq details{border-bottom:1px solid var(--line);padding:12px 0}
.faq summary{cursor:pointer;font-size:15px}
.faq p{color:var(--soft);font-size:14.5px;line-height:1.7;margin-top:8px}
.cats{display:flex;gap:10px;flex-wrap:wrap;margin:6px 0 30px}
.cats a{border:1px solid var(--line);padding:9px 16px;border-radius:30px;font-size:13.5px}
.cats a:hover{border-color:var(--gold);color:var(--gold)}
.about{max-width:760px;padding:10px 0 40px}
.about h1{font-size:48px;line-height:1.08}
.about .sub{font-family:'Cormorant Garamond',serif;font-style:italic;font-size:24px;color:var(--gold);margin:6px 0 24px}
.about p{font-size:16.5px;line-height:1.85;color:var(--ink)}
.about p+p{margin-top:16px}
.about blockquote{border-left:2px solid var(--gold);padding:6px 0 6px 18px;margin:26px 0;font-family:'Cormorant Garamond',serif;font-size:24px;line-height:1.4}
.pillars{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin:26px 0}
.pillar{background:var(--card);border:1px solid var(--line);padding:16px}
.pillar b{display:block;font-weight:500;margin-bottom:2px}
.pillar span{font-size:13.5px;color:var(--soft)}
footer{border-top:1px solid var(--line);color:var(--soft);font-size:13px;margin-top:30px}
footer .wrap{display:flex;flex-wrap:wrap;gap:12px 22px;justify-content:space-between;padding-top:24px;padding-bottom:90px}
footer .fl{display:flex;flex-wrap:wrap;gap:16px}
footer a:hover{color:var(--gold)}
.wa-float{position:fixed;right:18px;bottom:18px;width:56px;height:56px;border-radius:50%;background:#25D366;display:flex;align-items:center;justify-content:center;box-shadow:0 6px 24px rgba(0,0,0,.5);z-index:30}
.wa-float svg{width:28px;height:28px;fill:#fff}
.toast{position:fixed;left:50%;bottom:90px;transform:translateX(-50%) translateY(20px);background:var(--gold);color:#171410;padding:11px 18px;font-size:13.5px;opacity:0;transition:all .25s;z-index:40;pointer-events:none}
.toast.show{opacity:1;transform:translateX(-50%);pointer-events:auto}
.toast a{text-decoration:underline;margin-left:8px;font-weight:500}
@media(max-width:860px){
  .top .wrap{flex-wrap:wrap;gap:6px 14px;padding-left:14px;padding-right:14px}
  .top img{height:50px}
  .top nav{order:5;width:100%;margin:0;overflow-x:auto;gap:18px;padding:4px 0 6px;white-space:nowrap}
  .cartlink{margin-left:auto}
  .wrap{padding:0 16px}
  .prod{grid-template-columns:1fr;gap:20px}
  .prod .ph{position:static}
  .prod h1,.hero h1,.about h1{font-size:34px}
  .grid{grid-template-columns:repeat(2,1fr);gap:10px}
  .facts{grid-template-columns:1fr 1fr 1fr}
}
"""

WA_SVG = '<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M16.02 3C9.38 3 4 8.36 4 15c0 2.36.66 4.55 1.8 6.42L4 29l7.77-1.75A11.9 11.9 0 0 0 16.02 27C22.65 27 28 21.64 28 15S22.65 3 16.02 3zm0 21.7c-2 0-3.86-.58-5.43-1.58l-.39-.24-4.36.98.94-4.28-.26-.42A9.6 9.6 0 0 1 6.3 15c0-5.37 4.36-9.7 9.72-9.7 5.36 0 9.72 4.33 9.72 9.7 0 5.37-4.36 9.7-9.72 9.7zm5.34-7.26c-.29-.15-1.73-.86-2-.96-.27-.1-.46-.15-.66.15-.2.29-.76.95-.93 1.15-.17.2-.34.22-.63.07-.29-.15-1.22-.45-2.32-1.44-.86-.77-1.44-1.71-1.61-2-.17-.29-.02-.45.13-.6.13-.13.29-.34.44-.51.15-.17.2-.29.29-.49.1-.2.05-.37-.02-.51-.07-.15-.66-1.6-.9-2.2-.24-.57-.48-.5-.66-.5h-.56c-.2 0-.51.07-.78.37-.27.29-1.02 1-1.02 2.44s1.05 2.83 1.2 3.03c.15.2 2.06 3.15 5 4.42.7.3 1.24.48 1.67.62.7.22 1.34.19 1.84.12.56-.08 1.73-.71 1.97-1.39.24-.68.24-1.27.17-1.39-.07-.12-.26-.2-.55-.35z"/></svg>'


def shell(ctx, *, path, title, desc, body, og_image=None, og_type="website", jsonld=(), noindex=False, active="", scripts=""):
    """Wrap a page body. `path` is the page's folder relative to the site root ('' for root)."""
    prefix = "../" * (path.count("/")) if path else ""
    canonical = ctx["site"] + path
    og_image = og_image or ctx["site"] + "og-image.jpg"
    nav = "".join('<a href="%s%s/"%s>%s</a>' % (prefix, c["slug"], ' class="on"' if active == k else "", c["nav"]) for k, c in CATS.items())
    wa = "https://wa.me/%s?text=%s" % (ctx["wa"], urllib.request.quote("Hello Ziyaan Élite, I’d like to enquire about your fragrances."))
    foot_links = "".join('<a href="%s%s/">%s perfumes</a>' % (prefix, c["slug"], c["nav"]) for c in CATS.values())
    return f"""<!DOCTYPE html>
<html lang="en-KE">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{esc(canonical)}">
{'<meta name="robots" content="noindex, follow">' if noindex else ''}
<meta property="og:type" content="{og_type}">
<meta property="og:site_name" content="{BRAND}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{esc(canonical)}">
<meta property="og:image" content="{esc(og_image)}">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="{prefix}images/logo.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,500;1,400&family=Jost:wght@400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{prefix}pages.css">
{''.join(ld(j) for j in jsonld)}
</head>
<body>
<header class="top"><div class="wrap">
  <a href="{prefix or './'}" aria-label="{BRAND} home"><img src="{prefix}images/logo.png" alt="{BRAND} — Original Designer Perfumes" width="86" height="62"></a>
  <nav aria-label="Main"><a href="{prefix or './'}">Shop</a>{nav}<a href="{prefix}about/"{' class="on"' if active == 'about' else ''}>About</a><a href="{prefix or './'}#contact">Contact</a></nav>
  <a class="cartlink" href="{prefix or './'}?cart=1" aria-label="View cart">🛒<b id="cartN"></b></a>
</div></header>
<main class="wrap">
{body}
</main>
<footer><div class="wrap">
  <span>© {datetime.date.today().year} {BRAND} — Original perfumes in Kenya</span>
  <div class="fl"><a href="{prefix or './'}">Shop</a>{foot_links}<a href="{prefix}about/">About us</a><a href="{prefix or './'}#contact">Contact</a></div>
</div></footer>
<a class="wa-float" href="{esc(wa)}" target="_blank" rel="noopener" aria-label="Chat with us on WhatsApp">{WA_SVG}</a>
<div class="toast" id="toast"></div>
<script src="{prefix}config.js"></script>
<script src="{prefix}db.js"></script>
<script src="{prefix}track.js"></script>
<script>
(function(){{
  try{{var c=JSON.parse(localStorage.getItem('ziyaan-cart')||'null'),n=0;if(c&&c.items)for(var k in c.items)n+=c.items[k].q||0;document.getElementById('cartN').textContent=n||'';}}catch(e){{}}
  if(window.zTrack){{ zTrack('page_view'); document.addEventListener('click',function(e){{var a=e.target.closest('a');if(a&&/wa\\.me\\//.test(a.href)&&!a.dataset.tracked)zTrack('whatsapp',a.dataset.product||null);}},true); }}
}})();
</script>
{scripts}
</body>
</html>
"""


def card(p, prefix):
    cls, txt = stock_line(p)
    st = "" if cls == "ok" else '<div class="st %s">%s</div>' % (cls, esc("Out of stock" if cls == "out" else txt))
    return (f'<a class="card" href="{prefix}sprays/{p["slug"]}/"><div class="ph"><img src="{esc(img_src(p, prefix))}" alt="{esc(p["full"])}" loading="lazy" width="400" height="400"></div>'
            f'<div class="in"><div class="b">{esc(p.get("brand"))} · {LABEL[p["category"]]}</div><h3>{esc(p["name"])}</h3>'
            f'<div class="pr">{money(p["price"])}</div>{st}</div></a>')


def org_ld(ctx):
    o = {"@context": "https://schema.org", "@type": "OnlineStore", "name": BRAND, "url": ctx["site"],
         "logo": ctx["site"] + "images/logo.png", "image": ctx["site"] + "og-image.jpg",
         "description": "Original designer, niche and oud perfumes in Kenya.",
         "areaServed": {"@type": "Country", "name": "Kenya"}, "currenciesAccepted": "KES",
         "paymentAccepted": "M-Pesa, Cash on delivery"}
    tel = re.sub(r"[^0-9+]", "", ctx["cfg"].get("phone") or "")
    if tel:
        o["telephone"] = "+254" + tel[1:] if tel.startswith("0") else tel
    if ctx["cfg"].get("email"):
        o["email"] = ctx["cfg"]["email"]
    same = []
    if ctx["cfg"].get("instagram"):
        same.append("https://instagram.com/" + ctx["cfg"]["instagram"].lstrip("@"))
    if ctx["cfg"].get("tiktok"):
        same.append("https://www.tiktok.com/@" + ctx["cfg"]["tiktok"].lstrip("@"))
    if same:
        o["sameAs"] = same
    return o


def crumbs_ld(items):
    return {"@context": "https://schema.org", "@type": "BreadcrumbList",
            "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": n, "item": u} for i, (n, u) in enumerate(items)]}


# ---------------------------------------------------------------- pages
def product_page(ctx, p, products):
    path = "sprays/%s/" % p["slug"]; prefix = "../../"
    cat = CATS[p["category"]]
    cls, stxt = stock_line(p)
    notes = p["notes"]
    title = "%s – Original, %s | %s" % (p["full"], money(p["price"]), BRAND)
    desc = (p.get("tagline") or "").strip()
    desc = ((desc + " ") if desc else "") + "Original %s in Kenya for %s." % (p["full"], money(p["price"]))
    if notes:
        desc += " Notes: " + ", ".join(notes[:5]) + "."
    desc += " Free delivery over KES 6,500 · M-Pesa or pay on delivery."
    wa_msg = "Hello Ziyaan Élite, I’d like to order %s (%s). Is it available?" % (p["full"], money(p["price"]))
    wa = "https://wa.me/%s?text=%s" % (ctx["wa"], urllib.request.quote(wa_msg))
    facts = [("OCCASION", p.get("occasion")), ("SEASON", p.get("season")), ("PERFORMANCE", p.get("performance"))]
    facts_html = "".join('<div><b>%s</b><span>%s</span></div>' % (k, esc(v)) for k, v in facts if v)
    paras = p["paras"] or ["A refined fragrance from %s. Message us on WhatsApp to learn more about this scent." % p.get("brand", "")]
    related = [q for q in products if q is not p and q["category"] == p["category"]][:4]
    if len(related) < 4:
        related += [q for q in products if q is not p and q not in related][: 4 - len(related)]
    body = f"""
<nav class="crumbs" aria-label="Breadcrumb"><a href="{prefix}">Home</a><span>›</span><a href="{prefix}{cat['slug']}/">{cat['nav']} perfumes</a><span>›</span>{esc(p['full'])}</nav>
<article class="prod">
  <div class="ph"><img src="{esc(img_src(p, prefix))}" alt="{esc(p['full'])} — original, sold in Kenya by {BRAND}" width="800" height="800"></div>
  <div>
    <div class="k">{esc(p.get('brand'))} · {LABEL[p['category']].upper()}{' · OUD' if p.get('is_oud') else ''}</div>
    <h1>{esc(p['name'])}</h1>
    {'<div class="tag">' + esc(p.get('tagline')) + '</div>' if p.get('tagline') else ''}
    <div class="price" id="price">{money(p['price'])}</div>
    <div class="st {cls}" id="stock">{esc(stxt)}</div>
    <div class="acts">
      <button class="btn" id="addBtn" type="button"{' disabled' if cls == 'out' else ''}>{'OUT OF STOCK' if cls == 'out' else 'ADD TO CART'}</button>
      <a class="btn wa" href="{esc(wa)}" target="_blank" rel="noopener" data-product="{esc(p['full'])}">ORDER ON WHATSAPP</a>
    </div>
    <div class="perks"><span>✓ 100% authentic</span><span>✓ Free delivery over KES 6,500</span><span>✓ M-Pesa or pay on delivery</span></div>
    <section class="sec"><h2>The story</h2>{''.join('<p>' + esc(x) + '</p>' for x in paras)}</section>
    {'<section class="sec"><h2>Key notes</h2><div class="notes">' + ''.join('<span>' + esc(n) + '</span>' for n in notes) + '</div></section>' if notes else ''}
    {'<section class="sec"><h2>When to wear it</h2><div class="facts">' + facts_html + '</div></section>' if facts_html else ''}
  </div>
</article>
{'<section class="more"><h2>You may also like</h2><div class="grid">' + ''.join(card(q, prefix) for q in related) + '</div></section>' if related else ''}
"""
    offer = {"@type": "Offer", "url": ctx["site"] + path, "priceCurrency": "KES", "price": "%.0f" % p["price"],
             "availability": "https://schema.org/OutOfStock" if cls == "out" else "https://schema.org/InStock",
             "itemCondition": "https://schema.org/NewCondition", "seller": {"@type": "Organization", "name": BRAND}}
    prod_ld = {"@context": "https://schema.org", "@type": "Product", "name": p["full"], "image": [img_abs(p, ctx["site"])],
               "description": " ".join(paras)[:600], "sku": p["slug"], "brand": {"@type": "Brand", "name": p.get("brand") or BRAND},
               "category": LABEL[p["category"]] + " perfume", "offers": offer}
    data = {"id": p.get("id"), "key": p["full"], "price": p["price"], "stock": p["stock"], "low": p["low_stock_at"]}
    scripts = """<script>
(function(){
  var P=%s, CFG=window.ZIYAAN_CONFIG||{}, btn=document.getElementById('addBtn');
  function money(n){return 'KES '+Math.round(n).toLocaleString('en-KE')}
  function toast(h){var t=document.getElementById('toast');t.innerHTML=h;t.classList.add('show');clearTimeout(t._t);t._t=setTimeout(function(){t.classList.remove('show')},3200)}
  function paint(){
    var out=P.stock!==null&&P.stock<=0, low=P.stock!==null&&P.stock>0&&P.stock<=P.low, s=document.getElementById('stock');
    document.getElementById('price').textContent=money(P.price);
    s.className='st '+(out?'out':low?'low':'ok'); s.textContent=out?'Out of stock \\u2014 ask us on WhatsApp when it\\u2019s back':low?'Only '+P.stock+' left':'In stock';
    btn.disabled=out; btn.textContent=out?'OUT OF STOCK':'ADD TO CART';
  }
  if(window.zTrack) zTrack('story_open',P.key);
  // keep price and stock live between rebuilds
  if(CFG.supabaseUrl&&window.ZiyaanDB&&P.id){ window.ZiyaanDB.createClient(CFG.supabaseUrl,CFG.supabaseAnonKey,{auth:{persistSession:false}}).from('products').select('price,stock,low_stock_at,active').eq('id',P.id).then(function(r){
    var d=r.data&&r.data[0]; if(!d) return; P.price=+d.price||P.price; P.stock=(d.stock===null||d.stock===undefined)?null:+d.stock; P.low=d.low_stock_at==null?3:+d.low_stock_at; paint(); }); }
  btn.addEventListener('click',function(){
    var c; try{c=JSON.parse(localStorage.getItem('ziyaan-cart')||'null')}catch(e){} if(!c||!c.items) c={t:Date.now(),items:{}};
    var it=c.items[P.key]||{n:P.key,p:P.price,q:0,max:P.stock};
    if(P.stock!==null&&it.q>=P.stock){ toast('Only '+P.stock+' in stock'); return; }
    it.q++; it.p=P.price; it.max=P.stock; c.items[P.key]=it; c.t=Date.now();
    try{localStorage.setItem('ziyaan-cart',JSON.stringify(c))}catch(e){}
    var n=0; for(var k in c.items) n+=c.items[k].q; document.getElementById('cartN').textContent=n;
    if(window.zTrack) zTrack('add_to_cart',P.key);
    toast('Added to cart <a href="../../?cart=1">View cart &amp; checkout \\u2192</a>');
  });
})();
</script>""" % json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    crumbs = crumbs_ld([("Home", ctx["site"]), (cat["nav"] + " perfumes", ctx["site"] + cat["slug"] + "/"), (p["full"], ctx["site"] + path)])
    return path, shell(ctx, path=path, title=title, desc=desc[:300], body=body, og_image=img_abs(p, ctx["site"]),
                       og_type="product", jsonld=[prod_ld, crumbs], active=p["category"], scripts=scripts)


FAQ = [
    ("Are your perfumes original?", "Yes. Every bottle we sell is 100% authentic — we only stock original designer, niche and Arabian fragrances."),
    ("Do you deliver across Kenya?", "Yes. Delivery is free on orders over KES 6,500. Message us on WhatsApp with your location for delivery times and costs on smaller orders."),
    ("How can I pay?", "Pay with M-Pesa or pay on delivery. You can order straight from the website or on WhatsApp."),
    ("Not sure which perfume to choose?", "Tell us on WhatsApp what scents you like and when you plan to wear them, and we will recommend a few to try."),
]


def category_page(ctx, key, products):
    c = CATS[key]; path = c["slug"] + "/"; prefix = "../"
    items = [p for p in products if c["match"](p)]
    brands = []
    for p in items:
        if p.get("brand") and p["brand"] not in brands:
            brands.append(p["brand"])
    intro = list(c["intro"])
    if brands:
        intro.append("Currently in stock: fragrances from " + (", ".join(brands[:-1]) + " and " + brands[-1] if len(brands) > 1 else brands[0]) + ".")
    others = "".join('<a href="%s%s/">%s perfumes</a>' % (prefix, o["slug"], o["nav"]) for k2, o in CATS.items() if k2 != key)
    grid = "".join(card(p, prefix) for p in items) or '<p class="empty">New arrivals are coming soon. Message us on WhatsApp to ask what is available right now.</p>'
    body = f"""
<nav class="crumbs" aria-label="Breadcrumb"><a href="{prefix}">Home</a><span>›</span>{c['nav']} perfumes</nav>
<section class="hero"><div class="k">{c['kicker']}</div><h1>{c['h1']}</h1>{''.join('<p>' + esc(x) + '</p>' for x in intro)}</section>
<div class="grid">{grid}</div>
<div class="cats"><a href="{prefix}">All perfumes</a>{others}</div>
<section class="faq"><h2>Questions</h2>{''.join('<details><summary>' + esc(q) + '</summary><p>' + esc(a) + '</p></details>' for q, a in FAQ)}</section>
"""
    title = "%s | %s" % (c["title"], BRAND)
    desc = "%s at %s. %s 100%% authentic · free delivery over KES 6,500 · M-Pesa or pay on delivery." % (
        c["title"], BRAND, ("Shop " + ", ".join(brands[:4]) + " and more. ") if brands else "")
    lst = {"@context": "https://schema.org", "@type": "ItemList", "name": c["h1"],
           "itemListElement": [{"@type": "ListItem", "position": i + 1, "url": ctx["site"] + "sprays/" + p["slug"] + "/", "name": p["full"]} for i, p in enumerate(items)]}
    crumbs = crumbs_ld([("Home", ctx["site"]), (c["nav"] + " perfumes", ctx["site"] + path)])
    return path, shell(ctx, path=path, title=title, desc=desc, body=body, jsonld=[lst, crumbs], noindex=not items, active=key), bool(items)


ABOUT = [
    "Ziyaan Élite began with a personal love for fragrance — a fascination that started as a hobby and gradually grew into something much more meaningful.",
    "After a career in banking and an MBA specialising in Human Resource Management, I took the decision to follow something I had always genuinely enjoyed: discovering, collecting and sharing exceptional perfumes.",
    "What started with my own fragrance collection eventually became Ziyaan Élite — a business built around the belief that fragrance is deeply personal. It is not simply something you wear; it can become part of your identity, your memories and the way you leave an impression.",
    "Today, we bring together a carefully selected collection of original designer, niche and luxury fragrances, chosen with the same enthusiasm and attention to detail that I have always had as a fragrance enthusiast.",
]


def about_page(ctx):
    path = "about/"; prefix = "../"
    body = f"""
<nav class="crumbs" aria-label="Breadcrumb"><a href="{prefix}">Home</a><span>›</span>About us</nav>
<article class="about">
  <div class="k">ABOUT US</div>
  <h1>About {BRAND}</h1>
  <div class="sub">Born from passion. Curated with purpose.</div>
  {''.join('<p>' + esc(x) + '</p>' for x in ABOUT)}
  <blockquote>At {BRAND}, we don’t just sell fragrances.<br>We build collections. We share a passion. And we help you find scents worth remembering.</blockquote>
  <p>Welcome to {BRAND}.</p>
  <div class="pillars">
    <div class="pillar"><b>🛡 100% authentic</b><span>Original perfumes only.</span></div>
    <div class="pillar"><b>💬 Personal advice</b><span>Help choosing a scent on WhatsApp.</span></div>
    <div class="pillar"><b>🚚 Delivery</b><span>Free on orders over KES 6,500.</span></div>
    <div class="pillar"><b>📱 Easy payment</b><span>M-Pesa or pay on delivery.</span></div>
  </div>
  <a class="btn" href="{prefix}">SHOP THE COLLECTION →</a>
</article>
"""
    ab = {"@context": "https://schema.org", "@type": "AboutPage", "name": "About " + BRAND, "url": ctx["site"] + path,
          "description": "The story behind " + BRAND + " — original designer, niche and luxury fragrances in Kenya."}
    return path, shell(ctx, path=path, title="About Us — Our Story | " + BRAND,
                       desc="Born from passion, curated with purpose. The story behind Ziyaan Élite — original designer, niche and luxury fragrances in Kenya.",
                       body=body, jsonld=[ab, org_ld(ctx)], active="about")


def not_found_page(ctx):
    # a 404 page can be shown at any address, so every relative link is resolved from the site root
    body = '<section class="hero" style="padding:70px 0"><div class="k">PAGE NOT FOUND</div><h1>This page has moved or doesn’t exist</h1><p>The spray may have sold out or been renamed.</p><p style="margin-top:22px"><a class="btn" href="./">BACK TO THE SHOP →</a></p></section>'
    page = shell(ctx, path="", title="Page not found | " + BRAND, desc="Page not found.", body=body, noindex=True)
    return page.replace("<head>", '<head>\n<base href="%s">' % esc(ctx["site"]), 1)


def home_patch(ctx, products, out):
    """Write the spray list and structured data straight into index.html."""
    p_index = os.path.join(out, "index.html")
    s = open(p_index, encoding="utf-8").read()
    cards = []
    for p in products:
        cls, txt = stock_line(p)
        st = "" if cls == "ok" else '<div class="stock-note%s">%s</div>' % (" out" if cls == "out" else "", esc("Out of stock" if cls == "out" else txt))
        cards.append(f'<div class="product"><div class="imgbox"><img src="{esc(img_src(p, ""))}" alt="{esc(p["full"])}" loading="lazy"></div>'
                     f'<div class="info"><div class="brand">{esc(p.get("brand"))} · {LABEL[p["category"]]}</div><div class="name">{esc(p["name"])}</div>'
                     f'<div class="price">{money(p["price"])}</div>{st}<a class="read-story" href="sprays/{p["slug"]}/">Read the story →</a></div></div>')
    s = re.sub(r"<!--SEO:GRID-->.*?<!--/SEO:GRID-->", lambda m: "<!--SEO:GRID-->" + "".join(cards) + "<!--/SEO:GRID-->", s, flags=re.S)
    site_ld = {"@context": "https://schema.org", "@type": "WebSite", "name": BRAND, "url": ctx["site"]}
    lst = {"@context": "https://schema.org", "@type": "ItemList", "name": "Perfumes at " + BRAND,
           "itemListElement": [{"@type": "ListItem", "position": i + 1, "url": ctx["site"] + "sprays/" + p["slug"] + "/", "name": p["full"]} for i, p in enumerate(products)]}
    head = ('<link rel="canonical" href="%s">\n<meta property="og:url" content="%s">\n<meta property="og:image" content="%sog-image.jpg">\n%s%s%s'
            % (esc(ctx["site"]), esc(ctx["site"]), esc(ctx["site"]), ld(site_ld), ld(org_ld(ctx)), ld(lst)))
    s = re.sub(r"<!--SEO:HEAD-->.*?<!--/SEO:HEAD-->", lambda m: "<!--SEO:HEAD-->" + head + "<!--/SEO:HEAD-->", s, flags=re.S)
    open(p_index, "w", encoding="utf-8").write(s)


def share_image(out):
    """1200x630 picture used when the shop link is shared (WhatsApp, Facebook...)."""
    dst = os.path.join(out, "og-image.jpg")
    try:
        from PIL import Image, ImageDraw, ImageFilter
    except Exception:
        shutil.copyfile(os.path.join(ROOT, "images", "creed.jpg"), dst); return "fallback"
    W, H = 1200, 630
    im = Image.new("RGB", (W, H), (5, 5, 5))
    glow = Image.new("RGB", (W, H), (0, 0, 0)); g = ImageDraw.Draw(glow)
    g.ellipse((560, -120, 1320, 560), fill=(90, 66, 22)); glow = glow.filter(ImageFilter.GaussianBlur(120))
    im = Image.blend(im, glow, 0.9)
    heroes = [f for f in ("creed-hero.webp", "sauvage-hero.webp", "gucci-hero.webp") if os.path.exists(os.path.join(ROOT, "images", f))]
    for i, f in enumerate(heroes[:3]):
        h = Image.open(os.path.join(ROOT, "images", f)).convert("RGBA"); h.thumbnail((205, 400))
        im.paste(h, (545 + i * 215 + (205 - h.size[0]) // 2, (H - h.size[1]) // 2 + (0 if i == 1 else 24)), h)
    logo = Image.open(os.path.join(ROOT, "images", "logo.png")).convert("RGBA"); logo.thumbnail((430, 340))
    im.paste(logo, (60, (H - logo.size[1]) // 2), logo)
    im.save(dst, "JPEG", quality=86, optimize=True)
    return "ok"


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="_site")
    ap.add_argument("--site-url", default=os.environ.get("SITE_URL", ""))
    ap.add_argument("--data", help="read sprays from this JSON file instead of Supabase (for testing)")
    a = ap.parse_args()
    cfg = read_config()
    site = (a.site_url or "https://edgar595.github.io/ziyaan-elite/").rstrip("/") + "/"
    rows = json.load(open(a.data, encoding="utf-8")) if a.data else fetch_products(cfg)
    products = normalise(rows)
    if not products:
        sys.exit("No sprays came back from the database — stopping so the live site is left as it is.")
    ctx = {"site": site, "cfg": cfg, "wa": re.sub(r"\D", "", cfg.get("whatsapp") or "254720081710")}

    out = os.path.abspath(a.out)
    if os.path.exists(out):
        shutil.rmtree(out)
    for d, dirs, files in os.walk(ROOT):
        rel = os.path.relpath(d, ROOT)
        dirs[:] = [x for x in dirs if x not in SKIP and not x.startswith(".") and os.path.join(d, x) != out]
        for f in files:
            if f.startswith(".") or SKIP_FILES.search(f):
                continue
            os.makedirs(os.path.join(out, rel), exist_ok=True)
            shutil.copy2(os.path.join(d, f), os.path.join(out, rel, f))
    open(os.path.join(out, "pages.css"), "w", encoding="utf-8").write(CSS)

    today = datetime.date.today().isoformat()
    urls = [(site, today, "1.0")]
    def write(path, page):
        os.makedirs(os.path.join(out, path), exist_ok=True)
        open(os.path.join(out, path, "index.html"), "w", encoding="utf-8").write(page)
    for p in products:
        path, page = product_page(ctx, p, products); write(path, page)
        urls.append((site + path, (p.get("updated_at") or today)[:10], "0.8"))
    for k in CATS:
        path, page, indexable = category_page(ctx, k, products); write(path, page)
        if indexable:
            urls.append((site + path, today, "0.9"))
    path, page = about_page(ctx); write(path, page); urls.append((site + path, today, "0.5"))
    open(os.path.join(out, "404.html"), "w", encoding="utf-8").write(not_found_page(ctx))
    home_patch(ctx, products, out)
    img = share_image(out)

    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u, lm, pr in urls:
        sm.append("  <url><loc>%s</loc><lastmod>%s</lastmod><priority>%s</priority></url>" % (esc(u), lm, pr))
    sm.append("</urlset>")
    open(os.path.join(out, "sitemap.xml"), "w", encoding="utf-8").write("\n".join(sm) + "\n")
    open(os.path.join(out, "robots.txt"), "w", encoding="utf-8").write("User-agent: *\nAllow: /\nDisallow: /admin.html\n\nSitemap: %ssitemap.xml\n" % site)
    open(os.path.join(out, ".nojekyll"), "w").close()
    print("Built %d spray pages, %d category pages, share image: %s, site: %s" % (len(products), len(CATS), img, site))


if __name__ == "__main__":
    main()
