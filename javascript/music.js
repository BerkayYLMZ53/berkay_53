
document.addEventListener("DOMContentLoaded", () => {
  const linkler = document.querySelectorAll(".sesli-link");

  linkler.forEach(link => {
    link.addEventListener("click", function (e) {
      e.preventDefault();

      const hedefURL = this.href;

      let sesYolu = 'img/click.wav';
      if (window.location.pathname.includes('/pages/')) {
        sesYolu = '../img/click.wav';
      }

      const ses = new Audio(sesYolu);

      ses.play().then(() => {
        setTimeout(() => {
          window.location.href = hedefURL;
        }, 200);
      }).catch(err => {
        console.error("Ses çalma hatası:", err);
        window.location.href = hedefURL;
      });
    });
  });
});
