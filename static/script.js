// Socket.IO client kütüphanesini HTML'e eklediğinizi varsayıyoruz:
// <script src="https://cdn.socket.io/4.6.0/socket.io.min.js"></script>

// --- DOM Elementleri ---
// Oyun Kurma/Katılma Alanı
const setupArea = document.getElementById('setup-area'); // Bu ID'li bir div olduğunu varsayalım
const createGameButton = document.getElementById('create-game-button');
const joinGameButton = document.getElementById('join-game-button');
const secretInput = document.getElementById('secret-input'); // Gizli sayıyı girmek için
const gameIdInput = document.getElementById('game-id-input'); // Oyun ID'sini girmek için
const gameIdDisplay = document.getElementById('game-id-display'); // Oluşturulan oyun ID'sini göstermek için

// Oyun Alanı
const gameArea = document.getElementById('game-area'); // Ana oyun alanı div'i
const guessInput = document.getElementById('guess-input');
const guessButton = document.getElementById('guess-button');
const turnIndicator = document.getElementById('turn-indicator'); // Sıranın kimde olduğunu gösterir

// Mesaj ve Geçmiş Alanları
const messageArea = document.getElementById('message-area');
const myGuessesList = document.getElementById('my-guesses-list');     // Kendi tahminlerim
const opponentGuessesList = document.getElementById('opponent-guesses-list'); // Rakibin tahminleri
const opponentSecretLabel = document.getElementById('opponent-secret-label'); // Rakibin gizli sayısını oyun sonunda göstermek için

// --- Global Durum Değişkenleri ---
let socket = null;
let currentGameId = null;
let myPlayerId = null; // 'player1' veya 'player2' gibi bir tanımlayıcı (sunucu tarafından atanacak)
let currentTurnSid = null; // Sırası gelen oyuncunun SID'si (sunucudan gelecek)
let mySid = null; // Kendi SID'im (bağlantı kurulunca alınacak)
let gameStatus = 'setup'; // setup, waiting, active, finished

// --- Yardımcı Fonksiyonlar ---
function showArea(areaToShow) {
    setupArea.style.display = 'none';
    gameArea.style.display = 'none';
    if (areaToShow === 'setup') {
        setupArea.style.display = 'block';
    } else if (areaToShow === 'game') {
        gameArea.style.display = 'block';
    }
}

function updateGameUI(gameState) {
    console.log("Oyun durumu güncelleniyor:", gameState); // Gelen veriyi kontrol et

    currentGameId = gameState.game_id;
    myPlayerId = gameState.your_player_id; // Sunucu, SID'mize göre bize 'player1' veya 'player2' atamalı
    currentTurnSid = gameState.current_turn_sid;
    gameStatus = gameState.status;
    mySid = socket.id; // Güncel SID'mizi alalım

    // Oyun ID'sini (varsa) göster
    if (gameIdDisplay && currentGameId) {
         gameIdDisplay.textContent = `Oyun ID: ${currentGameId} (Paylaşın)`;
         gameIdDisplay.style.display = 'block';
    }

    // Alanları göster/gizle
    if (gameStatus === 'waiting') {
        showArea('setup'); // Hala kurulum ekranında, rakip bekleniyor
        messageArea.textContent = "Rakip bekleniyor...";
        disableSetupInputs(true); // Rakip beklenirken girişleri kapa
    } else if (gameStatus === 'active' || gameStatus === 'finished') {
        showArea('game');
        updateTurnIndicator();
        renderGuessList(myGuessesList, gameState.guesses[myPlayerId] || []); // Kendi tahminlerim
        const opponentPlayerId = myPlayerId === 'player1' ? 'player2' : 'player1';
        renderGuessList(opponentGuessesList, gameState.guesses[opponentPlayerId] || []); // Rakibin tahminleri

        if (gameStatus === 'finished') {
            messageArea.textContent = gameState.winner_sid === mySid ? "Tebrikler, KAZANDINIZ!" : "Kaybettiniz.";
            if (gameState.opponent_secret && opponentSecretLabel) {
                opponentSecretLabel.textContent = `Rakibin Gizli Sayısı: ${gameState.opponent_secret}`;
                opponentSecretLabel.style.display = 'block';
            }
            setGuessingEnabled(false); // Oyun bitince tahmin kapat
        } else {
             // Aktif oyunda mesajı temizle veya sıra mesajı göster
             messageArea.textContent = currentTurnSid === mySid ? "Sıra sizde!" : "Rakibin sırası bekleniyor...";
             setGuessingEnabled(currentTurnSid === mySid); // Sıra bizdeyse tahmin aç
        }
    } else {
         showArea('setup'); // Varsayılan olarak kurulum ekranı
    }
}

function updateTurnIndicator() {
    if (!turnIndicator) return;
    if (gameStatus === 'active') {
        turnIndicator.textContent = currentTurnSid === mySid ? "Sıra Sizde" : "Rakibin Sırası";
        turnIndicator.style.fontWeight = currentTurnSid === mySid ? 'bold' : 'normal';
    } else if (gameStatus === 'waiting') {
        turnIndicator.textContent = "Rakip Bekleniyor";
        turnIndicator.style.fontWeight = 'normal';
    } else if (gameStatus === 'finished') {
         turnIndicator.textContent = "Oyun Bitti";
         turnIndicator.style.fontWeight = 'bold';
    } else {
         turnIndicator.textContent = "";
    }
}


function renderGuessList(listElement, guesses) {
    if (!listElement) return;
    listElement.innerHTML = ''; // Listeyi temizle
    guesses.forEach((item, index) => {
        const listItem = document.createElement('li');
        listItem.textContent = `Deneme ${index + 1}: ${item.guess} -> +${item.result.plus} / -${item.result.minus}`;
        listElement.appendChild(listItem);
    });
    // Kaydırma çubuğunu en alta indir (yeni tahminleri görmek için)
    listElement.scrollTop = listElement.scrollHeight;
}

function setGuessingEnabled(enabled) {
    guessInput.disabled = !enabled;
    guessButton.disabled = !enabled;
}

function disableSetupInputs(disabled) {
    secretInput.disabled = disabled;
    gameIdInput.disabled = disabled;
    createGameButton.disabled = disabled;
    joinGameButton.disabled = disabled;
}

function validateSecret(secret) {
    if (!/^\d{3}$/.test(secret)) {
        messageArea.textContent = 'Gizli sayı 3 rakam olmalı.';
        return false;
    }
    if (new Set(secret).size !== 3) {
         messageArea.textContent = 'Gizli sayının rakamları farklı olmalı.';
         return false;
    }
    return true;
}

// --- Socket.IO Olayları ---
function setupSocketListeners() {
    if (!socket) return;

    socket.on('connect', () => {
        console.log('Sunucuya bağlandı. SID:', socket.id);
        mySid = socket.id; // Kendi SID'mizi sakla
        // Belki başlangıçta setup alanını göster
        showArea('setup');
        messageArea.textContent = "Oyun kurun veya bir oyuna katılın.";
        disableSetupInputs(false); // Başlangıçta girişler aktif
        if(gameIdDisplay) gameIdDisplay.style.display = 'none'; // Başta oyun ID'sini gizle
        if(opponentSecretLabel) opponentSecretLabel.style.display = 'none'; // Başta rakip sırrını gizle
    });

    socket.on('disconnect', (reason) => {
        console.log('Bağlantı kesildi:', reason);
        messageArea.textContent = 'Sunucu bağlantısı kesildi. Sayfayı yenileyin.';
        showArea('setup'); // Bağlantı kopunca setup'a dön
        gameStatus = 'setup';
        disableSetupInputs(true); // Bağlantı yokken girişleri kapa
    });

    // Sunucudan gelen hata mesajları
    socket.on('game_error', (data) => {
        console.error('Oyun Hatası:', data.message);
        messageArea.textContent = `Hata: ${data.message}`;
        // Hata durumuna göre UI'ı belki sıfırlamak veya butonları aktif etmek gerekebilir
        if (gameStatus === 'setup' || gameStatus === 'waiting') {
             disableSetupInputs(false); // Kurulumda hata olursa tekrar denemek için aç
        }
        if (gameStatus === 'active') {
             setGuessingEnabled(currentTurnSid === mySid); // Aktif oyunda tahmin butonunu sıraya göre tekrar ayarla
        }
    });

    // Oyun başarıyla kuruldu, ID geldi
    socket.on('game_created', (data) => {
        console.log('Oyun kuruldu:', data);
        currentGameId = data.game_id;
        myPlayerId = 'player1'; // Oyunu kuran kişi player1 olur (sunucu da böyle varsaymalı)
        gameStatus = 'waiting';
        updateGameUI({ // Geçici bir durumla UI'ı güncelle
            game_id: currentGameId,
            your_player_id: myPlayerId,
            current_turn_sid: null,
            status: gameStatus,
            guesses: { player1: [], player2: [] } // Başlangıçta boş
        });
        messageArea.textContent = "Oyun kuruldu. Rakip bekleniyor...";
        if (gameIdDisplay) {
             gameIdDisplay.textContent = `Oyun ID: ${currentGameId} (Bu ID'yi rakibinize verin)`;
             gameIdDisplay.style.display = 'block';
        }
        disableSetupInputs(true); // Rakip beklenirken girişler kapalı
    });

     // Oyun bulundu/başladı veya bir tahmin yapıldıktan sonraki durum
    socket.on('game_update', (gameState) => {
        updateGameUI(gameState);
    });

}


// --- Buton Olay Dinleyicileri ---
createGameButton.addEventListener('click', () => {
    const secret = secretInput.value.trim();
    if (!validateSecret(secret)) {
        return;
    }
    if (socket) {
        console.log("create_game olayı gönderiliyor...");
        socket.emit('create_game', { secret: secret });
        messageArea.textContent = "Oyun kuruluyor...";
        disableSetupInputs(true); // İstek gönderilirken girişleri kapa
    } else {
        messageArea.textContent = "Sunucuya bağlı değilsiniz.";
    }
});

joinGameButton.addEventListener('click', () => {
    const secret = secretInput.value.trim();
    const gameId = gameIdInput.value.trim();
    if (!validateSecret(secret)) {
        return;
    }
    if (!gameId) {
        messageArea.textContent = 'Lütfen katılmak için bir Oyun ID girin.';
        return;
    }

    if (socket) {
         console.log("join_game olayı gönderiliyor...");
        socket.emit('join_game', { game_id: gameId, secret: secret });
        messageArea.textContent = "Oyuna katılım isteği gönderiliyor...";
        disableSetupInputs(true); // İstek gönderilirken girişleri kapa
    } else {
        messageArea.textContent = "Sunucuya bağlı değilsiniz.";
    }
});

guessButton.addEventListener('click', () => {
    const guess = guessInput.value.trim();

    // Girdi kontrolü
    if (!/^\d{3}$/.test(guess)) {
        messageArea.textContent = 'Lütfen 3 rakam giriniz.';
        return;
    }
    // Rakam tekrarlılığı kontrolü (isteğe bağlı, sunucu da yapmalı)
    if (new Set(guess).size !== 3) {
        messageArea.textContent = 'Tahmindeki rakamlar farklı olmalı.';
        return;
    }

    if (socket && currentGameId && gameStatus === 'active' && currentTurnSid === mySid) {
         console.log("make_guess olayı gönderiliyor...");
        socket.emit('make_guess', { guess: guess }); // Sunucu hangi oyunda olduğumuzu SID'den bilir
        messageArea.textContent = "Tahmin gönderiliyor...";
        setGuessingEnabled(false); // Tahmin gönderilirken butonu kapa
        guessInput.value = ''; // Giriş alanını temizle
    } else if (currentTurnSid !== mySid) {
         messageArea.textContent = "Sıra sizde değil!";
    } else {
         messageArea.textContent = "Tahmin göndermek için aktif bir oyun olmalı ve sıra sizde olmalı.";
    }
});

// Enter tuşu ile tahmin gönderme (Oyun alanında aktif)
guessInput.addEventListener('keypress', function(event) {
    if (event.key === 'Enter' && !guessButton.disabled) {
        event.preventDefault();
        guessButton.click(); // Tahmin et butonuna tıkla
    }
});


// --- Başlangıç ---
document.addEventListener('DOMContentLoaded', () => {
    // Socket.IO bağlantısını başlat
    // Flask-SocketIO varsayılan olarak aynı host/port üzerinden '/socket.io' path'inde çalışır
    // Eğer farklı bir adres/port kullanıyorsanız io('http://adresiniz:portunuz') şeklinde belirtin
    try {
        socket = io(); // Bağlantıyı kurmayı dene
        setupSocketListeners(); // Olay dinleyicilerini ayarla
        showArea('setup'); // Başlangıçta kurulum alanını göster
        setGuessingEnabled(false); // Başlangıçta tahmin kapalı
        disableSetupInputs(false); // Başlangıçta setup girişleri açık
        if(opponentSecretLabel) opponentSecretLabel.style.display = 'none';
    } catch (e) {
        console.error("Socket.IO bağlantısı kurulamadı:", e);
        messageArea.textContent = "Oyun sunucusuna bağlanılamadı. Sayfayı yenileyin veya sunucunun çalıştığından emin olun.";
        disableSetupInputs(true);
    }
});
