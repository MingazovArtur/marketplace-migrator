# Используем легкую версию Node.js
FROM node:20-alpine

WORKDIR /app

# Копируем package.json и устанавливаем зависимости
COPY package.json package-lock.json* ./
RUN npm install

# Копируем исходный код
COPY . .

# Открываем порт 5173
EXPOSE 5173

# Запускаем Vite с флагом --host, чтобы он был доступен извне контейнера
CMD ["npm", "run", "dev", "--", "--host"]