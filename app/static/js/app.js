/*
 * app.js — comportamentos leves do front-end da AWS Database Lab Store.
 *
 * Mantido propositalmente simples (JavaScript "vanilla", sem framework),
 * porque o foco do laboratório é a arquitetura de banco de dados.
 */

(function () {
  "use strict";

  // Some com os avisos (flash) automaticamente após alguns segundos.
  document.addEventListener("DOMContentLoaded", function () {
    var avisos = document.querySelectorAll(".aviso");
    avisos.forEach(function (aviso) {
      window.setTimeout(function () {
        aviso.style.transition = "opacity 0.4s ease";
        aviso.style.opacity = "0";
        window.setTimeout(function () {
          if (aviso.parentNode) {
            aviso.parentNode.removeChild(aviso);
          }
        }, 400);
      }, 4000);
    });

    // Confirmação simples ao esvaziar o carrinho, evitando cliques acidentais.
    var formsLimpar = document.querySelectorAll('form[action$="/carrinho/limpar"]');
    formsLimpar.forEach(function (form) {
      form.addEventListener("submit", function (evento) {
        if (!window.confirm("Deseja realmente esvaziar o carrinho?")) {
          evento.preventDefault();
        }
      });
    });
  });
})();
