### 1. CONFIGURATION AND INITIALIZATION ###

import os, click, json
from flask import Flask, render_template, request, redirect, flash, jsonify, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

# Initialize Flask and extensions
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{
    os.path.join(app.instance_path, "demo_gifts.db")}'
app.config['SECRET_KEY'] = 'demo-secret-key'  # In production, use env variable
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db = SQLAlchemy(app)


login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

### 2. MODELS ###

# Define models
class Family(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    created_by = db.Column(db.String(80), db.ForeignKey('user.username'))
    created_at = db.Column(db.DateTime, default=datetime.now)

    # Relationships
    users = db.relationship('User',
                            back_populates='family',
                            foreign_keys='User.family_id',
                            lazy=True)
   
    gifts = db.relationship('Gift',
                            backref='family',
                            lazy=True,
                            cascade='all, delete-orphan')

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    family_id = db.Column(
        db.Integer, db.ForeignKey('family.id'), nullable=True)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

    # Relationship: Each user belongs to one family
    family = db.relationship('Family',
                             back_populates='users',
                             foreign_keys=[family_id],
                             lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Gift(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    family_id = db.Column(db.Integer, db.ForeignKey(
        'family.id'), nullable=False)
    gift_recipient_id = db.Column(
        db.Integer, db.ForeignKey('user.id'), nullable=False)
    gift_name = db.Column(db.String(255), nullable=False)
    details = db.Column(db.Text)  
    link = db.Column(db.String(255))
    price = db.Column(db.String(100))
    purchased_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.now)

    # Add this relationship to access the recipient
    recipient = db.relationship(
        'User',
        foreign_keys=[gift_recipient_id], 
        backref='gifts_received',
        lazy=True
        )
    
    # Relationship for purchaser
    purchased_by = db.relationship('User', foreign_keys=[purchased_by_id], lazy=True)

    @property
    def is_purchased(self):
        return self.purchased_by_id is not None

## Helper functions ##


def clean_price(price):
    return price.replace("Â", "") if price else None

def validate_price(price_str):
    """Validate price string and return numeric value"""
    if not price_str:
        return 0

    # Remove currency symbol and whitespace
    price_clean = price_str.replace('£', '').strip()
    try:
        price_value = float(price_clean)
        return price_value
    except ValueError:
        return 0

### 3. AUTHENTICATION FUNCTIONS ###


# User loader function
@login_manager.user_loader
def load_user(user_id):
    user = db.session.get(User, int(user_id))
    return user


@app.route('/login', methods=['GET', 'POST'])
def login():
    
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        print(f"Attempting login with username: {username}")  # Debug print

        # Query the database for the user
        user = User.query.filter_by(username=username).first()

        if user is None:
            return render_template('login.html', error="Invalid username. Please try again.")
        elif not check_password_hash(user.password_hash, password):
            return render_template('login.html', error="Incorrect password. Please try again.")
        else:
            login_user(user)  # Actually log in the user
            return redirect(url_for('family_list'))  
            
    return render_template('login.html', error=error)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    error = None
    success = None

    if request.method == 'POST':
        username = request.form['username'].lower()
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        user = User.query.filter_by(username=username).first()

        if not user or not user.check_password(current_password):
            error = 'Invalid password'
        elif new_password != confirm_password:
            error = 'New passwords do not match'
        else:
            user.set_password(new_password)
            db.session.commit()
            success = 'Password updated successfully'
            return redirect(url_for('login'))

    return render_template('password_reset.html', error=error, success=success)

### 4. CORE FAMILY MANAGEMENT ###

@app.route('/register_create_family', methods=['GET', 'POST'])
def register_create_family():
    if request.method == 'POST':
        family_name = request.form['family_name'].strip()
        username = request.form['username'].strip().lower()
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        # Check passwords match
        if password != confirm_password:
            flash("Passwords do not match!", "error")
            return redirect(url_for('register_create_family'))

        # Check if family already exists
        if Family.query.filter_by(name=family_name).first():
            flash("Family name already exists!", "error")
            return redirect(url_for('register_create_family'))

        if User.query.filter_by(username=username).first():
            flash("Username already exists!", "error")
            return redirect(url_for('register_create_family'))

        # Use create_new_family_group to create family and user
        try:
            create_new_family_group(username, password)
            flash("Family created successfully!", "success")
            return redirect(url_for('my_list'))

        except Exception as e:
            db.session.rollback()
            flash(f"Error creating family: {str(e)}", "error")
            return redirect(url_for('register_create_family'))

    return render_template('register_create_family.html')


@app.route('/add_family_member', methods=['GET', 'POST'])
@login_required
def add_family_member():    
    if request.method == 'POST':
        username = request.form['username'].strip().lower()
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        

        # Validation
        if password != confirm_password:
            flash("Passwords do not match!", "error")
            return redirect(url_for('add_family_member'))

        if User.query.filter_by(username=username).first():
            flash("Username already exists!", "error")
            return redirect(url_for('add_family_member'))

        try:
            # Create new user and add to current family
            new_user = User(
                username=username,
                family_id=current_user.family_id,
                is_admin=False
            )
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()

            flash(f"Successfully added {
                  username} to your family group!", "success")
            return redirect(url_for('family_list'))

        except Exception as e:
            db.session.rollback()
            flash(f"Error adding family member: {str(e)}", "error")
            return redirect(url_for('add_family_member'))

    return render_template('add_family_user.html')


@app.route('/choose_list')
@login_required
def choose_list():
    return render_template('choose_list.html')



### Route: My List (View, Add, Edit, Delete Gifts) ###



@app.route('/my_list', methods=['GET', 'POST'])
@login_required
def my_list():
    if not current_user.family_id:
        flash("Please join or create a family first.", "warning")
        return redirect(url_for('register_create_family'))

    family_id = current_user.family_id
    family_members = User.query.filter_by(
        family_id=current_user.family_id).filter(User.id != current_user.id).all()

    gifts = Gift.query.filter_by(gift_recipient_id=current_user.id,
                                 family_id=family_id).all()

    if request.method == 'POST':
        action = request.form.get('action', 'save')

        if action == 'save':
            try:
                for gift in gifts:
                    gift_name = request.form.get(f"gift_{gift.id}") 
                    details = request.form.get(f"details_{gift.id}") 
                    price = request.form.get(f"price_{gift.id}") 
                    link = request.form.get(f"link_{gift.id}")

                    if gift_name and gift_name.strip():  # Update only if gift_name is provided 
                        gift.gift_name = gift_name 
                        gift.details = details or "" 
                        gift.price = price or "" 
                        gift.link = link or "" 
                        db.session.add(gift)
                    
                # Handle new gifts 
                new_gift_keys = [key for key in request.form.keys() if key.startswith('new_gift_')] 
                for key in new_gift_keys: 
                    timestamp = key.split('_')[2] 
                    gift_name = request.form.get(f"new_gift_{timestamp}") 
                    details = request.form.get(f"new_details_{timestamp}") 
                    price = request.form.get(f"new_price_{timestamp}") 
                    link = request.form.get(f"new_link_{timestamp}")
                                            
                    if gift_name and gift_name.strip(): 
                        new_gift=Gift(
                            family_id=current_user.family_id, 
                            gift_recipient_id=current_user.id, 
                            gift_name=gift_name, details=details or "", 
                            price=price or "", link=link or ""
                        ) 
                        db.session.add(new_gift)

                db.session.commit()
                flash("Gift list updated successfully!", "success")
                return redirect(url_for('my_list'))

            except Exception as e:
                db.session.rollback()
                flash(f"Error updating gifts: {str(e)}", "error")

    return render_template('my_list.html', gifts=gifts, family_members=family_members)


@app.route('/')
@login_required
def family_list():
    if not current_user.family_id:
        flash("Please join or create a family first.", "warning")
        return redirect(url_for('register_create_family'))
    
    family_id = current_user.family_id

    # For gift recipients - exclude current user
    recipients = User.query.filter(
        User.family_id == family_id,
        User.id != current_user.id
    ).all()

    # Modified query to start with Users and left join with Gifts
    family_members = (User.query
                      .filter(
                          User.family_id == family_id
                      )
                      .all())
    
    # Get all gifts for these family members
    gifts = Gift.query.filter(
        Gift.family_id == family_id,
        Gift.gift_recipient_id.in_([member.id for member in recipients])
    ).all()


    return render_template('family_list.html',
                           gifts=gifts,
                           family_members=family_members,
                           recipients = family_members,
                           current_user=current_user
                           )

@app.route('/mark_gift_purchased/<int:gift_id>', methods=['POST'])
@login_required
def mark_gift_purchased(gift_id):
    purchased_by = request.form.get(f'purchased_by_{gift_id}')

    gift = Gift.query.get(gift_id)
    if gift:
        gift.purchased_by_id = purchased_by
        db.session.commit()

    if not gift or gift.family_id != current_user.family_id:
        flash("Invalid gift or permission denied", "error")
        return redirect(url_for('family_list'))

    purchaser_id = request.form.get(f"purchased_by{gift.id}")

    if purchaser_id:
        gift.purchased_by_id = purchaser_id
        db.session.commit()
        flash("Gift status updated successfully!", "success")
    else:
        flash("No buyer selected.", "warning")


    return redirect(url_for('family_list'))  

@app.route('/delete_gift/<int:gift_id>', methods=['POST'])
@login_required
def delete_gift(gift_id):
    try:
        gift = Gift.query.get(gift_id)

        if gift is None:
            return jsonify({"error": "Gift not found"}), 404

        db.session.delete(gift)
        db.session.commit()
        return jsonify({"success": True}), 200 
    
    except Exception as e: 
        db.session.rollback() 
        return jsonify({"error": str(e)}), 500

### 6. DEMO DATA SETUP ###
DEMO_DEFAULT_PASSWORD = 'demo123'  # Password for all demo accounts


def create_new_family_group(username, password=DEMO_DEFAULT_PASSWORD):
    try:
        # Create a new family
        family = Family(
            name=f"{username}'s Family"
        )
        db.session.add(family)
        db.session.flush()

        # Create a user with the provided password
        user = User(username=username)
        # Assuming set_password hashes the password
        user.set_password(password)
        family.users.append(user)

        db.session.commit()
        print(f"New family group '{family.name}' created successfully!")

    except Exception as e:
        db.session.rollback()
        print(f"Error creating new family group: {str(e)}")
        raise e


def create_prepopulated_family_group():
    try:
        # Get the directory where your Python file is located
        current_dir = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(current_dir, 'seeds', 'demo_data.json')

        print(f"Loading JSON data from {json_path}")

        # Read the JSON file
        with open(json_path, 'r') as file:
            demo_data = json.load(file)
            print(demo_data)

        # Get the first family from the data
        family_data = demo_data['families'][0]
        print(f"Creating family: {family_data['name']}")


        # Now create the family with the admin_id
        family = Family(
            name=family_data['name'] # We now have the admin_id
        )
        db.session.add(family)
        db.session.flush()

        # Create the other users and their gifts
        for member_data in family_data['members']:
            # Handle user creation
            user = User(
            username=member_data['username'],
            is_admin=member_data['is_admin'],
            family_id=family.id
            )
            user.set_password(DEMO_DEFAULT_PASSWORD)
            print(
                f"Created user and set password for: {member_data['username']}")
            db.session.add(user)
            db.session.flush()
        
            # Add gifts for all users, including admin
            for gift_data in member_data['gifts']:
                gift = Gift(
                    family_id=family.id,
                    gift_recipient_id= user.id,
                    gift_name=gift_data['gift_name'],
                    details=gift_data['details'],
                    price=gift_data['price'].replace('£', '').strip(),
                    link=gift_data['link']
                )
                db.session.add(gift)

        db.session.commit()
        print(
            f"Prepopulated family group '{family.name}' created successfully!")
        
        # Debug: Print all users and their family IDs
        all_users = User.query.all()
        print("\nAll users after creation:")
        for user in all_users:
            print(
                f"User: {user.username}, Family ID: {user.family_id}, Admin: {user.is_admin}")

    except Exception as e:
        db.session.rollback()
        print(f"Error creating prepopulated family group: {str(e)}")
        raise


def create_demo_user_group():
    try:
        family_name = 'Placeholder Family'
        family = Family.query.filter_by(name=family_name).first()

        if not family:
            # Create a new demo family if it doesn't exist
            family = Family(name=family_name)
            db.session.add(family)
            db.session.flush()

        empty_users = [
            ('demo_admin', True),
            ('demo_user1', False),
            ('demo_user2', False)
        ]

        for username, is_admin in empty_users:
            user = User(
                username=username,
                is_admin=is_admin,
                family_id=family.id
            )
            user.set_password(DEMO_DEFAULT_PASSWORD)
            db.session.add(user)

        db.session.commit()
        print(
            f"Demo user group '{family.name}' created successfully with empty gift data!")

    except Exception as e:
        db.session.rollback()
        print(f"Error creating demo user group: {str(e)}")


def setup_demo_data():
    try:
        create_demo_user_group()
        create_prepopulated_family_group()

        # Debug prints
        print("Families:", [f.name for f in Family.query.all()])
        print("Users:", [u.username for u in User.query.all()])
        print("Gifts:", [g.gift_name for g in Gift.query.all()])

        print("Demo data setup successfully!")

    except Exception as e:
        db.session.rollback()
        print(f"Error setting up demo data: {str(e)}")

@app.cli.command('seed-db')
def seed_db():
    """Seed the database with full demo data."""
    from demo_gift_list_app import create_demo_accounts, db

    # Drop all tables and recreate them
    db.drop_all()
    db.create_all()

    # Call the function to create demo accounts
    try:
        create_demo_accounts()
        click.echo("Database seeded with demo data successfully!")
    except Exception as e:
        click.echo(f"Error seeding database: {str(e)}")


print("Registered URL routes:")
for rule in app.url_map.iter_rules():
    print(f"{rule.endpoint:50s} {rule.methods} {rule.rule}")



### 7. MAIN APPLICATION ENTRY ###
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        setup_demo_data()

    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)



