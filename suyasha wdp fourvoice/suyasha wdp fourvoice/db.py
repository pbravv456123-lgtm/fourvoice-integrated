from flask_sqlalchemy import SQLAlchemy

# Type hinting helps with autocomplete in many code editors
db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users' # Good practice to name your table explicitly

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    
    # --- NEW FIELDS FOR SETUP ---
    selection = db.Column(db.String(50), nullable=True)      # 'create' or 'join'
    business_type = db.Column(db.String(100), nullable=True) # e.g. 'Freelance'
    country = db.Column(db.String(100), nullable=True)       # e.g. 'Singapore'
    currency = db.Column(db.String(50), nullable=True)       # e.g. 'SGD'
    company_join_code = db.Column(db.String(50), nullable=True) # Store code if they joined
    # ----------------------------

    def __repr__(self):
        return f'<User {self.email}>'