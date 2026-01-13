from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash
from flask_pymongo import PyMongo
from bson.objectid import ObjectId
import bcrypt
from datetime import datetime
from werkzeug.utils import secure_filename
import os
from dotenv import load_dotenv
from chatbot import get_bot_response

# ------------------ LOAD ENV ------------------ #
load_dotenv()

# ------------------ FLASK APP ------------------ #
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "mysecretkey")

# Upload folder setup
UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# ------------------ MONGODB SETUP ------------------ #
app.config["MONGO_URI"] = os.getenv("MONGO_URI", "mongodb://localhost:27017/smart_marketplace")
mongo = PyMongo(app)
db = mongo.db

# ------------------ HELPER FUNCTIONS ------------------ #
def update_products_category():
    """Ensure all products have a category and subcategory"""
    for item in db.products.find({"category": {"$exists": False}}):
        db.products.update_one(
            {"_id": item["_id"]},
            {"$set": {"category": "Uncategorized", "subcategory": "Others"}}
        )
    print("✅ Product categories updated.")

def calculate_cart_total(username):
    """Safely calculate total price of a user's cart"""
    cart_items = list(db.cart.find({"username": username}))
    total = sum(item.get("estimated_price", 0) for item in cart_items)
    return total or 0

# ------------------ AUTH ROUTES ------------------ #
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        address = request.form['address']
        password = request.form['password']

        if db.users.find_one({'username': username}):
            #flash("⚠️ User already exists! Please login.", "danger")
            return redirect(url_for('login'))

        hashed_pw = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        db.users.insert_one({
            "username": username,
            "name": name,
            "email": email,
            "phone": phone,
            "address": address,
            "password": hashed_pw
        })

        #flash("✅ Registration successful! Please login.", "success")
        return redirect(url_for('login'))

    return render_template('registration.html')


@app.route('/login', methods=['GET', 'POST']) 
def login(): 
    if request.method == 'POST':
        username = request.form['username'] 
        password = request.form['password'] 
        user = db.users.find_one({'username': username}) 
        print("DEBUG: Trying login for:", username)

        if user and bcrypt.checkpw(password.encode('utf-8'), user['password']): 
            session['user'] = username
            print("✅ Logged in:", username)
            
            if username.lower() =='admin':
                print("👉 Redirecting to admin_dashboard")
                return redirect(url_for('admin_dashboard'))
            
            else:
                print("👉 Redirecting to items")
                return redirect(url_for('items'))
            
        flash("❌ Invalid username or password", "danger") 
        return redirect(url_for('login')) 
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    #flash("👋 You have been logged out.", "info")
    return redirect(url_for('login'))

# ------------------ DASHBOARD ------------------ #
@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
    username = session['user']
    user_cart_count = db.cart.count_documents({"username": username})
    user_order_count = db.orders.count_documents({"username": username})
    return render_template('dashboard.html', username=username,
                           cart_count=user_cart_count, order_count=user_order_count)

# ------------------ PROFILE PAGE ------------------ #
@app.route('/profile')
def profile():
    if 'user' not in session:
        #flash("Please login first.", "warning")
        return redirect(url_for('login'))

    username = session['user']
    user = db.users.find_one({'username': username})

    if not user:
        #flash("User not found.", "danger")
        return redirect(url_for('login'))

    # ✅ Products currently listed by this seller
    user_products = list(db.products.find({'added_by': username}))

    # ✅ Products that have been sold by this seller
    sold_products = list(db.sold_products.find({'added_by': username}))

    # ✅ Commission summary for the seller
    total_commission = sum([prod.get('commission', 0) for prod in sold_products])
    total_sold_value = sum([prod.get('estimated_price', 0) for prod in sold_products])

    return render_template(
        'profile.html',
        user=user,
        user_products=user_products,
        sold_products=sold_products,
        total_commission=total_commission,
        total_sold_value=total_sold_value
    )

# ------------------ PRODUCT ROUTES ------------------ #
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/homepage')
def homepage():
    return redirect(url_for('items'))


@app.route('/items')
def items():
    if 'user' not in session:
        return redirect(url_for('login'))
    all_items = list(db.products.find())
    return render_template("items.html", items=all_items)


@app.route('/item/<item_id>')
def item_view(item_id):
    item = db.products.find_one({"_id": ObjectId(item_id)})
    if not item:
        #flash("❌ Item not found", "danger")
        return redirect(url_for('items'))
    return render_template("itemview.html", item=item)

# ------------------ CATEGORY ROUTE ------------------ #
@app.route('/category/<category_name>')
def category_view(category_name):
    if 'user' not in session:
        return redirect(url_for('login'))

    items = list(db.products.find({"category": category_name}))
    return render_template("category_item.html", category=category_name, items=items)

# ------------------ ANALYZE PRODUCT ------------------ #
@app.route('/analyze', methods=['GET', 'POST'])
def analyze():
    if 'user' not in session:
        return redirect(url_for('login'))

    product_types = ["Laptop", "Smartphone", "Tablet"]
    conditions = ["Like New", "Good", "Fair", "Poor", "Broken/Non-functional"]
    categories = {
        "Mobile & Accessories": ["Mobile", "Tablet", "Accessories"],
        "Computers & Laptop": ["Laptop", "Computer"],
        "Home Appliances": [
            "Fridge", "TV", "Washing Machine", "Ironbox",
            "Speakers", "AC", "Cooler", "Water Purifier", "Water Heater"
        ]
    }

    if request.method == "POST":
        action = request.form.get("action")

        image_url = ""
        if "image" in request.files and request.files["image"].filename != "":
            image_file = request.files["image"]
            filename = secure_filename(image_file.filename)
            image_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            image_file.save(image_path)
            image_url = f"/{image_path.replace(os.sep, '/')}"

        year_of_purchase = int(request.form['year_of_purchase'])
        age = datetime.now().year - year_of_purchase
        depreciation = min(0.9, age * 0.1)
        condition_factor = int(request.form['overall_condition']) / 10
        damage_condition = request.form['damage_condition']

        condition_multiplier = {
            "Like New": 0.9,
            "Good": 0.8,
            "Fair": 0.6,
            "Poor": 0.4,
            "Broken/Non-functional": 0.2
        }

        base_price = int(request.form['original_price'])
        estimated_price = int(base_price * (1 - depreciation) * condition_factor * condition_multiplier[damage_condition])

        product_data = {
            "category": request.form['category'],
            "subcategory": request.form['subcategory'],
            "product_type": request.form['product_type'],
            "brand": request.form['brand'],
            "year_of_purchase": year_of_purchase,
            "original_price": base_price,
            "overall_condition": int(request.form['overall_condition']),
            "damage_condition": damage_condition,
            "image_url": image_url,
            "created_at": datetime.now(),
            "estimated_price": estimated_price,
            "added_by": session['user'],
            "location": request.form.get('location', "Not Provided")
        }

        if action == "estimate":
            flash(f"💰 Estimated Resale Price: ₹{estimated_price}", "info")
            return render_template("analyze.html", product_types=product_types,
                                   conditions=conditions, categories=categories)

        elif action == "add":

            charge_amount = max(100, int(0.05 * estimated_price))

            # Save product and charge amount in session temporarily
            session['pending_product'] = product_data
            session['charge_amount'] = charge_amount

            # Redirect to payment page
            return redirect(url_for('payment'))
        
            '''db.products.insert_one(product_data)
            flash("✅ Product added successfully!", "success")
            return redirect(url_for('items'))'''

    return render_template('analyze.html', product_types=product_types,
                           conditions=conditions, categories=categories)

# ------------------ CART SYSTEM ------------------ #
@app.route("/cart")
def cart():
    if 'user' not in session:
        return redirect(url_for('login'))
    username = session['user']
    cart_items = list(db.cart.find({"username": username}))
    total_price = calculate_cart_total(username)
    return render_template("cart.html", cart_items=cart_items, total_price=total_price)

@app.route("/add_to_cart/<item_id>")
def add_to_cart(item_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    username = session['user']
    product = db.products.find_one({"_id": ObjectId(item_id)})
    if not product:
        #flash("❌ Product not found", "danger")
        return redirect(url_for('items'))
    
    seller_username = product.get("added_by", "Unknown Seller")
    seller_email = product.get("email", "Not Provided")
    seller_phone = product.get("phone", "Not Provided")
    seller_location = product.get("location", "Not Provided")

    # Avoid duplicate entries in cart
    if db.cart.find_one({"username": username, "product_id": item_id}):
        #flash("⚠️ Product already in cart.", "warning")
        return redirect(url_for('cart'))

    db.cart.insert_one({
        "username": username,
        "product_id": item_id,
        "brand": product.get("brand", "Unknown"),
        "product_type": product.get("product_type", "Item"),
        "estimated_price": product.get("estimated_price", 0),
        "image_url": product.get("image_url", ""),
        "seller_username": seller_username,
        "seller_email": seller_email,
        "seller_phone": seller_phone,
        "seller_location": seller_location,
        
    })
    #flash("✅ Added to cart successfully!", "success")
    return redirect(url_for('cart'))

@app.route("/remove_from_cart/<cart_id>")
def remove_from_cart(cart_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    db.cart.delete_one({"_id": ObjectId(cart_id)})
    #flash("🗑️ Item removed from cart.", "info")
    return redirect(url_for('cart'))

# ------------------ ORDER SYSTEM ------------------ #
@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    if 'user' not in session:
        return redirect(url_for('login'))

    username = session['user']
    cart_items = list(db.cart.find({"username": username}))
    total_price = calculate_cart_total(username)

    for item in cart_items:
        seller_username = item.get("seller_username")
        

        if seller_username:
            seller_info = db.users.find_one({"username": seller_username})
            if seller_info:
                item["seller"] = {
                    "name": seller_info.get("name", "Unknown Seller"),
                    "email": seller_info.get("email", "Not provided"),
                    "phone": seller_info.get("phone", "Not provided"),
                    "address": seller_info.get("address", "Not available")
                }
        else:
            item["seller"] = {
                "name": "Unknown Seller",
                "email": "Not provided",
                "phone": "Not provided"
            }
  
    if request.method == "POST":
        payment_method = request.form.get("payment_method", "COD")

        order = {
            "buyer_username": username,  # ✅ store buyer username explicitly
            "items": cart_items,
            "total_price": total_price,
            "payment_method": payment_method,
            "order_date": datetime.now(),
            "status": "Processing"
        }
    
        db.orders.insert_one(order)

        product = db.products.find_one({"_id": ObjectId(item["product_id"])})
        if product:
            product["sold_date"] = datetime.utcnow()
            product["buyer"] = username
            product["order_id"] = order["_id"]
            db.sold_products.insert_one(product)

        total_price = 0
        commission_rate = 0.10  # 10%

        total_commission=0

        for item in cart_items:
            product_id = item.get("product_id")
            product = db.products.find_one({"_id": ObjectId(product_id)})
##########################################################
            estimated_price = float(product.get('estimated_price', 0))
            commission = estimated_price * commission_rate
            total_commission += commission

        
            mongo.db.sold_products.insert_one({
                "category": product.get("category", "Other"),
                "subcategory": product.get("subcategory", "Unknown"),
                "product_type": product.get("product_type", "Unknown"),
                "brand": product.get("brand", "Unknown"),
                "year_of_purchase": product.get("year_of_purchase"),
                "original_price": product.get("original_price"),
                "overall_condition": product.get("overall_condition"),
                "damage_condition": product.get("damage_condition"),
                "image_url": product.get("image_url"),
                "estimated_price": estimated_price,
                "added_by": product.get("added_by"),
                "location": product.get("location"),
                "commission": round(commission, 2),
                "sold_date": datetime.utcnow(),
                "buyer": username,
                "order_id": ObjectId(),
            })



            if product_id:
                db.products.delete_one({"_id": ObjectId(item["product_id"])})
            mongo.db.orders.insert_one({
            "username": username,
            "items": cart_items,
            "total_price": total_price,
            "payment_method": payment_method,
            "order_date": datetime.utcnow(),
            "status": "Processing"
        })
            

        db.cart.delete_many({"username": username})

        metrics = mongo.db.admin_metrics.find_one({})
        if metrics:
            mongo.db.admin_metrics.update_one({}, {'$inc': {'total_profit': total_commission}})
        else:
            mongo.db.admin_metrics.insert_one({'total_profit': total_commission})

        #flash("✅ Order placed successfully!", "success")
        return render_template("order.html", user=username, items=cart_items,
                               total=total_price, payment_method=payment_method)

    return render_template("checkout.html", cart_items=cart_items, total_price=total_price)
# ------------------ SEARCH ------------------ #
@app.route('/search', methods=['GET'])
def search():
    if 'user' not in session:
        return redirect(url_for('login'))
    query = request.args.get('query', '').strip()
    if not query:
        flash("⚠️ Please enter a keyword to search.", "warning")
        return redirect(url_for('items'))

    search_filter = {
        "$or": [
            {"brand": {"$regex": query, "$options": "i"}},
            {"product_type": {"$regex": query, "$options": "i"}},
            {"category": {"$regex": query, "$options": "i"}},
            {"subcategory": {"$regex": query, "$options": "i"}}
        ]
    }
    filtered_products = list(db.products.find(search_filter))
    message = None
    if not filtered_products:
        message = f"No results found for '{query}'."
    return render_template('search_results.html', products=filtered_products, message=message, query=query)

############## ADMIN ############################################


'''@app.route('/create_admin')
def create_admin():
    existing_admin = mongo.db.users.find_one({"role": "admin"})
    if existing_admin:
        return "Admin already exists!"

    hashed_pw = generate_password_hash("admin123")
    admin_user = {
        "username": "admin",
        "email": "admin@example.com",
        "password": hashed_pw,
        "role": "admin"
    }
    mongo.db.users.insert_one(admin_user)
    return "✅ Admin user created successfully!"
'''

@app.route('/admin')
def admin_dashboard():
    if session.get('user') != 'admin':
        flash("Access denied. Admins only.", "danger")
        return redirect(url_for('login'))

    # ✅ Basic stats
    total_users = mongo.db.users.count_documents({})
    total_items = mongo.db.products.count_documents({})
    total_orders = mongo.db.orders.count_documents({})

    # ✅ Total commission (with safe default)
    metrics = mongo.db.admin_metrics.find_one({}) or {"total_profit": 0}
    total_commission = 0
    if metrics and "total_profit" in metrics:
        total_commission = round(metrics["total_profit"], 2)

    # ✅ Category-wise commission aggregation
    category_data = list(mongo.db.sold_products.aggregate([
        {"$group": {"_id": "$category", "commission": {"$sum": "$commission"}}}
    ]))

    # ✅ Render the dashboard
    return render_template(
        "admin_dashboard.html",
        total_users=total_users,
        total_items=total_items,
        total_orders=total_orders,
        total_commission=total_commission,
        category_data=category_data
    )
@app.route('/admin/orders')
def admin_orders():
    if session.get('user') != 'admin':
        flash("Access denied. Admins only.", "danger")
        return redirect(url_for('login'))

    orders_data = list(db.orders.find().sort("order_date", -1))
    orders = []

    for order in orders_data:
        username = order.get("username", "Unknown User")
        order_date = order.get("order_date", datetime.now()).strftime("%Y-%m-%d %H:%M")

        # Each order may contain multiple items
        for item in order.get("items", []):
            product = db.products.find_one({"_id": ObjectId(item.get("product_id"))}) if item.get("product_id") else None

            orders.append({
                "user": username,
                "item_name": product["subcategory"] if product else item.get("product_name", "Unknown Item"),
                "price": item.get("estimated_price", 0),
                "date": order_date,
                "status": order.get("status", "Pending")
            })
    return render_template('admin_orders.html', orders=orders)


@app.route('/admin/users')
def admin_users():
    if session.get('user') != 'admin':
        flash("Access denied. Admins only.", "danger")
        return redirect(url_for('login'))

    users = list(mongo.db.users.find())
    return render_template('admin_users.html', users=users)



# ------------------ CHATBOT ------------------ #
@app.route('/chatbot')
def chatbot():
    predefined_questions = [
        "Hello", "Hi", "How to buy a product", "How to sell a product",
        "What is smart circular economy", "Thank you", "Bye"
    ]
    return render_template('chatbot.html', predefined_questions=predefined_questions)

@app.route('/get-response', methods=['POST'])
def get_response():
    user_input = request.json.get('message')
    response = get_bot_response(user_input)
    return jsonify({'response': response})


#-----------------------------------------#

@app.route('/payment', methods=['GET', 'POST'])
def payment():
    product = session.get('pending_product')
    amount = session.get('charge_amount')

    if not product or not amount:
        flash("Payment session expired. Please try again.", "danger")
        return redirect(url_for('analyze'))

    if request.method == "POST":
        # Here you would integrate real payment gateway like Stripe/Razorpay
        payment_success = True  # Replace with actual payment processing

        if payment_success:

            product['commission'] = amount
            product['added_on'] = datetime.now()
            db.products.insert_one(product)

            session.pop('pending_product')
            session.pop('charge_amount')
            flash("✅ Payment successful! Product added.", "success")
            return redirect(url_for('items'))
        else:
            flash("Payment failed. Try again.", "danger")
            return redirect(url_for('payment'))

    return render_template('payment.html', product=product, amount=amount)


# ------------------ MAIN ------------------ #
if __name__ == '__main__':
    update_products_category()
    app.run(debug=True)
