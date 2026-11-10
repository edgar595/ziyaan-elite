# Ziyaan Elite: how to go live with the admin page

This folder holds the whole website:

| File | What it is |
|---|---|
| `index.html` | The shop customers see |
| `admin.html` | The private admin page where you add, edit, hide or delete sprays |
| `config.js` | Your settings (Supabase keys, WhatsApp and M-Pesa numbers) |
| `starter-products.js` | Your current 11 sprays. The shop shows these until the database is connected |
| `images/` | Logo and the photos of the starter sprays |
| `supabase-setup.sql` | Sets up the database. You run it once |

The sprays are stored in **Supabase**, a free online database that also keeps the photos and handles the admin login. The setup takes about 15 minutes.

---

## Step 1: Create the database (free)

1. Go to **supabase.com**, sign up, and click **New project**.
2. Name it `ziyaan-elite`, choose a strong database password (save it somewhere), and pick the region closest to Kenya.
3. Wait about a minute for the project to finish setting up.

## Step 2: Set up the tables and photo storage

1. In the left menu, open **SQL Editor** and click **New query**.
2. Open `supabase-setup.sql` from this folder, copy everything in it, paste it into the editor, and click **Run**.
3. You should see "Success". This also loads your 11 current sprays into the database.

## Step 3: Create the admin login

1. Open **Authentication → Users → Add user → Create new user**.
2. Enter the admin's email and a strong password. Tick **Auto Confirm User** and click **Create user**.
3. Go back to **SQL Editor**, open a new query, paste the text below (with your real email), and click **Run**:

```sql
insert into public.admins (user_id)
  select id from auth.users where email = 'YOUR-ADMIN-EMAIL@example.com'
on conflict do nothing;
```

Repeat this step for every extra person who should be allowed to manage sprays.

4. Recommended: open **Authentication → Sign In / Providers → Email** and turn **off** "Allow new users to sign up". Strangers can't change anything even if they sign up, but this keeps the user list clean.

## Step 4: Connect the website to the database

1. In Supabase, open **Project Settings → API** (in some accounts it's called **API Keys** or **Data API**).
2. Copy the **Project URL** and the **anon public** key.
3. Open `config.js` in Notepad and paste them between the quotes:

```js
supabaseUrl: 'https://abcdxyz.supabase.co',
supabaseAnonKey: 'eyJhbGciOi...',
```

The anon key is meant to be public and is safe on a website. **Never** paste the `service_role` key here.

## Step 5: Publish the website (free with Netlify)

1. Go to **netlify.com** and sign up for free.
2. Open **Sites → Add new site → Deploy manually**.
3. Drag the **whole folder** (the one with `index.html`, `admin.html` and `images`) onto the page.
4. Netlify gives you an address like `ziyaan-elite.netlify.app`. You can rename it or connect your own domain under **Domain management**.

To change the website itself later (not the sprays), edit the files and drag the folder in again under **Deploys**.

---

## Adding sprays every day

1. Open **your-site-address/admin.html** on your phone or computer and sign in.
2. Tap **+ ADD SPRAY**, then add a photo, brand, name, price, category, story and notes.
3. Tap **SAVE SPRAY**. It appears on the shop straight away. Customers only need to refresh the page.

On each spray card in the admin page:

- **Edit** changes the price, photo, story and other details.
- **Hide** takes the spray off the shop without deleting it (useful when it's out of stock). **Show** puts it back.
- **Delete** removes it for good. You tap twice to confirm.

**Tips**

- **Show in top slider** puts the spray in the big rotating picture at the top of the shop. A cut-out photo with a transparent background looks best there. If you don't add one, the main photo is used.
- **Position** sets the order on the shop. Lower numbers come first.
- In **The story**, leave an empty line between paragraphs.
- Photos are shrunk automatically before they upload, so large phone photos are fine.

## Stock (inventory)

- In **Edit**, set **Bottles in stock** and **Warn me at** (default 3). Leave stock empty if you don't want to track that spray.
- On each card, tap **−** when you sell one and **+** when you restock.
- When a spray reaches its warning level, a **Restock needed** box appears at the top of the admin page, and the browser tab shows how many sprays need attention. The page refreshes itself every minute.
- On the shop, low sprays show "Only X left". At 0 they show **Out of stock**, and customers can't add them to the cart (they can still ask on WhatsApp).
- Orders come in through WhatsApp, so the stock does **not** go down by itself. Tap **−** once the order is confirmed.

## If something goes wrong

- **The admin page says "Admin not connected yet"**: `config.js` is still empty, or the folder wasn't uploaded again after you edited it.
- **"Not an admin yet"**: run the SQL from Step 3 for that email.
- **"Wrong email or password"**: reset the password in Supabase → Authentication → Users.
- **The shop shows the old 11 sprays and none of the new ones**: check the URL and key in `config.js`.
- **Free plan note**: Supabase pauses free projects after about a week with no visitors at all. A shop with regular visitors won't be affected. If it does pause, log in to Supabase and click **Restore**.
