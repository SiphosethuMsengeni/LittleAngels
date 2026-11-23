import json
import io
import logging
import math
import mimetypes
import os
import shutil
import threading
import uuid
from datetime import datetime
from functools import wraps
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash, send_file, send_from_directory, abort
from dotenv import load_dotenv
from werkzeug.utils import secure_filename

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR")
if DATA_DIR:
    os.makedirs(DATA_DIR, exist_ok=True)
    CATALOG_PATH = os.path.join(DATA_DIR, "catalog.json")
    ORDERS_PATH = os.path.join(DATA_DIR, "orders.jsonl")
    UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.join(DATA_DIR, "uploads"))
    if not os.path.exists(CATALOG_PATH):
        shutil.copyfile(os.path.join(BASE_DIR, "catalog.json"), CATALOG_PATH)
else:
    CATALOG_PATH = os.path.join(BASE_DIR, "catalog.json")
    ORDERS_PATH = os.path.join(BASE_DIR, "orders.jsonl")
    UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.join(BASE_DIR, "static", "uploads"))
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_BUCKET = os.environ.get("SUPABASE_BUCKET", "little-angels-images")
STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "local").lower()
if STORAGE_BACKEND not in {"local", "supabase"}:
    raise RuntimeError("STORAGE_BACKEND must be either 'local' or 'supabase'.")
SUPABASE_ENABLED = STORAGE_BACKEND == "supabase" or bool(SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY)
if SUPABASE_ENABLED and not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
    raise RuntimeError("Set both SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY to enable Supabase.")
catalog_lock = threading.RLock()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-before-deployment")
app.config["SHOP_NAME"] = "Little Angels Boutique"
app.config["WHATSAPP_NUMBER"] = os.environ.get("WHATSAPP_NUMBER", "")  # international digits, no + or spaces
app.config["ADMIN_PIN"] = os.environ.get("ADMIN_PIN", "1234")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024


class SupabaseError(RuntimeError):
    def __init__(self, status_code, message):
        super().__init__(message)
        self.status_code = status_code


def supabase_request(method, path, payload=None, content_type="application/json", prefer=None, raw_response=False):
    if not SUPABASE_ENABLED:
        raise RuntimeError("Supabase storage is not configured.")
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Accept": "*/*" if raw_response else "application/json",
    }
    body = None
    if payload is not None:
        if isinstance(payload, bytes):
            body = payload
        else:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = content_type
    if prefer:
        headers["Prefer"] = prefer
    request = Request(SUPABASE_URL + path, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=20) as response:
            response_body = response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise SupabaseError(exc.code, f"Supabase returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not connect to Supabase: {exc.reason}") from exc
    if raw_response:
        return response_body
    return json.loads(response_body) if response_body else None


def save_supabase_catalog(products):
    supabase_request(
        "POST",
        "/rest/v1/app_data?on_conflict=key",
        [{"key": "catalog", "value": products}],
        prefer="resolution=merge-duplicates,return=minimal",
    )


def record_supabase_order(order):
    return supabase_request(
        "POST",
        "/rest/v1/rpc/record_order",
        {"p_order": order},
    )


def load_products():
    if SUPABASE_ENABLED:
        rows = supabase_request("GET", "/rest/v1/app_data?key=eq.catalog&select=value")
        if rows:
            products = rows[0]["value"]
        else:
            with open(os.path.join(BASE_DIR, "catalog.json"), "r", encoding="utf-8") as file:
                products = json.load(file)
            save_supabase_catalog(products)
    else:
        with open(CATALOG_PATH, "r", encoding="utf-8") as file:
            products = json.load(file)
    for product in products:
        if "images" not in product and product.get("image"):
            product["images"] = [product["image"]]
        product.pop("image", None)
        if not isinstance(product.get("images"), list):
            product["images"] = []
        if not isinstance(product.get("sizes"), list):
            product["sizes"] = [{"name": "One size", "stock": 0}]
        for size in product["sizes"]:
            size["stock"] = max(0, int(size.get("stock", 0)))
    return products


def save_products(products):
    if SUPABASE_ENABLED:
        save_supabase_catalog(products)
        return
    temporary_path = CATALOG_PATH + ".tmp"
    with open(temporary_path, "w", encoding="utf-8") as file:
        json.dump(products, file, indent=2, ensure_ascii=False)
    os.replace(temporary_path, CATALOG_PATH)


def load_orders():
    if SUPABASE_ENABLED:
        rows = supabase_request(
            "GET",
            "/rest/v1/orders?select=data&order=created_at.asc,id.asc",
        )
        return [row["data"] for row in rows]
    orders = []
    if os.path.exists(ORDERS_PATH):
        with open(ORDERS_PATH, "r", encoding="utf-8") as file:
            for line in file:
                try:
                    orders.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return orders


def parse_product_form(form):
    name = form.get("name", "").strip()
    category = form.get("category", "").strip()
    description = form.get("description", "").strip()
    raw_price = form.get("price", "").strip()
    if not name or not category:
        raise ValueError("Product name and category are required.")
    if len(name) > 120 or len(category) > 80 or len(description) > 1000:
        raise ValueError("Product text is too long.")
    try:
        price = round(float(raw_price), 2) if raw_price else None
    except ValueError as exc:
        raise ValueError("Enter a valid product price.") from exc
    if price is not None and (not math.isfinite(price) or price < 0):
        raise ValueError("Product price must be zero or more.")

    size_names = form.getlist("size_name")
    stocks = form.getlist("size_stock")
    if len(size_names) != len(stocks):
        raise ValueError("Each size needs a matching stock quantity.")
    sizes = []
    seen_sizes = set()
    for raw_size, raw_stock in zip(size_names, stocks):
        size = raw_size.strip()
        raw_stock = raw_stock.strip()
        if not size and not raw_stock:
            continue
        if not size or not raw_stock:
            raise ValueError("Enter both a size name and its stock quantity.")
        try:
            stock = int(raw_stock)
        except ValueError as exc:
            raise ValueError("Stock quantities must be whole numbers.") from exc
        if stock < 0 or stock > 100000:
            raise ValueError("Stock quantities must be between 0 and 100000.")
        if len(size) > 40 or size.casefold() in seen_sizes:
            raise ValueError("Size names must be unique and no longer than 40 characters.")
        seen_sizes.add(size.casefold())
        sizes.append({"name": size, "stock": stock})
    if not sizes:
        raise ValueError("Add at least one size with its stock quantity.")
    return {
        "name": name,
        "category": category,
        "description": description,
        "price": price,
        "sizes": sizes,
    }


def save_uploaded_images(files):
    validated_files = []
    for image in files:
        if not image or not image.filename:
            continue
        safe_name = secure_filename(image.filename)
        extension = os.path.splitext(safe_name)[1].lower()
        if extension not in ALLOWED_IMAGE_EXTENSIONS:
            raise ValueError("Upload JPG, PNG, or WebP product photos only.")
        signature = image.stream.read(12)
        image.stream.seek(0)
        is_valid_image = (
            signature.startswith(b"\xff\xd8\xff")
            or signature.startswith(b"\x89PNG\r\n\x1a\n")
            or (signature.startswith(b"RIFF") and signature[8:12] == b"WEBP")
        )
        if not is_valid_image:
            raise ValueError(f"{safe_name} is not a valid JPG, PNG, or WebP image.")
        validated_files.append((image, extension))

    saved_names = []
    if not SUPABASE_ENABLED:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
    try:
        for image, extension in validated_files:
            stored_name = f"{uuid.uuid4().hex}{extension}"
            relative_name = f"uploads/{stored_name}"
            if SUPABASE_ENABLED:
                content_type = mimetypes.guess_type(stored_name)[0] or "application/octet-stream"
                supabase_request(
                    "POST",
                    f"/storage/v1/object/{quote(SUPABASE_BUCKET, safe='')}/{quote(relative_name, safe='/')}",
                    image.stream.read(),
                    content_type=content_type,
                )
            else:
                image.save(os.path.join(UPLOAD_DIR, stored_name))
            saved_names.append(relative_name)
    except (OSError, RuntimeError):
        remove_uploaded_images(saved_names)
        raise
    return saved_names


def remove_uploaded_images(images):
    if SUPABASE_ENABLED:
        for image in images:
            if image.startswith("uploads/"):
                try:
                    supabase_request(
                        "DELETE",
                        f"/storage/v1/object/{quote(SUPABASE_BUCKET, safe='')}",
                        {"prefixes": [image]},
                    )
                except RuntimeError:
                    logging.exception("Could not clean up uploaded photo %s.", image)
        return
    for image in images:
        if not image.startswith("uploads/"):
            continue
        path = os.path.join(UPLOAD_DIR, os.path.basename(image))
        try:
            if os.path.isfile(path):
                os.remove(path)
        except OSError:
            logging.exception("Could not clean up uploaded photo %s.", image)


@app.template_filter("product_image_url")
def product_image_url(filename):
    if filename.startswith("uploads/"):
        return url_for("uploaded_file", filename=filename[len("uploads/"):])
    return url_for("static", filename="images/" + filename)


@app.route("/media/<path:filename>")
def uploaded_file(filename):
    if SUPABASE_ENABLED:
        try:
            image_data = supabase_request(
                "GET",
                f"/storage/v1/object/{quote(SUPABASE_BUCKET, safe='')}/{quote('uploads/' + filename, safe='/')}",
                raw_response=True,
            )
        except SupabaseError as exc:
            if exc.status_code == 404:
                abort(404)
            raise
        return send_file(
            io.BytesIO(image_data),
            download_name=os.path.basename(filename),
            mimetype=mimetypes.guess_type(filename)[0] or "application/octet-stream",
        )
    return send_from_directory(UPLOAD_DIR, filename)


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)
    return wrapped


@app.route("/")
def home():
    return render_template(
        "index.html",
        products=load_products(),
        shop_name=app.config["SHOP_NAME"],
        whatsapp_number=app.config["WHATSAPP_NUMBER"]
    )


@app.route("/api/order", methods=["POST"])
def place_order():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"ok": False, "message": "The order details are invalid."}), 400
    customer = {
        "name": str(data.get("name", "")).strip(),
        "phone": str(data.get("phone", "")).strip(),
        "email": str(data.get("email", "")).strip(),
        "delivery": str(data.get("delivery", "")).strip(),
        "address": str(data.get("address", "")).strip(),
        "notes": str(data.get("notes", "")).strip(),
    }
    items = data.get("items", [])
    if not customer["name"] or not customer["phone"] or not isinstance(items, list) or not items:
        return jsonify({"ok": False, "message": "Please provide your name, phone number and at least one item."}), 400
    with catalog_lock:
        products = load_products()
        products_by_id = {product["id"]: product for product in products}
        requested = {}
        for item in items:
            try:
                product_id = int(item.get("id"))
                quantity = int(item.get("quantity", 1))
            except (AttributeError, TypeError, ValueError):
                return jsonify({"ok": False, "message": "Your basket contains an invalid product or quantity."}), 400
            size_name = str(item.get("size", "")).strip()
            if quantity < 1 or quantity > 20 or not size_name:
                return jsonify({"ok": False, "message": "Choose a size and a quantity between 1 and 20."}), 400
            product = products_by_id.get(product_id)
            if not product:
                return jsonify({"ok": False, "message": "A product in your basket is no longer available."}), 409
            size = next((entry for entry in product["sizes"] if entry["name"] == size_name), None)
            if not size:
                return jsonify({"ok": False, "message": f"{product['name']} is no longer available in size {size_name}."}), 409
            key = (product_id, size_name)
            requested[key] = requested.get(key, 0) + quantity
            if requested[key] > 20:
                return jsonify({"ok": False, "message": "A product size can be ordered up to 20 times per order."}), 400

        clean_items = []
        for (product_id, size_name), quantity in requested.items():
            product = products_by_id[product_id]
            size = next(entry for entry in product["sizes"] if entry["name"] == size_name)
            if quantity > size["stock"]:
                return jsonify({
                    "ok": False,
                    "message": f"Only {size['stock']} left in size {size_name} for {product['name']}. Please update your basket."
                }), 409
            clean_items.append({
                "id": product_id,
                "name": product["name"],
                "size": size_name,
                "quantity": quantity,
                "price": product.get("price")
            })
            size["stock"] -= quantity

        now = datetime.now()
        order = {
            "order_reference": "LA-" + now.strftime("%Y%m%d-%H%M%S-%f"),
            "created_at": now.isoformat(timespec="seconds"),
            "customer": customer,
            "items": clean_items,
            "status": "New"
        }
        try:
            if SUPABASE_ENABLED:
                result = record_supabase_order(order)
                if not isinstance(result, dict) or not result.get("ok"):
                    return jsonify({
                        "ok": False,
                        "message": "Stock changed while you were checking out. Please update your basket and try again."
                    }), 409
            else:
                order_line = json.dumps(order, ensure_ascii=False) + "\n"
                order_existed = os.path.exists(ORDERS_PATH)
                original_size = os.path.getsize(ORDERS_PATH) if order_existed else 0
                try:
                    with open(ORDERS_PATH, "a", encoding="utf-8") as file:
                        file.write(order_line)
                        file.flush()
                    save_products(products)
                except OSError:
                    if order_existed:
                        with open(ORDERS_PATH, "r+b") as file:
                            file.truncate(original_size)
                    elif os.path.exists(ORDERS_PATH):
                        os.remove(ORDERS_PATH)
                    raise
        except (OSError, RuntimeError):
            logging.exception("Could not save an order or update product stock.")
            return jsonify({"ok": False, "message": "We could not save your order. Please try again or contact the boutique."}), 500
    return jsonify({"ok": True, "message": "Your order has been received.", "reference": order["order_reference"]})


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        pin = request.form.get("pin", "")
        if pin == app.config["ADMIN_PIN"]:
            session["is_admin"] = True
            return redirect(url_for("admin"))
        flash("That PIN is not correct. Please try again.", "error")
    return render_template("admin_login.html", shop_name=app.config["SHOP_NAME"])


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/admin")
@admin_required
def admin():
    products = load_products()
    orders = load_orders()
    orders.reverse()
    return render_template("admin.html", products=products, orders=orders, shop_name=app.config["SHOP_NAME"])


@app.route("/admin/products/create", methods=["POST"])
@admin_required
def create_product():
    images = []
    try:
        product = parse_product_form(request.form)
        images = save_uploaded_images(request.files.getlist("images"))
        if not images:
            raise ValueError("Choose at least one product photo.")
        with catalog_lock:
            products = load_products()
            product["id"] = max((entry["id"] for entry in products), default=0) + 1
            product["images"] = images
            products.append(product)
            save_products(products)
    except ValueError as exc:
        flash(str(exc), "error")
    except OSError:
        logging.exception("Could not create a product.")
        remove_uploaded_images(images)
        flash("The product could not be saved. Please try again.", "error")
    else:
        flash("Product created successfully.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/products/<int:product_id>/update", methods=["POST"])
@admin_required
def update_product(product_id):
    new_images = []
    try:
        values = parse_product_form(request.form)
        with catalog_lock:
            products = load_products()
            product = next((entry for entry in products if entry["id"] == product_id), None)
            if product is None:
                return jsonify({"ok": False, "message": "Product not found."}), 404
            new_images = save_uploaded_images(request.files.getlist("images"))
            removed_images = set(request.form.getlist("remove_images"))
            images = [image for image in product["images"] if image not in removed_images]
            images.extend(new_images)
            if not images:
                raise ValueError("A product must have at least one photo.")
            product.update(values)
            product["images"] = images
            save_products(products)
    except ValueError as exc:
        flash(str(exc), "error")
    except OSError:
        logging.exception("Could not update product %s.", product_id)
        remove_uploaded_images(new_images)
        flash("The product could not be updated. Please try again.", "error")
    else:
        flash("Product updated successfully.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/products/<int:product_id>/delete", methods=["POST"])
@admin_required
def delete_product(product_id):
    with catalog_lock:
        products = load_products()
        remaining = [product for product in products if product["id"] != product_id]
        if len(remaining) == len(products):
            flash("That product no longer exists.", "error")
        else:
            try:
                save_products(remaining)
            except OSError:
                logging.exception("Could not delete product %s.", product_id)
                flash("The product could not be deleted. Please try again.", "error")
            else:
                flash("Product deleted. Its photo files were kept.", "success")
    return redirect(url_for("admin"))


if __name__ == "__main__":
    app.run(debug=True)
