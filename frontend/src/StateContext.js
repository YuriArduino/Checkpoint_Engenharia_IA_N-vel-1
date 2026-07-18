import { createContext, useContext, useState } from "react";

const StateContext = createContext();

export function StateProvider({ children }) {
    const [state, setState] = useState({});
    const [messages, setMessages] = useState([]);
    const [stateVisible, setStateVisible] = useState(true);
    const [loading, setLoading] = useState(false);

    const updateState = (newState) => {
        setState((prev) => ({
            ...prev,
            ...newState,
            response: [
                ...(prev.response || []),
                ...(newState.response || [])
            ],
        }));
    };

    return (
        <StateContext.Provider
            value={{
                state,
                updateState,
                messages,
                setMessages,
                stateVisible,
                setStateVisible,
                loading,
                setLoading,
            }}
        >
            {children}
        </StateContext.Provider>
    );
}

// --- ADICIONADO: O hook customizado que as outras páginas estão tentando importar ---
export function useAppState() {
    const context = useContext(StateContext);
    if (!context) {
        throw new Error("useAppState deve ser usado dentro de um StateProvider");
    }
    return context;
}
