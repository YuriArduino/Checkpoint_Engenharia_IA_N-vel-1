FROM node:20-alpine

WORKDIR /app

# Variáveis para garantir hot reload no Linux/Ubuntu
ENV CHOKIDAR_USEPOLLING=true
ENV WATCHPACK_POLLING=true

# Busca os arquivos de dependência direto da pasta correta
COPY package*.json ./

RUN npm install

# Copia o restante do código da pasta frontend2
COPY . .

EXPOSE 3000

CMD ["npm", "start"]
