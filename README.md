# Little Angels Boutique

A children's clothing boutique web application built with Python Flask, HTML, CSS and JavaScript. The 29 photos from the supplied ZIP are included in `static/images/`.

## Features
- Responsive boutique storefront and searchable product gallery
- Seven visually grouped products using all 29 supplied clothing photographs
- Admin product create, view, update and delete
- Product photo uploads and size-by-size stock management
- Size selection and stock-aware shopping basket
- Shopping basket saved in the customer's browser
- Website order form; local orders use `orders.jsonl`, while hosted orders and stock use Supabase
- WhatsApp order message generator
- Admin area to edit product names, categories and prices and view website orders

## Run locally
1. Install Python 3.10 or newer.
2. Open a terminal in this project folder.
3. Create and activate a virtual environment:
   - Windows: `py -m venv .venv` then `.venv\\Scripts\\activate`
   - macOS/Linux: `python3 -m venv .venv` then `source .venv/bin/activate`
4. Install dependencies: `pip install -r requirements.txt`
5. Copy `.env.example` to `.env` and set your own `SECRET_KEY`, `ADMIN_PIN` and `WHATSAPP_NUMBER`. The app loads this file automatically.
6. Start the app: `python app.py`
7. Open `http://127.0.0.1:5000` in your browser.

### Windows PowerShell environment example
```powershell
$env:SECRET_KEY="your-long-random-secret"
$env:ADMIN_PIN="your-private-pin"
$env:WHATSAPP_NUMBER="27xxxxxxxxx"
python app.py
```

### Admin
Open `http://127.0.0.1:5000/admin/login`. The development default PIN is `1234`; change `ADMIN_PIN` before using the site beyond local testing. Use **Product inventory** to adjust item details, photos, sizes, and stock, or **Add a product** to create a new listing. New uploads accept JPG, PNG, and WebP files up to the request size limit. Photo removal unlinks a photo from the product but keeps the file on disk.

The supplied products start with zero stock because the actual quantities and sizes were not provided. Enter the boutique's real sizes and quantities in the admin before taking orders. Products with stock set to zero are shown as out of stock and cannot be added to the basket. Website orders reserve the ordered quantities immediately; update stock manually if an order is later cancelled.

## Before going live
- Add the boutique's real WhatsApp number in international digits-only format (South Africa starts with `27`).
- Update product names, categories and prices at `/admin`.
- Replace the development secret and admin PIN with private values.
- Use HTTPS, secure secret management and regular backups.
- Add a privacy notice and confirm the business's delivery, returns, payment and customer-data policies.
- This starter app does not process card payments. It records customer orders for the shop to confirm manually.

## Host on Render with Supabase
1. Create a private GitHub repository and push this project folder to it. Keep `.env`, `orders.jsonl`, local uploads, and all service keys out of GitHub; `.gitignore` excludes local data and secrets.
2. Create a Supabase project. In its SQL Editor, run [`supabase/schema.sql`](./supabase/schema.sql) to create the catalog and orders tables, the atomic order/stock update function, and the private image bucket.
3. Copy the Supabase project URL and its `service_role` key from the Supabase project settings. Keep the key private; add it only as a Render environment variable, never to GitHub or chat.
4. In Render, choose **New → Blueprint** and connect the GitHub repository containing `render.yaml`. The boutique WhatsApp contact is preconfigured; supply `ADMIN_PIN`, `SUPABASE_URL`, and `SUPABASE_SERVICE_ROLE_KEY` when prompted. Render generates `SECRET_KEY`.
5. Deploy, then open the Render-provided `onrender.com` address and `/admin/login`. Add the boutique's real sizes and stock before taking orders.

The Render Blueprint uses its free web-service plan. Its filesystem is temporary, so the hosted app is configured to keep catalog and stock data in Supabase Postgres and new photos in the private Supabase Storage bucket. Website orders and the matching stock decrement are written together in one database transaction. Supabase free-tier limits and project-pause policies apply; review the provider's current limits and keep backups of order data.

## Product photo note
The original 29 photos are grouped into seven products in `catalog.json`. The original files in `static/images/` are retained. Additional photos uploaded from the admin area are stored locally under `static/uploads/` or in Supabase Storage when hosted with `STORAGE_BACKEND=supabase`.
