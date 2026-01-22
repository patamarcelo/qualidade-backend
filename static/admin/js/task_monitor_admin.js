(function () {
    window.__adminTaskMonitor = window.__adminTaskMonitor || {
        runningByTask: new Map(),   // taskId -> { stop(), controller }
        completed: new Set(),       // taskIds já finalizados
    };

    window.startAdminTaskMonitor = function startAdminTaskMonitor(taskId, onSuccess) {
        console.log("⏳ Iniciando monitoramento da task:", taskId);
        if (!taskId) return;

        const state = window.__adminTaskMonitor;

        // já finalizada anteriormente
        if (state.completed.has(taskId)) {
            console.log("ℹ️ Task já concluída, ignorando:", taskId);
            return;
        }

        // já tem monitor ativo pra esse taskId
        if (state.runningByTask.has(taskId)) {
            console.log("ℹ️ Monitor já ativo para essa task:", taskId);
            return;
        }

        let stopped = false;
        let doneHandled = false;  // impede duplicar “done/failed” por qualquer motivo
        let inFlight = false;

        const controller = new AbortController();

        const stop = () => {
            if (stopped) return;
            stopped = true;
            try { controller.abort(); } catch (_) { }
            state.runningByTask.delete(taskId);
        };

        state.runningByTask.set(taskId, { stop, controller });

        async function poll() {
            if (stopped || doneHandled) return;

            // evita reentrância (extra segurança)
            if (inFlight) {
                setTimeout(poll, 500);
                return;
            }

            inFlight = true;

            try {
                const res = await fetch(`/diamante/backgroundtask_status/${taskId}/`, {
                    cache: "no-store",
                    headers: { "Accept": "application/json" },
                    signal: controller.signal,
                });

                if (!res.ok) throw new Error(`HTTP ${res.status}`);

                const data = await res.json();

                if (data.status === "done" && !doneHandled) {
                    doneHandled = true;
                    state.completed.add(taskId);
                    stop();

                    console.log("✅ Tarefa finalizada com sucesso!");

                    if (typeof onSuccess === "function") {
                        try { onSuccess(); } catch (e) { console.error("onSuccess error:", e); }
                    }

                    // evita abrir múltiplos swals (paranoia)
                    if (!Swal.isVisible()) {
                        Swal.fire({
                            title: "Concluído!",
                            html: `<b>A Atualização do Programa ${data.name} foi finalizada com sucesso.</b>`,
                            icon: "success",
                        });
                    }

                    return;
                }

                if (data.status === "failed" && !doneHandled) {
                    doneHandled = true;
                    state.completed.add(taskId);
                    stop();

                    if (!Swal.isVisible()) {
                        Swal.fire({
                            title: "Erro!",
                            html: "<b>A tarefa falhou ao ser executada.</b>",
                            icon: "error",
                        });
                    }

                    return;
                }

            } catch (error) {
                if (error?.name === "AbortError") return; // monitor foi interrompido
                console.error("Erro ao verificar status da tarefa:", error);
                stop();
                return;
            } finally {
                inFlight = false;
            }

            // só agenda o próximo poll depois que terminou o atual
            setTimeout(poll, 1000);
        }

        poll();
    };
})();
