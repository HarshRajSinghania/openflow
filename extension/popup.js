const element = id => document.getElementById(id);
const labels = {
  disconnected: "Conexão desabilitada", connecting: "Aguardando MCP",
  pairing: "Autenticando conexão…", awaiting_approval: "Aguardando autorização pelo agente",
  paired: "Conectado", waiting: "Aguardando MCP",
  retry_unavailable: "Aguardando MCP; desabilite e habilite a conexão para tentar novamente",
  authorization_required: "Autorização necessária. Habilite a conexão para solicitar."
};

let refreshRevision = 0;

async function refresh() {
  const revision = ++refreshRevision;
  const response = await chrome.runtime.sendMessage({type: "status"});
  if (revision !== refreshRevision) return;
  element("account").textContent = `Conta: ${response.email ?? "indisponível"} · Créditos: ${response.credits ?? "indisponíveis"}`;
  element("status").textContent = response.status === "waiting" && response.retry_delay_minutes
    ? `Aguardando MCP; nova tentativa automática em até ${response.retry_delay_minutes * 60} s`
    : labels[response.status] || "Indisponível";
  element("pairing").textContent = response.pairing_id || "";
  element("enabled").checked = response.enabled;
  element("authorization").hidden = response.status !== "awaiting_approval" || !response.pairing_id;
  element("ambiguity").hidden = (response.tabs || []).length < 2;
  const previous = element("tabs").value;
  element("tabs").replaceChildren(...(response.tabs || []).map(tab => {
    const option = document.createElement("option");
    option.value = String(tab.tab_id);
    option.textContent = `Aba ${tab.tab_id}: ${tab.project_id || "Página inicial"}`;
    return option;
  }));
  element("tabs").value = previous || String(response.selected?.tab_id || "");
  element("selected").textContent = response.selected
    ? `Projeto: ${response.selected.project_id || "Página inicial"} · Aba ${response.selected.tab_id}`
    : "Projeto: abra uma aba do Flow ou escolha entre as abas abertas.";
}

const safely = action => async () => {
  try { await action(); }
  catch { element("status").textContent = "Extensão indisponível; abra o painel novamente."; }
};

element("enabled").onchange = safely(async () => {
  const control = element("enabled");
  control.disabled = true;
  ++refreshRevision;
  try {
    await chrome.runtime.sendMessage({type: control.checked ? "connect" : "disconnect"});
    await refresh();
  } finally { control.disabled = false; }
});
element("select").onclick = safely(async () => {
  if (!element("tabs").value) return;
  const result = await chrome.runtime.sendMessage({type: "select", tab_id: Number(element("tabs").value)});
  if (result.error) element("status").textContent = "Aba indisponível ou operação em andamento.";
  else await refresh();
});
await safely(refresh)();
setInterval(safely(refresh), 2000);
