document.addEventListener("DOMContentLoaded", function () {
  // Los avisos ya NO se borran solos.
  //
  // Antes desaparecían a los 6 segundos. Con una importación que tarda cerca
  // de un minuto, para cuando la persona volvía a mirar la pantalla el aviso
  // ya no estaba: quedaba sin saber si el archivo se cargó bien o falló.
  // Ahora se quedan hasta que se cierran con la X o hasta cambiar de página,
  // que además es lo que corresponde para un error: no debería poder pasar
  // inadvertido.

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
    // Ojo: el 0 es un valor válido, así que no se puede usar "valor || ''".
    var texto = valor === null || valor === undefined ? "" : valor.toString();
    var digitos = texto.replace(/[^0-9-]/g, "");
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

  // Sumas en vivo del Costeo (Documentos y Gastos internos): se recalculan
  // mientras se escribe, sin esperar a "Guardar todo".
  function parseNumeroLibre(valor) {
    var texto = (valor || "").toString().trim().replace(/[^0-9.,-]/g, "");
    if (!texto) return 0;
    var numero = parseFloat(texto.replace(",", "."));
    return isNaN(numero) ? 0 : numero;
  }
  function parseEnteroCLP(valor) {
    var digitos = (valor || "").toString().replace(/[^0-9-]/g, "");
    var numero = parseInt(digitos, 10);
    return isNaN(numero) ? 0 : numero;
  }

  function pintar(id, valor) {
    var celda = document.getElementById(id);
    if (celda) celda.textContent = formatearCLP(valor);
  }

  function sumaCIF() {
    var total = 0;
    // El Ad Valorem también es una línea de documentos, pero queda fuera del
    // CIF (en la planilla va bajo la fila TOTAL CIF), así que no se suma acá.
    document.querySelectorAll('[id^="doc-clp-"]:not([data-fuera-cif])').forEach(function (celda) {
      total += parseEnteroCLP(celda.textContent);
    });
    return total;
  }

  function sumaAdValorem() {
    var total = 0;
    document.querySelectorAll('[id^="doc-clp-"][data-fuera-cif]').forEach(function (celda) {
      total += parseEnteroCLP(celda.textContent);
    });
    return total;
  }

  function sumaGastosInternos() {
    var total = 0;
    document.querySelectorAll(".gasto-valor-clp").forEach(function (campo) {
      total += parseEnteroCLP(campo.value);
    });
    return total;
  }

  function actualizarTotales() {
    var cif = sumaCIF();
    var gastos = sumaGastosInternos();
    var costoTotal = cif + sumaAdValorem() + gastos;
    pintar("total-cif", cif);
    pintar("total-gastos-internos", gastos);
    pintar("kpi-cif", cif);
    pintar("kpi-gastos-internos", gastos);
    pintar("kpi-costo-total", costoTotal);
    pintar("total-costo", costoTotal);
  }

  document.querySelectorAll(".doc-tc, .doc-total").forEach(function (campo) {
    campo.addEventListener("input", function () {
      var docId = campo.getAttribute("data-doc-id");
      var tcInput = document.querySelector('.doc-tc[data-doc-id="' + docId + '"]');
      var totalInput = document.querySelector('.doc-total[data-doc-id="' + docId + '"]');
      var celda = document.getElementById("doc-clp-" + docId);
      if (!tcInput || !totalInput || !celda) return;
      var clp = Math.round(parseNumeroLibre(tcInput.value) * parseNumeroLibre(totalInput.value));
      celda.textContent = formatearCLP(clp);
      actualizarTotales();
    });
  });

  document.querySelectorAll(".gasto-valor-clp").forEach(function (campo) {
    campo.addEventListener("input", actualizarTotales);
  });
  // Campos del Costeo sin llenar: se pintan de rojo mientras no tengan dato,
  // y vuelven al amarillo apenas se escribe algo. Un 0 cuenta como "sin
  // llenar", porque en estas planillas significa que todavía no se cargó.
  function estaVacio(campo) {
    var valor = (campo.value || "").trim();
    if (campo.tagName === "SELECT") return valor === "";
    if (valor === "") return true;
    var esNumerico =
      campo.inputMode === "decimal" ||
      campo.inputMode === "numeric" ||
      campo.classList.contains("campo-clp");
    if (!esNumerico) return false;
    var numero = parseFloat(valor.replace(/[^0-9.,-]/g, "").replace(/\.(?=.*[.,])/g, "").replace(",", "."));
    return !isNaN(numero) && numero === 0;
  }

  function marcarVacios(campos) {
    campos.forEach(function (campo) {
      if (campo.disabled) return;
      campo.classList.toggle("esta-vacio", estaVacio(campo));
    });
  }

  var camposExcel = Array.prototype.slice.call(document.querySelectorAll(".campo-excel"));
  if (camposExcel.length) {
    marcarVacios(camposExcel);
    camposExcel.forEach(function (campo) {
      campo.addEventListener("input", function () { marcarVacios([campo]); });
      campo.addEventListener("change", function () { marcarVacios([campo]); });
      campo.addEventListener("blur", function () { marcarVacios([campo]); });
    });
  }
  // Provisión de Ingresos: al escribir el monto de reversa, el saldo de esa
  // misma fila se recalcula al vuelo (provisión - reversa) y se marca en verde
  // cuando llega a $0, que es cuando la provisión queda reversada por completo.
  document.querySelectorAll(".campo-monto-reversa").forEach(function (campo) {
    function refrescarSaldo() {
      var id = campo.getAttribute("data-linea");
      var celda = document.getElementById("saldo-" + id);
      if (!celda) return;
      var provision = parseInt(campo.getAttribute("data-provision"), 10) || 0;
      var saldo = provision - parseEnteroCLP(campo.value);
      celda.textContent = formatearCLP(saldo);
      celda.classList.toggle("saldo-cerrado", saldo === 0);

      var estado = document.getElementById("estado-" + id);
      if (estado) {
        estado.innerHTML = saldo === 0
          ? '<span class="badge bg-success">\u{1F512} Cerrado</span>'
          : '<span class="badge bg-warning text-dark">Pendiente</span>';
      }
    }
    campo.addEventListener("input", refrescarSaldo);
    campo.addEventListener("blur", refrescarSaldo);
  });

  // Cambiar un dato que ya estaba cargado pide confirmación: llenar un campo
  // vacío no molesta, pero pisar algo escrito antes sí conviene pensarlo.
  document.querySelectorAll("[data-confirmar-cambio]").forEach(function (campo) {
    var original = campo.value;
    campo.addEventListener("change", function () {
      if (campo.value === original) return;
      if (!original.trim()) {          // estaba vacío: es carga, no cambio
        original = campo.value;
        return;
      }
      var etiqueta = campo.getAttribute("data-confirmar-cambio") || "este dato";
      var mensaje =
        "\u26A0\uFE0F Vas a cambiar " + etiqueta + ".\n\n" +
        "Antes decía: " + original + "\n" +
        "Va a quedar: " + (campo.value.trim() || "(vacío)") + "\n\n" +
        "\u00BFSeguro?";
      if (window.confirm(mensaje)) {
        original = campo.value;
      } else {
        campo.value = original;
      }
      campo.dispatchEvent(new Event("input", { bubbles: true }));
    });
  });

  // Formularios que tardan (importar una planilla de miles de filas): avisan que
  // están trabajando y bloquean el botón.
  //
  // Sin esto la página se queda quieta sin señal de nada, parece colgada y la
  // reacción natural es volver a apretar. Ese segundo envío no acelera nada:
  // procesa el mismo archivo otra vez en paralelo, deja ocupado un proceso más
  // del servidor y hace que las dos importaciones terminen más tarde.
  document.querySelectorAll("[data-boton-ocupado]").forEach(function (formulario) {
    formulario.addEventListener("submit", function () {
      var boton = formulario.querySelector('button[type="submit"]');
      if (!boton) return;
      // El submit ya se disparó; deshabilitar aquí no cancela este envío,
      // sólo impide los siguientes.
      setTimeout(function () {
        boton.disabled = true;
        boton.textContent = formulario.getAttribute("data-boton-ocupado");
      }, 0);
      var aviso = formulario.querySelector("[data-aviso-ocupado]");
      if (aviso) aviso.hidden = false;
    });
  });
});
