import { HttpAgent } from "@ag-ui/client";

export class MDBankAgent {
    constructor(url, agentName) {
        this.url = url;
        this.agent = new HttpAgent({ url });
        this.agentName = agentName;
    }

    async run(message) {
        try {
            console.log("Enviando para:", this.url);

            const response = await fetch(this.url, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                //atualizar de acordo com o backend
                body: JSON.stringify({
                    message: message,
                    session_id: "123",
                    client_id: "123",
                    agent: this.agentName,
                }),
            });
            console.log("Status:", response.status);

            if (!response.ok) {
                const text = await response.text();
                console.error("Erro backend:", text);
                throw new Error("Erro na API");
            }
            const data = await response.json();
            console.log("Resposta:", data);
            return {
                messages: [
                    {
                        role: "assistant",
                        content: data?.resposta || "Sem resposta",
                    },
                ],
            };
        } catch (err) {
            console.error("ERRO COMPLETO:", err);

            return {
                messages: [
                    {
                        role: "assistant",
                        content: "Erro ao chamar agente",
                    },
                ],
            };
        }
    }
}
