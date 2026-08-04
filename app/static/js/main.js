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

  // Selects de Cliente/Proveedor: se reemplazan por un campo de texto que
  // filtra las opciones por nombre o RUT a medida que se escribe. El <select>
  // original se mantiene oculto pero funcional, así el formulario se sigue
  // enviando igual.
  document.querySelectorAll("select[data-buscable]").forEach(function (select) {
    var envoltorio = document.createElement("div");
    envoltorio.className = "buscable-select";
    select.insertAdjacentElement("beforebegin", envoltorio);
    envoltorio.appendChild(select);
    select.classList.add("visually-hidden");
    select.tabIndex = -1;

    var input = document.createElement("input");
    input.type = "text";
    input.className = "form-control";
    input.autocomplete = "off";
    input.placeholder = "Escribe para buscar por nombre o RUT…";
    envoltorio.appendChild(input);

    var lista = document.createElement("div");
    lista.className = "buscable-select-lista";
    envoltorio.appendChild(lista);

    function normalizar(texto) {
      return (texto || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
    }

    function opciones() {
      return Array.prototype.slice.call(select.options).filter(function (o) { return o.value; });
    }

    function textoDeSeleccion() {
      var actual = select.options[select.selectedIndex];
      return actual && actual.value ? actual.textContent.trim() : "";
    }

    function cerrar() {
      envoltorio.classList.remove("is-open");
    }

    function pintar(filtro) {
      var termino = normalizar(filtro);
      var coincidencias = opciones().filter(function (o) {
        return normalizar(o.textContent).indexOf(termino) !== -1;
      });
      lista.innerHTML = "";
      if (!coincidencias.length) {
        var vacio = document.createElement("div");
        vacio.className = "buscable-select-vacio";
        vacio.textContent = "Sin resultados";
        lista.appendChild(vacio);
        return;
      }
      coincidencias.forEach(function (o) {
        var item = document.createElement("button");
        item.type = "button";
        item.className = "buscable-select-item" + (o.value === select.value ? " is-active" : "");
        item.textContent = o.textContent;
        item.addEventListener("mousedown", function (e) {
          e.preventDefault();
          select.value = o.value;
          select.dispatchEvent(new Event("change", { bubbles: true }));
          input.value = o.textContent.trim();
          cerrar();
        });
        lista.appendChild(item);
      });
    }

    input.value = textoDeSeleccion();
    input.addEventListener("focus", function () {
      input.select();
      pintar(input.value);
      envoltorio.classList.add("is-open");
    });
    input.addEventListener("input", function () {
      pintar(input.value);
      envoltorio.classList.add("is-open");
    });
    input.addEventListener("keydown", function (e) {
      if (e.key === "Escape") input.blur();
    });
    input.addEventListener("blur", function () {
      cerrar();
      // Si lo escrito no corresponde a ninguna opción, se restaura el nombre de la selección vigente.
      input.value = textoDeSeleccion();
    });
    document.addEventListener("click", function (e) {
      if (!envoltorio.contains(e.target)) cerrar();
    });
  });

  // Campos de plata en CLP (ej. Gastos internos del Costeo): se muestran
  // formateados con separador de miles ($1.234). Al enfocarlos se muestran
  // como número simple para editar cómodo, y se reformatean al salir.
  function formatearCLP(valor) {
    var digitos = (valor || "").toString().replace(/[^0-9-]/g, "");
    if (!digitos) return "";
    var numero = parseInt(digitos, 10);
    if (isNaN(numero)) return "";
    return "$" + numero.toLocaleString("es-CL");
  }
  document.querySelectorAll(".campo-clp").forEach(function (campo) {
    campo.addEventListener("focus", function () {
      campo.value = campo.value.replace(/[^0-9-]/g, "");
    });
    campo.addEventListener("blur", function () {
      campo.value = formatearCLP(campo.value);
    });
  });
});
