const cardContainer = document.getElementById("cardContainer");
const resultText = document.getElementById("result");
let correctIndex = 0;
let gameEnded = false;

function generateCards() {
  cardContainer.innerHTML = "";
  resultText.textContent = "";
  gameEnded = false;

  const totalCards = 6;
  correctIndex = Math.floor(Math.random() * totalCards);

  for (let i = 0; i < totalCards; i++) {
    const card = document.createElement("div");
    card.classList.add("card");
    card.textContent = i === correctIndex ? "🎉" : "❌";
    card.addEventListener("click", () => revealCard(card, i));
    cardContainer.appendChild(card);
  }
}

function revealCard(card, index) {
  if (gameEnded || card.classList.contains("revealed")) return;

  card.classList.add("revealed");
  if (index === correctIndex) {
    resultText.textContent = "Tebrikler! Doğru kartı buldun!";
  } else {
    resultText.textContent = "Yanlış kart. Tekrar dene!";
  }

  gameEnded = true;
}

function resetGame() {
  generateCards();
}

generateCards();