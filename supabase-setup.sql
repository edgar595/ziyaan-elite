-- =====================================================================
--  Ziyaan Elite — Supabase setup
--  Run this ONCE in Supabase:  SQL Editor  →  New query  →  paste  →  Run
-- =====================================================================

-- 1) Who is allowed to manage the shop -------------------------------
create table if not exists public.admins (
  user_id uuid primary key references auth.users(id) on delete cascade,
  created_at timestamptz not null default now()
);
alter table public.admins enable row level security;
drop policy if exists "Admins can see themselves" on public.admins;
create policy "Admins can see themselves" on public.admins
  for select to authenticated using (user_id = auth.uid());

create or replace function public.is_admin() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.admins where user_id = auth.uid());
$$;

-- 2) The sprays --------------------------------------------------------
create table if not exists public.products (
  id              uuid primary key default gen_random_uuid(),
  brand           text    not null,
  name            text    not null,
  category        text    not null default 'designer'
                  check (category in ('designer','niche','arabian')),
  is_oud          boolean not null default false,
  is_best         boolean not null default false,
  featured        boolean not null default false,   -- shows in the big slider at the top
  price           integer not null check (price >= 0), -- KES
  tagline         text    not null default '',
  story           text    not null default '',      -- blank line = new paragraph
  notes           text[]  not null default '{}',
  occasion        text    not null default '',
  season          text    not null default '',
  performance     text    not null default '',
  image_url       text    not null default '',
  hero_image_url  text    not null default '',      -- optional cut-out photo for the slider
  sort_order      integer not null default 100,     -- lower = shown first
  active          boolean not null default true,    -- false = hidden from the shop
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);
-- stock: empty (null) = not tracked; low_stock_at = warn when stock is at or below this
alter table public.products add column if not exists stock integer check (stock >= 0);
alter table public.products add column if not exists low_stock_at integer not null default 3 check (low_stock_at >= 0);
alter table public.products enable row level security;

drop policy if exists "Anyone can see visible sprays" on public.products;
create policy "Anyone can see visible sprays" on public.products
  for select using (active = true or public.is_admin());
drop policy if exists "Admins can add sprays" on public.products;
create policy "Admins can add sprays" on public.products
  for insert to authenticated with check (public.is_admin());
drop policy if exists "Admins can edit sprays" on public.products;
create policy "Admins can edit sprays" on public.products
  for update to authenticated using (public.is_admin()) with check (public.is_admin());
drop policy if exists "Admins can delete sprays" on public.products;
create policy "Admins can delete sprays" on public.products
  for delete to authenticated using (public.is_admin());

-- 3) Photo storage -----------------------------------------------------
insert into storage.buckets (id, name, public)
values ('product-images', 'product-images', true)
on conflict (id) do nothing;

drop policy if exists "Admins upload spray photos" on storage.objects;
create policy "Admins upload spray photos" on storage.objects
  for insert to authenticated with check (bucket_id = 'product-images' and public.is_admin());
drop policy if exists "Admins update spray photos" on storage.objects;
create policy "Admins update spray photos" on storage.objects
  for update to authenticated using (bucket_id = 'product-images' and public.is_admin());
drop policy if exists "Admins delete spray photos" on storage.objects;
create policy "Admins delete spray photos" on storage.objects
  for delete to authenticated using (bucket_id = 'product-images' and public.is_admin());

-- 4) Starter catalogue (your current 11 sprays) ------------------------
--    Only added if the table is still empty.
do $$ begin
if not exists (select 1 from public.products) then
insert into public.products (brand, name, category, is_oud, is_best, price, tagline, story, notes, occasion, season, performance, image_url, hero_image_url, featured, sort_order, active) values
('Maison Crivelli', 'Oud Maracujá', 'niche', true, false, 80000, 'Sun-ripened fruit meets dark, smoky oud.', 'Maison Crivelli builds every scent around a “sensory shock” — a moment of travel that stayed with its founder. Oud Maracujá began on a trip to Brazil, where the sweet-sour tang of fresh passion fruit collided with the rich, resinous warmth of oud.

The result is a bold contrast: juicy and bright on first spray, then deepening into saffron, rose and soft leather over smoky oud. It is a statement scent for people who want to be remembered.', array['Passion fruit','Saffron','Rose','Leather','Oud']::text[], 'Evening', 'Cool nights', 'Beast mode', 'images/maracuja.jpg', '', false, 10, true),
('Creed', 'Absolu Aventus', 'niche', false, false, 78000, 'A darker, smokier chapter of a modern legend.', 'Since its launch in 2010, Creed Aventus has become one of the most famous men’s fragrances in the world — a scent built around strength, success and vision. Absolu Aventus is its deeper, more intense interpretation.

The famous fruity opening of pineapple and blackcurrant is still there, but it settles into a richer heart of smoky birch and a long, mossy, musky dry-down. Confident, polished and quietly powerful.', array['Pineapple','Blackcurrant','Bergamot','Birch','Musk']::text[], 'Office & events', 'All year', 'Strong', 'images/creed.jpg', 'images/creed-hero.webp', true, 20, true),
('Afnan', 'Supremacy Not Only Intense', 'niche', false, false, 7000, 'Royal confidence, at an everyday price.', 'Afnan is a respected perfume house from the UAE, known for rich, long-lasting compositions. Supremacy Not Only Intense is one of its most celebrated creations — loved worldwide for its smooth, fruity-woody character.

It opens with crisp blackcurrant, bergamot and apple, then dries down into patchouli, oakmoss and ambergris. A crowd-pleaser that lasts all day and earns compliments without trying.', array['Blackcurrant','Bergamot','Apple','Patchouli','Oakmoss','Ambergris']::text[], 'Daily wear', 'All year', 'Long-lasting', 'images/supremacy.jpg', '', false, 30, true),
('Valentino', 'Uomo Born in Roma Intense', 'designer', false, false, 21000, 'Rome after dark — rebellious, warm and modern.', 'Valentino’s Born in Roma line celebrates the Eternal City’s mix of couture tradition and street-style attitude. Uomo Intense is the most sensual of the family, inspired by Roman nights.

A creamy, addictive vanilla is lifted by aromatic lavender and grounded in earthy vetiver. Sweet but masculine — the kind of scent people lean in to ask about.', array['Vanilla','Lavender','Vetiver']::text[], 'Date night', 'Cool season', 'Strong', 'images/valentino.jpg', '', false, 40, true),
('Dior', 'Sauvage Eau de Parfum', 'designer', false, false, 26000, 'Wide-open skies and raw, untamed freshness.', 'Dior’s Sauvage was inspired by wild desert landscapes under a blue dusk sky. The Eau de Parfum takes that spirit and adds warmth — a sensual, rounder version of the modern classic.

Juicy Calabrian bergamot and spicy Sichuan pepper open bright and clean, before lavender, nutmeg and star anise lead into smooth vanilla and ambroxan. Fresh enough for day, rich enough for night.', array['Bergamot','Sichuan pepper','Lavender','Nutmeg','Vanilla','Ambroxan']::text[], 'Anytime', 'All year', 'Versatile', 'images/sauvage.jpg', 'images/sauvage-hero.webp', true, 50, true),
('YSL', 'L''Homme', 'designer', false, false, 15000, 'Effortless elegance for the modern gentleman.', 'Created in 2006, YSL L’Homme was designed around the idea of a man who is both strong and refined — classic tailoring with a relaxed touch. It has remained a timeless signature ever since.

Fresh ginger and bergamot sparkle at the top, softened by a spicy heart of white pepper and violet leaf, then a smooth base of cedar and tonka. Clean, mature and always appropriate.', array['Ginger','Bergamot','White pepper','Violet leaf','Cedar','Tonka']::text[], 'Office', 'Spring & summer', 'Moderate', 'images/lhomme.jpg', '', false, 60, true),
('YSL', 'MYSLF', 'designer', false, false, 21500, 'A new masculinity — bold, tender and true to yourself.', 'MYSLF (pronounced “myself”) is YSL’s celebration of modern masculinity — a man confident enough to show his softer side. Its bottle is crowned with the iconic Cassandre logo.

The signature is a rare floral-woody accord: a luminous heart of orange blossom over bright bergamot and warm, woody patchouli. Clean, radiant and unexpectedly addictive.', array['Bergamot','Orange blossom','Patchouli','Woods']::text[], 'Day & evening', 'All year', 'Moderate', 'images/myslf.jpg', '', false, 70, true),
('Gucci', 'Intense Oud', 'designer', true, false, 23000, 'Precious oud with Italian sophistication.', 'Gucci Intense Oud brings the treasured wood of the Middle East into the world of Italian luxury. It is a rich, unisex fragrance designed to feel opulent yet wearable.

Deep oud is wrapped in smoky incense, soft leather and glowing amber — warm, mysterious and long-lasting. Perfect for those who love Arabian depth with designer polish.', array['Oud','Incense','Leather','Amber']::text[], 'Evening', 'Cool season', 'Strong', 'images/gucci.jpg', 'images/gucci-hero.webp', true, 80, true),
('Hugo Boss', 'Bottled Absolu', 'designer', false, false, 20000, 'The most intense expression of BOSS Bottled.', 'BOSS Bottled has been a symbol of the confident, successful man for over 20 years. Bottled Absolu pushes that identity to its most intense form — darker, richer and made to make an impression.

Supple leather and smoky myrrh lead the way, with incense and patchouli adding depth over warm cedarwood. Bold, sensual and built to last.', array['Leather','Myrrh','Incense','Patchouli','Cedarwood']::text[], 'Night out', 'Cool season', 'Strong', 'images/boss.jpg', '', false, 90, true),
('Armaf', 'Club de Nuit Iconic', 'designer', false, false, 10500, 'Fresh, blue and ready for every occasion.', 'Armaf’s Club de Nuit line made the Dubai-based house famous for luxury-quality scents at accessible prices. Club de Nuit Iconic is its fresh “blue” fragrance — clean, polished and endlessly versatile.

Sparkling grapefruit, bergamot and pink pepper open into ginger, before a smooth woody base of incense, cedar and sandalwood. A dependable signature for work, weekends and everything between.', array['Grapefruit','Bergamot','Pink pepper','Ginger','Incense','Cedar','Sandalwood']::text[], 'Daily wear', 'All year', 'Long-lasting', 'images/iconic.jpg', '', false, 100, true),
('Giorgio Armani', 'Acqua di Giò Profondo', 'designer', false, false, 21000, 'Dive into the deep blue.', 'Since 1996, Acqua di Giò has captured the freedom of the Mediterranean sea. Profondo takes that story deeper — inspired by the intensity of the ocean’s depths and the thrill of diving in.

Marine notes, bergamot and green mandarin open fresh and salty, followed by aromatic rosemary, lavender and cypress, then a mineral, musky base with patchouli. Cool, clean and effortlessly elegant.', array['Marine notes','Bergamot','Green mandarin','Rosemary','Lavender','Cypress','Musk']::text[], 'Daytime', 'Hot weather', 'Moderate', 'images/armani.jpg', '', false, 110, true);
end if;
end $$;

-- =====================================================================
--  5) MAKE YOURSELF ADMIN  (run separately, AFTER creating your login)
--     Supabase → Authentication → Users → Add user → (your email + password)
--     Then change the email below and run just this line:
-- =====================================================================
-- insert into public.admins (user_id)
--   select id from auth.users where email = 'admin@example.com'
-- on conflict do nothing;
