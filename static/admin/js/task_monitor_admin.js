// static/admin/js/task_monitor_admin.js

function startAdminTaskMonitor(taskId, onSuccess) {
    if (!taskId) return;

    const interval = setInterval(async () => {
        try {
            const res = await fetch(`/diamante/backgroundtask_status/${taskId}/`);
            const data = await res.json();

            if (data.status === "done") {
                clearInterval(interval);
                console.log("✅ Tarefa finalizada com sucesso!");

                if (typeof onSuccess === "function") {
                    onSuccess();
                }

                Swal.fire({
                    title: "Concluído!",
                    html: `<b>A Atualização do Programa ${data.name} foi finalizada com sucesso.</b>`,
                    icon: "success"
                });
            }

            if (data.status === "failed") {
                clearInterval(interval);

                Swal.fire({
                    title: "Erro!",
                    html: "<b>A tarefa falhou ao ser executada.</b>",
                    icon: "error"
                });
            }
        } catch (error) {
            console.error("Erro ao verificar status da tarefa:", error);
            clearInterval(interval);
        }
    }, 2000);
}