FROM node:22-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci --omit=dev

COPY src ./src

RUN mkdir -p /app/auth_state

ENV NODE_ENV=production
ENV PORT=8085
ENV AUTH_STATE_DIR=/app/auth_state

EXPOSE 8085

CMD ["node", "src/index.js"]
