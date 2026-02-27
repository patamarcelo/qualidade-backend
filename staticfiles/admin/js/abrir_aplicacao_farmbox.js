document.addEventListener('DOMContentLoaded', function () {
    const appData = document.getElementById("app-data");

    const colorDict = [
        { tipo: "Acaricida", color: "rgba(221,129,83)" },
        { tipo: "Inseticida", color: "rgb(218,78,75)" },
        { tipo: "Herbicida", color: "rgb(166,166,54)" },
        { tipo: "Adjuvante", color: "rgb(136,171,172)" },
        { tipo: "Óleo", color: "rgb(120,161,144)" },
        { tipo: "Óleo Mineral/Vegetal", color: "rgb(120,161,144)" },
        { tipo: "Micronutrientes", color: "rgb(118,192,226)" },
        { tipo: "Fungicida", color: "rgb(238,165,56)" },
        { tipo: "Fertilizante", color: "rgb(76,180,211)" },
        { tipo: "Nutrição", color: "rgb(87,77,109)" },
        { tipo: "Biológico", color: "rgb(69,133,255)" },
        { tipo: "Operacão", color: "grey" }
    ];

    function iniciarSelectAvancado(elemento) {
        if (elemento.tomselect) return; 
        new TomSelect(elemento, {
            create: false,
            sortField: {
                field: "text",
                direction: "asc"
            },
            placeholder: "-- Selecione um defensivo --",
            normalize: true,
        });
    }

    function normalizeText(str) {
        return (str || "")
            .normalize("NFD")                   
            .replace(/[\u0300-\u036f]/g, "")    
            .toLowerCase()
            .trim();
    }

    function getColorByTipo(tipo) {
        const normalizedTipo = normalizeText(tipo);
        const found = colorDict.find(c => normalizeText(c.tipo) === normalizedTipo);
        return found ? found.color : "rgb(200,200,200)"; 
    }

    function atualizarTipo(selectEl) {
        const unidade = selectEl.selectedOptions[0]?.getAttribute("data-tipo") || "";
        const inputTipo = selectEl.parentElement.querySelector('input[name="tipo_defensivo"]');

        if (inputTipo) {
            inputTipo.value = unidade;
            const cor = getColorByTipo(unidade);
            inputTipo.style.backgroundColor = cor;
            inputTipo.style.color = "white"; 
            inputTipo.style.fontWeight = "600";
            inputTipo.style.textAlign = "center";
        }
    }

    function formatarNumeroBR(valor) {
        return valor.toLocaleString('pt-BR', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }

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
        const total = obterAreaTotal(); 
        const inputTotal = document.getElementById("total-area-display");
        if (inputTotal) inputTotal.value = formatarNumeroBR(total) + " Há";
        return total;
    }

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
                return unidadeRaw;  
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

            let dose = parseFloat(String(inputDose.value).replace(',', '.'));

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
            atualizarDoseResultados();
        }
    }

    function duplicarLinha(botao) {
        const container = document.getElementById("defensivos-container");
        const linhaAtual = botao.closest(".defensivo-group");
        
        // Clona a linha inteira
        const novaLinha = linhaAtual.cloneNode(true);

        // ==== LIMPEZA PROFUNDA DOS RESÍDUOS DO TOM SELECT ====
        // Remove as divs "falsas" (wrappers) criadas pelo Tom Select
        const wrappers = novaLinha.querySelectorAll(".ts-wrapper");
        wrappers.forEach(w => w.remove());

        // Pega o <select> original clonado
        const novoSelect = novaLinha.querySelector("select[name='input_id']");
        
        // Restaura todas as classes e limpa os atributos de "escondido" que o Tom Select aplicou
        novoSelect.className = "form-select form-select-sm select-busca-avancada"; 
        novoSelect.removeAttribute("hidden");
        novoSelect.removeAttribute("id"); 
        novoSelect.removeAttribute("tabindex");
        novoSelect.style.display = ""; 
        novoSelect.style.visibility = "visible";
        novoSelect.style.opacity = "1";
        if (novoSelect.tomselect) delete novoSelect.tomselect; // Apaga o rastro do objeto JS antigo
        
        // Limpa os valores
        novoSelect.value = "";
        
        const novoInputDose = novaLinha.querySelector("input[name='dosage_value']");
        if (novoInputDose) novoInputDose.value = "";
        
        const inputTipo = novaLinha.querySelector("input[name='tipo_defensivo']");
        if (inputTipo) {
            inputTipo.value = "";
            inputTipo.style.backgroundColor = ""; 
        }
        
        const divResultado = novaLinha.querySelector(".dose-result");
        if (divResultado) divResultado.textContent = "0,00";

        // Insere a linha nova limpa no container
        container.appendChild(novaLinha);

        // Reinicializa o Tom Select de forma nativa nesta nova linha limpa
        iniciarSelectAvancado(novoSelect);

        verificaDefensivosSelecionados();
        atualizarDoseResultados();

        const novoBtnRemover = novaLinha.querySelector('.remove-defensivo-btn');
        novoBtnRemover.disabled = false;
        novoBtnRemover.title = "";

        atualizarEstadoBotoesRemoverDefensivo();

        // Foca automaticamente no campo do defensivo recém criado
        setTimeout(() => {
            if (novoSelect.tomselect) {
                novoSelect.tomselect.focus();
            }
        }, 50);
    }

    function removerLinha(botao) {
        const container = document.getElementById("defensivos-container");
        const linha = botao.closest(".defensivo-group");

        if (container.children.length > 1) {
            const sel = linha.querySelector("select");
            if (sel && sel.tomselect) sel.tomselect.destroy();

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

    // Evento para selects defensivo (com foco automático na dose)
    document.getElementById("defensivos-container").addEventListener("change", function (event) {
        if (event.target.matches("select[name='input_id']")) {
            atualizarTipo(event.target);
            verificaDefensivosSelecionados();

            if (event.target.value) {
                const linha = event.target.closest('.defensivo-group');
                const doseInput = linha.querySelector("input[name='dosage_value']");
                if (doseInput) {
                    setTimeout(() => doseInput.focus(), 50);
                }
            }
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

    // =========== PARTE NOVA: Programa → Estágio → Itens ===========
    const programasRaw = document.getElementById('programas-json')?.textContent || '[]';
    const PROGRAMAS = JSON.parse(programasRaw);

    const selPrograma = document.getElementById('select-programa');
    const selEstagio = document.getElementById('select-estagio');
    const programaMeta = document.getElementById('programa-meta');

    function montarSelectPrograma() {
        [...selPrograma.options].slice(1).forEach(() => selPrograma.remove(1));
        PROGRAMAS.forEach(p => {
            const opt = document.createElement('option');
            opt.value = String(p.id);
            opt.textContent = p.nome || `Programa ${p.id}`;
            selPrograma.appendChild(opt);
        });
    }

    function onProgramaChange() {
        const id = selPrograma.value.trim();
        selEstagio.innerHTML = '<option value="">-- Selecione um estágio --</option>';
        selEstagio.disabled = true;
        programaMeta.textContent = '';

        if (!id) return;

        const prog = PROGRAMAS.find(p => String(p.id) === id);
        if (!prog) return;

        const metas = [
            prog.cultura ? `Cultura: ${prog.cultura}` : null,
            prog.safra ? `Safra: ${prog.safra}` : null,
            prog.ciclo ? `Ciclo: ${prog.ciclo}` : null,
        ].filter(Boolean).join(' • ');
        programaMeta.textContent = metas;

        prog.estagios.forEach(e => {
            const opt = document.createElement('option');
            opt.value = e.nome;
            opt.textContent = (e.ord ?? e.ord === 0) ? `${e.nome} (DAP: ${e.ord})` : e.nome;
            selEstagio.appendChild(opt);
        });

        selEstagio.disabled = prog.estagios.length === 0;
    }

    selPrograma?.addEventListener('change', onProgramaChange);
    montarSelectPrograma();

    function setSelectByValue(selectEl, value) {
        const valStr = String(value);
        let found = false;
        for (let i = 0; i < selectEl.options.length; i++) {
            if (String(selectEl.options[i].value) === valStr) {
                found = true;
                break;
            }
        }
        
        if (found) {
            if (selectEl.tomselect) {
                selectEl.tomselect.setValue(valStr);
            } else {
                selectEl.value = valStr;
            }
            return true;
        }
        return false;
    }

    function ensureRowCount(count) {
        const container = document.getElementById("defensivos-container");
        while (container.children.length < count) {
            const lastAddBtn = container.lastElementChild?.querySelector('button.btn.btn-outline-primary.btn-sm');
            if (lastAddBtn) lastAddBtn.click();
            else {
                const base = container.lastElementChild || container.querySelector('.defensivo-group');
                container.appendChild(base.cloneNode(true));
            }
        }
        while (container.children.length > count && container.children.length > 1) {
            container.lastElementChild.querySelector('.remove-defensivo-btn')?.click();
        }
    }

    function limparResultadosDasLinhas() {
        document.querySelectorAll("#defensivos-container .defensivo-group").forEach(g => {
            g.querySelector("input[name='dosage_value']").value = "";
            const res = g.querySelector(".dose-result");
            if (res) res.textContent = "0,00";
            
            const sel = g.querySelector("select[name='input_id']");
            if (sel.tomselect) {
                sel.tomselect.clear();
            } else {
                sel.selectedIndex = 0;
            }
            atualizarTipo(sel);
        });
        atualizarDoseResultados();
    }

    function onEstagioChange() {
        const progId = selPrograma.value.trim();
        const estagioNome = selEstagio.value.trim();
        if (!progId || !estagioNome) {
            limparResultadosDasLinhas();
            return;
        }

        const prog = PROGRAMAS.find(p => String(p.id) === progId);
        if (!prog) return;

        const estagio = prog.estagios.find(e => e.nome === estagioNome);
        if (!estagio) {
            limparResultadosDasLinhas();
            return;
        }

        const itens = estagio.itens || [];
        ensureRowCount(itens.length);

        const grupos = document.querySelectorAll("#defensivos-container .defensivo-group");
        const norm = s => (s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();

        const itensOrdenados = itens
            .map((it, i) => ({ ...it, __idx: i }))
            .sort((a, b) => {
                const isAOperacao = norm(a.tipo) === 'operacao';
                const isBOperacao = norm(b.tipo) === 'operacao';
                if (isAOperacao && !isBOperacao) return -1;
                if (!isAOperacao && isBOperacao) return 1;

                const ta = norm(a.tipo);
                const tb = norm(b.tipo);
                if (ta !== tb) return ta.localeCompare(tb, 'pt-BR', { sensitivity: 'base' });

                return a.__idx - b.__idx;
            });

        itensOrdenados.forEach((it, idx) => {
            const grupo = grupos[idx];
            const select = grupo.querySelector("select[name='input_id']");
            const doseInput = grupo.querySelector("input[name='dosage_value']");

            if (setSelectByValue(select, it.id_farmbox)) {
                atualizarTipo(select);
            } else {
                if (select.tomselect) select.tomselect.clear();
                else select.selectedIndex = 0;
            }

            doseInput.value = (it.dose ?? "").toString();
        });

        for (let i = itens.length; i < grupos.length; i++) {
            const grupo = grupos[i];
            const select = grupo.querySelector("select[name='input_id']");
            const doseInput = grupo.querySelector("input[name='dosage_value']");
            
            if (select.tomselect) select.tomselect.clear();
            else select.selectedIndex = 0;
            
            doseInput.value = "";
            atualizarTipo(select);
        }

        atualizarDoseResultados();
        verificaDefensivosSelecionados();
        atualizarEstadoBotoesRemoverDefensivo();
    }

    selEstagio?.addEventListener('change', onEstagioChange);

    function resetProgramaEstagio() {
        const selPrograma = document.getElementById('select-programa');
        const selEstagio = document.getElementById('select-estagio');
        const programaMeta = document.getElementById('programa-meta');

        if (selPrograma) selPrograma.value = '';
        if (selEstagio) {
            selEstagio.innerHTML = '<option value="">-- Selecione um estágio --</option>';
            selEstagio.disabled = true;
        }
        if (programaMeta) programaMeta.textContent = '';

        ensureRowCount(1);
        const unica = document.querySelector("#defensivos-container .defensivo-group");
        if (unica) {
            const select = unica.querySelector("select[name='input_id']");
            const doseInput = unica.querySelector("input[name='dosage_value']");
            const res = unica.querySelector(".dose-result");
            
            if (select) { 
                if (select.tomselect) select.tomselect.clear();
                else select.selectedIndex = 0;
                atualizarTipo(select); 
            }
            if (doseInput) doseInput.value = "";
            if (res) res.textContent = "0,00";
        }

        atualizarDoseResultados();
        verificaDefensivosSelecionados();
        atualizarEstadoBotoesRemoverDefensivo();
    }

    document.getElementById('btn-reset-programa')?.addEventListener('click', resetProgramaEstagio);

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
                const parsedDose = parseFloat(String(dose).replace(',', '.'));

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

    // Inicializa os selects avançados na carga da página
    document.querySelectorAll('.select-busca-avancada').forEach(iniciarSelectAvancado);

    // Expor funções para chamadas inline
    window.removerPlantio = removerPlantio;
    window.duplicarLinha = duplicarLinha;
    window.removerLinha = removerLinha;
    window.calcularAreaTotal = calcularAreaTotal;
    window.enviarAplicacao = enviarAplicacao;
});