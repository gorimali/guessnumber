const guessInput = document.getElementById('guess-input');
const guessButton = document.getElementById('guess-button');
const newGameButton = document.getElementById('new-game-button');
const messageArea = document.getElementById('message-area');
const guessesList = document.getElementById('guesses-list');

let currentGameId = null;

// --- API İstek Fonksiyonları ---
async function startGame() {
    try {
        const response = await fetch('/api/games', { method: 'POST' });
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        currentGameId = data.game_id;
        // Arayüzü temizle
        messageArea.textContent = 'Yeni oyun başladı. Tahmininizi girin.';
        guessesList.innerHTML = '';
        guessInput.value = '';
        guessInput.disabled = false;
        guessButton.disabled = false;
        console.log("Yeni oyun ID:", currentGameId); // Debug
    } catch (error) {
        messageArea.textContent = 'Hata: Yeni oyun başlatılamadı. Lütfen sayfayı yenileyin.';
        console.error('Yeni oyun hatası:', error);
    }
}

async function submitGuess() {
    const guess = guessInput.value.trim();

    // Girdi kontrolü
    if (!/^\d{3}$/.test(guess)) {
        messageArea.textContent = 'Lütfen 3 rakam giriniz.';
        return;
    }
    // --- Rakam Tekrarlılığı Kontrolü (Frontend - İsteğe Bağlı) ---
    // if (new Set(guess).size !== 3) {
    //     messageArea.textContent = 'Rakamlar farklı olmalıdır.';
    //     return;
    // }

    if (!currentGameId) {
        messageArea.textContent = 'Önce yeni bir oyun başlatmalısınız.';
        return;
    }

    guessButton.disabled = true; // İstek sırasında butonu pasif yap

    try {
        const response = await fetch(`/api/games/${currentGameId}/guess`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ guess: guess }),
        });

        const data = await response.json();

        if (!response.ok) {
            // Sunucudan gelen hata mesajını göster
            messageArea.textContent = `Hata: ${data.error || response.statusText}`;
            guessButton.disabled = false; // Hata durumunda butonu tekrar aktif et
            return;
        }

        // Başarılı tahmin, arayüzü güncelle
        messageArea.textContent = data.message; // Sunucudan gelen mesajı göster

        // Tahmini listeye ekle
        const listItem = document.createElement('li');
        listItem.textContent = `Deneme ${data.attempts}: ${data.guess} -> +${data.result.plus} / -${data.result.minus}`;
        // guessesList.appendChild(listItem); // Listenin sonuna ekler
        guessesList.insertBefore(listItem, guessesList.firstChild); // Listenin başına ekler

        guessInput.value = ''; // Giriş alanını temizle

        if (data.is_won) {
            messageArea.textContent += " Oyunu kazandınız!";
            guessInput.disabled = true;
            guessButton.disabled = true;
        } else {
             guessButton.disabled = false; // Yeni tahmin için butonu aktif et
        }

    } catch (error) {
        messageArea.textContent = 'Tahmin gönderilirken bir hata oluştu.';
        console.error('Tahmin hatası:', error);
        guessButton.disabled = false; // Hata durumunda butonu aktif et
    }
}

// --- Olay Dinleyicileri ---
guessButton.addEventListener('click', submitGuess);
newGameButton.addEventListener('click', startGame);

// Enter tuşu ile tahmin gönderme
guessInput.addEventListener('keypress', function(event) {
    if (event.key === 'Enter') {
        event.preventDefault(); // Form gönderimini engelle (varsa)
        submitGuess();
    }
});


// --- Sayfa Yüklendiğinde ---
document.addEventListener('DOMContentLoaded', () => {
    startGame(); // Sayfa yüklenince otomatik olarak yeni oyun başlat
});
