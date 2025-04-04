import os
import random
import uuid # Benzersiz oyun ID'leri için
from flask import Flask, render_template, request, jsonify # jsonify artık daha az kullanılacak
from flask_socketio import SocketIO, emit, join_room, leave_room, send # SocketIO importları
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from datetime import datetime # created_at için

load_dotenv()

app = Flask(__name__)

# --- Yapılandırma ---
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'cok_gizli_bir_anahtar_olmalidir') # SocketIO için gerekli
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
if not app.config['SQLALCHEMY_DATABASE_URI']:
    raise ValueError("DATABASE_URL ortam değişkeni ayarlanmamış!")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# app.config['SQLALCHEMY_ECHO'] = True # SQL sorgularını görmek için (debugging)

db = SQLAlchemy(app)
# async_mode='eventlet' veya 'gevent' olmalı. Render için eventlet genellikle iyi çalışır.
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins="*") # CORS ayarı gerekebilir

# --- Veritabanı Modeli ---
# Not: JSONB PostgreSQL'de daha verimli olabilir ama JSON yeterli
class MultiplayerGame(db.Model):
    id = db.Column(db.String(10), primary_key=True) # Rastgele oyun ID'si
    player1_sid = db.Column(db.String, nullable=True)
    player2_sid = db.Column(db.String, nullable=True)
    player1_secret = db.Column(db.String(3), nullable=True)
    player2_secret = db.Column(db.String(3), nullable=True)
    current_turn_sid = db.Column(db.String, nullable=True) # Kimin sırası
    # JSON listesi olarak tahminleri sakla: [{'guess': '123', 'result': {'plus': 1, 'minus': 0}}]
    player1_guesses = db.Column(db.JSON, default=lambda: [])
    player2_guesses = db.Column(db.JSON, default=lambda: [])
    status = db.Column(db.String, default='waiting') # waiting, active, finished, abandoned
    winner_sid = db.Column(db.String, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_opponent_sid(self, player_sid):
        return self.player2_sid if player_sid == self.player1_sid else self.player1_sid

    def get_opponent_secret(self, player_sid):
         return self.player2_secret if player_sid == self.player1_sid else self.player1_secret

    def add_guess(self, player_sid, guess, result):
        # SQLAlchemy'de JSON listesini değiştirmek için kopyala-ekle-ata yöntemi
        if player_sid == self.player1_sid:
            guesses = list(self.player1_guesses)
            guesses.append({'guess': guess, 'result': result})
            self.player1_guesses = guesses
            return len(guesses) # Deneme sayısını döndür
        elif player_sid == self.player2_sid:
             guesses = list(self.player2_guesses)
             guesses.append({'guess': guess, 'result': result})
             self.player2_guesses = guesses
             return len(guesses) # Deneme sayısını döndür
        return 0

# --- Yardımcı Fonksiyonlar ---
def generate_secret_number():
    """Rakamları tekrarsız 3 basamaklı bir sayı üretir."""
    digits = list('0123456789')
    random.shuffle(digits)
    if digits[0] == '0':
        non_zero_idx = next((i for i, d in enumerate(digits) if d != '0'), None)
        if non_zero_idx is not None:
             digits[0], digits[non_zero_idx] = digits[non_zero_idx], digits[0]
        else: # Hepsi sıfırsa (imkansız ama yine de)
             return "123" # Veya hata fırlat
    return "".join(digits[:3])

def check_guess(secret, guess):
    """Tahmini kontrol eder ve +1/-1 sayısını döndürür."""
    if not isinstance(secret, str) or not isinstance(guess, str) or len(guess) != 3 or not guess.isdigit() or len(secret) != 3:
        return None # Geçersiz girdi

    plus_count = 0
    minus_count = 0
    secret_digits = list(secret)
    guess_digits = list(guess)

    # +1 (Boğa) kontrolü
    for i in range(3):
        if guess_digits[i] == secret_digits[i]:
            plus_count += 1

    # -1 (İnek) kontrolü (Doğru yerde olanları tekrar sayma)
    counted_secret_indices = set()
    for i in range(3):
         if guess_digits[i] == secret_digits[i]:
             counted_secret_indices.add(i) # Doğru yerdekini işaretle

    for i in range(3):
        # Hem aynı pozisyonda değilse, hem de tahmindeki rakam sırda varsa, VE o sır rakamı daha önce doğru pozisyonda sayılmadıysa
        if guess_digits[i] != secret_digits[i] and guess_digits[i] in secret_digits:
            # Bu rakamın sır içindeki pozisyonunu bul
            found_in_secret = False
            for j in range(3):
                # Eğer tahmindeki rakam, sır'daki j pozisyonundaki rakama eşitse VE j pozisyonu daha önce doğru (+1) olarak sayılmadıysa VE j pozisyonu bu -1 turunda başka bir tahminle eşleşmediyse
                 if guess_digits[i] == secret_digits[j] and j not in counted_secret_indices:
                     minus_count += 1
                     counted_secret_indices.add(j) # Bu sır pozisyonunu da sayıldı olarak işaretle
                     found_in_secret = True
                     break # Bu tahmin rakamı için bir eşleşme bulduk, diğer sır pozisyonlarına bakmaya gerek yok


    return {'plus': plus_count, 'minus': minus_count}

def generate_game_id():
    """Kısa, benzersiz oyun ID'si üretir (örn: ABCDE1)"""
    return str(uuid.uuid4())[:6].upper() # 6 karakterlik büyük harf/sayı

def build_game_state(game, player_sid):
    """İstemciye gönderilecek oyun durumu sözlüğünü oluşturur."""
    if not game:
        return None

    # Güvenlik: Rakibin sırrını sadece oyun bittiyse ve kazanan belliyse gönder
    opponent_secret_to_send = None
    if game.status == 'finished':
        opponent_secret_to_send = game.get_opponent_secret(player_sid)

    # Oyuncunun rolünü belirle
    your_role = 'observer' # Varsayılan (eğer oyuncu değilse)
    if player_sid == game.player1_sid:
        your_role = 'player1'
    elif player_sid == game.player2_sid:
        your_role = 'player2'

    return {
        'game_id': game.id,
        'status': game.status,
        'current_turn_sid': game.current_turn_sid,
        'winner_sid': game.winner_sid,
        'your_player_id': your_role, # 'player1' veya 'player2'
        'opponent_secret': opponent_secret_to_send, # Sadece oyun bitince gönderilir
        'guesses': {
            'player1': game.player1_guesses if hasattr(game, 'player1_guesses') else [],
            'player2': game.player2_guesses if hasattr(game, 'player2_guesses') else []
        }
        # İleride: oyuncu adları, kalan süre vb. eklenebilir
    }


# --- HTTP Rotaları ---
@app.route('/')
def index():
    """Ana HTML sayfasını sunar."""
    return render_template('index.html')

# --- SocketIO Olayları ---
@socketio.on('connect')
def handle_connect():
    """İstemci bağlandığında."""
    print(f"İstemci bağlandı: {request.sid}")
    emit('message', {'msg': 'Sunucuya hoş geldiniz!'}) # Sadece bağlanan kişiye

@socketio.on('disconnect')
def handle_disconnect():
    """İstemci ayrıldığında."""
    sid = request.sid
    print(f"İstemci ayrıldı: {sid}")
    # Oyuncunun olduğu aktif bir oyunu bul
    game = MultiplayerGame.query.filter(
        (MultiplayerGame.player1_sid == sid) | (MultiplayerGame.player2_sid == sid)
    ).filter(MultiplayerGame.status == 'active').first()

    if game:
        opponent_sid = game.get_opponent_sid(sid)
        game.status = 'abandoned' # Oyunu terk edilmiş olarak işaretle
        # game.winner_sid = opponent_sid # İsteğe bağlı: Kalan oyuncuyu kazanan yap
        try:
            db.session.commit()
            print(f"Oyun {game.id} terk edildi olarak işaretlendi.")
            if opponent_sid:
                # Rakibe haber ver
                opponent_game_state = build_game_state(game, opponent_sid)
                socketio.emit('game_update', opponent_game_state, room=opponent_sid) # Sadece rakibe gönder
                socketio.emit('game_error', {'message': 'Rakibiniz oyundan ayrıldı.'}, room=opponent_sid)
        except Exception as e:
            db.session.rollback()
            print(f"Ayrılma sırasında DB hatası: {e}")

@socketio.on('create_game')
def handle_create_game(data):
    """Yeni bir oyun oluşturma isteği."""
    sid = request.sid
    secret = data.get('secret')

    # Basit doğrulama
    if not secret or len(secret) != 3 or not secret.isdigit() or len(set(secret)) != 3:
         emit('game_error', {'message': 'Geçersiz gizli sayı (3 farklı rakam olmalı).'})
         return

    game_id = generate_game_id()
    new_game = MultiplayerGame(
        id=game_id,
        player1_sid=sid,
        player1_secret=secret,
        status='waiting'
    )
    try:
        db.session.add(new_game)
        db.session.commit()
        join_room(game_id) # Oyuncuyu oyun odasına ekle
        print(f"Oyun oluşturuldu: {game_id} oleh {sid}")
        emit('game_created', {'game_id': game_id}) # Sadece oluşturan kişiye ID'yi gönder
    except Exception as e:
        db.session.rollback()
        print(f"Oyun oluşturma hatası: {e}")
        emit('game_error', {'message': 'Oyun oluşturulurken bir hata oluştu.'})

@socketio.on('join_game')
def handle_join_game(data):
    """Mevcut bir oyuna katılma isteği."""
    sid = request.sid
    game_id = data.get('game_id')
    secret = data.get('secret')

    # Doğrulamalar
    if not game_id:
         emit('game_error', {'message': 'Oyun ID eksik.'})
         return
    if not secret or len(secret) != 3 or not secret.isdigit() or len(set(secret)) != 3:
         emit('game_error', {'message': 'Geçersiz gizli sayı (3 farklı rakam olmalı).'})
         return

    game = db.session.get(MultiplayerGame, game_id) # SQLAlchemy 2.0+
    # game = MultiplayerGame.query.get(game_id) # Eski sürüm

    if not game:
        emit('game_error', {'message': 'Oyun bulunamadı.'})
        return
    if game.status != 'waiting':
        emit('game_error', {'message': 'Bu oyuna şu anda katılamazsınız (dolu veya bitmiş).'})
        return
    if game.player1_sid == sid:
         emit('game_error', {'message': 'Kendi oluşturduğunuz oyuna katılamazsınız.'})
         return

    # Oyuna katıl
    game.player2_sid = sid
    game.player2_secret = secret
    game.status = 'active'
    game.current_turn_sid = game.player1_sid # İlk kuran başlasın
    try:
        db.session.commit()
        join_room(game_id) # İkinci oyuncuyu da odaya ekle
        print(f"{sid}, {game_id} oyununa katıldı.")

        # Her iki oyuncuya da oyunun başladığını ve güncel durumu bildir
        player1_state = build_game_state(game, game.player1_sid)
        player2_state = build_game_state(game, game.player2_sid)

        socketio.emit('game_update', player1_state, room=game.player1_sid) # Odadaki herkese değil, özel gönderim
        socketio.emit('game_update', player2_state, room=game.player2_sid) # Odadaki herkese değil, özel gönderim
        # Veya odadaki herkese genel bir state gönderip, client tarafında kim olduğunu ayırt etmesini sağla
        # generic_state = build_game_state(game, None) # 'your_player_id' olmadan
        # socketio.emit('game_update', generic_state, room=game_id) # Bu daha basit olabilir client tarafında ayrıştırma yapılırsa

    except Exception as e:
        db.session.rollback()
        print(f"Oyuna katılma hatası: {e}")
        emit('game_error', {'message': 'Oyuna katılırken bir hata oluştu.'})


@socketio.on('make_guess')
def handle_make_guess(data):
    """Bir oyuncudan tahmin geldiğinde."""
    sid = request.sid
    guess = data.get('guess')

    # Tahmini doğrula
    if not guess or len(guess) != 3 or not guess.isdigit() or len(set(guess)) != 3:
         emit('game_error', {'message': 'Geçersiz tahmin formatı (3 farklı rakam olmalı).'})
         return

    # Oyuncunun oyununu bul
    # Bu sorgu optimize edilebilir (örn: oyuncu SID'lerini ayrı bir tabloda oyun ID'si ile tutmak)
    game = MultiplayerGame.query.filter(
        (MultiplayerGame.player1_sid == sid) | (MultiplayerGame.player2_sid == sid)
    ).filter(MultiplayerGame.status == 'active').first()

    if not game:
        emit('game_error', {'message': 'Aktif oyununuz bulunamadı veya oyun bitmiş.'})
        return

    if game.current_turn_sid != sid:
        emit('game_error', {'message': 'Sıra sizde değil!'})
        return

    # Rakibin sırrını al
    opponent_secret = game.get_opponent_secret(sid)
    result = check_guess(opponent_secret, guess)

    if result is None: # check_guess içinde bir hata olduysa
         emit('game_error', {'message': 'Tahmin kontrol edilirken bir sorun oluştu.'})
         return

    # Tahmini kaydet
    game.add_guess(sid, guess, result)

    # Kazanma durumu kontrolü
    if result['plus'] == 3:
        game.status = 'finished'
        game.winner_sid = sid
        game.current_turn_sid = None # Oyun bitti, sıra kimsede değil
        print(f"Oyun {game.id} bitti. Kazanan: {sid}")
    else:
        # Sırayı rakibe geçir
        game.current_turn_sid = game.get_opponent_sid(sid)

    try:
        db.session.commit()
        # Oyun durumunu her iki oyuncuya da gönder
        player1_state = build_game_state(game, game.player1_sid)
        player2_state = build_game_state(game, game.player2_sid)

        # Özel mesajlarla gönderim
        if game.player1_sid:
             socketio.emit('game_update', player1_state, room=game.player1_sid)
        if game.player2_sid:
             socketio.emit('game_update', player2_state, room=game.player2_sid)

        # Veya odaya genel gönderim (client tarafında ayrıştırma ile)
        # socketio.emit('game_update', build_game_state(game, None), room=game.id)

    except Exception as e:
        db.session.rollback()
        print(f"Tahmin işleme hatası: {e}")
        emit('game_error', {'message': 'Tahmininiz işlenirken bir hata oluştu.'})


# --- Veritabanı ve Çalıştırma ---
with app.app_context():
    db.create_all() # Tabloları oluştur/kontrol et

if __name__ == '__main__':
    print("Sunucu başlatılıyor...")
    # Gunicorn yerine lokal geliştirme için:
    # host='0.0.0.0' ile ağdaki diğer cihazlardan erişim sağlanabilir
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
    # Render için Start Command: gunicorn --worker-class eventlet -w 1 app:socketio
