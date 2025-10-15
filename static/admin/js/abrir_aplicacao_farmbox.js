document.addEventListener('DOMContentLoaded', function () {
    const appData = document.getElementById("app-data");

    function formatarNumeroBR(valor) {
        return valor.toLocaleString('pt-BR', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }

    // function obterAreaTotal() {
    //     const inputTotal = document.getElementById("total-area-display");
    //     if (!inputTotal) return 0;
    //     let val = inputTotal.value.replace(' ha', '').replace(/\./g, '').replace(',', '.');
    //     let numero = parseFloat(val);
    //     return isNaN(numero) ? 0 : numero;
    // }

    function obterAreaTotal() {
        let total = 0;
        document.querySelectorAll(".area-input").forEach(input => {
            const val = parseFloat(input.value.replace(',', '.'));
            if (!isNaN(val)) {
                total += val;
            }
        });
        return total;
    }

    function calcularAreaTotal() {
        const total = obterAreaTotal(); // usar mesma lógica
        const inputTotal = document.getElementById("total-area-display");
        if (inputTotal) inputTotal.value = formatarNumeroBR(total) + " Há";
        return total;
    }

    // function calcularAreaTotal() {
    //     const areas = document.querySelectorAll(".area-input");
    //     let total = 0;
    //     areas.forEach(input => {
    //         const val = parseFloat(input.value);
    //         if (!isNaN(val)) {
    //             total += val;
    //         }
    //     });
    //     const inputTotal = document.getElementById("total-area-display");
    //     if (inputTotal) inputTotal.value = formatarNumeroBR(total) + " Há";
    //     return total;
    // }

    function getUnidadeFormatada(unidadeRaw) {
        if (!unidadeRaw) return "";
        switch (unidadeRaw) {
            case "un_ha":
                return " - Un/Há";
            case "kg":
            case "kg_ha":
                return " - Kg/Há";
            case "lts":
            case "lt":
            case "L":
            case "l_ha":
                return " - L/Há";
            default:
                return unidadeRaw;  // fallback
        }
    }

    function atualizarDoseResultados() {
        const areaTotal = obterAreaTotal();
        const grupos = document.querySelectorAll("#defensivos-container .defensivo-group");

        grupos.forEach(grupo => {
            const inputDose = grupo.querySelector("input[name='dosage_value']");
            const divResultado = grupo.querySelector(".dose-result");
            const select = grupo.querySelector("select[name='input_id']");
            const selectedOption = select.selectedOptions[0];
            const unidadeRaw = selectedOption?.dataset?.unidade;
            const unidadeFormatada = getUnidadeFormatada(unidadeRaw);

            let dose = parseFloat(inputDose.value);
            if (isNaN(dose) || dose <= 0 || areaTotal <= 0) {
                divResultado.textContent = "0,00";
            } else {
                let resultado = dose * areaTotal;
                divResultado.textContent = `${formatarNumeroBR(resultado)} ${unidadeFormatada}`;
            }
        });
    }

    function atualizarEstadoBotoesRemoverPlantio() {
        const plantios = document.querySelectorAll('.plantio-wrapper');
        const botoesRemover = document.querySelectorAll('.remove-plantio-btn');

        if (plantios.length <= 1) {
            botoesRemover.forEach(btn => {
                btn.disabled = true;
                btn.title = "Deve ter pelo menos 1 plantio para abrir aplicação";
            });
        } else {
            botoesRemover.forEach(btn => {
                btn.disabled = false;
                btn.title = "";
            });
        }
    }

    function atualizarEstadoBotoesRemoverDefensivo() {
        const container = document.getElementById("defensivos-container");
        const botoesRemover = container.querySelectorAll('.remove-defensivo-btn');
        if (container.children.length <= 1) {
            botoesRemover.forEach(btn => {
                btn.disabled = true;
                btn.title = "Deve ter pelo menos 1 defensivo.";
            });
        } else {
            botoesRemover.forEach(btn => {
                btn.disabled = false;
                btn.title = "";
            });
        }
    }

    function removerPlantio(botao) {
        const wrapper = botao.closest('.plantio-wrapper');
        if (wrapper) {
            wrapper.remove();
            calcularAreaTotal();
            atualizarEstadoBotoesRemoverPlantio();
            atualizarDoseResultados();  // ← adicione aqui
        }
    }

    function duplicarLinha(botao) {
        const container = document.getElementById("defensivos-container");
        const linhaAtual = botao.closest(".defensivo-group");
        const novaLinha = linhaAtual.cloneNode(true);

        const novoSelect = novaLinha.querySelector("select");
        const novoInputDose = novaLinha.querySelector("input[name='dosage_value']");
        const divResultado = novaLinha.querySelector(".dose-result");

        // Limpa os campos
        novoSelect.selectedIndex = 0;
        novoInputDose.value = "";
        if (divResultado) divResultado.textContent = "0,00";

        container.appendChild(novaLinha);

        // Foca no novo select de defensivo
        novoSelect.focus();

        verificaDefensivosSelecionados();
        atualizarDoseResultados();

        const novoBtnRemover = novaLinha.querySelector('.remove-defensivo-btn');
        novoBtnRemover.disabled = false;     // o clone herda "disabled"; reabilite aqui
        novoBtnRemover.title = "";           // limpa o tooltip

        atualizarEstadoBotoesRemoverDefensivo(); // reavalia estado após adicionar linha
    }

    function removerLinha(botao) {
        const container = document.getElementById("defensivos-container");
        const linha = botao.closest(".defensivo-group");

        if (container.children.length > 1) {
            container.removeChild(linha);
            verificaDefensivosSelecionados();
            atualizarDoseResultados();
            atualizarEstadoBotoesRemoverDefensivo();
        } else {
            alert("Você deve manter pelo menos um defensivo.");
        }
    }

    function verificaDefensivosSelecionados() {
        const selects = document.querySelectorAll("#defensivos-container select[name='input_id']");
        let algumSelecionado = false;
        selects.forEach(select => {
            if (select.value.trim() !== '') {
                algumSelecionado = true;
            }
        });
        const btnSubmit = document.getElementById("btn-submit");
        if (btnSubmit) btnSubmit.disabled = !algumSelecionado;
    }

    // Evento para inputs dosagem
    document.getElementById("defensivos-container").addEventListener("input", function (event) {
        if (event.target.matches("input[name='dosage_value']")) {
            atualizarDoseResultados();
        }
    });

    // Evento para selects defensivo
    document.getElementById("defensivos-container").addEventListener("change", function (event) {
        if (event.target.matches("select[name='input_id']")) {
            verificaDefensivosSelecionados();
        }
    });

    // Evento para inputs área
    document.querySelectorAll(".area-input").forEach(input => {
        input.addEventListener("input", () => {
            calcularAreaTotal();
            atualizarDoseResultados();
        });
    });

    // Evento global para remover plantio (delegação)
    document.addEventListener('click', function (e) {
        if (e.target && e.target.classList.contains('remove-plantio-btn')) {
            const plantioCard = e.target.closest('.plantio-wrapper');
            if (plantioCard) {
                plantioCard.remove();
                calcularAreaTotal();
                atualizarEstadoBotoesRemoverPlantio();
            }
        }
    });

    function enviarAplicacao() {
        const btn = document.getElementById("btn-submit");
        const originalText = btn.innerHTML;

        btn.disabled = true;
        btn.innerHTML =
            `<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span> Enviando...`;

        const inputs = [];
        const defensivoGroups = document.querySelectorAll(".defensivo-group");
        const areaInputs = document.querySelectorAll("input[name='sought_area']");
        const plantations = [];

        areaInputs.forEach(input => {
            const plantation_id = parseInt(input.dataset.plantationId.replace(/\./g, ''), 10);
            const sought_area = parseFloat(input.value);
            if (!isNaN(sought_area)) {
                plantations.push({
                    plantation_id: plantation_id,
                    sought_area: sought_area
                });
            }
        });

        defensivoGroups.forEach(group => {
            const defensivoId = group.querySelector("select[name='input_id']").value;
            const dose = group.querySelector("input[name='dosage_value']").value;

            if (defensivoId && dose) {
                const selectedOption = group.querySelector("select[name='input_id']").selectedOptions[0];
                const unidade = selectedOption?.dataset?.unidade;
                const parsedDose = parseFloat(dose);

                inputs.push({
                    input_id: parseInt(defensivoId.replace(/\./g, ''), 10),
                    dosage_value: parsedDose,
                    dosage_unity: unidade || null,
                });
            }
        });

        const payload = {
            date: new Date().toISOString().slice(0, 10),
            end_date: new Date(Date.now() + 6 * 86400000).toISOString().slice(0, 10),
            harvest_id: parseInt(String(appData.dataset.harvestId).replace('.', '')),
            farm_id: parseInt(String(appData.dataset.farmId).replace('.', '')),
            responsible_id: parseInt(String(appData.dataset.responseId).replace('.', '')),
            charge_id: parseInt(String(appData.dataset.chargeId).replace('.', '')),
            plantations: plantations,
            inputs: inputs,
            observations: "Aplicação Aberta via Django-Admin"
        };

        console.log('payload: ', payload)

        fetch("/diamante/plantio/open_app_farmbox/", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Token ${appData.dataset.token}`
            },
            body: JSON.stringify({ data: payload })
        })
            .then(async response => {
                const data = await response.json();
                if (!response.ok) {
                    console.log('data error: ', data)
                    throw new Error(data?.msg || "Erro desconhecido ao enviar aplicação.");
                }

                let code = "";
                if (data?.result) {
                    try {
                        const parsed = JSON.parse(data.result);
                        code = parsed.code || "";
                    } catch (err) {
                        console.warn("Erro ao parsear result:", err);
                    }
                }
                Swal.fire({
                    icon: "success",
                    title: "Aplicação criada!",
                    html: data.msg
                        ? `${data.msg}<br><b>${code}</b>`
                        : `<b>${code}</b>`,
                    confirmButtonText: "OK"
                }).then(() => {
                    window.location.href = document.referrer;
                });
            })
            .catch(err => {
                Swal.fire({
                    icon: "error",
                    title: "Erro!",
                    text: err.message || "Erro ao enviar aplicação."
                });
                btn.disabled = false;
                btn.innerHTML = originalText;
            });
    }


    // Inicializações
    calcularAreaTotal();
    verificaDefensivosSelecionados();
    atualizarEstadoBotoesRemoverPlantio();
    atualizarEstadoBotoesRemoverDefensivo();
    atualizarDoseResultados();

    // Expor funções para chamadas inline
    window.removerPlantio = removerPlantio;
    window.duplicarLinha = duplicarLinha;
    window.removerLinha = removerLinha;
    window.calcularAreaTotal = calcularAreaTotal;
    window.enviarAplicacao = enviarAplicacao;
});