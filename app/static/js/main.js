document.addEventListener("DOMContentLoaded", function () {
  var alerts = document.querySelectorAll(".alert");
  alerts.forEach(function (alert) {
    setTimeout(function () {
      alert.classList.remove("show");
    }, 6000);
  });

  // Filtros escritos bajo los títulos de las tablas: se envían solos tras una
  // pausa al escribir, o al instante con Enter / al cambiar un desplegable.
  var temporizador = null;
  document.querySelectorAll("[data-autofiltro]").forEach(function (campo) {
    var formulario = campo.form || document.getElementById(campo.getAttribute("form"));
    if (!formulario) return;

    function enviar() {
      window.clearTimeout(temporizador);
      // Algunas páginas repiten un mismo filtro en dos layouts (tabla de
      // escritorio y tarjetas móviles) que apuntan al mismo formulario. Antes
      // de enviar, se deshabilitan los campos que no están visibles para que
      // no viajen duplicados ni pisen el valor del campo que el usuario sí ve.
      document.querySelectorAll('[form="' + formulario.id + '"]').forEach(function (dup) {
        dup.disabled = dup.offsetParent === null;
      });
      formulario.submit();
    }

    if (campo.tagName === "SELECT") {
      campo.addEventListener("change", enviar);
      return;
    }
    campo.addEventListener("input", function () {
      window.clearTimeout(temporizador);
      temporizador = window.setTimeout(enviar, 550);
    });
    campo.addEventListener("keydown", function (e) {
      if (e.key === "Enter") {
        e.preventDefault();
        enviar();
      }
    });
  });
});
