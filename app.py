import os
import random
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv

load_dotenv() # .env dosyasındaki değişkenleri yükle

app = Flask(__name__)

# --- Veritabanı Yapılandırması ---
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
if not app.config['SQLALCHEMY_DATABASE_URI']:
    raise ValueError("DATABASE_URL ortam değişkeni ayarlanmamış!")
# Render PostgreSQL'in eski sürümleri SSL gerektirebilir, gerekirse ekleyin:
# app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'sslmode': 'require'} # Render'da genellikle gerekmez
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- Veritabanı Modeli ---
class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    secret_number = db.Column(db.String(3), nullable=False)
    attempts = db.Column(db.Integer, default=0)
    is_won = db.Column(db.Boolean, default=False)
    # created_at = db.Column(db.DateTime, server_default=db.func.now()) # İsterseniz ekleyebilirsiniz

    def __repr__(self):
        return f'<Game {self.id}>'

# --- Yardımcı Fonksiyonlar ---
def generate_secret_number():
    """Rakamları tekrarsız 3 basamaklı bir sayı üretir."""
    digits = list('0123456789')
    random.shuffle(digits)
    # İlk rakam 0 olamaz (3 basamaklı olması için)
    if digits[0] == '0':
        # İlk sıfır olmayan rakamla yer değiştir
        for i in range(1, 10):
            if digits[i] != '0':
                digits[0], digits[i] = digits[i], digits[0]
                break
    return "".join(digits[:3])

def check_guess(secret, guess):
    """Tahmini kontrol eder ve +1/-1 sayısını döndürür."""
    if len(guess) != 3 or not guess.isdigit():
        return None # Geçersiz tahmin

    plus_count = 0
    minus_count = 0
    secret_digits = list(secret)
    guess_digits = list(guess)

    # +1 (Boğa) kontrolü
    for i in range(3):
        if guess_digits[i] == secret_digits[i]:
            plus_count += 1

    # -1 (İnek) kontrolü
    for i in range(3):
        # Aynı pozisyonda eşleşenleri tekrar saymamak için kontrol
        if guess_digits[i] != secret_digits[i] and guess_digits[i] in secret_digits:
             minus_count += 1

    return {'plus': plus_count, 'minus': minus_count}


# --- Rotalar (Endpoints) ---
@app.route('/')
def index():
    """Ana oyun sayfasını gösterir."""
    return render_template('index.html')

@app.route('/api/games', methods=['POST'])
def start_new_game():
    """Yeni bir oyun başlatır."""
    try:
        secret = generate_secret_number()
        new_game = Game(secret_number=secret)
        db.session.add(new_game)
        db.session.commit()
        return jsonify({'game_id': new_game.id}), 201 # 201 Created
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Yeni oyun başlatılırken hata: {e}")
        return jsonify({'error': 'Oyun başlatılamadı'}), 500

@app.route('/api/games/<int:game_id>/guess', methods=['POST'])
def make_guess(game_id):
    """Belirli bir oyun için tahmin yapar."""
    game = db.session.get(Game, game_id) # SQLAlchemy 2.0+ için get kullanımı
    # game = Game.query.get(game_id) # Eski SQLAlchemy sürümleri için

    if not game:
        return jsonify({'error': 'Oyun bulunamadı'}), 404

    if game.is_won:
        return jsonify({'error': 'Oyun zaten kazanılmış'}), 400

    data = request.get_json()
    if not data or 'guess' not in data:
        return jsonify({'error': 'Tahmin bilgisi eksik'}), 400

    guess = data['guess']

    # Basit girdi doğrulama
    if not isinstance(guess, str) or len(guess) != 3 or not guess.isdigit():
         return jsonify({'error': 'Geçersiz tahmin formatı (3 rakam olmalı)'}), 400

    # --- Rakam Tekrarlılığı Kontrolü (Opsiyonel ama önerilir) ---
    # if len(set(guess)) != 3:
    #     return jsonify({'error': 'Tahmindeki rakamlar farklı olmalı'}), 400

    result = check_guess(game.secret_number, guess)

    game.attempts += 1
    message = ""

    if result['plus'] == 3:
        game.is_won = True
        message = f"Tebrikler! {game.attempts} denemede bildiniz!"
    else:
        message = f"Sonuç: +{result['plus']} / -{result['minus']}"

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Tahmin kaydedilirken hata: {e}")
        return jsonify({'error': 'Tahmin işlenemedi'}), 500

    return jsonify({
        'guess': guess,
        'result': result,
        'attempts': game.attempts,
        'is_won': game.is_won,
        'message': message
    })

# --- Veritabanı Tablolarını Oluşturma ---
# Uygulama bağlamı içinde tabloları oluşturmak önemlidir.
# Bunu bir kereye mahsus çalıştırmak veya uygulamanın başlangıcında kontrol etmek gerekir.
# Basit bir yol:
with app.app_context():
    db.create_all() # Veritabanında eksik tabloları oluşturur. Mevcutları değiştirmez.

# --- Uygulamayı Çalıştırma (Lokal Geliştirme İçin) ---
if __name__ == '__main__':
    # port=5001 gibi farklı bir port kullanabilirsiniz
    app.run(debug=True) # debug=True geliştirme modunda otomatik yeniden başlatma ve daha fazla hata detayı sağlar
