import os
from datetime import datetime
from flask import Flask, request, jsonify, render_template, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///moods.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.secret_key = 'change_this_secret_key'

db = SQLAlchemy(app)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Настройка Flask-Login
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = "Пожалуйста, войдите, чтобы получить доступ к этой странице."
login_manager.login_message_category = "warning"

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
EMOJIS = {1: '😞', 2: '😐', 3: '🙂', 4: '😄', 5: '😁'}

# --- Модели БД ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    moods = db.relationship('Mood', backref='author', lazy=True, cascade="all, delete-orphan")

class Mood(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.String(20), nullable=False, default=lambda: datetime.now().strftime('%Y-%m-%d %H:%M'))
    level = db.Column(db.Integer, nullable=False) # Общее настроение
    stress = db.Column(db.Integer, default=3)     # Уровень стресса
    sleep = db.Column(db.Integer, default=3)      # Качество сна
    energy = db.Column(db.Integer, default=3)     # Уровень энергии
    note = db.Column(db.String(500), nullable=True)
    image = db.Column(db.String(255), nullable=True)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def handle_image_upload():
    file = request.files.get('image')
    if not file or not file.filename:
        return None
    if not allowed_file(file.filename):
        raise ValueError("Недопустимый формат. Разрешены: png, jpg, jpeg, gif, webp")
    filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    return filename

# --- Маршруты авторизации ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username').strip()
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash('Пользователь с таким именем уже существует.', 'error')
            return redirect(url_for('register'))
            
        hashed_password = generate_password_hash(password)
        new_user = User(username=username, password_hash=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        flash('Регистрация успешна! Теперь вы можете войти.', 'success')
        return redirect(url_for('login'))
    return render_template('auth.html', action='register')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username').strip()
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Неверное имя пользователя или пароль.', 'error')
    return render_template('auth.html', action='login')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- Основные маршруты ---
@app.route('/')
@login_required
def index():
    moods = Mood.query.filter_by(user_id=current_user.id).order_by(Mood.date.desc()).limit(10).all()
    return render_template('index.html', moods=moods, emojis=EMOJIS)

@app.route('/add', methods=['POST'])
@login_required
def add_mood():
    level = request.form.get('level', type=int)
    stress = request.form.get('stress', type=int)
    sleep = request.form.get('sleep', type=int)
    energy = request.form.get('energy', type=int)
    note = request.form.get('note', '').strip()
    
    if level not in EMOJIS:
        flash('⚠️ Выберите настроение перед сохранением.', 'error')
        return redirect(url_for('index'))
        
    try:
        filename = handle_image_upload()
    except ValueError as e:
        flash(f'⚠️ {e}', 'error')
        return redirect(url_for('index'))

    new_mood = Mood(user_id=current_user.id, level=level, stress=stress, sleep=sleep, energy=energy, note=note, image=filename)
    db.session.add(new_mood)
    db.session.commit()
    flash('Запись успешно сохранена!', 'success')
    return redirect(url_for('index'))

@app.route('/history')
@login_required
def history():
    moods = Mood.query.filter_by(user_id=current_user.id).order_by(Mood.date.desc()).all()
    return render_template('history.html', moods=moods, emojis=EMOJIS)

@app.route('/delete/<int:mood_id>')
@login_required
def delete_mood(mood_id):
    mood = Mood.query.get_or_404(mood_id)
    if mood.user_id != current_user.id:
        flash('У вас нет прав для удаления этой записи.', 'error')
        return redirect(url_for('history'))
        
    if mood.image:
        path = os.path.join(app.config['UPLOAD_FOLDER'], mood.image)
        if os.path.exists(path):
            os.remove(path)
    db.session.delete(mood)
    db.session.commit()
    flash('Запись удалена.', 'info')
    return redirect(url_for('history'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    # host='0.0.0.0' заставляет Flask "слушать" все сетевые адреса компьютера
    app.run(debug=True, host='0.0.0.0')