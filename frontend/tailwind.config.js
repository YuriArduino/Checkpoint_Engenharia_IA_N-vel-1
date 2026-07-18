/** @type {import('tailwindcss').Config} */
module.exports = {
    content: [
        "./src/**/*.{js,jsx,ts,tsx}", // todos os arquivos React
        "./public/index.html",
    ],
    theme: {
        extend: {
            colors: {
                primary: "#2563EB", // azul customizado
                secondary: "#FBBF24", // amarelo
            },
            fontFamily: {
                sans: ["Inter", "sans-serif"],
            },
        },
    },
    plugins: [require("@tailwindcss/typography")],
};
