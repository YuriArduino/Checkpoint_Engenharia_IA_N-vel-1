// StateUtilPage.jsx
import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { motion, AnimatePresence } from "framer-motion";
import { useAppState } from "./StateContext";
import AppLayout from "./Layout";

export default function StateUtilPage() {
    const { state } = useAppState();
    const responses = state.responses || [];

    // -------------------------
    // Função para extrair dados
    // -------------------------
    const extractData = (text) => {
        if (typeof text !== "string") return null;
        const data = {};

        const nameMatch = text.match(
            /(?:\**\s*nome\s*(?:completo)?\s*\**\s*[:\-]?\s*)([\p{L}\s]+)/iu,
        );
        if (nameMatch) data.Nome = nameMatch[1].trim();

        const cpfMatch = text.match(/cpf\s*[:\-]?\s*([\d.-]{11,14})/i);
        if (cpfMatch) data.CPF = cpfMatch[1].trim();

        const accountMatch = text.match(
            /(?:\**\s*N[uú]mero\s*(?:da\s*)?conta\s*\**\s*[:\-]?\s*)(\d+)/i,
        );
        if (accountMatch) data.Conta = accountMatch[1].trim();

        const saldoMatch = text.match(
            /(?:\**\s*Saldo\s*\**\s*[:\-]?\s*R\$\s*)([\d.,]+)/i,
        );
        if (saldoMatch) data.Saldo = `R$ ${saldoMatch[1].trim()}`;

        const cardNumberMatch = text.match(
            /(?:n[uú]mero\s*(?:do\s*cart[ãa]o)?\s*[:]?[\s\*]*)(\d{4,16})/i,
        );
        if (cardNumberMatch) data.CartaoNumero = cardNumberMatch[1].trim();

        const cardTypeMatch = text.match(
            /(?:tipo\s*[:]?[\s\*]*)([\p{L}\s]+)[\*]*/iu,
        );
        if (cardTypeMatch) data.CartaoTipo = cardTypeMatch[1].trim();

        const cardLimitMatch = text.match(
            /limite\s*(?:disponível)?\s*[:]?[\sR$]*([\d.,]+)/i,
        );
        if (cardLimitMatch) data.CartaoLimite = `R$ ${cardLimitMatch[1].trim()}`;

        return Object.keys(data).length ? data : null;
    };

    // ------------------------------
    // Preparar respostas filtradas
    // ------------------------------
    const filteredResponses = [];
    for (const r of responses) {
        if (typeof r === "string") {
            filteredResponses.push({ message: r, data: extractData(r) });
        } else {
            for (const value of Object.values(r)) {
                if (value && value.trim())
                    filteredResponses.push({ message: value, data: extractData(value) });
            }
        }
    }

    // ------------------------------
    // Função para mascarar cartão
    // ------------------------------
    const maskCardNumber = (number) => {
        if (!number) return "**** **** **** ****";
        const clean = number.replace(/\D/g, "");
        if (clean.length <= 8) return clean.slice(0, 4) + " ****";
        return `${clean.slice(0, 4)} **** **** ${clean.slice(-2)}`;
    };

    // ------------------------------
    // Motion Variants
    // ------------------------------
    const cardVariants = {
        hidden: { opacity: 0, y: 20 },
        visible: { opacity: 1, y: 0 },
    };

    return (
        <AppLayout>
            <div className="p-6 flex-1 overflow-auto flex flex-col gap-6 bg-gray-900">
                <h1 className="text-3xl font-bold mb-6 text-white">
                    📋 Histórico de Respostas
                </h1>

                {filteredResponses.length === 0 ? (
                    <p className="text-gray-400 text-lg">
                        Nenhuma resposta registrada ainda.
                    </p>
                ) : (
                    <div className="flex flex-col gap-4">
                        <AnimatePresence>
                            {filteredResponses.map(({ message, data }, i) => {
                                const isCard = data && data.CartaoNumero && data.CartaoTipo;

                                return (
                                    <motion.div
                                        key={i}
                                        initial="hidden"
                                        animate="visible"
                                        exit={{ opacity: 0, scale: 0.95 }}
                                        variants={cardVariants}
                                        transition={{ duration: 0.3, ease: "easeOut" }}
                                        className={`p-4 rounded-2xl shadow-lg max-w-xl w-full ${data
                                                ? isCard
                                                    ? "self-end bg-gradient-to-r from-blue-600 to-blue-400"
                                                    : "bg-green-700 self-end"
                                                : "bg-gray-700 self-start"
                                            } hover:scale-[1.02] transition-transform duration-200`}
                                        title={
                                            data ? "Informação registrada" : "Mensagem do sistema"
                                        }
                                    >
                                        <ReactMarkdown
                                            remarkPlugins={[remarkGfm]}
                                            className="whitespace-pre-wrap text-white"
                                        >
                                            {message}
                                        </ReactMarkdown>
                                        {data && (
                                            <div className="flex flex-col gap-3 mt-3">
                                                {isCard ? (
                                                    <div className="relative rounded-2xl shadow-xl w-80 font-sans overflow-hidden">
                                                        {/* O gradiente azul agora só no cartão */}
                                                        <div className="bg-gradient-to-r from-blue-700 to-blue-300 p-6">
                                                            <div className="flex justify-between items-center mb-4 text-white">
                                                                <span className="text-lg font-bold">
                                                                    {data.CartaoTipo}
                                                                </span>
                                                                <span className="text-xl font-bold">VISA</span>
                                                            </div>
                                                            <div className="text-xl font-mono tracking-widest mb-4 text-white">
                                                                {maskCardNumber(data.CartaoNumero)}
                                                            </div>
                                                            {data.CartaoLimite && (
                                                                <div className="flex justify-between text-sm opacity-90 text-white">
                                                                    <span>Limite</span>
                                                                    <span>{data.CartaoLimite}</span>
                                                                </div>
                                                            )}
                                                        </div>

                                                        {/* Nome do usuário fora do gradiente */}
                                                        {data.Nome && (
                                                            <div className="mt-2 p-2 text-sm uppercase opacity-90 bg-gray-800 text-white rounded-b-2xl">
                                                                {data.Nome}
                                                            </div>
                                                        )}
                                                    </div>
                                                ) : (
                                                    <div className="flex flex-wrap gap-2">
                                                        {Object.entries(data).map(([key, value]) => (
                                                            <span
                                                                key={key}
                                                                className="bg-gray-800 px-3 py-1 rounded-full text-sm text-white"
                                                            >
                                                                {key}: {value}
                                                            </span>
                                                        ))}
                                                    </div>
                                                )}
                                            </div>
                                        )}
                                    </motion.div>
                                );
                            })}
                        </AnimatePresence>
                    </div>
                )}
            </div>
        </AppLayout>
    );
}
